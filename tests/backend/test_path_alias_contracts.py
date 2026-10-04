"""Compatibility fixtures captured before introducing link_count."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from packages.contracts.common import BatchEnvelope
from packages.contracts.inventory import FileObjectRecord, InventoryRecord

OLD_RECORD = {
    "occurred_at": "2026-01-01T00:00:00Z",
    "kind": "object",
    "volume_identity": "synthetic-volume",
    "file_id": "42",
    "parent_file_id": None,
    "object_type": "FILE",
    "name": "Отчёт.txt",
    "relative_path": "Отдел/Отчёт.txt",
    "size_bytes": None,
}
OLD_BATCH = {
    "collector_id": "00000000-0000-0000-0000-000000000001",
    "batch_id": "old-inventory",
    "schema_version": 1,
    "sent_at": "2026-01-01T00:00:00Z",
    "first_event_at": "2026-01-01T00:00:00Z",
    "last_event_at": "2026-01-01T00:00:00Z",
    "record_count": 1,
    "records": [OLD_RECORD],
}
OLD_RAW = (
    '{"collector_id":"00000000-0000-0000-0000-000000000001",'
    '"batch_id":"old-inventory","schema_version":1,"sent_at":"2026-01-01T00:00:00Z",'
    '"first_event_at":"2026-01-01T00:00:00Z","last_event_at":"2026-01-01T00:00:00Z",'
    '"record_count":1,"records":[{"occurred_at":"2026-01-01T00:00:00Z","kind":"object",'
    '"volume_identity":"synthetic-volume","file_id":"42","parent_file_id":null,'
    '"object_type":"FILE","name":"Отчёт.txt","relative_path":"Отдел/Отчёт.txt",'
    '"size_bytes":null}]}'
).encode()


def digest(data):
    return hashlib.sha256(
        json.dumps(
            dict(kind="inventory", batch=data),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


@pytest.mark.parametrize("extra", [{}, {"link_count": None}])
def test_unknown_count_preserves_pre_upgrade_bytes_and_canonical_digest(extra):
    data = dict(OLD_BATCH, records=[dict(OLD_RECORD, **extra)])
    parsed = BatchEnvelope[InventoryRecord].model_validate(data)
    assert parsed.records[0].link_count is None
    assert parsed.model_dump(mode="json") == OLD_BATCH
    assert parsed.model_dump_json().encode() == OLD_RAW
    assert digest(parsed.model_dump(mode="json")) == digest(OLD_BATCH)
    assert digest(parsed.model_dump(mode="json")) == (
        "190d3057c7dc0831f650bb3be5234ee28f701dde420ebb835beedbf8a968cf83"
    )
    assert BatchEnvelope[InventoryRecord].model_validate_json(OLD_RAW) == parsed


@pytest.mark.parametrize("count", [1, 2, 4294967295])
def test_positive_count_is_serialized_and_changes_the_receipt_digest(count):
    data = dict(OLD_BATCH, records=[dict(OLD_RECORD, link_count=count)])
    parsed = BatchEnvelope[InventoryRecord].model_validate(data)
    assert parsed.records[0].link_count == count
    assert parsed.model_dump(mode="json")["records"][0]["link_count"] == count
    assert digest(parsed.model_dump(mode="json")) != digest(OLD_BATCH)


@pytest.mark.parametrize("count", [True, False, "2", 2.0, 0, -1, 4294967296])
def test_invalid_count_is_rejected(count):
    with pytest.raises(ValidationError):
        FileObjectRecord.model_validate(dict(OLD_RECORD, link_count=count))


def test_directory_has_no_file_link_count():
    with pytest.raises(ValidationError):
        FileObjectRecord.model_validate(dict(OLD_RECORD, object_type="DIRECTORY", link_count=1))
    directory = FileObjectRecord.model_validate(dict(OLD_RECORD, object_type="DIRECTORY"))
    assert directory.link_count is None
    assert "link_count" not in directory.model_dump(mode="json")


def test_existing_nulls_and_datetime_uuid_encoders_are_preserved():
    record = FileObjectRecord.model_validate(OLD_RECORD)
    assert record.model_dump()["size_bytes"] is None
    assert record.model_dump()["parent_file_id"] is None
    batch = BatchEnvelope[InventoryRecord].model_validate(OLD_BATCH)
    assert batch.collector_id == UUID(OLD_BATCH["collector_id"])
    assert batch.sent_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert batch.model_dump(mode="json") == OLD_BATCH
