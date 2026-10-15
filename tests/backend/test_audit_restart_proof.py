"""Portable negative controls for the disposable native restart witness."""

from copy import deepcopy

import pytest
from audit_restart_proof import assert_restart_continuity, assert_retained_prefix


def checkpoint(record=100, *, read=10, accepted=3, filtered=8):
    return (
        f"<BookmarkList><Bookmark Channel='Security' RecordId='{record}' "
        "IsCurrent='true'/></BookmarkList>",
        {
            "boot_id": "synthetic-boot",
            "host_id": "synthetic-host",
            "generation": "synthetic-generation",
            "counters": {"read": read, "accepted": accepted, "filtered": filtered},
        },
    )


def test_filtered_security_traffic_may_advance_a_resumed_bookmark():
    assert_restart_continuity(checkpoint(), checkpoint(108, read=12, filtered=10))


def test_unread_scoped_access_may_be_captured_after_restart():
    assert_restart_continuity(checkpoint(), checkpoint(108, read=12, accepted=5, filtered=9))


def test_idle_checkpoint_is_preserved():
    assert_restart_continuity(checkpoint(), checkpoint())


@pytest.mark.parametrize("field", ["boot_id", "host_id", "generation"])
def test_restart_must_not_relabel_identity(field):
    before = checkpoint()
    after = deepcopy(before)
    after[1][field] = "different"
    with pytest.raises(AssertionError):
        assert_restart_continuity(before, after)


@pytest.mark.parametrize(
    "after",
    [
        checkpoint(99),
        checkpoint(108),  # Future-only rebaseline without consuming records.
        checkpoint(108, read=1, accepted=1, filtered=0),
        checkpoint(108, read=12, accepted=2, filtered=10),
        checkpoint(108, read=12, filtered=11),
        checkpoint(108, read=12, accepted=5, filtered=10),
        checkpoint(100, read=11, filtered=9),  # Duplicate processing at an unchanged position.
    ],
)
def test_regression_reset_skip_and_inconsistent_counters_are_rejected(after):
    with pytest.raises(AssertionError):
        assert_restart_continuity(checkpoint(), after)


@pytest.mark.parametrize(
    "bookmark",
    [
        None,
        "invalid",
        "<BookmarkList/>",
        "<BookmarkList><Bookmark Channel='Other' RecordId='108' IsCurrent='true'/></BookmarkList>",
    ],
)
def test_invalid_or_foreign_bookmark_is_rejected(bookmark):
    after = checkpoint(108, read=12, filtered=10)
    with pytest.raises(AssertionError):
        assert_restart_continuity(checkpoint(), (bookmark, after[1]))


def test_new_capture_may_append_without_rewriting_retained_batches():
    assert_retained_prefix([("one", b"retained")], [("one", b"retained"), ("two", b"new")])


@pytest.mark.parametrize("after", [[], [("one", b"changed")], [("other", b"retained")]])
def test_lost_or_rewritten_retained_batch_is_rejected(after):
    with pytest.raises(AssertionError):
        assert_retained_prefix([("one", b"retained")], after)
