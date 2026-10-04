import os
import subprocess
from uuid import uuid4

import pytest

from collectors.windows.errors import SecurityError
from collectors.windows.security import ProtectedState

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows DACL")


def test_world_readable_private_file_is_rejected_without_changing_its_acl(tmp_path):
    with ProtectedState(tmp_path / str(uuid4()), create=True) as state:
        state.write("config.json", b"synthetic")
        changed = subprocess.run(
            ["icacls.exe", str(state.root / "config.json"), "/grant", "*S-1-1-0:(R)"],
            capture_output=True,
            timeout=5,
        )
        assert changed.returncode == 0
        with pytest.raises(SecurityError, match="^UNSAFE_STATE$"):
            state.read("config.json", 64)
        # Failure does not delete or rewrite the evidence.
        assert (state.root / "config.json").read_bytes() == b"synthetic"


def test_reparse_private_file_is_rejected(tmp_path):
    with ProtectedState(tmp_path / str(uuid4()), create=True) as state:
        target = tmp_path / "target"
        target.write_bytes(b"synthetic")
        (state.root / "config.json").symlink_to(target)
        with pytest.raises(SecurityError, match="^UNSAFE_STATE$"):
            state.read("config.json", 64)
