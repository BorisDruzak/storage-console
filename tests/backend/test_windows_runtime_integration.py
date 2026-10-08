import json
import os
import sqlite3
import threading
import time
from contextlib import closing

import pytest
from sqlalchemy import func, select
from test_windows_runtime_native import installed_python as installed_python

from collectors.common.outbox import Outbox, OutboxError
from collectors.common.transport import DeliveryOutcome
from collectors.windows.capture_process import CaptureProcess
from collectors.windows.configuration import Loaded, RuntimeSettings, activate, load
from collectors.windows.inventory import Scope
from collectors.windows.runtime import Runtime
from collectors.windows.security import ProtectedState
from packages.shared.models.core import collector_heartbeats, filesystem_objects
from tests.deployment.collector_delivery import serving_ingest

pytestmark = [
    pytest.mark.skipif(os.name != "nt", reason="Installed native foreground runtime"),
    pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"),
]


def test_native_runtime_queue_pressure_and_lost_ack_replay_over_strict_https(
    authenticated_setup,
    tmp_path,
    installed_python,
):
    client, engine, collector, token, _ = authenticated_setup
    data = tmp_path / "data"
    data.mkdir()
    for index in range(10):
        (data / f"synthetic-{index}.txt").write_bytes(b"synthetic")
    with serving_ingest(client.app, tmp_path / "tls") as (origin, ca):
        with ProtectedState(tmp_path / "state", create=True) as state:
            settings = RuntimeSettings(
                heartbeat_seconds=5,
                inventory_seconds=3600,
                poll_seconds=0.05,
                batch_records=2,
                retained_batches=4,
                reserve_batches=1,
                capacity_wait_seconds=20,
            )
            activate(
                state, collector, origin, Scope((str(data),)), token, ca.read_bytes(), settings
            )
            loaded = load(state)
            observer = Outbox(
                loaded.outbox.path, collector, loaded.outbox.limits, read_only=True,
            )
            # A status observer must read while a producer reserves the writer lock.
            with closing(sqlite3.connect(loaded.outbox.path, autocommit=True)) as writer:
                writer.execute("BEGIN IMMEDIATE")
                try:
                    assert observer.status().pending_count == 0
                finally:
                    writer.execute("ROLLBACK")

            class LoseOnce:
                collector_id = collector

                def __init__(self):
                    self.lost = False
                    self.duplicates = 0

                def send(self, claim):
                    outcome = loaded.transport.send(claim)
                    if outcome.kind == "accepted":
                        self.duplicates += int(outcome.duplicate is True)
                        if claim.domain == "inventory" and not self.lost:
                            self.lost = True
                            return DeliveryOutcome("retry", code="NETWORK")
                    return outcome

            sender = LoseOnce()
            runtime = Runtime(
                Loaded(loaded.config, loaded.outbox, sender),
                capture_factory=lambda: CaptureProcess(loaded, python=installed_python),
            )
            stop = threading.Event()
            failures = []

            def run():
                try:
                    runtime.run(stop)
                except Exception as error:
                    failures.append(type(error).__name__)

            thread = threading.Thread(target=run)
            thread.start()
            high_water = 0
            completed = False
            try:
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline and thread.is_alive():
                    try:
                        pending = observer.status().pending_count
                    except OutboxError as error:
                        # Synthetic failure metadata only, never exception text/paths/locals.
                        chain = []
                        current = error
                        seen = set()
                        while current is not None and id(current) not in seen and len(chain) < 4:
                            seen.add(id(current))
                            item = {"type": type(current).__name__}
                            for name in ("errno", "winerror", "sqlite_errorcode"):
                                value = getattr(current, name, None)
                                if type(value) is int:
                                    item[name] = value
                            frames = []
                            trace = current.__traceback__
                            while trace is not None and len(frames) < 16:
                                frames.append({
                                    "function": trace.tb_frame.f_code.co_name,
                                    "line": trace.tb_lineno,
                                })
                                trace = trace.tb_next
                            item["frames"] = frames
                            chain.append(item)
                            current = current.__cause__ or current.__context__
                        print("SYNTHETIC_OUTBOX_FAILURE:" + json.dumps({
                            "busy_seconds": settings.busy_seconds, "chain": chain,
                        }), flush=True)
                        raise
                    high_water = max(high_water, pending)
                    completed = any(
                        event.kind == "inventory" and event.code is None and event.records == 12
                        for event in runtime.events
                    )
                    if completed and pending == 0:
                        break
                    time.sleep(0.05)
                assert completed and not failures, (runtime.events, observer.status())
                assert high_water >= 3 and sender.lost and sender.duplicates == 1
                assert observer.status().pending_count == 0
            finally:
                started = time.monotonic()
                stop.set()
                thread.join(5)
                assert not thread.is_alive() and time.monotonic() - started < 5
            assert not failures
            with engine.connect() as connection:
                assert connection.scalar(select(func.count()).select_from(filesystem_objects)) == 11
                assert (
                    connection.scalar(select(func.count()).select_from(collector_heartbeats)) >= 2
                )
            assert observer.checkpoint("windows:inventory").revision == 6
            assert len(runtime.events) <= 64
