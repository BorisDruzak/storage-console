import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from collectors.common.outbox import Outbox
from collectors.windows.inventory import Scope
from collectors.windows.usn_capture import capture_usn


@pytest.mark.skipif(os.name != "nt", reason="native Windows NTFS required")
def test_native_scoped_capture_reopen_outgoing_events_and_no_sibling_paths(tmp_path):
    root = tmp_path / "approved"
    root.mkdir()
    sibling = tmp_path / "outside"
    sibling.mkdir()
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", uuid4())
    scope = Scope((str(root),))
    baseline = capture_usn(box, scope)
    assert baseline.completed and baseline.errors == ()
    file = root / "Отчёт.txt"
    file.write_text("one", encoding="utf-8")
    file.write_text("two", encoding="utf-8")
    file = file.rename(root / "После.txt")
    file.unlink()
    (sibling / "private-outside-must-not-upload.txt").write_text("synthetic", encoding="utf-8")
    report = capture_usn(box, scope)
    assert report.completed and report.errors == ()
    assert report.records >= 4
    restored = Outbox(box.path, box.collector_id)
    actual = []
    for _ in range(100):
        claim = restored.claim(datetime.now(UTC))
        if claim is None:
            break
        import json
        payload = json.loads(claim.body)
        actual.extend(payload["records"])
        assert restored.acknowledge(claim)
    assert {row["event_type"] for row in actual} >= {"CREATE", "WRITE", "RENAME", "DELETE"}
    assert len({row["file_id"] for row in actual}) == 1
    assert len({row["source_event_id"] for row in actual}) == len(actual)
    assert b"private-outside-must-not-upload" not in box.path.read_bytes()
    assert capture_usn(restored, scope).records == 0
