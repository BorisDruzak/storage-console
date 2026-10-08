import json
import os
import time
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from test_collector_transport import authorities as authorities
from test_windows_runtime_native import installed_python as installed_python

from collectors.windows.capture_process import CaptureProcess
from collectors.windows.configuration import activate, load, set_usn_enabled
from collectors.windows.inventory import Scope
from collectors.windows.security import ProtectedState

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Actual installed Windows USN worker")


def test_installed_owned_usn_worker_reopens_durable_cache_and_queue(
    tmp_path, authorities, installed_python,
):
    root = tmp_path / "approved"
    root.mkdir()
    with ProtectedState(tmp_path / "state", create=True) as state:
        activate(state, uuid4(), "https://localhost", Scope((str(root),)), "a" * 43,
                 (authorities[0] / "ca.pem").read_bytes())
        set_usn_enabled(state, True)
        loaded = load(state)

        def capture():
            worker = CaptureProcess(loaded, python=installed_python, mode="usn")
            try:
                deadline = time.monotonic() + 15
                while (report := worker.poll()) is None and time.monotonic() < deadline:
                    time.sleep(0.05)
                assert report is not None and report.completed and not report.errors
                assert str(root) not in repr(worker._process.args)
                assert "a" * 43 not in repr(worker._process.args)
                return report
            finally:
                worker.stop(0.05)

        assert capture().records == 0
        file = root / "Отчёт.txt"
        file.write_text("synthetic", encoding="utf-8")
        file.write_text("once-modified", encoding="utf-8")
        file = file.rename(root / "После.txt")
        file.unlink()
        assert capture().records >= 4
        assert capture().records == 0
        events = []
        while (claim := loaded.outbox.claim(datetime.now(UTC))) is not None:
            events.extend(json.loads(claim.body)["records"])
            assert loaded.outbox.acknowledge(claim)
        assert {row["event_type"] for row in events} >= {"CREATE", "WRITE", "RENAME", "DELETE"}
        assert len({row["source_event_id"] for row in events}) == len(events)
        assert len({row["file_id"] for row in events}) == 1
