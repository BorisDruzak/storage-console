import json
import os
import sqlite3
import subprocess
import threading
import time
from contextlib import closing
from dataclasses import replace

import pytest
from sqlalchemy import func, select
from test_windows_runtime_native import installed_python as installed_python
from windows_capture_diagnostics import read_trace, trace_program

from collectors.common.outbox import Limits, Outbox, OutboxError
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
    monkeypatch,
):
    client, engine, collector, token, _ = authenticated_setup
    data = tmp_path / "data"
    data.mkdir()
    for index in range(10):
        (data / f"synthetic-{index}.txt").write_bytes(b"synthetic")
    diagnostic_path = tmp_path / "synthetic-capture-codes.json"
    real_popen = subprocess.Popen
    worker_command = [str(installed_python), "-I", "-m", "collectors.windows._capture_worker"]

    def diagnostic_popen(args, **kwargs):
        if args == worker_command:
            args = [str(installed_python), "-I", "-c", trace_program(diagnostic_path)]
        return real_popen(args, **kwargs)

    # Installed modules/stdin/Job/settings are unchanged; only this worker entry
    # is instrumented. Other native tests retain the ordinary -I -m entrypoint.
    monkeypatch.setattr(subprocess, "Popen", diagnostic_popen)
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
                loaded.outbox.path, collector,
                replace(loaded.outbox.limits,
                        busy_timeout_seconds=Limits().busy_timeout_seconds),
                read_only=True,
            )
            # A status observer must read while a producer reserves the writer lock.
            with closing(sqlite3.connect(loaded.outbox.path, autocommit=True)) as writer:
                writer.execute("BEGIN IMMEDIATE")
                try:
                    assert observer.status().pending_count == 0
                finally:
                    writer.execute("ROLLBACK")

            # An independent monitor must also tolerate a bounded exclusive commit.
            locked = threading.Event()
            writer_failures = []

            def commit_writer():
                try:
                    with closing(sqlite3.connect(loaded.outbox.path, autocommit=True)) as writer:
                        writer.execute("BEGIN EXCLUSIVE")
                        locked.set()
                        time.sleep(2)
                        writer.execute("ROLLBACK")
                except Exception as error:
                    writer_failures.append(type(error).__name__)
                    locked.set()

            writer_thread = threading.Thread(target=commit_writer)
            writer_thread.start()
            try:
                assert locked.wait(5) and not writer_failures
                assert observer.status().pending_count == 0
            finally:
                writer_thread.join(5)
                assert not writer_thread.is_alive() and not writer_failures

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
                    # Observe completion first, then the queue: otherwise a producer
                    # can finish between an old empty-queue read and the event read.
                    completed = any(
                        event.kind == "inventory" and event.code is None and event.records == 12
                        for event in runtime.events
                    )
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
                            "busy_seconds": observer.limits.busy_timeout_seconds, "chain": chain,
                        }), flush=True)
                        raise
                    high_water = max(high_water, pending)
                    if completed and pending == 0:
                        break
                    time.sleep(0.05)
                if not completed or failures:
                    print("SYNTHETIC_CAPTURE_FAILURE:" + json.dumps({
                        "trace": read_trace(diagnostic_path),
                        "failures": failures,
                        "events": [{"kind": e.kind, "code": e.code,
                                    "records": e.records, "batches": e.batches}
                                   for e in runtime.events],
                    }), flush=True)
                assert completed and not failures, (runtime.events, observer.status())
                assert high_water >= 3 and sender.lost and sender.duplicates == 1
                # Heartbeats remain live; assert the same post-completion snapshot.
                assert pending == 0
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
