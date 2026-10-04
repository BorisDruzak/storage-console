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


class Delivery:
    def __init__(
        self,
        outbox: Outbox,
        transport: Sender,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        randomness: Callable[[], float] = random.random,
    ) -> None:
        if transport.collector_id != outbox.collector_id:
            raise TransportError("INVALID_CONFIG")
        self._outbox = outbox
        self._transport = transport
        self._clock = clock
        self._randomness = randomness
        self._generation = outbox.credential_generation()
        self._closed = False
        self._lock = threading.Lock()

    def refresh_credentials(self, transport: Sender) -> None:
        if transport.collector_id != self._outbox.collector_id:
            raise TransportError("INVALID_CONFIG")
        with self._lock:
            if self._closed:
                raise TransportError("INVALID_CONFIG")
            self._generation = self._outbox.resume_auth()
            self._transport = transport

    def close(self) -> None:
        with self._lock:
            self._closed = True

    def run_once(self) -> DeliveryResult:
        with self._lock:
            if self._closed:
                return DeliveryResult("stopped")
            if self._outbox.auth_suspended() or (
                self._generation != self._outbox.credential_generation()
            ):
                return DeliveryResult("suspended", "AUTH_REQUIRED")
            claim = self._outbox.claim(self._clock())
            if claim is None:
                return DeliveryResult("idle")
            generation = self._generation
            if claim.credential_generation != generation:
                return DeliveryResult("stale")
            transport = self._transport
        try:
            value = transport.send(claim)
            if not valid_outcome(value):
                value = DeliveryOutcome("retry", code="INVALID_RECEIPT")
        except Exception:
            value = DeliveryOutcome("retry", code="NETWORK")
        with self._lock:
            if self._closed:
                return DeliveryResult("stopped")
            if generation != self._generation or generation != self._outbox.credential_generation():
                return DeliveryResult("stale")
            if value.kind == "accepted":
                changed = self._outbox.acknowledge(claim)
                return DeliveryResult("accepted" if changed else "stale")
            if value.kind == "suspended":
                changed = self._outbox.suspend_auth(claim)
                return DeliveryResult("suspended" if changed else "stale", "AUTH_REQUIRED")
            if value.kind == "quarantined":
                changed = self._outbox.quarantine(claim, value.code or "HTTP_REJECTED")
                return DeliveryResult("quarantined" if changed else "stale", value.code)
            base = min(300.0, 2.0 ** min(claim.attempts, 9))
            jitter = self._randomness()
            if type(jitter) not in (int, float) or not math.isfinite(jitter):
                jitter = 0
            delay = min(300.0, max(base * (1 + max(0, min(1, jitter))), value.retry_after or 0))
            changed = self._outbox.retry(
                claim, value.code or "NETWORK", self._clock() + timedelta(seconds=delay)
            )
            return DeliveryResult("retry" if changed else "stale", value.code)
