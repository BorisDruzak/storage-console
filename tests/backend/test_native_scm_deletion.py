"""Portable Win32 timelines; never open real SCM or install a service."""
import ctypes
from collections import deque
from types import SimpleNamespace

import pytest

from collectors.windows import _scm_native as native
from collectors.windows.errors import SecurityError
from collectors.windows.scm import ServiceSpec


class Clock:
    now = 0.0

    def sleep(self, seconds):
        self.now += seconds


class Api:
    def __init__(self, probes=(), *, drain=(1,), initial_missing=False):
        self.probes = deque(probes)
        self.drain = deque(drain)
        self.initial_missing = initial_missing
        self.deleted = False
        self.error = 0
        self.active = {}
        self.next_handle = 1
        self.delete_calls = self.stop_calls = self.probe_calls = 0

    def handle(self, kind):
        handle = self.next_handle
        self.next_handle += 1
        self.active[handle] = kind
        return handle

    def OpenSCManagerW(self, machine, database, access):
        return self.handle("manager")

    def OpenServiceW(self, manager, name, access):
        if not self.deleted:
            if self.initial_missing:
                self.error = 1060
                return 0
            return self.handle("delete-service")
        # Holding our original service handle would prevent actual deletion.
        assert "delete-service" not in self.active.values()
        self.probe_calls += 1
        result = self.probes.popleft() if self.probes else "marked"
        if result == "present":
            return self.handle("probe-service")
        self.error = {"marked": 1072, "missing": 1060, "denied": 5, "unknown": 87}[result]
        return 0

    def CloseServiceHandle(self, handle):
        del self.active[handle]
        return 1

    def DeleteService(self, handle):
        assert self.active[handle] == "delete-service" and not self.deleted
        self.deleted = True
        self.delete_calls += 1
        return 1

    def QueryServiceStatusEx(self, handle, level, pointer, size, needed):
        status = self.drain.popleft() if self.drain else 1
        ctypes.cast(pointer, ctypes.POINTER(native.Status)).contents.state = status
        return 1

    def ControlService(self, handle, control, status):
        assert self.active[handle] == "delete-service"
        self.stop_calls += 1
        return 1


def setup(monkeypatch, **kwargs):
    api, clock = Api(**kwargs), Clock()
    monkeypatch.setattr(native, "api", lambda: api)
    monkeypatch.setattr(native, "last_error", lambda: api.error)
    monkeypatch.setattr(native, "time", SimpleNamespace(
        monotonic=lambda: clock.now, sleep=clock.sleep,
    ))
    spec = ServiceSpec(r"C:\synthetic\python.exe", r"C:\synthetic-state")
    return native.NativeBackend(), spec, api, clock


def test_delete_waits_for_actual_absence_after_own_handles_close(monkeypatch):
    backend, spec, api, clock = setup(monkeypatch, probes=("present", "marked", "missing"))
    backend.delete(spec)
    assert api.probe_calls == 3 and api.delete_calls == 1 and api.stop_calls == 0
    assert not api.active and clock.now > 0


@pytest.mark.parametrize("result, code", [("denied", "SERVICE_ACCESS_DENIED"),
                                          ("unknown", "SCM_FAILED")])
def test_probe_error_never_means_removed_and_closes_handles(monkeypatch, result, code):
    backend, spec, api, _ = setup(monkeypatch, probes=(result,))
    with pytest.raises(SecurityError, match=code):
        backend.delete(spec)
    assert api.delete_calls == 1 and not api.active


@pytest.mark.parametrize("probes", [(), ("present",) * 1000])
def test_pending_or_replacement_registration_times_out_without_mutation(monkeypatch, probes):
    backend, spec, api, clock = setup(monkeypatch, probes=probes)
    with pytest.raises(SecurityError, match="SERVICE_REMOVE_TIMEOUT"):
        backend.delete(spec)
    assert 150 <= clock.now < 150.21
    assert api.delete_calls == 1 and api.stop_calls == 0 and not api.active


def test_delete_drain_and_absence_share_one_deadline(monkeypatch):
    backend, spec, api, clock = setup(monkeypatch, drain=(4,) * 700 + (1,))
    with pytest.raises(SecurityError, match="SERVICE_REMOVE_TIMEOUT"):
        backend.delete(spec)
    assert 150 <= clock.now < 150.21
    assert api.delete_calls == api.stop_calls == 1 and not api.active


def test_already_absent_registration_needs_no_delete(monkeypatch):
    backend, spec, api, clock = setup(monkeypatch, initial_missing=True)
    backend.delete(spec)
    assert api.delete_calls == api.probe_calls == 0 and not api.active and clock.now == 0
