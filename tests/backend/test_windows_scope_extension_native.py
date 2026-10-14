"""Owned Windows fixture only: previous scope remains observed after extension."""

import json
import os
import sqlite3
import time
from uuid import uuid4

import pytest
from test_collector_transport import authorities as authorities

from collectors.windows.configuration import activate, load, set_usn_enabled
from collectors.windows.inventory import Scope
from collectors.windows.scope_extension import extend_scope
from collectors.windows.security import ProtectedState
from collectors.windows.usn_capture import capture_usn
from collectors.windows.usn_state import UsnState

pytestmark = pytest.mark.skipif(os.name != "nt", reason="owned Windows NTFS fixture required")


def test_native_stopped_scope_extension_keeps_cursor_and_captures_both_roots(tmp_path, authorities):
    old_root, new_root = tmp_path / "Original", tmp_path / "Дополнительный"
    old_root.mkdir()
    new_root.mkdir()
    old_file, new_file = old_root / "old.txt", new_root / "новый.txt"
    old_file.write_text("synthetic-old", encoding="utf8")
    new_file.write_text("synthetic-new", encoding="utf8")
    old_scope = Scope((str(old_root),))
    with ProtectedState(tmp_path / "private-state", create=True) as state:
        original = activate(
            state,
            uuid4(),
            "https://localhost",
            old_scope,
            "a" * 43,
            (authorities[0] / "ca.pem").read_bytes(),
        )
        set_usn_enabled(state, True)
        initial = load(state)
        report = capture_usn(initial.outbox, old_scope)
        assert report.completed
        from collectors.windows.usn_native import NativeJournal

        volume = NativeJournal(old_scope).volumes[0]
        cursor = UsnState(initial.outbox, volume, old_scope.fingerprint).cursor
        extend_scope(state, (str(old_root), str(new_root)))
        extended = load(state)
        assert extended.config.collector_id == original.collector_id
        assert extended.config.credential_version == original.credential_version
        assert UsnState(extended.outbox, volume, extended.config.scope.fingerprint).cursor == cursor
        old_file.unlink()
        new_file.unlink()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            report = capture_usn(extended.outbox, extended.config.scope)
            if report.completed:
                break
            assert report.errors == ("USN_LAG",)
        assert report.completed
        with sqlite3.connect(extended.outbox.path.as_uri() + "?mode=ro", uri=True) as connection:
            rows = connection.execute("SELECT body FROM batches WHERE domain='changes'").fetchall()
        deletes = [
            record
            for (body,) in rows
            for record in json.loads(body)["records"]
            if record["event_type"] == "DELETE"
        ]
        assert len(deletes) == 2
        assert {record["old_relative_path"].rsplit("\\", 1)[-1] for record in deletes} == {
            "old.txt",
            "новый.txt",
        }
