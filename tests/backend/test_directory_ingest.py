"""Own PostgreSQL schema: pages and receipts commit atomically within source/domain."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select, update
from test_directory_contract import DOMAIN, page, scope, user

from packages.shared.models.core import collectors, source_nodes
from packages.shared.models.directory import directory_snapshots, directory_users
from packages.shared.models.jobs import ingest_batches


@pytest.fixture
def directory_setup(ingest_setup):
    client, engine, collector, token, source = ingest_setup
    with engine.begin() as conn:
        conn.execute(
            update(collectors)
            .where(collectors.c.id == collector)
            .values(collector_type="AUDIT_WINDOWS", directory_scope=scope())
        )
    return client, engine, collector, token, source


def wire(setup, **changes):
    value = page(collector_id=setup[2], sent_at=datetime.now(UTC), observed_at=datetime.now(UTC))
    value["sent_at"] = value["observed_at"]
    value.update(changes)
    from packages.contracts.directory import DirectoryPage

    return DirectoryPage.model_validate(value).model_dump(mode="json")


def post(setup, payload):
    return setup[0].post(
        "/api/v1/ingest/directory", json=payload, headers={"Authorization": "Bearer " + setup[3]}
    )


def count(engine, table):
    with engine.connect() as conn:
        return conn.scalar(select(func.count()).select_from(table))


def test_partial_pages_only_become_complete_after_matching_terminal_count(directory_setup):
    setup = directory_setup
    first = wire(setup, finished=False, complete=False, total_records=None)
    assert post(setup, first).status_code == 202
    with setup[1].connect() as conn:
        assert conn.execute(select(directory_snapshots.c.state)).scalar_one() == "COLLECTING"
    last = wire(
        setup,
        snapshot_id=first["snapshot_id"],
        observed_at=first["observed_at"],
        page_index=1,
        records=[],
        total_records=1,
    )
    invalid = dict(last, total_records=2)
    assert post(setup, invalid).status_code == 409
    assert count(setup[1], ingest_batches) == 1
    assert post(setup, last).status_code == 202
    with setup[1].connect() as conn:
        assert conn.execute(select(directory_snapshots.c.state)).scalar_one() == "COMPLETE"
    assert count(setup[1], directory_users) == 1


def test_exact_replay_and_conflicting_batch_or_page_leave_evidence_unchanged(directory_setup):
    setup = directory_setup
    payload = wire(setup)
    assert post(setup, payload).status_code == 202
    assert post(setup, payload).json() == {"accepted": True, "duplicate": True}
    conflict = dict(payload, records=[])
    assert post(setup, conflict).status_code == 409
    conflict = dict(payload, batch_id=uuid4().hex)
    assert post(setup, conflict).status_code == 409
    assert count(setup[1], directory_users) == count(setup[1], ingest_batches) == 1


@pytest.mark.parametrize("same", ["sid", "object_guid"])
def test_duplicate_identity_across_pages_refuses_whole_page(directory_setup, same):
    setup = directory_setup
    record = user()
    first = wire(setup, records=[record], finished=False, complete=False, total_records=None)
    assert post(setup, first).status_code == 202
    duplicate = user()
    duplicate[same] = record[same]
    if same == "object_guid":
        duplicate["sid"] = DOMAIN + "-2001"
    second = wire(
        setup,
        snapshot_id=first["snapshot_id"],
        observed_at=first["observed_at"],
        page_index=1,
        records=[duplicate],
        total_records=2,
    )
    assert post(setup, second).status_code == 409
    assert count(setup[1], directory_users) == count(setup[1], ingest_batches) == 1


def test_failed_snapshot_preserves_previous_complete_users(directory_setup):
    setup = directory_setup
    assert post(setup, wire(setup)).status_code == 202
    failed = wire(setup, records=[], total_records=0, complete=False, error_code="LDAP_UNAVAILABLE")
    assert post(setup, failed).status_code == 202
    assert count(setup[1], directory_users) == 1
    with setup[1].connect() as conn:
        assert set(conn.scalars(select(directory_snapshots.c.state))) == {"COMPLETE", "ERROR"}


def test_source_domain_capability_and_revocation_are_not_request_controlled(directory_setup):
    setup = directory_setup
    payload = wire(setup, records=[], total_records=0)
    payload["scope"] = {"dns_domain": "other.test", "domain_sid": DOMAIN}
    assert post(setup, payload).status_code == 403
    with setup[1].begin() as conn:
        conn.execute(
            update(collectors).where(collectors.c.id == setup[2]).values(directory_scope=None)
        )
    assert post(setup, wire(setup)).status_code == 403
    with setup[1].begin() as conn:
        conn.execute(update(collectors).where(collectors.c.id == setup[2]).values(enabled=False))
    assert post(setup, wire(setup)).status_code == 401
    assert count(setup[1], ingest_batches) == count(setup[1], directory_users) == 0


def test_snapshot_identity_cannot_cross_sources(directory_setup):
    from apps.api.auth import token_hash

    setup = directory_setup
    payload = wire(setup)
    assert post(setup, payload).status_code == 202
    other_source, other_collector = uuid4(), uuid4()
    other_token = "b" * 43
    with setup[1].begin() as conn:
        conn.execute(
            insert(source_nodes).values(
                id=other_source,
                source_type="FILESERVER",
                hostname="other-synthetic",
                instance_id=str(other_source),
            )
        )
        conn.execute(
            insert(collectors).values(
                id=other_collector,
                source_node_id=other_source,
                collector_type="AUDIT_WINDOWS",
                directory_scope=scope(),
                token_hash=token_hash(other_token),
            )
        )
    other = (setup[0], setup[1], other_collector, other_token, other_source)
    payload["collector_id"] = str(other_collector)
    payload["batch_id"] = uuid4().hex
    assert post(other, payload).status_code == 403
    assert count(setup[1], directory_users) == count(setup[1], ingest_batches) == 1


def test_future_observation_has_no_receipt(directory_setup):
    future = datetime.now(UTC) + timedelta(minutes=1)
    assert (
        post(directory_setup, wire(directory_setup, observed_at=future, sent_at=future)).status_code
        == 422
    )
    assert count(directory_setup[1], ingest_batches) == 0


def test_capability_is_an_explicit_audit_enrollment_and_grants_no_web_role(authenticated_setup):
    from test_source_control import headers

    from packages.shared.models.security import user_roles, users

    client, engine, _, _, source = authenticated_setup
    before = (count(engine, users), count(engine, user_roles))
    endpoint = f"/api/v1/sources/{source}/collectors"
    payload = {"collector_type": "AUDIT_WINDOWS", "directory_scope": scope()}
    result = client.post(endpoint, json=payload, headers=headers(client))
    assert result.status_code == 201
    assert result.json()["directory_scope"] == scope()
    assert (
        client.post(
            endpoint, json=dict(payload, collector_type="WINDOWS"), headers=headers(client)
        ).status_code
        == 422
    )
    assert (count(engine, users), count(engine, user_roles)) == before
    ordinary = client.post(endpoint, json={"collector_type": "WINDOWS"}, headers=headers(client))
    assert ordinary.status_code == 201 and "directory_scope" not in ordinary.json()
