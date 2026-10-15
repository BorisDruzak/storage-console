"""Portable checkpoint witness shared with disposable native SCM acceptance."""

import re
from xml.etree import ElementTree as ET


def _position(bookmark):
    assert isinstance(bookmark, str) and 0 < len(bookmark) <= 16384, "BOOKMARK_REQUIRED"
    assert "<!" not in bookmark, "BOOKMARK_INVALID"
    try:
        root = ET.fromstring(bookmark)
    except ET.ParseError:
        raise AssertionError("BOOKMARK_INVALID") from None
    assert root.tag == "BookmarkList" and len(root) == 1, "BOOKMARK_INVALID"
    item = root[0]
    assert item.tag == "Bookmark" and item.get("Channel") == "Security", "BOOKMARK_INVALID"
    value = item.get("RecordId", "")
    assert re.fullmatch(r"[0-9]{1,20}", value) and int(value) > 0, "BOOKMARK_INVALID"
    return int(value)


def assert_restart_continuity(before, after):
    prior, current = _position(before[0]), _position(after[0])
    assert current >= prior, "RESTART_REGRESSED_BOOKMARK"
    for key in ("boot_id", "host_id", "generation"):
        assert before[1].get(key) and after[1].get(key) == before[1][key], (
            "RESTART_IDENTITY_CHANGED"
        )
    deltas = {}
    for key in ("read", "accepted", "filtered"):
        old, new = before[1]["counters"][key], after[1]["counters"][key]
        assert type(old) is int and type(new) is int and 0 <= old <= new, "RESTART_COUNTER_RESET"
        deltas[key] = new - old
    assert (current > prior) == (deltas["read"] > 0), "RESTART_SKIPPED_OR_DUPLICATED_RECORDS"
    selected = deltas["read"] - deltas["filtered"]
    assert 0 <= selected <= deltas["read"], "RESTART_COUNTERS_INCONSISTENT"
    assert (selected == 0) == (deltas["accepted"] == 0), "RESTART_COUNTERS_INCONSISTENT"
    assert deltas["accepted"] >= selected, "RESTART_COUNTERS_INCONSISTENT"


def assert_retained_prefix(before, after):
    assert len(after) >= len(before), "RESTART_LOST_RETAINED_QUEUE"
    assert all(old == new for old, new in zip(before, after, strict=False)), "RESTART_CHANGED_QUEUE"
