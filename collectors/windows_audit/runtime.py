"""Atomic Security capture; a latched gap requires an explicit operator baseline."""

import json
import os
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from .events import parse_event
from .native import STALE, EventLogError, EventLogPending
from .readiness_worker import ReadinessWorker, native_probe
from .scope import AuditScope, Selector
from .store import AuditStore


class Reader(Protocol):
    def next(self) -> tuple[str, str] | None: ...


class RuntimeStatus:
    """Cross-thread snapshot; protected file reads pin replacement targets on Windows."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value: dict[str, Any] = {}

    def publish(self, value: dict[str, Any]) -> None:
        with self._lock:
            self._value = json.loads(json.dumps(value))

    def read(self) -> dict[str, Any]:
        with self._lock:
            return cast(dict[str, Any], json.loads(json.dumps(self._value)))


class Capture:
    def __init__(
        self,
        store: AuditStore,
        reader: Reader,
        scope: AuditScope,
        *,
        host_id: UUID,
        boot_id: str,
        generation: UUID,
        boot_started_at: datetime | None = None,
    ) -> None:
        self.store, self.reader, self.scope = store, reader, scope
        self.host_id, self.boot_id, self.generation = host_id, boot_id, generation
        self.boot_started_at = boot_started_at
        _, self.cache = store.checkpoint()
        if self.cache.get("boot_id", boot_id) != boot_id:
            store.latch_gap("AUDIT_BOOT_CHANGED")
        if self.cache.get("host_id", str(host_id)) != str(host_id) or self.cache.get(
            "generation", str(generation)
        ) != str(generation):
            store.latch_gap("AUDIT_BOOKMARK_STALE")
        self.selector = Selector(scope, state=self.cache.get("selector"))
        self.pending: tuple[str, str] | None = None

    def step(self) -> str:
        if self.store.gap():
            return "gap"
        try:
            self.pending = self.pending or self.reader.next()
        except EventLogPending:
            return "pending"
        except EventLogError as error:
            if error.code in STALE:
                self.store.latch_gap("AUDIT_BOOKMARK_STALE")
                return "gap"
            raise
        if self.pending is None:
            return "idle"
        xml, bookmark = self.pending
        event = parse_event(
            xml, host_id=self.host_id, boot_id=self.boot_id, generation=self.generation
        )
        if event and event.event_id == 1102:
            self.store.latch_gap("AUDIT_LOG_CLEARED")
            return "gap"
        previous: dict[str, Any] = self.selector.snapshot()
        counters = dict(self.cache.get("counters", {}))
        counters["read"] = counters.get("read", 0) + 1
        accepted = []
        # Historical events across an unknown boot cannot be assigned the current epoch.
        if event and (self.boot_started_at is None or event.occurred_at >= self.boot_started_at):
            accepted = self.selector.process(event)
        counters["accepted"] = counters.get("accepted", 0) + len(accepted)
        counters["filtered"] = counters.get("filtered", 0) + int(not accepted)
        from hashlib import sha256

        cache = {
            "boot_id": self.boot_id,
            "host_id": str(self.host_id),
            "anchor_digest": sha256(xml.encode()).hexdigest(),
            "selector": self.selector.snapshot(),
            "counters": counters,
            "generation": str(self.generation),
            "last_collected_at": datetime.now(UTC).isoformat(),
            "last_record_id": event.record_id if event else self.cache.get("last_record_id"),
            "last_event_at": event.occurred_at.isoformat()
            if event
            else self.cache.get("last_event_at"),
        }
        body = None
        if accepted:
            body = json.dumps(
                {
                    "schema_version": 1,
                    "collector_id": str(self.store.collector_id),
                    "batch_id": uuid4().hex,
                    "sent_at": datetime.now(UTC).isoformat(),
                    "records": [
                        {**e.model_dump(mode="json"), "digest": e.digest()} for e in accepted
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        try:
            self.store.commit(bookmark, cache, body)
        except BaseException:
            self.selector = Selector(self.scope, state=previous)
            raise
        self.cache, self.pending = cache, None
        return "accepted" if accepted else "filtered"


def run_capture(state: Any, config: Any, stop: threading.Event) -> None:
    if config.mode == "deliver" and getattr(config, "readiness_max_objects", 256) != 256:
        with ReadinessWorker(
            native_probe(list(config.roots), config.audit_sids, config.readiness_max_objects)
        ) as verifier:
            _run_capture(state, config, stop, verifier=verifier)
        return
    _run_capture(state, config, stop)


def _run_capture(
    state: Any, config: Any, stop: threading.Event, *, verifier: ReadinessWorker | None = None
) -> None:
    if config.mode == "capture_only":
        _capture(state, config, stop)
        return
    from .delivery import run_delivery

    shared = RuntimeStatus()
    delivery = threading.Thread(
        target=run_delivery,
        args=(state, config, stop),
        kwargs={"status_reader": shared.read},
        name="audit-https",
    )
    delivery.start()
    try:
        _capture(state, config, stop, publish_status=shared.publish, verifier=verifier)
    finally:
        stop.set()
        delivery.join(timeout=25)
        if delivery.is_alive():
            from collectors.windows.errors import SecurityError

            raise SecurityError("AUDIT_DELIVERY_STOP_TIMEOUT")


def _capture(
    state: Any,
    config: Any,
    stop: threading.Event,
    *,
    publish_status: Callable[[dict[str, Any]], None] | None = None,
    verifier: ReadinessWorker | None = None,
) -> None:
    from collectors.windows.errors import SecurityError

    from .configuration import MachineCipher
    from .native import AuditReadFailure, SecurityReader, boot_epoch, no_reparse_ancestry
    from .readiness import readiness
    from .store import AuditStoreError

    store = AuditStore(state.root / "audit.sqlite3", config.collector_id, MachineCipher())
    diagnostics: dict[str, Any] = {"read_errors": 0, "bounds_error": None}

    def status(health: str) -> None:
        _, cache = store.checkpoint()
        value = {
            **store.status(),
            **diagnostics,
            "pid": os.getpid(),
            "health": health,
            "mode": config.mode,
            "counters": cache.get("counters", {}),
            "last_collected_at": cache.get("last_collected_at"),
            "last_accepted_at": store.delivery_state().get("last_accepted_at"),
            "delivery": store.delivery_state(),
        }
        state.write(
            "audit-status.json",
            json.dumps(value, separators=(",", ":")).encode(),
        )
        if publish_status:
            publish_status(value)

    if not config.configured:
        status("NOT_CONFIGURED")
        stop.wait()
        return
    if config.mode == "deliver":
        if verifier is None:
            policy, sacl = readiness(list(config.roots), config.audit_sids)
            diagnostics.update(policy_verified=policy, sacl_verified=sacl)
        else:
            while not stop.is_set():
                diagnostics.update(verifier.snapshot())
                if diagnostics.get("readiness_complete") and not diagnostics.get("readiness_stale"):
                    break
                status("OBSERVE")
                stop.wait(1)
            if stop.is_set():
                return
            policy, sacl = diagnostics["policy_verified"], diagnostics["sacl_verified"]
        if not (policy and sacl):
            status("NOT_CONFIGURED")
            stop.wait()
            return
    bookmark, cache = store.checkpoint()
    boot, boot_started_at = boot_epoch()
    if cache.get("boot_id", boot) != boot:
        store.latch_gap("AUDIT_BOOT_CHANGED")
    if store.gap():
        status("GAP")
        stop.wait()
        return
    try:
        reader = SecurityReader(
            bookmark,
            initial_baseline=config.initial_baseline,
            anchor_digest=cache.get("anchor_digest"),
        )
    except EventLogError as error:
        if error.code in STALE:
            store.latch_gap("AUDIT_BOOKMARK_STALE")
            status("GAP")
            stop.wait()
            return
        raise AuditReadFailure(error) from None
    with reader:
        capture = Capture(
            store,
            reader,
            AuditScope(config.roots, guard=no_reparse_ancestry),
            host_id=config.host_id,
            boot_id=boot,
            generation=config.generation,
            boot_started_at=boot_started_at,
        )
        refresh_at = 0.0
        while not stop.is_set():
            if verifier is not None:
                diagnostics.update(verifier.snapshot())
                if (
                    diagnostics.get("readiness_complete")
                    and not diagnostics.get("readiness_stale")
                    and not (diagnostics["policy_verified"] and diagnostics["sacl_verified"])
                ):
                    store.latch_gap("AUDIT_CONFIGURATION_CHANGED")
            if time.monotonic() >= refresh_at:
                if config.mode == "deliver" and verifier is None:
                    policy, sacl = readiness(list(config.roots), config.audit_sids)
                    diagnostics.update(policy_verified=policy, sacl_verified=sacl)
                    if not (policy and sacl):
                        store.latch_gap("AUDIT_CONFIGURATION_CHANGED")
                try:
                    bounds = reader.bounds()
                    diagnostics.update(bounds)
                    last = capture.cache.get("last_record_id")
                    diagnostics["bookmark_remaining_record_margin"] = (
                        max(0, last - bounds["oldest_record_id"]) if last else None
                    )
                    diagnostics["bounds_error"] = None
                    if last and last < bounds["oldest_record_id"]:
                        store.latch_gap("AUDIT_BOOKMARK_STALE")
                except EventLogError:
                    diagnostics["read_errors"] += 1
                    diagnostics["bounds_error"] = "AUDIT_BOUNDS_FAILED"
                refresh_at = time.monotonic() + 30
            last_event = capture.cache.get("last_event_at")
            diagnostics["bookmark_age_seconds"] = (
                max(0, (datetime.now(UTC) - datetime.fromisoformat(last_event)).total_seconds())
                if last_event
                else None
            )
            health = "OBSERVE"  # Stage A is local capture only; no central acceptance proof.
            for _ in range(64):
                if stop.is_set():
                    break
                try:
                    result = capture.step()
                except AuditStoreError as error:
                    if str(error) != "AUDIT_BACKPRESSURE":
                        raise SecurityError("AUDIT_STORE_FAILED") from None
                    health = "BACKPRESSURE"
                    break
                except EventLogError as error:
                    raise AuditReadFailure(error) from None
                if result == "gap":
                    health = "GAP"
                    break
                if result == "pending":
                    break  # OBSERVE, without advancing the historical coverage timestamp.
                if result == "idle":
                    diagnostics["observed_through_at"] = datetime.now(UTC).isoformat()
                    if verifier is not None:
                        diagnostics.update(verifier.snapshot())
                    if (
                        config.mode == "deliver"
                        and not diagnostics.get("bounds_error")
                        and diagnostics.get("policy_verified")
                        and diagnostics.get("sacl_verified")
                    ):
                        health = "HEALTHY"
                    break
            status(health)
            stop.wait(1 if health != "BACKPRESSURE" else 5)
