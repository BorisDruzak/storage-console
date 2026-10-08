from datetime import UTC, datetime
from uuid import uuid4

from collectors.common.outbox import Outbox
from collectors.windows.usn import UsnRecord
from collectors.windows.usn_state import UsnState

STAMP = datetime(2026, 10, 8, tzinfo=UTC)
VOLUME = "volume:00000000-0000-0000-0000-000000000001"
ROOT = (1).to_bytes(16, "little").hex()
FILE = (2).to_bytes(16, "little").hex()
DIR = (3).to_bytes(16, "little").hex()
OUTSIDE = (4).to_bytes(16, "little").hex()


def item(usn, reason, name="Отчёт.txt", file_id=FILE, parent=ROOT):
    return UsnRecord(file_id, parent, usn, STAMP, reason, 0, name)


def state(tmp_path):
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", uuid4())
    result = UsnState(box, VOLUME, "synthetic-scope")
    result.initialize(42, 0, {ROOT: {"parent": None, "name": "", "root": "pilot"}})
    return result


def test_rename_close_summary_does_not_repeat_pair_after_restart(tmp_path):
    capture = state(tmp_path)
    capture.consume(42, 32, [item(1, 0x80000100)])
    pair = capture.consume(42, 64, [item(33, 0x1000), item(34, 0x2000, "После.txt")])
    assert len(pair) == 1 and pair[0].event_type == "RENAME"
    restarted = UsnState(capture.box, VOLUME, "synthetic-scope")
    assert restarted.consume(42, 96, [item(65, 0x80002000, "После.txt")]) == ()
    again = restarted.consume(42, 128, [item(97, 0x1000, "После.txt"),
                                        item(98, 0x2000, "Следующее.txt"),
                                        item(99, 0x80002000, "Следующее.txt")])
    assert len(again) == 1 and again[0].event_type == "RENAME"
    assert again[0].old_relative_path == "pilot\\После.txt"


def test_orphan_new_name_is_observed_once_and_new_destination_is_not_suppressed(tmp_path):
    capture = state(tmp_path)
    first = capture.consume(42, 32, [item(1, 0x2000, "Первое.txt")])
    assert len(first) == 1 and first[0].old_relative_path is None
    assert capture.consume(42, 64, [item(33, 0x80002000, "Первое.txt")]) == ()
    second = capture.consume(42, 96, [item(65, 0x80002000, "Иное.txt")])
    assert len(second) == 1 and second[0].new_relative_path == "pilot\\Иное.txt"


def test_first_orphan_close_on_cached_path_is_not_inferred_as_duplicate(tmp_path):
    capture = state(tmp_path)
    capture.consume(42, 32, [item(1, 0x80000100)])
    orphan = capture.consume(42, 64, [item(33, 0x80002000)])
    assert len(orphan) == 1 and orphan[0].event_type == "RENAME"
    assert orphan[0].old_relative_path is None
    next_cycle = capture.consume(42, 96, [item(65, 0x80002000)])
    assert len(next_cycle) == 1 and next_cycle[0].event_type == "RENAME"


def test_rename_close_summary_still_flushes_data_write(tmp_path):
    capture = state(tmp_path)
    capture.consume(42, 32, [item(1, 0x80000100)])
    capture.consume(42, 64, [item(33, 0x1000), item(34, 0x2000, "После.txt")])
    events = capture.consume(42, 96, [item(65, 0x80002001, "После.txt")])
    assert [event.event_type for event in events] == ["WRITE"]


def test_accumulated_new_reason_before_close_is_not_another_rename(tmp_path):
    capture = state(tmp_path)
    capture.consume(42, 32, [item(1, 0x80000100)])
    pair = capture.consume(42, 64, [item(33, 0x1000), item(34, 0x2000, "После.txt")])
    assert len(pair) == 1 and pair[0].event_type == "RENAME"
    restarted = UsnState(capture.box, VOLUME, "synthetic-scope")
    assert restarted.consume(42, 96, [item(65, 0x2001, "После.txt")]) == ()
    closed = restarted.consume(42, 128, [item(97, 0x80002001, "После.txt")])
    assert [event.event_type for event in closed] == ["WRITE"]


def test_changed_cache_signature_cannot_suppress_a_markerless_destination(tmp_path):
    capture = state(tmp_path)
    capture.consume(42, 32, [item(1, 0x2000, "Первое.txt")])
    capture.consume(42, 64, [item(33, 0x8000, "Иное.txt")])
    orphan = capture.consume(42, 96, [item(65, 0x80002000, "Иное.txt")])
    assert len(orphan) == 1 and orphan[0].event_type == "RENAME"
    assert orphan[0].old_relative_path is None


def test_crud_close_noise_rename_restart_and_deleted_cached_path(tmp_path):
    capture = state(tmp_path)
    events = capture.consume(42, 32, [item(1, 0x100), item(2, 0x80000100)])
    assert [e.event_type for e in events] == ["CREATE"]
    events = capture.consume(42, 64, [item(33, 1), item(34, 3), item(35, 0x80000003)])
    assert [e.event_type for e in events] == ["WRITE"]
    assert events[0].reason_mask == "0x80000003"
    assert capture.consume(42, 96, [item(65, 0x1000)]) == ()
    assert capture.status == "USN_PATH_UNKNOWN"
    restarted = UsnState(capture.box, VOLUME, "synthetic-scope")
    events = restarted.consume(42, 128, [item(97, 0x2000, "Новое.txt")])
    assert len(events) == 1 and events[0].event_type == "RENAME"
    assert restarted.status is None
    assert events[0].old_relative_path == "pilot\\Отчёт.txt"
    assert events[0].new_relative_path == "pilot\\Новое.txt"
    events = restarted.consume(42, 160, [item(129, 0x80000200, "Новое.txt")])
    assert len(events) == 1 and events[0].event_type == "DELETE"
    assert events[0].old_relative_path == "pilot\\Новое.txt"
    assert all(e.file_id == FILE and e.source_event_id.startswith("ntfs-usn:") for e in events)
    assert capture.box.status().pending_count == 4


def test_ancestor_rename_updates_descendant_path_without_changing_id(tmp_path):
    capture = state(tmp_path)
    capture.consume(42, 32, [item(1, 0x80000100, "До", DIR),
                            item(2, 0x80000100, parent=DIR)])
    renamed = capture.consume(42, 64, [item(33, 0x1000, "До", DIR),
                                       item(34, 0x2000, "После", DIR)])
    assert len(renamed) == 1
    restarted = UsnState(capture.box, VOLUME, "synthetic-scope")
    assert restarted.consume(42, 65, [item(64, 0x80002000, "После", DIR)]) == ()
    deleted = capture.consume(42, 96, [item(65, 0x80000200, parent=DIR)])
    assert deleted[0].file_id == FILE
    assert deleted[0].old_relative_path == "pilot\\После\\Отчёт.txt"


def test_unknown_and_outside_names_never_persist_and_move_out_redacts_name(tmp_path):
    capture = state(tmp_path)
    assert capture.consume(42, 32, [item(1, 0x100, "private-outside", parent=OUTSIDE)]) == ()
    capture.consume(42, 64, [item(33, 0x80000100)])
    capture.consume(42, 96, [item(65, 0x1000)])
    events = capture.consume(42, 128, [item(97, 0x2000, "outside-destination", parent=OUTSIDE)])
    assert len(events) == 1
    assert events[0].old_relative_path == "pilot\\Отчёт.txt"
    assert events[0].new_relative_path is None
    assert capture.consume(42, 160, [item(129, 0x80000001, "outside-destination",
                                        parent=OUTSIDE)]) == ()
    data = capture.box.path.read_bytes()
    assert b"private-outside" not in data and b"outside-destination" not in data


def test_duplicate_raw_reads_have_no_new_batch_or_logical_event(tmp_path):
    capture = state(tmp_path)
    record = item(1, 0x80000100)
    first = capture.consume(42, 32, [record])
    assert capture.consume(42, 32, [record]) == ()
    assert capture.box.status().pending_count == 1
    assert len(first) == 1


def test_reset_and_wrap_latch_gap_without_advancing_or_recovering_silently(tmp_path):
    capture = state(tmp_path)
    capture.consume(42, 32, [item(1, 0x80000100)])
    capture.check_continuity(99, 0, 128)
    assert capture.status == "CONTINUITY_GAP"
    assert capture.consume(42, 64, [item(33, 0x80000200)]) == ()
    assert capture.cursor == 32 and capture.box.status().pending_count == 1
    restarted = UsnState(capture.box, VOLUME, "synthetic-scope")
    assert restarted.status == "CONTINUITY_GAP"


def test_long_cyrillic_paths_and_metadata_security_have_no_actor_fields(tmp_path):
    capture = state(tmp_path)
    parent = ROOT
    cursor = 0
    for number in range(10, 40):
        identifier = number.to_bytes(16, "little").hex()
        capture.consume(42, cursor + 32, [item(cursor + 1, 0x80000100,
                                              "я" * 200, identifier, parent)])
        parent, cursor = identifier, cursor + 32
    events = capture.consume(42, cursor + 32, [item(cursor + 1, 0x80008800, parent=parent)])
    assert {e.event_type for e in events} == {"METADATA_CHANGE", "SECURITY_CHANGE"}
    assert all(len(e.new_relative_path) > 6000 for e in events)
    assert not any("actor" in e.model_dump() or "client" in e.model_dump() for e in events)


def test_unpaired_new_is_rename_with_explicit_unknown_old_path(tmp_path):
    capture = state(tmp_path)
    events = capture.consume(42, 32, [item(1, 0x2000, "Вход.txt")])
    assert len(events) == 1 and events[0].event_type == "RENAME"
    assert events[0].old_relative_path is None
    assert events[0].new_relative_path == "pilot\\Вход.txt"
    assert events[0].path_quality == "UNAVAILABLE"


def test_unknown_parent_does_not_invent_a_rename_from_a_write(tmp_path):
    capture = state(tmp_path)
    capture.consume(42, 32, [item(1, 0x80000100)])
    assert capture.consume(42, 64, [item(33, 0x80000001, "private-outside",
                                        parent=OUTSIDE)]) == ()
    assert capture.status == "USN_PATH_UNKNOWN"
    assert capture.cursor == 32
    assert b"private-outside" not in capture.box.path.read_bytes()


def test_pending_write_and_combined_old_data_survive_move_out(tmp_path):
    for combined in [False, True]:
        capture = state(tmp_path / str(combined))
        capture.consume(42, 32, [item(1, 0x80000100)])
        if not combined:
            capture.consume(42, 64, [item(33, 1)])
        old_cursor = 64 if not combined else 32
        capture.consume(42, old_cursor + 32, [item(old_cursor + 1, 0x1001 if combined else 0x1000)])
        events = capture.consume(42, old_cursor + 64,
                                 [item(old_cursor + 33, 0x80002000, "private-outside",
                                       parent=OUTSIDE)])
        assert [e.event_type for e in events] == ["WRITE", "RENAME"]
        assert events[0].new_relative_path == "pilot\\Отчёт.txt"
        assert events[1].new_relative_path is None
        assert b"private-outside" not in capture.box.path.read_bytes()


def test_directory_move_out_then_descendant_noise_does_not_stop_inside_stream(tmp_path):
    capture = state(tmp_path)
    capture.consume(42, 32, [item(1, 0x80000100, "До", DIR),
                            item(2, 0x80000100, parent=DIR)])
    capture.consume(42, 64, [item(33, 0x1000, "До", DIR),
                            item(34, 0x2000, "private-outside", DIR, OUTSIDE)])
    events = capture.consume(42, 96, [item(65, 0x80000001, "private-child", parent=DIR),
                                      item(66, 0x80000100, "Внутри.txt",
                                           (5).to_bytes(16, "little").hex())])
    assert len(events) == 1 and events[0].event_type == "CREATE"
    assert events[0].new_relative_path == "pilot\\Внутри.txt"
    assert capture.status is None and capture.cursor == 96
    assert b"private-child" not in capture.box.path.read_bytes()


def test_descendant_of_moved_out_directory_reenters_with_unknown_old_path(tmp_path):
    capture = state(tmp_path)
    capture.consume(42, 32, [item(1, 0x80000100, "До", DIR),
                            item(2, 0x80000100, parent=DIR)])
    capture.consume(42, 64, [item(33, 0x1000, "До", DIR),
                            item(34, 0x2000, "private-directory", DIR, OUTSIDE)])
    assert capture.consume(42, 96, [item(65, 0x1000, "private-old", parent=DIR)]) == ()
    events = capture.consume(42, 128, [item(97, 0x80002000, "Внутри.txt")])
    assert len(events) == 1 and events[0].event_type == "RENAME"
    assert events[0].old_relative_path is None
    assert events[0].new_relative_path == "pilot\\Внутри.txt"
    assert events[0].path_quality == "UNAVAILABLE" and capture.status is None
    assert b"private-old" not in capture.box.path.read_bytes()


def test_unpaired_new_for_cached_file_is_explicit_unknown_old_rename(tmp_path):
    capture = state(tmp_path)
    capture.consume(42, 32, [item(1, 0x80000100)])
    events = capture.consume(42, 64, [item(33, 0x80002000, "После.txt")])
    assert len(events) == 1 and events[0].event_type == "RENAME"
    assert events[0].old_relative_path is None
    assert events[0].new_relative_path == "pilot\\После.txt"
    assert events[0].path_quality == "UNAVAILABLE"


def test_ancestor_reentry_never_reuses_child_name_changed_while_outside(tmp_path):
    capture = state(tmp_path)
    capture.consume(42, 32, [item(1, 0x80000100, "До", DIR),
                            item(2, 0x80000100, parent=DIR)])
    capture.consume(42, 64, [item(33, 0x1000, "До", DIR),
                            item(34, 0x2000, "private-directory", DIR, OUTSIDE)])
    assert capture.consume(42, 96, [item(65, 0x80002000, "private-renamed-child",
                                        parent=DIR)]) == ()
    capture.consume(42, 128, [item(97, 0x80002000, "Вернулась", DIR)])
    events = capture.consume(42, 160, [item(129, 0x80000200, "После.txt", parent=DIR)])
    assert len(events) == 1 and events[0].event_type == "DELETE"
    assert events[0].file_id == FILE
    assert events[0].old_relative_path == "pilot\\Вернулась\\После.txt"
    assert b"private-renamed-child" not in capture.box.path.read_bytes()


def test_pending_inside_write_and_old_survive_ancestor_move_out_and_restart(tmp_path):
    capture = state(tmp_path)
    capture.consume(42, 32, [item(1, 0x80000100, "До", DIR),
                            item(2, 0x80000100, parent=DIR)])
    capture.consume(42, 64, [item(33, 1, parent=DIR), item(34, 0x1000, parent=DIR)])
    capture = UsnState(capture.box, VOLUME, "synthetic-scope")
    capture.consume(42, 96, [item(65, 0x1000, "До", DIR),
                            item(66, 0x2000, "private-directory", DIR, OUTSIDE)])
    events = capture.consume(42, 128, [item(97, 0x80002000, "private-new", parent=DIR)])
    assert [e.event_type for e in events] == ["WRITE", "RENAME"]
    assert events[0].new_relative_path is None and events[0].occurred_at == STAMP
    assert events[0].reason_mask == "0x80000001"
    assert events[1].old_relative_path == "pilot\\До\\Отчёт.txt"
    assert events[1].new_relative_path is None and events[1].path_quality == "UNAVAILABLE"
    assert capture.status is None and capture.cursor == 128
    assert capture.consume(42, 128, [item(97, 0x80002000, "private-new", parent=DIR)]) == ()
    assert b"private-new" not in capture.box.path.read_bytes()


def test_pending_directory_pair_reenters_then_descendant_is_inside(tmp_path):
    capture = state(tmp_path)
    capture.consume(42, 32, [item(1, 0x80000100, "До", DIR),
                            item(2, 0x80000100, "Вложена", FILE, DIR)])
    capture.consume(42, 64, [item(33, 0x1000, "Вложена", FILE, DIR)])
    capture.consume(42, 96, [item(65, 0x1000, "До", DIR),
                            item(66, 0x2000, "private-directory", DIR, OUTSIDE)])
    assert capture.consume(42, 128, [item(97, 0x80000001, "private-pending", FILE, DIR)]) == ()
    events = capture.consume(42, 160, [item(129, 0x80002000, "Вернулась", FILE)])
    assert len(events) == 1 and events[0].event_type == "RENAME"
    assert events[0].old_relative_path == "pilot\\До\\Вложена"
    assert events[0].new_relative_path == "pilot\\Вернулась"
    events = capture.consume(42, 192, [item(161, 0x80000100, "Дочерний.txt",
                                           (5).to_bytes(16, "little").hex(), FILE)])
    assert len(events) == 1 and events[0].event_type == "CREATE"
    assert events[0].new_relative_path == "pilot\\Вернулась\\Дочерний.txt"
    assert capture.status is None
    assert b"private-pending" not in capture.box.path.read_bytes()


def test_pending_write_before_ancestor_rename_has_original_or_unknown_path(tmp_path):
    capture = state(tmp_path)
    capture.consume(42, 32, [item(1, 0x80000100, "До", DIR),
                            item(2, 0x80000100, parent=DIR)])
    capture.consume(42, 64, [item(33, 1, parent=DIR)])
    capture = UsnState(capture.box, VOLUME, "synthetic-scope")
    capture.consume(42, 96, [item(65, 0x1000, "До", DIR),
                            item(66, 0x2000, "После", DIR)])
    events = capture.consume(42, 128, [item(97, 0x80000000, parent=DIR)])
    assert len(events) == 1 and events[0].event_type == "WRITE"
    assert events[0].new_relative_path in (None, "pilot\\До\\Отчёт.txt")
    assert events[0].occurred_at == STAMP
    assert events[0].parent_file_id == DIR


def test_pending_write_cross_parent_rename_keeps_first_parent_and_known_path(tmp_path):
    capture = state(tmp_path)
    capture.consume(42, 32, [item(1, 0x80000100, "До", DIR),
                            item(2, 0x80000100, parent=DIR)])
    capture.consume(42, 64, [item(33, 1, parent=DIR), item(34, 0x1000, parent=DIR)])
    capture = UsnState(capture.box, VOLUME, "synthetic-scope")
    events = capture.consume(42, 96, [item(65, 0x80002000, "После.txt")])
    assert [e.event_type for e in events] == ["WRITE", "RENAME"]
    assert events[0].new_relative_path == "pilot\\До\\Отчёт.txt"
    assert events[0].parent_file_id == DIR and events[0].reason_mask == "0x80000001"
    assert events[1].parent_file_id == ROOT
