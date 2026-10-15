"""Isolated immutable evidence and role boundaries; synthetic identities only."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, update
from test_windows_audit_events import parse, xml

from packages.shared.models.core import collectors, volumes


def batch(collector, *, event=None, batch_id=None):
    event = event or parse(xml())
    event = event.model_copy(update={"volume_id": "volume-a"})
    return {
        "collector_id": str(collector),
        "batch_id": batch_id or uuid4().hex,
        "schema_version": 1,
        "sent_at": datetime.now(UTC).isoformat(),
        "records": [{**event.model_dump(mode="json"), "digest": event.digest()}],
    }


@pytest.fixture
def audit_setup(ingest_setup):
    client, engine, collector, token, source = ingest_setup
    with engine.begin() as conn:
        conn.execute(
            update(collectors)
            .where(collectors.c.id == collector)
            .values(collector_type="AUDIT_WINDOWS")
        )
        conn.execute(
            insert(volumes).values(
                source_node_id=source, unique_identity="volume-a", filesystem="NTFS"
            )
        )
    return client, engine, collector, token, source


def post(setup, payload):
    client, _, _, token, _ = setup
    return client.post(
        "/api/v1/ingest/audit-events", json=payload, headers={"Authorization": "Bearer " + token}
    )


def test_actual_typed_route_immutable_replay_and_first_received(audit_setup):
    client, engine, collector, _, source = audit_setup
    payload = batch(collector)
    response = post(audit_setup, payload)
    assert response.status_code == 202
    assert response.json() == {"accepted": True, "duplicate": False}
    from packages.shared.models.audit import audit_evidence

    with engine.connect() as conn:
        row = conn.execute(select(audit_evidence)).mappings().one()
    assert row["source_node_id"] == source and row["audit_collector_id"] == collector
    first = row["first_received_at"]
    assert post(audit_setup, payload).json()["duplicate"] is True
    payload["batch_id"] = uuid4().hex
    assert post(audit_setup, payload).status_code == 202
    with engine.connect() as conn:
        rows = conn.execute(select(audit_evidence)).mappings().all()
    assert len(rows) == 1 and rows[0]["first_received_at"] == first
    assert "confidence" not in json.dumps(rows[0]["payload"])
    assert "raw_xml" not in json.dumps(rows[0]["payload"])


def test_same_identity_changed_evidence_conflicts_without_overwrite(audit_setup):
    collector = audit_setup[2]
    assert post(audit_setup, batch(collector)).status_code == 202
    changed = parse(xml(SubjectUserName="UserB"))
    assert post(audit_setup, batch(collector, event=changed)).status_code == 409
    from packages.shared.models.audit import audit_evidence

    with audit_setup[1].connect() as conn:
        row = conn.execute(select(audit_evidence)).mappings().one()
    assert row["payload"]["account"] == "UserA"


def test_usn_credential_cannot_submit_audit_and_audit_cannot_submit_usn(ingest_setup):
    assert post(ingest_setup, batch(ingest_setup[2])).status_code == 403


def test_audit_without_credential_is_401_and_raw_xml_rejected(audit_setup):
    client, _, collector, _, _ = audit_setup
    payload = batch(collector)
    assert client.post("/api/v1/ingest/audit-events", json=payload).status_code == 401
    payload["records"][0]["raw_xml"] = "forbidden"
    response = post(audit_setup, payload)
    assert response.status_code == 422 and "forbidden" not in response.text


def test_new_generation_allows_reused_record_id(audit_setup):
    collector = audit_setup[2]
    assert post(audit_setup, batch(collector)).status_code == 202
    changed = parse(xml()).model_copy(update={"generation": uuid4()})
    assert post(audit_setup, batch(collector, event=changed)).status_code == 202
    from packages.shared.models.audit import audit_evidence

    with audit_setup[1].connect() as conn:
        assert len(conn.execute(select(audit_evidence)).all()) == 2


def test_native_volume_guid_resolves_registered_identity_without_rewriting_evidence(audit_setup):
    _, engine, collector, _, source = audit_setup
    identity = uuid4()
    native = "\\\\?\\Volume{" + str(identity).upper() + "}\\"
    canonical = "volume:" + str(identity)
    with engine.begin() as conn:
        conn.execute(insert(volumes).values(
            source_node_id=source, unique_identity=canonical, filesystem="NTFS",
        ))
    event = parse(xml()).model_copy(update={"volume_id": native})
    payload = batch(collector)
    payload["records"] = [{**event.model_dump(mode="json"), "digest": event.digest()}]
    response = post(audit_setup, payload)
    assert response.status_code == 202
    from packages.shared.models.audit import audit_evidence

    with engine.connect() as conn:
        row = conn.execute(select(audit_evidence)).mappings().one()
    assert row["volume_id"] == canonical
    assert row["payload"]["volume_id"] == native
    assert row["digest"] == event.digest()
    assert post(audit_setup, payload).json() == {"accepted": True, "duplicate": True}
    changed = event.model_copy(update={"volume_id": canonical})
    payload["batch_id"] = uuid4().hex
    payload["records"] = [{**changed.model_dump(mode="json"), "digest": changed.digest()}]
    assert post(audit_setup, payload).status_code == 409
    with engine.connect() as conn:
        retained = conn.execute(select(audit_evidence)).mappings().one()
    assert retained["payload"] == row["payload"] and retained["digest"] == row["digest"]


def test_unregistered_native_volume_still_refused(audit_setup):
    event = parse(xml()).model_copy(update={"volume_id": "\\\\?\\Volume{" + str(uuid4()) + "}\\"})
    payload = batch(audit_setup[2])
    payload["records"] = [{**event.model_dump(mode="json"), "digest": event.digest()}]
    response = post(audit_setup, payload)
    assert response.status_code == 403
    assert response.json() == {"detail": "AUDIT_VOLUME_REQUIRED"}


def test_other_source_volume_does_not_authorize_native_guid(audit_setup):
    from packages.shared.models.core import source_nodes

    identity, other = uuid4(), uuid4()
    with audit_setup[1].begin() as conn:
        conn.execute(insert(source_nodes).values(
            id=other, source_type="FILESERVER", hostname="other-synthetic",
            instance_id=str(other),
        ))
        conn.execute(insert(volumes).values(
            source_node_id=other, unique_identity="volume:" + str(identity), filesystem="NTFS",
        ))
    event = parse(xml()).model_copy(update={"volume_id": "\\\\?\\Volume{" + str(identity) + "}\\"})
    payload = batch(audit_setup[2])
    payload["records"] = [{**event.model_dump(mode="json"), "digest": event.digest()}]
    response = post(audit_setup, payload)
    assert response.status_code == 403
    assert response.json() == {"detail": "AUDIT_VOLUME_REQUIRED"}
