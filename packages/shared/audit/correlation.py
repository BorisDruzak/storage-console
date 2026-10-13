"""v1: access facts for all operations; HIGH requires a corroborated deletion.

CREATE disposition, WRITE aggregation bounds and RENAME two-name operation links
are absent from the current streams. They deliberately never become HIGH in v1.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from packages.contracts.audit import AuditEvent

RULE_VERSION = "windows-security-usn-v1"
WINDOW = timedelta(seconds=2)


@dataclass(frozen=True)
class Decision:
    classification: str
    reason: str
    actor: dict[str, Any] | None = None
    supporting_record_id: int | None = None


def context(event: AuditEvent) -> tuple[Any, ...]:
    return (
        event.host_id,
        event.boot_id,
        event.generation,
        event.sid,
        event.logon_id,
        event.process_id,
        event.handle_id,
    )


def session(access: AuditEvent, event: AuditEvent) -> bool:
    return (
        event.event_id == 4624
        and access.logon_id is not None
        and access.sid is not None
        and (event.host_id, event.boot_id, event.generation, event.sid, event.logon_id)
        == (access.host_id, access.boot_id, access.generation, access.sid, access.logon_id)
        and event.record_id < access.record_id
        and timedelta(0) <= access.occurred_at - event.occurred_at <= timedelta(days=1)
    )


def decide(
    change: Mapping[str, Any],
    events: list[AuditEvent],
    *,
    identity_reason: str,
    coverage: bool,
    saturated: bool = False,
    identity_checks: dict[int, str] | None = None,
    coverage_checks: dict[int, bool] | None = None,
) -> Decision:
    accesses = [
        e
        for e in events
        if e.event_id == 4663 and abs(e.occurred_at - change["occurred_at"]) <= WINDOW
    ]
    if saturated:
        return Decision("AMBIGUOUS", "CANDIDATE_LIMIT")
    if not accesses:
        return Decision("UNKNOWN", "NO_SCOPED_ACCESS")
    if len({context(e) for e in accesses}) != 1:
        return Decision("AMBIGUOUS", "MULTIPLE_CONTEXTS")
    if identity_checks is None and identity_reason != "PROVEN_PRIOR_IDENTITY":
        return Decision("ACCESS_OBSERVED", identity_reason)
    if coverage_checks is None and not coverage:
        return Decision("ACCESS_OBSERVED", "INTERVAL_COVERAGE_UNKNOWN")
    kind = change["event_type"]
    if kind != "DELETE":
        reasons = {
            "CREATE": "CREATE_DISPOSITION_UNKNOWN",
            "WRITE": "WRITE_AGGREGATION_UNKNOWN",
            "RENAME": "RENAME_CHAIN_UNKNOWN",
        }
        return Decision("ACCESS_OBSERVED", reasons.get(kind, "OPERATION_UNSUPPORTED"))
    try:
        mask = int(change["reason_mask"], 0)
    except (TypeError, ValueError):
        mask = 0
    if not mask & 0x200 or not (change.get("source_event_id") or "").startswith("ntfs-usn:"):
        return Decision("ACCESS_OBSERVED", "USN_DELETE_UNPROVEN")
    matched: list[tuple[AuditEvent, AuditEvent]] = []
    rejection = "DELETE_CHAIN_UNPROVEN"
    for access in accesses:
        access_reason = (identity_checks or {}).get(access.record_id, identity_reason)
        access_coverage = (coverage_checks or {}).get(access.record_id, coverage)
        if access_reason != "PROVEN_PRIOR_IDENTITY" or not access_coverage:
            if (access.access_mask or 0) & 0x10000:
                rejection = (
                    access_reason
                    if access_reason != "PROVEN_PRIOR_IDENTITY"
                    else "INTERVAL_COVERAGE_UNKNOWN"
                )
            continue
        if not (access.access_mask or 0) & 0x10000 or not access.handle_id or not access.process_id:
            continue
        logons = [e for e in events if session(access, e)]
        if len(logons) != 1:
            continue
        for deletion in events:
            if (
                deletion.event_id == 4660
                and context(deletion) == context(access)
                and deletion.path is None
                and access.record_id in deletion.linked_record_ids
                and access.record_id < deletion.record_id
                and timedelta(0)
                <= deletion.occurred_at - access.occurred_at
                <= timedelta(seconds=30)
                and abs(deletion.occurred_at - change["occurred_at"]) <= WINDOW
            ):
                matched.append((access, logons[0]))
    if len(matched) != 1:
        return Decision("ACCESS_OBSERVED" if not matched else "AMBIGUOUS", rejection)
    access, logon = matched[0]
    return Decision(
        "CORRELATED_HIGH",
        "UNIQUE_DELETE_CHAIN",
        {
            "sid": access.sid,
            "account": access.account,
            "domain": access.domain,
            "logon_id": access.logon_id,
            "host_id": str(access.host_id),
            "boot_id": access.boot_id,
            "client_ip": logon.client_ip if logon.logon_type == 3 else None,
            "workstation": logon.workstation if logon.logon_type == 3 else None,
        },
        access.record_id,
    )
