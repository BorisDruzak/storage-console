from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from packages.contracts.acl import ACLRecord
from packages.contracts.changes import ChangeRecord
from packages.contracts.common import BatchEnvelope
from packages.contracts.heartbeat import HeartbeatRecord
from packages.contracts.inventory import FileObjectRecord, VolumeRecord
from packages.contracts.recovery import BackupRecord
from packages.contracts.telemetry import TelemetryRecord


def envelope(records):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return dict(
        collector_id=uuid4(),
        batch_id="synthetic-batch",
        schema_version=1,
        sent_at=now,
        first_event_at=now,
        last_event_at=now,
        record_count=len(records),
        records=records,
    )


def test_batch_timestamps_normalize_to_utc_and_count_matches():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    data = envelope([dict(occurred_at=now, version="test")])
    result = BatchEnvelope[HeartbeatRecord].model_validate(data)
    assert result.sent_at.utcoffset() == timedelta(0)
    for field, value in [
        ("schema_version", 2),
        ("record_count", 2),
        ("sent_at", datetime(2026, 1, 1)),
        ("first_event_at", now + timedelta(seconds=1)),
    ]:
        with pytest.raises(ValidationError):
            BatchEnvelope[HeartbeatRecord].model_validate(dict(data, **{field: value}))


def test_batch_rejects_record_outside_declared_window_and_extra_content():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError):
        BatchEnvelope[HeartbeatRecord].model_validate(
            envelope([dict(occurred_at=now - timedelta(seconds=1), version="test")])
        )
    with pytest.raises(ValidationError):
        VolumeRecord.model_validate(
            dict(
                kind="volume",
                occurred_at=now,
                unique_identity="volume",
                filesystem="NTFS",
                document_content="Forbidden",
            )
        )


def test_inventory_capacity_and_file_identity_validation():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError):
        VolumeRecord(
            kind="volume",
            occurred_at=now,
            unique_identity="v",
            filesystem="NTFS",
            total_bytes=100,
            free_bytes=101,
        )
    with pytest.raises(ValidationError):
        FileObjectRecord(
            kind="object",
            occurred_at=now,
            volume_identity="v",
            file_id="",
            object_type="FILE",
            name="test",
            relative_path="test",
        )
    obj = FileObjectRecord(
        kind="object",
        occurred_at=now,
        volume_identity="v",
        file_id="42",
        object_type="FILE",
        name="Отчёт.txt",
        relative_path="Отдел/Отчёт.txt",
    )
    assert obj.relative_path == "Отдел/Отчёт.txt"


def test_telemetry_rejects_non_finite_values_and_huge_batch():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError):
        TelemetryRecord(occurred_at=now, metric_name="capacity", value=float("nan"), unit="bytes")
    with pytest.raises(ValidationError):
        BatchEnvelope[HeartbeatRecord].model_validate(
            envelope([dict(occurred_at=now, version="test")] * 10001)
        )


@pytest.mark.parametrize("version", [True, 1.0, "1"])
def test_schema_version_requires_json_integer(version):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError):
        BatchEnvelope[HeartbeatRecord].model_validate(
            dict(envelope([dict(occurred_at=now, version="test")]), schema_version=version)
        )


def test_contract_values_fit_postgresql_columns():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    for values in [
        dict(version="x" * 65),
        dict(version="v1", error_code="x" * 65),
        dict(version="v1", lag_seconds=2**31),
    ]:
        with pytest.raises(ValidationError):
            HeartbeatRecord(occurred_at=now, **values)
    with pytest.raises(ValidationError):
        VolumeRecord(occurred_at=now, unique_identity="v", filesystem="NTFS", total_bytes=2**63)
    with pytest.raises(ValidationError):
        ChangeRecord(
            occurred_at=now,
            volume_identity="v",
            file_id="42",
            event_type="WRITE",
            reason_mask="x" * 65,
        )


def test_recovery_rejects_contradictory_or_orphaned_evidence():
    at = datetime(2026, 1, 1, tzinfo=UTC)
    base = dict(
        occurred_at=at,
        job_identity="job",
        workload_identity="vm",
        state="COMPLETE",
        started_at=at - timedelta(seconds=60),
        finished_at=at,
    )
    invalid = [
        dict(finished_at=at - timedelta(seconds=61)),
        dict(verification_state="COMPLETE", verified_at=at),
        dict(measured_rto_seconds=20),
        dict(snapshot_identity="snapshot"),
    ]
    for fields in invalid:
        with pytest.raises(ValidationError):
            BackupRecord(**dict(base, **fields))


def test_acl_object_identity_is_a_complete_pair():
    with pytest.raises(ValidationError):
        ACLRecord(
            occurred_at=datetime.now(UTC),
            scope_identity="Dept",
            file_id="42",
            dacl_fingerprint="a" * 64,
            inheritance_enabled=True,
            aces=[],
        )
