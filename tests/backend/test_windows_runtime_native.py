import ctypes
import os
import shutil
import subprocess
import sys
import sysconfig
import time
from pathlib import Path
from uuid import uuid4

import pytest
from test_collector_transport import authorities as authorities

from collectors.windows.capture_process import CaptureProcess
from collectors.windows.configuration import activate, load
from collectors.windows.inventory import Scope
from collectors.windows.security import ProtectedState, _api

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Installed native Windows worker")


def test_parent_process_crash_closes_its_owned_job_and_kills_child(installed_python):
    script = """
import os,subprocess,sys
from collectors.windows.capture_process import _Job
job=_Job()
child=subprocess.Popen([sys.executable,'-I','-c','import time; time.sleep(60)'],
    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
    creationflags=0x08000000)
job.assign(child)
print(child.pid,flush=True)
os._exit(23)
"""
    crashed = subprocess.run(
        [str(installed_python), "-I", "-c", script], capture_output=True, timeout=10
    )
    assert crashed.returncode == 23 and not crashed.stderr
    assert len(crashed.stdout) <= 32
    pid = int(crashed.stdout)
    api = _api()
    api.bind(
        api.kernel,
        "OpenProcess",
        [ctypes.c_uint32, ctypes.c_int32, ctypes.c_uint32],
        ctypes.c_void_p,
    )
    api.bind(api.kernel, "WaitForSingleObject", [ctypes.c_void_p, ctypes.c_uint32], ctypes.c_uint32)
    handle = api.kernel.OpenProcess(0x100000, False, pid)
    if handle:
        try:
            assert api.kernel.WaitForSingleObject(handle, 2000) == 0
        finally:
            api.kernel.CloseHandle(handle)


@pytest.fixture(scope="module")
def installed_python(tmp_path_factory):
    root = tmp_path_factory.mktemp("installed-capture")
    wheel_dir = root / "wheels"
    source = root / "source"
    source.mkdir()
    for directory in ("apps", "packages", "collectors"):
        shutil.copytree(
            Path.cwd() / directory, source / directory, ignore=shutil.ignore_patterns("__pycache__")
        )
    for name in ("pyproject.toml", "requirements.txt"):
        shutil.copy2(Path.cwd() / name, source / name)
    build = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--quiet",
            "--wheel-dir",
            str(wheel_dir),
            str(source),
        ],
        capture_output=True,
        timeout=120,
    )
    assert build.returncode == 0, "WHEEL_BUILD_FAILED"
    environment = root / "environment"
    created = subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(environment)],
        capture_output=True,
        timeout=30,
    )
    assert created.returncode == 0, "TEST_INTERPRETER_FAILED"
    packages = environment / "Lib" / "site-packages"
    wheel = next(wheel_dir.glob("storage_console-*.whl"))
    install = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--no-deps",
            "--target",
            str(packages),
            str(wheel),
        ],
        capture_output=True,
        timeout=30,
    )
    assert install.returncode == 0, "WHEEL_INSTALL_FAILED"
    # Existing dependency binaries only; the collector itself comes from the new wheel.
    (packages / "test-dependencies.pth").write_text(sysconfig.get_path("purelib"), encoding="utf-8")
    python = environment / "Scripts" / "python.exe"
    probe = subprocess.run(
        [
            str(python),
            "-I",
            "-c",
            "import collectors; from pathlib import Path; "
            "assert Path(collectors.__file__).parent.parent.name=='site-packages'",
        ],
        capture_output=True,
        timeout=10,
    )
    assert probe.returncode == 0 and not probe.stderr, "INSTALLED_ISOLATION_FAILED"
    return python


def test_installed_child_captures_only_owned_tree_with_no_credentials_in_process_args(
    tmp_path,
    authorities,
    installed_python,
):
    data = tmp_path / "data"
    data.mkdir()
    (data / "synthetic.txt").write_bytes(b"synthetic")
    with ProtectedState(tmp_path / "state", create=True) as state:
        activate(
            state,
            uuid4(),
            "https://localhost",
            Scope((str(data),)),
            "a" * 43,
            (authorities[0] / "ca.pem").read_bytes(),
        )
        loaded = load(state)
        capture = CaptureProcess(loaded, python=installed_python)
        try:
            deadline = time.monotonic() + 10
            while (report := capture.poll()) is None and time.monotonic() < deadline:
                time.sleep(0.05)
            assert report is not None and report.completed and not report.errors, (
                capture._process.returncode,
                CaptureProcess.decode(capture._output),
            )
            assert report.records == 3 and report.batches == 1
            assert "a" * 43 not in repr(capture._process.args)
            assert str(data) not in repr(capture._process.args)
            assert loaded.outbox.checkpoint("windows:inventory").revision == 1
        finally:
            capture.stop(0.05)
