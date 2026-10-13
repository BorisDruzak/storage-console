"""Rule expectations deliberately separate account access from USN causality."""

from datetime import timedelta

import pytest
from test_windows_audit_events import parse, xml


def inputs(kind="DELETE"):
    access = parse(xml(AccessMask="0x10000"))
    logon = parse(xml(4624, record=8)).model_copy(
        update={"occurred_at": access.occurred_at - timedelta(seconds=10)}
    )
    deleted = parse(xml(4660, record=11)).model_copy(
        update={
            "occurred_at": access.occurred_at + timedelta(milliseconds=500),
            "linked_record_ids": [10],
        }
    )
    change = {
        "event_type": kind,
        "occurred_at": access.occurred_at + timedelta(seconds=1),
        "file_id": "file-a",
        "volume_identity": "volume-a",
        "reason_mask": "0x200",
        "source_event_id": "ntfs-usn:" + "a" * 64,
    }
    return change, [access, logon, deleted]


def evaluate(change, events, **options):
    from packages.shared.audit.correlation import decide

    return decide(
        change,
        events,
        identity_reason=options.get("identity_reason", "PROVEN_PRIOR_IDENTITY"),
        coverage=options.get("coverage", True),
        saturated=options.get("saturated", False),
    )


def test_delete_strong_chain_preserves_account_session_and_missing_client():
    result = evaluate(*inputs())
    assert result.classification == "CORRELATED_HIGH"
    assert result.actor["account"] == "UserA" and result.actor["logon_id"] == 257
    assert result.actor["client_ip"] is None and result.actor["workstation"] is None


@pytest.mark.parametrize("kind", ["CREATE", "WRITE", "RENAME"])
def test_delete_access_is_not_proof_of_create_write_rename(kind):
    result = evaluate(*inputs(kind))
    assert result.classification == "ACCESS_OBSERVED" and result.actor is None


@pytest.mark.parametrize(
    "change",
    [
        {"handle_id": None},
        {"process_id": 99},
        {"logon_id": 99},
        {"boot_id": "other-boot"},
        {"linked_record_ids": []},
    ],
)
def test_broken_delete_chain_has_no_actor(change):
    usn, events = inputs()
    events[2] = events[2].model_copy(update=change)
    assert evaluate(usn, events).actor is None


def test_same_numeric_logon_other_boot_is_not_session_proof():
    usn, events = inputs()
    events[1] = events[1].model_copy(update={"boot_id": "reused"})
    assert evaluate(usn, events).actor is None


def test_two_sids_sessions_are_explicitly_ambiguous():
    usn, events = inputs()
    second = events[0].model_copy(
        update={
            "sid": "S-1-5-21-100-200-300-1002",
            "account": "UserB",
            "logon_id": 258,
            "record_id": 12,
        }
    )
    result = evaluate(usn, events + [second])
    assert result.classification == "AMBIGUOUS" and result.actor is None


@pytest.mark.parametrize(
    "identity_reason", ["PATH_TIME_ONLY", "HARDLINK", "ALIAS_UNKNOWN", "PARENT_RENAME"]
)
def test_time_path_without_independent_identity_never_high(identity_reason):
    result = evaluate(*inputs(), identity_reason=identity_reason)
    assert result.actor is None and result.classification != "CORRELATED_HIGH"


def test_gap_and_candidate_cap_never_high():
    assert evaluate(*inputs(), coverage=False).actor is None
    result = evaluate(*inputs(), saturated=True)
    assert result.classification == "AMBIGUOUS" and result.actor is None
