"""Read-only effective policy/SACL checks, no configuration based false healthy."""

import pytest


def test_readiness_requires_effective_policy_and_every_approved_sid_root():
    from collectors.windows_audit.readiness import readiness

    assert readiness(["synthetic-root"], ["sid-a"], policy=lambda: False, sacl=lambda *_: True) == (
        False,
        True,
    )
    assert readiness(
        ["one", "two"], ["sid-a", "sid-b"], policy=lambda: True, sacl=lambda root, _: root == "one"
    ) == (True, False)
    assert readiness(["one"], ["sid-a"], policy=lambda: True, sacl=lambda *_: True) == (True, True)


@pytest.mark.parametrize(
    "flags,mask",
    [
        (0x43, 0x10006),
        (0x41, 0x10006),
        (0x03, 0x10006),
        (0x43, 2),
        (0x47, 0x10006),
        (0x4B, 0x10006),
    ],
)
def test_only_success_write_append_delete_inheritable_aces_cover_sid(flags, mask):
    from collectors.windows_audit.readiness import covered

    assert covered([(2, flags, mask, "sid-a")], ["sid-a"]) == (flags == 0x43 and mask == 0x10006)


def test_unknown_readiness_or_missing_principals_never_means_verified():
    from collectors.windows_audit.readiness import readiness

    assert readiness(["one"], [], policy=lambda: True, sacl=lambda *_: True) == (False, False)

    def denied():
        raise PermissionError

    assert readiness(["one"], ["sid-a"], policy=denied, sacl=lambda *_: True) == (False, False)


@pytest.mark.parametrize("result,error", [(0, 0), (1, 1300)])
def test_privilege_restore_failure_cannot_return_verified(monkeypatch, result, error):
    import ctypes
    from types import SimpleNamespace

    from collectors.windows_audit.readiness import Native

    calls = []
    native = object.__new__(Native)
    native.api = SimpleNamespace(
        OpenProcessToken=lambda *_: 1,
        LookupPrivilegeValueW=lambda *_: 1,
        AdjustTokenPrivileges=lambda *_: calls.append(True) or (1 if len(calls) == 1 else result),
    )
    native.kernel = SimpleNamespace(
        GetCurrentProcess=lambda: 1, CloseHandle=lambda *_: calls.append("closed")
    )
    monkeypatch.setattr(ctypes, "set_last_error", lambda _: None, raising=False)
    monkeypatch.setattr(
        ctypes, "get_last_error", lambda: 0 if len(calls) == 1 else error, raising=False
    )
    with pytest.raises(ValueError, match="AUDIT_READINESS_UNKNOWN"):
        with native.privilege():
            pass
    assert calls[-1] == "closed"


def test_bounded_scope_verifies_descendants_and_rejects_reparse(tmp_path):
    from collectors.windows_audit.readiness import scope_covered

    child = tmp_path / "protected"
    child.mkdir()
    assert not scope_covered(str(tmp_path), ["sid"], lambda path, *_: path != str(child))
    assert scope_covered(str(tmp_path), ["sid"], lambda *_: True)
    assert not scope_covered(str(tmp_path), ["sid"], lambda *_: True, limit=1)
