"""Independent bounded collection and durable push; never stop Security on LDAP failure."""

import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from collectors.common.transport import Transport
from packages.contracts.directory import DirectoryPage, DirectoryUser, Failure, normalized_ip

from .directory_native import DirectoryError, DirectorySettings, NativeDirectory
from .directory_resolver import ClientResolver
from .directory_store import DirectoryStore, DirectoryStoreError

MAX_SNAPSHOT_BYTES = 32 * 1024**2
TERMINAL_ERROR_RESERVE = 4096


class Native(Protocol):
    def users(self, stop: threading.Event) -> Iterator[dict[str, Any]]: ...


class DirectoryWorker:
    def __init__(
        self,
        store: DirectoryStore,
        settings: DirectorySettings,
        native: Native,
        *,
        targets: Callable[[], list[str]],
    ) -> None:
        self.store, self.settings, self.native, self.targets = store, settings, native, targets

    def collect(self, stop: threading.Event, *, now: datetime | None = None) -> None:
        at, identity = now or datetime.now(UTC), uuid4()
        page_index = count = encoded_bytes = 0
        finished = False
        try:
            for frame in self.native.users(stop):
                if stop.is_set():
                    raise DirectoryError("DIRECTORY_STOPPED")
                if frame["page_index"] != page_index:
                    raise DirectoryError("DIRECTORY_PROTOCOL_INVALID")
                records = [DirectoryUser.model_validate(value) for value in frame["records"]]
                candidate_count = count + len(records)
                if candidate_count > self.settings.max_objects:
                    raise DirectoryError("DIRECTORY_LIMIT")
                complete = frame["finished"]
                if page_index == 511 and not complete:
                    raise DirectoryError("DIRECTORY_LIMIT")
                value = DirectoryPage(
                    collector_id=self.store.collector_id,
                    batch_id=uuid4().hex,
                    snapshot_id=identity,
                    schema_version=1,
                    sent_at=max(datetime.now(UTC), at),
                    observed_at=at,
                    scope=self.settings.scope,
                    page_index=page_index,
                    records=records,
                    finished=complete,
                    complete=complete,
                    total_records=candidate_count if complete else None,
                )
                candidate_bytes = encoded_bytes + len(value.model_dump_json().encode())
                ceiling = MAX_SNAPSHOT_BYTES - (0 if complete else TERMINAL_ERROR_RESERVE)
                if candidate_bytes > ceiling:
                    raise DirectoryError("DIRECTORY_LIMIT")
                self.store.enqueue("directory", value)
                encoded_bytes = candidate_bytes
                count = candidate_count
                finished = complete
                page_index += 1
            if not finished:
                raise DirectoryError("DIRECTORY_PROTOCOL_INVALID")
        except Exception as error:
            code: Failure = (
                "DIRECTORY_STOPPED"
                if stop.is_set()
                else "DIRECTORY_LIMIT"
                if isinstance(error, DirectoryStoreError)
                or isinstance(error, DirectoryError)
                and error.code in {"DIRECTORY_LIMIT", "LOOKUP_LIMIT"}
                else "LDAP_UNAVAILABLE"
            )
            failed = DirectoryPage(
                collector_id=self.store.collector_id,
                batch_id=uuid4().hex,
                snapshot_id=identity,
                schema_version=1,
                sent_at=max(datetime.now(UTC), at),
                observed_at=at,
                scope=self.settings.scope,
                page_index=page_index,
                records=[],
                finished=True,
                complete=False,
                total_records=count,
                error_code=code,
            )
            self.store.enqueue("directory", failed, terminal_error=True)
            self.store.save_state(self.store.delivery_state() | {"collection_error": code})
        else:
            self.store.save_state(self.store.delivery_state() | {"collection_error": None})


def run_directory(state: Any, config: Any, stop: threading.Event) -> None:
    from .configuration import MachineCipher
    from .directory_targets import read_targets

    settings = config.directory
    if settings is None:
        return
    cipher = MachineCipher()
    path = state.root / "directory.sqlite3"
    if not path.exists():
        state.create_file("directory.sqlite3")
    store = DirectoryStore(path, config.collector_id, cipher)
    native = NativeDirectory(settings, stop=stop)
    worker = DirectoryWorker(
        store, settings, native, targets=lambda: read_targets(state.root / "audit.sqlite3", cipher)
    )
    resolver = ClientResolver(config.collector_id, settings.scope, native)
    sender = Transport(
        config.origin,
        Path(config.ca_file),
        config.token.get_secret_value(),
        collector_id=config.collector_id,
        timeout=10,
    )
    next_collect = 0.0
    target_cursor = 0
    while not stop.is_set():
        try:
            delivery = store.delivery_state()
            claim = store.peek()
            if claim is not None:
                if (
                    not delivery.get("suspended")
                    and not delivery.get("quarantine")
                    and delivery.get("next_attempt", 0) <= time.time()
                ):
                    store.record_outcome(sender.send(claim), now=time.time())
            elif time.monotonic() >= next_collect:
                worker.collect(stop)
                next_collect = time.monotonic() + settings.refresh_seconds
            elif not delivery.get("suspended") and not delivery.get("quarantine"):
                targets = worker.targets()
                if targets:
                    target = targets[target_cursor % len(targets)]
                    target_cursor += 1
                    observation = resolver.resolve(target)
                    key = normalized_ip(target)
                    queued = delivery.get("last_queued", {})
                    if queued.get(key) != observation.batch_id:
                        store.enqueue("client-names", observation)
                        queued[key] = observation.batch_id
                        while len(queued) > 512:
                            queued.pop(next(iter(queued)))
                        store.save_state(delivery | {"last_queued": queued})
        except Exception:
            # Fixed metadata only; LDAP/store errors must not stop the Security thread.
            try:
                store.save_state(store.delivery_state() | {"collection_error": "LDAP_UNAVAILABLE"})
            except Exception:
                pass
        stop.wait(1)
