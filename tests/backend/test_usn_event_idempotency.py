import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_path_alias_ingest import initial, object_record, paths, upload

from packages.contracts.changes import ChangeRecord
from packages.shared.ingest.core import change
from packages.shared.ingest.errors import IngestConflict
from packages.shared.models.activity import change_events

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL required")


def event():
    return ChangeRecord(
        occurred_at=datetime.now(UTC), volume_identity="volume:synthetic", file_id="42",
        event_type="CREATE", new_relative_path="pilot\\Отчёт.txt", reason_mask="0x00000100",
        source_event_id="ntfs-usn:" + uuid4().hex,
    )


def test_identical_usn_event_in_distinct_batches_has_one_effect(ingest_setup):
    _, engine, _, _, source = ingest_setup
    record = event()
    for _ in range(2):
        with engine.begin() as connection:
            change(connection, source, record)
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(change_events)) == 1


def test_changed_payload_under_same_usn_identity_is_conflict(ingest_setup):
    _, engine, _, _, source = ingest_setup
    record = event()
    with engine.begin() as connection:
        change(connection, source, record)
    with pytest.raises(IngestConflict):
        with engine.begin() as connection:
            change(connection, source, record.model_copy(update={"new_relative_path": "changed"}))


@pytest.mark.parametrize("before_inventory", [False, True])
@pytest.mark.parametrize("move_out", [False, True])
def test_unknown_rename_side_only_updates_proven_aliases(ingest_setup, before_inventory, move_out):
    initial(ingest_setup)
    if not before_inventory:
        upload(ingest_setup, "inventory", [object_record("a/x")], 1)
    upload(ingest_setup, "changes", [dict(
        event_type="RENAME", volume_identity="v", file_id="42",
        old_relative_path="a/x" if move_out else None,
        new_relative_path=None if move_out else "b/y", path_quality="UNAVAILABLE",
        source_event_id="ntfs-usn:" + uuid4().hex, reason_mask="0x2000",
    )], 2)
    if before_inventory:
        upload(ingest_setup, "inventory", [object_record("a/x")], 1)
    _, active, _ = paths(ingest_setup)
    assert active == (set() if move_out else {"a/x", "b/y"})
