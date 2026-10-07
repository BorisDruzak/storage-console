import subprocess
import sys

import pytest

from collectors.windows.capture_process import CaptureProcess


@pytest.mark.parametrize(
    "payload",
    [b"{}\n", b"not-json\n", b"x" * 131073 + b"\n"],
    ids=["missing-fields", "invalid-json", "oversized"],
)
def test_capture_worker_rejects_bad_input_with_summary_only(payload):
    result = subprocess.run(
        [sys.executable, "-m", "collectors.windows._capture_worker"],
        input=payload,
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0 and not result.stderr
    report = CaptureProcess.decode(result.stdout)
    assert report.errors == ("METADATA_INVALID",) and not report.completed
    assert len(result.stdout) <= 4096
