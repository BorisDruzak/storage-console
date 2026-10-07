import ctypes
import os
from pathlib import Path
from uuid import uuid4

import pytest

from collectors.windows import security

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows security")


def test_capture_child_state_requires_a_live_parent_lock(tmp_path):
    path = tmp_path / str(uuid4())
    with security.ProtectedState(path, create=True):
        with security.ProtectedState(path, _child=True) as child:
            assert child.root == path
    with pytest.raises(security.SecurityError, match="^STATE_INVALID$"):
        with security.ProtectedState(path, _child=True):
            pass


def test_temporary_cleanup_failure_is_a_fixed_code(tmp_path, monkeypatch):
    original = Path.unlink

    def fail_temporary(path, *args, **kwargs):
        if path.suffix == ".tmp":
            raise OSError("synthetic-private-path")
        return original(path, *args, **kwargs)

    with security.ProtectedState(tmp_path / str(uuid4()), create=True) as state:
        monkeypatch.setattr(Path, "unlink", fail_temporary)
        with pytest.raises(security.SecurityError, match="^STATE_INVALID$"):
            state.write("config.json", b"synthetic")


def test_machine_dpapi_round_trip_and_tamper_fail_without_exposing_plaintext():
    token = b"synthetic-test-token"
    sealed = security.seal(token)
    assert token not in sealed
    assert security.unseal(sealed) == token
    with pytest.raises(security.SecurityError, match="^CREDENTIAL_INVALID$"):
        security.unseal(sealed[:20])


def test_protected_state_creation_reopen_and_exclusive_lock(tmp_path):
    path = tmp_path / str(uuid4())
    with security.ProtectedState(path, create=True) as state:
        state.write("config.json", b"synthetic")
        assert state.read("config.json", 64) == b"synthetic"
        with pytest.raises(security.SecurityError, match="^STATE_BUSY$"):
            with security.ProtectedState(path):
                pass
    with security.ProtectedState(path) as state:
        assert state.read("config.json", 64) == b"synthetic"
        with pytest.raises(security.SecurityError, match="^STATE_INVALID$"):
            state.read("config.json", 2)


def test_existing_unsafe_directory_is_rejected_without_acl_repair(tmp_path):
    path = tmp_path / str(uuid4())
    path.mkdir()
    with pytest.raises(security.SecurityError, match="^UNSAFE_STATE$"):
        with security.ProtectedState(path):
            pass
    assert list(path.iterdir()) == []


def test_pinned_ancestor_cannot_be_renamed_and_junction_is_rejected(tmp_path):
    parent = tmp_path / "parent"
    parent.mkdir()
    with security.ProtectedState(parent / "state", create=True):
        with pytest.raises(PermissionError):
            os.replace(parent, tmp_path / "renamed")
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(security.SecurityError, match="^UNSAFE_STATE$"):
        with security.ProtectedState(link):
            pass


def test_lock_file_cannot_be_replaced_through_public_write_api(tmp_path):
    with security.ProtectedState(tmp_path / str(uuid4()), create=True) as state:
        with pytest.raises(security.SecurityError, match="^STATE_INVALID$"):
            state.write("runtime.lock", b"synthetic")
        with pytest.raises(security.SecurityError, match="^STATE_BUSY$"):
            with security.ProtectedState(state.root):
                pass


def test_private_hardlink_is_rejected(tmp_path):
    path = tmp_path / str(uuid4())
    with security.ProtectedState(path, create=True) as state:
        state.write("config.json", b"synthetic")
        os.link(path / "config.json", path / "alias.json")
        with pytest.raises(security.SecurityError, match="^UNSAFE_STATE$"):
            state.read("config.json", 64)


def test_restricted_windows_token_cannot_read_or_write_private_state(tmp_path):
    api = security._api()
    pointer = ctypes.c_void_p
    pp = ctypes.POINTER(pointer)

    class SidAndAttributes(ctypes.Structure):
        _fields_ = [("sid", pointer), ("attributes", ctypes.c_uint32)]

    api.bind(api.kernel, "GetCurrentProcess", [], pointer)
    api.bind(api.advapi, "OpenProcessToken", [pointer, ctypes.c_uint32, pp], ctypes.c_int32)
    api.bind(api.advapi, "ConvertStringSidToSidW", [ctypes.c_wchar_p, pp], ctypes.c_int32)
    api.bind(
        api.advapi,
        "CreateRestrictedToken",
        [
            pointer,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.POINTER(SidAndAttributes),
            ctypes.c_uint32,
            pointer,
            ctypes.c_uint32,
            pointer,
            pp,
        ],
        ctypes.c_int32,
    )
    api.bind(api.advapi, "ImpersonateLoggedOnUser", [pointer], ctypes.c_int32)
    api.bind(api.advapi, "RevertToSelf", [], ctypes.c_int32)
    original, restricted, sid = pointer(), pointer(), pointer()
    with security.ProtectedState(tmp_path / str(uuid4()), create=True) as state:
        state.write("config.json", b"synthetic")
        try:
            assert api.advapi.OpenProcessToken(
                api.kernel.GetCurrentProcess(), 0xF01FF, ctypes.byref(original)
            )
            assert api.advapi.ConvertStringSidToSidW("S-1-5-32-544", ctypes.byref(sid))
            disabled = SidAndAttributes(sid, 0)
            assert api.advapi.CreateRestrictedToken(
                original, 1, 1, ctypes.byref(disabled), 0, None, 0, None, ctypes.byref(restricted)
            )
            assert api.advapi.ImpersonateLoggedOnUser(restricted)
            try:
                with pytest.raises(PermissionError):
                    (state.root / "config.json").read_bytes()
                with pytest.raises(PermissionError):
                    (state.root / "untrusted").write_bytes(b"synthetic")
            finally:
                assert api.advapi.RevertToSelf()
        finally:
            if sid.value:
                api.kernel.LocalFree(sid)
            if restricted.value:
                api.kernel.CloseHandle(restricted)
            if original.value:
                api.kernel.CloseHandle(original)


@pytest.mark.parametrize("name", ["../other", "other/path", "x:stream", "CON", "x.", ""])
def test_private_names_cannot_escape_state_or_open_devices(tmp_path, name):
    with security.ProtectedState(tmp_path / str(uuid4()), create=True) as state:
        with pytest.raises(security.SecurityError, match="^STATE_INVALID$"):
            state.write(name, b"synthetic")
