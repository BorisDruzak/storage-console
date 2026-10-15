"""Delivery policy. Network runs outside local transactions and controller locks."""

import math
import random
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID

from .outbox import Claim, Outbox
from .transport import DeliveryOutcome, TransportError, valid_outcome


class Sender(Protocol):
    @property
    def collector_id(self) -> UUID: ...

    def send(self, claim: Claim) -> DeliveryOutcome: ...


State = Literal["idle", "accepted", "retry", "suspended", "quarantined", "stale", "stopped"]


@dataclass(frozen=True)
class DeliveryResult:
    state: State
    code: str | None = None


@dataclass(frozen=True)
class _Settlement:
    claim: Claim
    generation: int
    outcome: DeliveryOutcome
    next_attempt: datetime | None


class Delivery:
    def __init__(
        self,
        outbox: Outbox,
        transport: Sender,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        randomness: Callable[[], float] = random.random,
        prefer_heartbeat: bool = False,
        heartbeat_burst: int = 4,
    ) -> None:
        if (
            transport.collector_id != outbox.collector_id
            or type(prefer_heartbeat) is not bool
            or type(heartbeat_burst) is not int
            or not 1 <= heartbeat_burst <= 100
        ):
            raise TransportError("INVALID_CONFIG")
        self._outbox = outbox
        self._transport = transport
        self._clock = clock
        self._randomness = randomness
        self._generation = outbox.credential_generation()
        self._closed = False
        self._prefer_heartbeat = prefer_heartbeat
        self._heartbeat_burst = heartbeat_burst
        self._heartbeat_run = 0
        self._sending = False
        self._pending: _Settlement | None = None
        self._lock = threading.Lock()

    def refresh_credentials(self, transport: Sender) -> None:
        if transport.collector_id != self._outbox.collector_id:
            raise TransportError("INVALID_CONFIG")
        with self._lock:
            if self._closed:
                raise TransportError("INVALID_CONFIG")
            self._generation = self._outbox.resume_auth()
            self._transport = transport
            self._heartbeat_run = 0
            self._pending = None

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._pending = None

    def run_once(self) -> DeliveryResult:
        with self._lock:
            if self._closed:
                return DeliveryResult("stopped")
            if self._pending is not None:
                return self._settle_pending()
            if self._sending:
                return DeliveryResult("idle")
            if self._outbox.auth_suspended() or (
                self._generation != self._outbox.credential_generation()
            ):
                return DeliveryResult("suspended", "AUTH_REQUIRED")
            if self._prefer_heartbeat:
                claim = self._outbox.claim(
                    self._clock(),
                    heartbeat_priority="first"
                    if self._heartbeat_run < self._heartbeat_burst
                    else "last",
                )
            else:
                claim = self._outbox.claim(self._clock())
            if claim is None:
                return DeliveryResult("idle")
            generation = self._generation
            if claim.credential_generation != generation:
                return DeliveryResult("stale")
            self._heartbeat_run = (
                min(self._heartbeat_burst, self._heartbeat_run + 1)
                if claim.domain == "heartbeat"
                else 0
            )
            transport = self._transport
            self._sending = True
        try:
            value = transport.send(claim)
            if not valid_outcome(value):
                value = DeliveryOutcome("retry", code="INVALID_RECEIPT")
        except Exception:
            value = DeliveryOutcome("retry", code="NETWORK")
        with self._lock:
            self._sending = False
            if self._closed:
                return DeliveryResult("stopped")
            next_attempt = None
            if value.kind == "retry":
                next_attempt = self._retry_at(claim, value)
            # Retain the response before any local state access can fail. There is
            # at most one claim in memory, and local retries never send it again.
            self._pending = _Settlement(claim, generation, value, next_attempt)
            return self._settle_pending()

    def _settle_pending(self) -> DeliveryResult:
        # Called only under the controller lock; Outbox still fences lease and
        # credential generation atomically inside each settlement transaction.
        pending = self._pending
        assert pending is not None
        claim, generation, value = pending.claim, pending.generation, pending.outcome
        if generation != self._generation or generation != self._outbox.credential_generation():
            result = DeliveryResult("stale")
        elif value.kind == "accepted":
            changed = self._outbox.acknowledge(claim)
            result = DeliveryResult("accepted" if changed else "stale")
        elif value.kind == "suspended":
            changed = self._outbox.suspend_auth(claim)
            result = DeliveryResult("suspended" if changed else "stale", "AUTH_REQUIRED")
        elif value.kind == "quarantined":
            changed = self._outbox.quarantine(claim, value.code or "HTTP_REJECTED")
            result = DeliveryResult("quarantined" if changed else "stale", value.code)
        else:
            assert pending.next_attempt is not None
            changed = self._outbox.retry(claim, value.code or "NETWORK", pending.next_attempt)
            result = DeliveryResult("retry" if changed else "stale", value.code)
        # Exceptions deliberately preserve pending and propagate unchanged, so
        # callers retain their existing retryable/fatal state-error policy.
        self._pending = None
        return result

    def _retry_at(self, claim: Claim, value: DeliveryOutcome) -> datetime:
        base = min(300.0, 2.0 ** min(claim.attempts, 9))
        jitter = self._randomness()
        if type(jitter) not in (int, float) or not math.isfinite(jitter):
            jitter = 0
        delay = min(300.0, max(base * (1 + max(0, min(1, jitter))), value.retry_after or 0))
        return self._clock() + timedelta(seconds=delay)
