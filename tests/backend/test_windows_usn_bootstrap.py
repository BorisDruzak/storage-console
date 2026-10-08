from uuid import uuid4

import pytest
from test_windows_usn_scope import DIR, OUTSIDE, ROOT, STAMP, VOLUME, item

from collectors.common.outbox import Limits, Outbox
from collectors.windows import usn_capture
from collectors.windows.inventory import Observation, Scope
from collectors.windows.usn import UsnError
from collectors.windows.usn_native import JournalInfo
from collectors.windows.usn_state import UsnState
from packages.contracts.inventory import FileObjectRecord


@pytest.mark.parametrize("change_inside", [True, False])
def test_bootstrap_fences_ancestry_without_persisting_outside_names(
    tmp_path, monkeypatch, change_inside,
):
    box = Outbox(tmp_path / "private" / "queue", uuid4())
    scope = Scope(("C:\\pilot",))
    enumerated = False

    def scan(*args):
        nonlocal enumerated
        for identifier, parent, name, path in [(ROOT, None, "pilot", "pilot"),
                                                (DIR, ROOT, "old-dir", "pilot\\old-dir")]:
            yield Observation(record=FileObjectRecord(
                occurred_at=STAMP, volume_identity=VOLUME, file_id=identifier,
                parent_file_id=parent, object_type="DIRECTORY", name=name, relative_path=path,
            ))
        enumerated = True

    monkeypatch.setattr(usn_capture.NativeInventory, "_root", scan)

    class Stream:
        def query(self):
            return JournalInfo(42, 0, 100 if enumerated else 0, 0, 1024, 512)

        def read(self, journal, cursor):
            parent = ROOT if change_inside else OUTSIDE
            file_id = DIR if change_inside else OUTSIDE
            return 100, (item(50, 0x1000, "old-dir", file_id, parent),
                         item(60, 0x2000, "private-outside-child", file_id, OUTSIDE))

        def close(self):
            pass

    class Journal:
        volumes = (VOLUME,)
        _api = None

        def open(self, volume):
            return Stream()

    if change_inside:
        with pytest.raises(UsnError, match="^USN_PATH_UNKNOWN$"):
            usn_capture._bootstrap(box, scope, Journal(), lambda: False)
        assert UsnState(box, VOLUME, scope.fingerprint).status == "USN_BOOTSTRAP"
    else:
        usn_capture._bootstrap(box, scope, Journal(), lambda: False)
        assert UsnState(box, VOLUME, scope.fingerprint).cursor == 100
    assert box.status().pending_count == 0
    assert b"private-outside-child" not in box.path.read_bytes()


@pytest.mark.parametrize("code", ["CONTINUITY_GAP", "USN_UNSUPPORTED", "USN_ACCESS_DENIED",
                                  "USN_VOLUME_LOST", "USN_MALFORMED"])
def test_native_read_failure_is_latched_until_explicit_rebaseline(tmp_path, monkeypatch, code):
    box = Outbox(tmp_path / "private" / "queue", uuid4())
    scope = Scope(("C:\\pilot",))
    state = UsnState(box, VOLUME, scope.fingerprint)
    state.initialize(42, 0, {ROOT: {"name": "pilot", "root": "pilot"}})
    failing = True

    class Stream:
        def query(self):
            if failing:
                raise UsnError(code)
            return JournalInfo(42, 0, 0, 0, 1024, 512)

        def read(self, journal, cursor):
            return cursor, ()

        def close(self):
            pass

    class Journal:
        volumes = (VOLUME,)

        def open(self, volume):
            return Stream()

    monkeypatch.setattr(usn_capture, "NativeJournal", lambda scope: Journal())
    assert usn_capture.capture_usn(box, scope).errors == (code,)
    failing = False
    recovered = usn_capture.capture_usn(box, scope)
    assert not recovered.completed and recovered.errors == (code,)
    assert state.status == code


def test_bounded_pass_with_remaining_backlog_never_claims_complete(tmp_path, monkeypatch):
    box = Outbox(tmp_path / "private" / "queue", uuid4())
    scope = Scope(("C:\\pilot",))
    state = UsnState(box, VOLUME, scope.fingerprint)
    state.initialize(42, 0, {ROOT: {"name": "pilot", "root": "pilot"}})

    class Stream:
        def query(self):
            return JournalInfo(42, 0, 3000, 0, 1024, 512)

        def read(self, journal, cursor):
            return 3000, tuple(item(n, 0x100, "outside", OUTSIDE, OUTSIDE)
                               for n in range(max(1, cursor), 3000))

        def close(self):
            pass

    class Journal:
        volumes = (VOLUME,)

        def open(self, volume):
            return Stream()

    monkeypatch.setattr(usn_capture, "NativeJournal", lambda scope: Journal())
    report = usn_capture.capture_usn(box, scope)
    assert not report.completed and report.errors == ("USN_LAG",)
    assert 0 < state.cursor < 3000 and state.status is None
    assert usn_capture.capture_usn(box, scope).completed


def test_oversized_transition_splits_before_committing_cursor_or_dropping_events(
    tmp_path, monkeypatch,
):
    box = Outbox(tmp_path / "private" / "queue", uuid4(), Limits(max_body_bytes=1800))
    scope = Scope(("C:\\pilot",))
    state = UsnState(box, VOLUME, scope.fingerprint)
    state.initialize(42, 0, {ROOT: {"name": "pilot", "root": "pilot"}})

    class Stream:
        def query(self):
            return JournalInfo(42, 0, 64, 0, 1024, 512)

        def read(self, journal, cursor):
            return 64, tuple(item(n, 0x80000100, "Я"*200, n.to_bytes(16, "little").hex())
                             for n in range(2, 5) if n >= cursor)

        def close(self):
            pass

    class Journal:
        volumes = (VOLUME,)

        def open(self, volume):
            return Stream()

    monkeypatch.setattr(usn_capture, "NativeJournal", lambda scope: Journal())
    report = usn_capture.capture_usn(box, scope)
    assert report.completed and not report.errors and report.records == 3
    assert report.batches >= 2 and state.cursor == 64
