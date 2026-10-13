"""Own retained queue delivery; pure HTTPS transport never opens the USN outbox."""

import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

from collectors.common.outbox import Claim
from collectors.common.transport import DeliveryOutcome, Transport, valid_outcome
from packages.contracts.audit import AuditHealth
from packages.contracts.common import BatchEnvelope
from packages.contracts.heartbeat import HeartbeatRecord

from .store import AuditStore


class Sender(Protocol):
    def send(self, claim: Claim) -> DeliveryOutcome: ...


class Delivery:
    def __init__(self, store: AuditStore, sender: Sender) -> None:
        self.store, self.sender = store, sender

    def step(self, *, now: float | None = None) -> None:
        clock = time.time() if now is None else now
        state = self.store.delivery_state()
        if (
            state.get("suspended")
            or state.get("quarantine")
            or state.get("next_attempt", 0) > clock
        ):
            return
        pending = self.store.peek()
        if pending is None:
            return
        identity, body = pending
        outcome = self.sender.send(
            Claim(identity, "audit", body, "audit", state.get("attempts", 0))
        )
        if not valid_outcome(outcome):
            outcome = DeliveryOutcome("retry", "INVALID_RECEIPT")
        if outcome.kind == "accepted":
            # Lost ACK or a crash between ACK and status still replays the same body.
            self.store.acknowledge(identity)
            self.store.save_delivery({"last_accepted_at": datetime.now(UTC).isoformat()})
            return
        attempts = min(state.get("attempts", 0) + 1, 10)
        state.update(
            attempts=attempts,
            error_code=outcome.code,
            next_attempt=clock + max(outcome.retry_after or 0, min(300, 2**attempts)),
            suspended=outcome.kind == "suspended",
            quarantine=outcome.kind == "quarantined",
        )
        self.store.save_delivery(state)


def run_delivery(state: Any, config: Any, stop: threading.Event) -> None:
    from .configuration import MachineCipher

    store = AuditStore(state.root / "audit.sqlite3", config.collector_id, MachineCipher())
    sender = Transport(
        config.origin,
        Path(config.ca_file),
        config.token.get_secret_value(),
        timeout=10,
        collector_id=config.collector_id,
    )
    delivery = Delivery(store, sender)
    heartbeat_at = 0.0
    pending_heartbeat: Claim | None = None
    while not stop.is_set():
        try:
            delivery.step()
            if time.monotonic() >= heartbeat_at and not stop.is_set():
                queue, status = store.status(), {}
                try:
                    if (state.root / "audit-status.json").exists():
                        status = json.loads(state.read("audit-status.json", 65536))
                except (OSError, ValueError):
                    pass
                outcome_state = store.delivery_state()
                health = AuditHealth(
                    configured=config.configured
                    and bool(status.get("policy_verified"))
                    and bool(status.get("sacl_verified")),
                    host_id=config.host_id,
                    generation=config.generation,
                    boot_id=store.checkpoint()[1].get("boot_id"),
                    state=status.get("health", "OBSERVE"),
                    gap=cast(str | None, queue["gap"]),
                    last_collected_at=status.get("observed_through_at"),
                    last_accepted_at=outcome_state.get("last_accepted_at"),
                    bookmark_age_seconds=status.get("bookmark_age_seconds"),
                    remaining_record_margin=status.get("bookmark_remaining_record_margin"),
                    read_count=status.get("counters", {}).get("read", 0),
                    filtered_count=status.get("counters", {}).get("filtered", 0),
                    backlog_count=cast(int, queue["backlog"]),
                    backlog_bytes=cast(int, queue["encrypted_bytes"]),
                    quarantine=bool(outcome_state.get("quarantine")),
                    error_code=outcome_state.get("error_code") or status.get("bounds_error"),
                    policy_verified=bool(status.get("policy_verified")),
                    sacl_verified=bool(status.get("sacl_verified")),
                )
                now = datetime.now(UTC)
                if pending_heartbeat is None:
                    body = BatchEnvelope[HeartbeatRecord](
                        collector_id=config.collector_id,
                        batch_id=uuid4().hex,
                        schema_version=1,
                        sent_at=now,
                        first_event_at=now,
                        last_event_at=now,
                        record_count=1,
                        records=[HeartbeatRecord(occurred_at=now, version="0.1.0", audit=health)],
                    )
                    pending_heartbeat = Claim(
                        body.batch_id,
                        "heartbeat",
                        body.model_dump_json().encode(),
                        "audit-health",
                        0,
                    )
                outcome = sender.send(pending_heartbeat)
                if outcome.kind == "accepted":
                    pending_heartbeat = None
                elif outcome.kind in ("suspended", "quarantined"):
                    saved = store.delivery_state()
                    saved.update(
                        error_code=outcome.code,
                        suspended=outcome.kind == "suspended",
                        quarantine=outcome.kind == "quarantined",
                    )
                    store.save_delivery(saved)
                heartbeat_at = time.monotonic() + 30
        except Exception:
            # Fixed-code failure; SCM and central freshness expose lost diagnostics.
            stop.set()
            return
        stop.wait(1)
