"""SCM lifecycle contracts, independent of a live Windows machine."""

import ctypes
import importlib
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest

from collectors.windows import cli
from collectors.windows.errors import SecurityError


@pytest.mark.parametrize("action", ["install", "start", "status", "stop", "uninstall"])
def test_service_verbs_parse_without_credentials(action):
    args = cli._parser().parse_args(["service", action])
    assert args.command == "service" and args.action == action
    assert args.state == (cli.DEFAULT_STATE if action == "install" else None)


def test_service_status_does_not_open_runtime_state(monkeypatch):
    monkeypatch.setattr(cli, "_windows", lambda: True)
    def forbidden(*args, **kwargs):
        pytest.fail("SCM status must not acquire the runtime lock")
    monkeypatch.setattr(cli, "ProtectedState", forbidden)
    calls = []
    monkeypatch.setattr(cli, "service_command", lambda args: calls.append(args.action) or 0,
                        raising=False)
    assert cli.main(["service", "status"]) == 0
    assert calls == ["status"]


def test_service_arguments_never_echo_secret(capsys):
    assert cli.main(["service", "install", "--token", "synthetic-private-value"]) == 2
    assert "synthetic-private-value" not in str(capsys.readouterr())


def test_cli_status_discovers_registered_state_without_opening_lock(monkeypatch, capsys):
    from collectors.windows import _scm_native, scm
    spec = scm.ServiceSpec(r"C:\private-python\python.exe", r"C:\custom-state")
    status = scm.ServiceStatus("RUNNING", spec.command, 2, "LocalSystem", 0x10, 123, 0,
                               True, ((1, 10000), (0, 0)), 86400, False)
    class Backend:
        def query(self, requested):
            assert requested.name == spec.name
            return status
    monkeypatch.setattr(_scm_native, "NativeBackend", Backend)
    monkeypatch.setattr(cli.sys, "executable", spec.executable)
    monkeypatch.setattr(cli, "_windows", lambda: True)
    monkeypatch.setattr(cli, "ProtectedState", lambda *args, **kwargs: pytest.fail("SCM only"))
    assert cli.main(["service", "status"]) == 0
    assert "RUNNING" in capsys.readouterr().out
    assert cli.main(["service", "start"]) == 0
    assert "уже работает" in capsys.readouterr().out


@pytest.fixture
def scm():
    return importlib.import_module("collectors.windows.scm")


@pytest.fixture
def spec(scm):
    return scm.ServiceSpec(r"C:\Program Files\Collector\python.exe", r"C:\private-state")


@pytest.fixture
def backend(scm, spec):
    class Backend:
        current = None
        operations = []
        stalled = False

        def query(self, requested):
            assert requested == spec
            return self.current

        def create(self, requested):
            self.operations.append("create")
            self.current = scm.ServiceStatus(
                "STOPPED", spec.command, 2, "LocalSystem", 0x10, 0, 0,
                True, ((1, 10000), (0, 0)), 86400, False,
            )

        def start(self, requested):
            self.operations.append("start")
            self.current = replace(
                self.current, state="START_PENDING" if self.stalled else "RUNNING",
            )

        def stop(self, requested):
            self.operations.append("stop")
            self.current = replace(
                self.current, state="STOP_PENDING" if self.stalled else "STOPPED",
            )

        def delete(self, requested):
            self.operations.append("delete")
            self.current = None

    return Backend()


def manager(scm, spec, backend, **kwargs):
    return scm.ServiceManager(spec, backend, **kwargs)


def test_install_and_start_repeats_do_not_create_second_runtime(scm, spec, backend):
    service = manager(scm, spec, backend)
    assert service.status() is None
    assert service.install().state == "STOPPED"
    service.install()
    assert service.start().state == "RUNNING"
    service.start()
    assert backend.operations == ["create", "start"]


def test_stop_and_uninstall_repeats_only_remove_registration(scm, spec, backend):
    service = manager(scm, spec, backend)
    service.install()
    service.start()
    assert service.stop().state == "STOPPED"
    service.stop()
    service.uninstall()
    service.uninstall()
    assert backend.operations == ["create", "start", "stop", "delete"]


def test_disabled_registration_stays_disabled(scm, spec, backend):
    service = manager(scm, spec, backend)
    service.install()
    backend.current = replace(backend.current, start_type=4)
    assert service.install().start_type == 4
    with pytest.raises(SecurityError, match="SERVICE_DISABLED"):
        service.start()
    assert backend.operations == ["create"]


@pytest.mark.parametrize("changes", [
    {"command": "unrelated.exe"}, {"account": "another-account"}, {"service_type": 0x20},
    {"recovery": ((2, 0),)}, {"failure_command": "unrelated.exe"},
])
def test_incompatible_registration_is_never_managed(scm, spec, backend, changes):
    service = manager(scm, spec, backend)
    service.install()
    backend.current = replace(backend.current, **changes)
    for operation in (service.install, service.start, service.stop, service.uninstall):
        with pytest.raises(SecurityError, match="SERVICE_CONFLICT"):
            operation()
    assert backend.operations == ["create"]


def test_pending_start_wait_is_finite_without_second_start(scm, spec, backend):
    clock = iter([0.0, 2.0])
    service = manager(scm, spec, backend, timeout=1,
                      monotonic=lambda: next(clock), sleep=lambda _: None)
    service.install()
    backend.current = replace(backend.current, state="START_PENDING")
    with pytest.raises(SecurityError, match="SERVICE_START_TIMEOUT"):
        service.start()
    assert backend.operations == ["create"]


def test_stop_timeout_never_deletes_or_kills_service(scm, spec, backend):
    clock = iter([0.0, 2.0])
    service = manager(scm, spec, backend, timeout=1,
                      monotonic=lambda: next(clock), sleep=lambda _: None)
    service.install()
    service.start()
    backend.stalled = True
    with pytest.raises(SecurityError, match="SERVICE_STOP_TIMEOUT"):
        service.uninstall()
    assert backend.operations == ["create", "start", "stop"]


def test_service_binary_and_state_are_absolute_and_unambiguously_quoted(scm, spec):
    assert spec.command == (
        '"C:\\Program Files\\Collector\\python.exe" -I -m collectors.windows.service '
        '--name SosnadminStorageCollector --state "C:\\private-state"'
    )
    for path in ("relative", 'C:\\bad"quote', "C:\\bad\nline", r"\\server\share\python.exe"):
        with pytest.raises(SecurityError, match="SERVICE_PATH_INVALID"):
            scm.ServiceSpec(path, spec.state_path)


def test_registration_discovery_accepts_only_the_emitted_command(scm, spec):
    assert scm.ServiceSpec.registered(spec.executable, spec.command) == spec
    for command in (spec.command + " --extra", spec.command.replace(" -I ", " "),
                    spec.command.replace("--state", "--credential")):
        with pytest.raises(SecurityError, match="SERVICE_CONFLICT"):
            scm.ServiceSpec.registered(spec.executable, command)


def test_host_only_reports_running_after_config_loaded(monkeypatch):
    service = importlib.import_module("collectors.windows.service")
    order = []
    def run(stop):
        order.append("runtime")
        host.control(1)
        assert stop.is_set()
    host = service.RuntimeHost(
        lambda stop: order.append("loaded") or run,
        lambda state, code=0: order.append(state),
        lambda code: order.append(code),
    )
    assert host.run() == 0
    assert order == ["START_PENDING", "loaded", "RUNNING", "runtime", "STOP_PENDING", "STOPPED"]


@pytest.mark.parametrize("control", [1, 5])
def test_stop_and_shutdown_signal_runtime_without_waiting(control):
    service = importlib.import_module("collectors.windows.service")
    started = threading.Event()
    host = service.RuntimeHost(lambda stop: lambda event: (started.set(), event.wait(2)),
                               lambda *args: None, lambda code: None)
    worker = threading.Thread(target=host.run)
    worker.start()
    assert started.wait(1)
    assert host.control(control) == 0
    worker.join(1)
    assert not worker.is_alive() and host.requested_stop.is_set()


def test_runtime_return_is_not_mistaken_for_operator_stop():
    service = importlib.import_module("collectors.windows.service")
    states, failures = [], []
    # Runtime's finally sets its own event even after an internal failure.
    host = service.RuntimeHost(lambda stop: lambda event: event.set(),
                               lambda *args: states.append(args), failures.append)
    assert host.run() == 1
    assert failures == ["RUNTIME_FAILED"]
    assert ("STOPPED", 0) not in states


def test_startup_security_failure_reports_error_without_running():
    service = importlib.import_module("collectors.windows.service")
    states, failures = [], []
    def fail(stop):
        raise SecurityError("STATE_BUSY")
    host = service.RuntimeHost(fail, lambda *args: states.append(args), failures.append)
    assert host.run() == 1
    assert states == [("START_PENDING",), ("STOPPED", 1066)]
    assert failures == ["STATE_BUSY"]


def test_crash_stopped_is_not_reported_as_operator_stopped(scm, spec, backend):
    service = manager(scm, spec, backend)
    service.install()
    backend.current = replace(backend.current, exit_code=1067)
    with pytest.raises(SecurityError, match="SERVICE_RECOVERY_PENDING"):
        service.stop()
    assert backend.operations == ["create"]


def test_uninstall_removes_failed_registration_without_claiming_stop(scm, spec, backend):
    service = manager(scm, spec, backend)
    service.install()
    backend.current = replace(backend.current, exit_code=1067)
    service.uninstall()
    assert backend.operations == ["create", "delete"]
    assert service.status() is None


def test_source_checkout_is_not_accepted_as_local_system_installation(monkeypatch, tmp_path):
    from collectors.windows import service_installation
    monkeypatch.setattr(service_installation.sys, "prefix", str(tmp_path / "environment"))
    monkeypatch.setattr(service_installation.sys, "base_prefix", str(tmp_path / "python"))
    with pytest.raises(SecurityError, match="SERVICE_WHEEL_REQUIRED"):
        service_installation.validate_installation()


def test_external_pth_dependency_must_also_be_protected(monkeypatch, tmp_path):
    from collectors.windows import service_installation as installation
    prefix, dependency = tmp_path / "python", tmp_path / "external-dependency"
    prefix.mkdir()
    dependency.mkdir()
    monkeypatch.setattr(installation.sys, "prefix", str(prefix))
    monkeypatch.setattr(installation.sys, "base_prefix", str(prefix))
    monkeypatch.setattr(installation.sys, "path", [str(prefix), str(dependency)])
    monkeypatch.setattr(installation.importlib.util, "find_spec", lambda name: SimpleNamespace(
        origin=str(prefix / "collectors/windows/service.py"),
    ))
    def acl(path, **kwargs):
        if path == dependency:
            raise SecurityError("UNSAFE_SERVICE_INSTALLATION")
    monkeypatch.setattr(installation, "_safe_acl", acl)
    with pytest.raises(SecurityError, match="UNSAFE_SERVICE_INSTALLATION"):
        installation.validate_installation()


def test_base_interpreter_is_checked_after_nested_venv_ancestors(monkeypatch, tmp_path):
    from collectors.windows import service_installation as installation
    base = tmp_path / "python"
    prefix = base / "venv"
    prefix.mkdir(parents=True)
    unsafe = base / "stdlib.dll"
    unsafe.write_bytes(b"synthetic")
    monkeypatch.setattr(installation.sys, "prefix", str(prefix))
    monkeypatch.setattr(installation.sys, "base_prefix", str(base))
    monkeypatch.setattr(installation.sys, "path", [str(prefix), str(base)])
    monkeypatch.setattr(installation.importlib.util, "find_spec", lambda name: SimpleNamespace(
        origin=str(prefix / "collectors/windows/service.py"),
    ))
    def acl(path, **kwargs):
        if path == unsafe:
            raise SecurityError("UNSAFE_SERVICE_INSTALLATION")
    monkeypatch.setattr(installation, "_safe_acl", acl)
    with pytest.raises(SecurityError, match="UNSAFE_SERVICE_INSTALLATION"):
        installation.validate_installation()


@pytest.mark.parametrize("panic", [False, True])
def test_dispatcher_failure_exits_without_leaking_callback(panic, monkeypatch, capsys):
    from collectors.windows import _scm_native, service
    exits = []
    class Host:
        def __init__(self, prepare, report, log):
            self.report = report
        def run(self):
            if panic:
                raise BaseException("synthetic-private-callback-value")
            self.report("STOPPED", 1066)
            return 1  # Runtime cleanup timed out with a non-daemon delivery thread.
    class API:
        def RegisterServiceCtrlHandlerExW(self, *args):
            return 1
        def SetServiceStatus(self, *args):
            return 1
        def RegisterEventSourceW(self, *args):
            return 0
        def StartServiceCtrlDispatcherW(self, entries):
            callback = ctypes.CFUNCTYPE(None, ctypes.c_uint32, ctypes.c_void_p)(entries[0].main)
            callback(0, None)
            return 1
    monkeypatch.setattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE, raising=False)
    monkeypatch.setattr(_scm_native, "api", API)
    monkeypatch.setattr(service, "RuntimeHost", Host)
    monkeypatch.setattr(service.os, "_exit", exits.append)
    spec = _scm_native.ServiceSpec(r"C:\private-python\python.exe", r"C:\private-state")
    assert service.dispatch(spec) == 1
    assert exits == [1]
    assert "synthetic-private-callback-value" not in capsys.readouterr().err
