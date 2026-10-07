import os
import subprocess
import sys

import pytest
from test_windows_runtime_native import installed_python as installed_python

from collectors.windows.errors import SecurityError
from collectors.windows.security import ProtectedState

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Installed Windows pilot entrypoint")


@pytest.fixture(scope="module")
def installed_cli(installed_python):
    # Install normally into the venv so console script's interpreter is that venv.
    # The existing capture fixture uses pip --target only for isolated module tests.
    wheel = next((installed_python.parent.parent.parent / "wheels").glob("*.whl"))
    result = subprocess.run(
        [sys.executable, "-m", "pip", "--python", str(installed_python), "install",
         "--quiet", "--no-deps", "--force-reinstall", str(wheel)],
        capture_output=True, timeout=60,
    )
    assert result.returncode == 0, "INSTALLED_CLI_INSTALL_FAILED"
    return installed_python.parent / "storage-collector.exe"


def test_installed_wheel_console_entrypoint_has_four_pilot_commands(installed_cli, tmp_path):
    result = subprocess.run(
        [str(installed_cli), "--help"], capture_output=True, timeout=15, cwd=tmp_path,
        env=dict(os.environ, PYTHONIOENCODING="ascii"),
    )
    assert result.returncode == 0 and not result.stderr
    assert "Операторский Windows pilot" in result.stdout.decode("utf-8")
    for name in (b"activate", b"status", b"inventory-once", b"run"):
        assert name in result.stdout


def test_native_cli_rejects_invalid_scope_and_config_without_echo(installed_cli, tmp_path):
    secret = "synthetic-private-value"
    result = subprocess.run(
        [str(installed_cli), "activate", "--collector-id", secret],
        capture_output=True, timeout=15, cwd=tmp_path,
    )
    assert result.returncode == 2 and secret.encode() not in result.stdout + result.stderr
    result = subprocess.run(
        [str(installed_cli), "status", "--state", str(tmp_path / "absent")],
        capture_output=True, timeout=15, cwd=tmp_path,
    )
    assert result.returncode == 1 and not (tmp_path / "absent").exists()


def test_read_only_protected_state_does_not_recreate_missing_lock(tmp_path):
    root = tmp_path / "state"
    with ProtectedState(root, create=True):
        pass
    (root / "runtime.lock").unlink()
    before = list(root.iterdir())
    with pytest.raises(SecurityError, match="STATE_INVALID"):
        with ProtectedState(root, read_only=True):
            pytest.fail("Missing lock must not be repaired by status")
    assert list(root.iterdir()) == before
