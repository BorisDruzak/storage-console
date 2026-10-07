import json
import os
import subprocess
import sys
import time
from uuid import uuid4

import pytest

from collectors.common.outbox import Outbox
from collectors.windows.capture_process import CaptureProcess
from collectors.windows.configuration import Loaded, PrivateConfig, RuntimeSettings
from collectors.windows.producer import CaptureReport


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows owned job")
def test_closing_owned_job_terminates_its_blocked_child(tmp_path, monkeypatch):
    original = subprocess.Popen
    children = []

    def blocked(*args, **kwargs):
        child = original(
            [sys.executable, "-I", "-c", "import time; time.sleep(60)"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000,
        )
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", blocked)
    capture = CaptureProcess(prepared(tmp_path))
    try:
        assert children[0].poll() is None
        capture._job.close()
        children[0].wait(timeout=2)
        assert capture.poll().errors == ("NATIVE_FAILED",)
    finally:
        capture.stop(0.05)


def prepared(tmp_path):
    box = Outbox(tmp_path / "private" / "queue", uuid4())
    config = PrivateConfig(
        collector_id=box.collector_id,
        credential_version=uuid4(),
        origin="https://localhost",
        roots=("C:\\synthetic",),
        encrypted_token="synthetic-private-token",
        settings=RuntimeSettings(),
    )
    return Loaded(config, box, None)


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows owned subprocess")
def test_owned_child_stop_kills_and_reaps_only_its_process(tmp_path, monkeypatch):
    original = subprocess.Popen
    children = []
    payloads = []

    def blocked(*args, **kwargs):
        child = original(
            [sys.executable, "-I", "-c", "import time; time.sleep(60)"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000,
        )
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", blocked)
    capture = CaptureProcess(prepared(tmp_path))
    assert capture.poll() is None
    started = time.monotonic()
    report = capture.stop(0.05)
    assert time.monotonic() - started < 3
    assert children[0].poll() is not None
    assert report.completed is False and report.errors == ("STOPPED",)
    assert capture.stop(0.05) == report
    assert not payloads


@pytest.mark.parametrize(
    "value",
    [
        {"records": True, "batches": 0, "completed": False, "errors": []},
        {"records": 1, "batches": 1, "completed": True, "errors": ["private-value"]},
        {"records": 1, "batches": 1, "completed": True, "errors": [], "root": "synthetic"},
    ],
)
def test_untrusted_child_report_cannot_emit_values_or_claim_complete(value):
    assert CaptureProcess.decode(json.dumps(value).encode()).errors == ("NATIVE_FAILED",)


def test_valid_child_report_only_contains_bounded_counts_and_fixed_codes():
    report = CaptureReport(2, 1, False, ("ACCESS_DENIED",))
    assert (
        CaptureProcess.decode(
            b'{"records":2,"batches":1,"completed":false,"errors":["ACCESS_DENIED"]}'
        )
        == report
    )
