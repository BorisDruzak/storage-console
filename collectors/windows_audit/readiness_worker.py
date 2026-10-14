"""One bounded background verifier; snapshots never wait for directory I/O."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

Probe = Callable[[Callable[[], bool]], tuple[bool, bool, int]]


class ReadinessWorker:
    def __init__(self, probe: Probe, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.probe, self.clock = probe, clock
        self._stop = threading.Event()
        self._initial = threading.Event()
        self._lock = threading.Lock()
        self._proof: dict[str, Any] | None = None
        self._started = 0.0
        self._thread = threading.Thread(target=self._run, name="audit-readiness", daemon=True)

    def __enter__(self) -> ReadinessWorker:
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        self._thread.join(timeout=3)
        if self._thread.is_alive():
            raise TimeoutError("AUDIT_READINESS_STOP_TIMEOUT")

    def wait_initial(self, timeout: float) -> bool:
        return self._initial.wait(timeout)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            proof = dict(self._proof) if self._proof else None
            started = self._started
        age = self.clock() - started if proof is not None else None
        fresh = age is not None and math.isfinite(age) and 0 <= age <= 60
        if proof is None:
            proof = {
                "policy_verified": False,
                "sacl_verified": False,
                "readiness_complete": False,
                "readiness_error": "AUDIT_READINESS_PENDING",
                "readiness_objects": 0,
            }
        if not fresh or self._stop.is_set():
            proof.update(policy_verified=False, sacl_verified=False)
        proof.update(readiness_age_seconds=age, readiness_stale=not fresh)
        return proof

    def _run(self) -> None:
        while not self._stop.is_set():
            started = self.clock()
            try:
                policy, sacl, count = self.probe(self._stop.is_set)
                duration = self.clock() - started
                if (
                    type(policy) is not bool
                    or type(sacl) is not bool
                    or type(count) is not int
                    or not 0 <= count <= 100000
                    or not math.isfinite(duration)
                    or not 0 <= duration <= 30
                ):
                    raise ValueError("AUDIT_READINESS_UNAVAILABLE")
                proof: dict[str, Any] = {
                    "policy_verified": policy,
                    "sacl_verified": sacl,
                    "readiness_complete": True,
                    "readiness_error": None,
                    "readiness_objects": count,
                    "readiness_duration_seconds": duration,
                    "readiness_checked_at": datetime.now(UTC).isoformat(),
                }
            except Exception:
                proof = {
                    "policy_verified": False,
                    "sacl_verified": False,
                    "readiness_complete": False,
                    "readiness_error": "AUDIT_READINESS_UNAVAILABLE",
                    "readiness_objects": 0,
                }
            with self._lock:
                self._proof, self._started = proof, started
            self._initial.set()
            # Schedule from probe start, so two valid <=30s scans fit within
            # the unchanged 60s proof lifetime. Failed probes retain backoff.
            elapsed = self.clock() - started
            delay = (
                max(0.0, 30 - elapsed)
                if proof["readiness_complete"] and math.isfinite(elapsed) and elapsed >= 0
                else 30
            )
            self._stop.wait(delay)


def native_probe(roots: list[str], sids: list[str], limit: int) -> Probe:
    from .readiness import Native, scope_covered

    def probe(stopped: Callable[[], bool]) -> tuple[bool, bool, int]:
        native = Native()
        checked = 0
        negative = False
        started = time.monotonic()

        def expired() -> bool:
            return stopped() or checked > limit or time.monotonic() - started > 30

        def check(path: str, principals: list[str], directory: bool) -> bool:
            nonlocal checked, negative
            if checked >= limit:
                raise ValueError("AUDIT_READINESS_INCOMPLETE")
            checked += 1
            valid = native.sacl_entry(path, principals, directory)
            negative = negative or not valid
            return valid

        with native.privilege():
            policy = native.policy()
            if not policy:
                return False, False, 0
            for root in roots:
                if not scope_covered(root, sids, check, limit=limit, stopped=expired):
                    if not negative:
                        raise ValueError("AUDIT_READINESS_INCOMPLETE")
                    return True, False, checked
        return True, True, checked

    return probe
