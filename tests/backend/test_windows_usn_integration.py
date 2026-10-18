import json
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import replace

import pytest
from sqlalchemy import func, select
from test_windows_runtime_native import installed_python as installed_python
from windows_capture_diagnostics import (
    drain_watermark,
    drained_through,
    emit_activity_snapshot,
    outcome_metadata,
    readonly_observer,
    runtime_snapshot,
    safe_failure,
)

from collectors.common.outbox import OutboxError
from collectors.common.transport import DeliveryOutcome
from collectors.windows.capture_process import CaptureProcess
from collectors.windows.configuration import RuntimeSettings, activate, load, set_usn_enabled
from collectors.windows.inventory import Scope
from collectors.windows.native import _Api
from collectors.windows.runtime import Runtime
from collectors.windows.security import ProtectedState
from packages.shared.models.activity import change_events
from tests.deployment.collector_delivery import serving_ingest

pytestmark = [pytest.mark.skipif(os.name != "nt", reason="Installed native USN runtime"),
              pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Real PostgreSQL")]


def test_native_usn_runtime_changes_https_lost_ack_and_activity_read(
    authenticated_setup, tmp_path, installed_python,
):
    client, engine, collector, token, source = authenticated_setup
    root = tmp_path / "approved"
    root.mkdir()
    sibling = tmp_path / "outside-sibling"
    sibling.mkdir()
    outside_marker = "outside-" + uuid.uuid4().hex
    with serving_ingest(client.app, tmp_path / "tls") as (origin, ca):
        with ProtectedState(tmp_path / "state", create=True) as state:
            activate(state, collector, origin, Scope((str(root),)), token, ca.read_bytes(),
                     RuntimeSettings(poll_seconds=0.05))
            set_usn_enabled(state, True)
            loaded = load(state)
            observer = readonly_observer(loaded)

            class LoseOnce:
                collector_id = collector

                def __init__(self):
                    self.bodies = {}
                    self.all_bodies = []
                    self.lost = False
                    self.duplicate = False
                    self.outcomes = deque(maxlen=24)
                    self.started = time.monotonic()

                def send(self, claim):
                    self.all_bodies.append(claim.body)
                    if claim.domain == "changes":
                        assert self.bodies.setdefault(claim.batch_id, claim.body) == claim.body
                    underlying = outcome = loaded.transport.send(claim)
                    if claim.domain == "changes" and outcome.kind == "accepted":
                        self.duplicate |= outcome.duplicate is True
                        if not self.lost:
                            self.lost = True
                            outcome = DeliveryOutcome("retry", code="NETWORK")
                    self.outcomes.append(outcome_metadata(
                        claim.domain, underlying, outcome,
                        elapsed_ms=round((time.monotonic() - self.started)*1000),
                    ))
                    return outcome

            sender = LoseOnce()
            runtime = Runtime(replace(loaded, transport=sender),
                              capture_factory=lambda: CaptureProcess(
                                  loaded, python=installed_python),
                              usn_factory=lambda: CaptureProcess(loaded, python=installed_python,
                                                                 mode="usn"))
            stop = threading.Event()
            failures = []
            failure_details = []

            def run():
                try:
                    runtime.run(stop)
                except Exception as error:
                    failures.append(type(error).__name__)
                    failure_details.append(safe_failure(error))

            def wait(condition, seconds=40, phase="initial_usn"):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline and not condition():
                    assert not failures, {"phase": phase, **runtime_snapshot(
                        runtime, loaded.outbox.path, failure_details, sender.outcomes,
                    )}
                    time.sleep(0.1)
                ready = condition() and not failures
                if not ready:
                    diagnostic = {"phase": phase, **runtime_snapshot(
                        runtime, loaded.outbox.path, failure_details, sender.outcomes,
                    )}
                    print("NATIVE_RUNTIME_DIAGNOSTIC " + json.dumps(diagnostic), flush=True)
                    assert ready, diagnostic

            thread = threading.Thread(target=run)
            thread.start()
            try:
                wait(lambda: any(e.kind == "usn" and e.code is None for e in runtime.events))
                outside = sibling / (outside_marker + ".txt")
                outside.write_text("synthetic-outside", encoding="utf-8")
                native = _Api()
                with native.opened(str(outside)) as handle:
                    outside_file_id = native.metadata(handle).file_id
                outside.write_text("modified-outside", encoding="utf-8")
                outside = outside.rename(sibling / (outside_marker + "-renamed.txt"))
                outside.unlink()
                parent = root / "До"
                parent.mkdir()
                file = parent / "Отчёт.txt"
                file.write_text("synthetic", encoding="utf-8")
                file.write_text("modified-once", encoding="utf-8")
                file.rename(parent / "После.txt")
                parent = parent.rename(root / "После-папка")
                (parent / "После.txt").unlink()

                def accepted():
                    with engine.connect() as connection:
                        kinds = set(connection.scalars(select(change_events.c.event_type)))
                    return {"CREATE", "WRITE", "RENAME", "DELETE"} <= kinds and sender.duplicate

                wait(accepted, phase="accepted_changes")
                watermark = None

                def closed_batches_acked():
                    nonlocal watermark
                    try:
                        if watermark is None:
                            watermark = drain_watermark(observer)
                        return drained_through(observer, watermark)
                    except OutboxError as error:
                        if error.retryable:
                            return False
                        raise

                wait(closed_batches_acked, phase="closed_batches_acked")
                page = client.get("/api/v1/activity", params={"source_id":str(source)}).json()
                assert page["items"] and {"CREATE", "WRITE", "RENAME", "DELETE"} <= {
                    row["event_type"] for row in page["items"]
                }
                assert all(row["actor"] is None and row["client"] is None for row in page["items"])
                assert all(row["provenance"] == "NTFS_USN" for row in page["items"])
                with engine.connect() as connection:
                    total = connection.scalar(select(func.count()).select_from(change_events))
                    unique = connection.scalar(select(func.count(func.distinct(
                        change_events.c.source_event_id))))
                assert total == unique and sender.lost and sender.duplicate
                # Positive in-scope delivery above prevents a vacuous empty-stream pass.
                # Inspect actual HTTPS request bytes and persisted/read-back rows.
                assert sender.all_bodies
                assert all(outside_marker.encode() not in body for body in sender.all_bodies)
                assert all(outside_file_id.encode() not in body for body in sender.all_bodies)
                assert outside_marker not in str(page)
                assert all(row["file_id"] != outside_file_id for row in page["items"])
                with engine.connect() as connection:
                    persisted = connection.execute(select(change_events)).mappings().all()
                assert persisted and outside_marker not in str(persisted)
                assert all(row["file_id"] != outside_file_id for row in persisted)
                assert any(e.kind == "inventory" and e.code is None for e in runtime.events)
                assert any(e.kind == "heartbeat" for e in runtime.events)
                assert loaded.config.settings.heartbeat_seconds == 30

                def activity_proved():
                    # Data ACKs can precede the first post-bootstrap heartbeat.
                    # Admit the freshness assertions only after the read API has
                    # actually received an eligible continuity proof.
                    response = client.get("/api/v1/activity", params={"source_id": str(source)})
                    page = response.json()
                    return (
                        response.status_code == 200
                        and page.get("quality") == "COMPLETE"
                        and page.get("continuity") == "CONTINUOUS_SINCE_BASELINE"
                        and 0 < int(response.headers["X-Evidence-Valid-For-Ms"]) <= 15000
                    )

                wait(activity_proved, phase="post_bootstrap_activity_proof")
                for _ in range(4):
                    response = client.get("/api/v1/activity", params={"source_id":str(source)})
                    assert (response.json()["quality"] == "COMPLETE"
                            and response.json()["continuity"] == "CONTINUOUS_SINCE_BASELINE"
                            and 0 < int(response.headers["X-Evidence-Valid-For-Ms"]) <= 15000), (
                        emit_activity_snapshot(engine, source, response, runtime,
                                               loaded.outbox.path, failure_details, sender.outcomes)
                    )
                    time.sleep(5)
            finally:
                stop.set()
                thread.join(30)
            assert not thread.is_alive() and not failures
