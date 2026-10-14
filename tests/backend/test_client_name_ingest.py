"""A current lookup is source-bound and cannot rewrite native Windows witnesses."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from test_directory_contract import DOMAIN, client
from test_directory_ingest import count
from test_directory_ingest import directory_setup as directory_setup

from packages.contracts.audit import AuditEvent
from packages.contracts.directory import ClientNameObservation
from packages.shared.models.audit import audit_evidence
from packages.shared.models.directory import audit_client_ips, client_name_observations


def observation(setup, **changes):
    now = datetime.now(UTC)
    value = client(
        collector_id=setup[2],
        sent_at=now,
        observed_at=now,
        expires_at=now + timedelta(seconds=300),
        **changes,
    )
    return ClientNameObservation.model_validate(value).model_dump(mode="json")


def post(setup, payload):
    return setup[0].post(
        "/api/v1/ingest/client-names", json=payload, headers={"Authorization": "Bearer " + setup[3]}
    )


def native_logon(setup, ip="192.0.2.10"):
    event = AuditEvent(
        host_id=uuid4(),
        boot_id="synthetic-boot",
        generation=uuid4(),
        record_id=1,
        provider=uuid4(),
        event_id=4624,
        version=0,
        occurred_at=datetime.now(UTC),
        sid=DOMAIN + "-1001",
        account="native-name",
        client_ip=ip,
        logon_id=77,
        workstation=None,
    )
    payload = dict(
        collector_id=str(setup[2]),
        batch_id=uuid4().hex,
        schema_version=1,
        sent_at=datetime.now(UTC).isoformat(),
        records=[dict(event.model_dump(mode="json"), digest=event.digest())],
    )
    result = setup[0].post(
        "/api/v1/ingest/audit-events", json=payload, headers={"Authorization": "Bearer " + setup[3]}
    )
    assert result.status_code == 202
    return event


def test_lookup_requires_a_source_native_ip_then_replays_without_changing_event(directory_setup):
    setup = directory_setup
    payload = observation(setup)
    assert post(setup, payload).status_code == 403
    assert count(setup[1], client_name_observations) == 0
    event = native_logon(setup)
    assert count(setup[1], audit_client_ips) == 1
    assert post(setup, payload).status_code == 202
    assert post(setup, payload).json() == {"accepted": True, "duplicate": True}
    assert count(setup[1], client_name_observations) == 1
    with setup[1].connect() as conn:
        row = conn.execute(select(audit_evidence)).mappings().one()
        assert row["digest"] == event.digest() and row["payload"] == event.model_dump(mode="json")
        assert row["payload"]["workstation"] is None and row["payload"]["account"] == "native-name"


def test_lookup_normalizes_mapped_ip_only_in_the_derived_index(directory_setup):
    setup = directory_setup
    event = native_logon(setup, "::ffff:192.0.2.10")
    assert post(setup, observation(setup)).status_code == 202
    with setup[1].connect() as conn:
        assert conn.scalar(select(audit_client_ips.c.client_ip_key)) == "192.0.2.10"
        assert conn.scalar(select(audit_evidence.c.payload))["client_ip"] == event.client_ip
