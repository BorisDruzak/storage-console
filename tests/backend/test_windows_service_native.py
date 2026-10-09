"""Owned synthetic services only; real installed wheel, SCM and LocalSystem."""

import ctypes
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import sysconfig
import tarfile
import time
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_collector_transport import authorities as authorities
from test_collector_transport import servers as servers
from test_windows_runtime_native import installed_python as installed_python

from collectors.common.outbox import Outbox
from collectors.windows._scm_native import Action, D, NativeBackend, P, Recovery, Status, check
from collectors.windows.configuration import RuntimeSettings, activate
from collectors.windows.errors import SecurityError
from collectors.windows.inventory import Scope
from collectors.windows.scm import SERVICE_NAME, ServiceManager, ServiceSpec
from collectors.windows.security import ProtectedState, _api
from collectors.windows.service_installation import _safe_acl
from packages.shared.models.core import collector_heartbeats, filesystem_objects
from tests.deployment.collector_delivery import serving_ingest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows SCM acceptance")


def eventually(predicate, seconds=30, diagnostics=None):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    detail = ""
    if diagnostics is not None:
        try:
            detail = ":" + json.dumps(diagnostics())
        except Exception as error:
            detail = ":" + json.dumps({"diagnostic_error": type(error).__name__})
    pytest.fail("SERVICE_ACCEPTANCE_TIMEOUT" + detail)


@pytest.fixture
def service(installed_python, tmp_path):
    # CI runs on an elevated disposable Windows runner. Missing privileges is a
    # failed acceptance, never a silent skip for the newly introduced checks.
    shell = vars(ctypes)["WinDLL"]("shell32")
    assert shell.IsUserAnAdmin(), "SCM_ACCEPTANCE_REQUIRES_ADMIN"
    spec = ServiceSpec(str(installed_python), str(tmp_path / "state"),
                       SERVICE_NAME + "Test" + uuid4().hex)
    backend = NativeBackend()
    manager = ServiceManager(spec, backend, timeout=130)
    manager.install()
    try:
        yield manager
    finally:
        # Cleanup only our unique registration, including a queued crash restart.
        with backend._service(spec, 0x10000 | 0x20 | 4) as handle:
            if handle is not None:
                status = Status()
                backend.api.ControlService(handle, 1, ctypes.byref(status))
                check(backend.api.DeleteService(handle))


def principal(pid):
    api = _api()
    api.bind(api.kernel, "OpenProcess", [D, D, D], P)
    api.bind(api.advapi, "OpenProcessToken", [P, D, ctypes.POINTER(P)], D)
    api.bind(api.advapi, "GetTokenInformation", [P, D, P, D, ctypes.POINTER(D)], D)
    process = api.kernel.OpenProcess(0x1000, False, pid)
    check(process)
    token, needed = P(), D()
    try:
        check(api.advapi.OpenProcessToken(process, 8, ctypes.byref(token)))
        buffer = ctypes.create_string_buffer(4096)
        check(api.advapi.GetTokenInformation(token, 1, buffer, len(buffer), ctypes.byref(needed)))
        user = P.from_buffer(buffer)
        text = P()
        check(api.advapi.ConvertSidToStringSidW(user, ctypes.byref(text)))
        try:
            return ctypes.wstring_at(text.value)
        finally:
            api.kernel.LocalFree(text)
    finally:
        if token.value:
            api.kernel.CloseHandle(token)
        api.kernel.CloseHandle(process)


def test_native_install_migrates_the_legacy_recovery_policy(service):
    backend = service.backend
    with backend._service(service.spec, 2 | 0x10) as handle:
        actions = (Action * 2)(Action(1, 10000), Action(0, 0))
        legacy = Recovery(86400, None, None, 2, actions)
        check(backend.api.ChangeServiceConfig2W(handle, 2, ctypes.byref(legacy)))
    assert service.status().recovery == ((1, 10000), (0, 0))
    result = service.install()
    assert result.recovery == ((1, 10000), (1, 30000), (1, 60000))
    assert result.state == "STOPPED"


def crash(service):
    status = service.status()
    assert status.state == "RUNNING" and status.pid > 0
    api = _api()
    api.bind(api.kernel, "OpenProcess", [D, D, D], P)
    api.bind(api.kernel, "TerminateProcess", [P, D], D)
    handle = api.kernel.OpenProcess(1, False, status.pid)
    check(handle)
    try:
        assert service.status().pid == status.pid
        check(api.kernel.TerminateProcess(handle, 23))
    finally:
        api.kernel.CloseHandle(handle)
    return status.pid


def activate_fixture(service, tmp_path, origin, ca, *, settings=None):
    data = tmp_path / "data"
    data.mkdir()
    (data / "synthetic.txt").write_bytes(b"synthetic")
    identity = uuid4()
    with ProtectedState(tmp_path / "state", create=True) as state:
        config = activate(
            state, identity, origin, Scope((str(data),)), "a" * 43, ca.read_bytes(),
            settings or RuntimeSettings(
                heartbeat_seconds=5, inventory_seconds=3600, poll_seconds=0.05,
            ),
        )
    return config, Outbox(tmp_path / "state" / "outbox.sqlite3", identity, read_only=True)


def test_actual_scm_registration_is_bounded_idempotent_and_disabled_is_preserved(service):
    before = service.status()
    assert before.state == "STOPPED" and before.account == "LocalSystem"
    assert before.delayed and before.recovery == ((1, 10000), (1, 30000), (1, 60000))
    assert not before.recover_non_crash and before.recovery_reset_seconds == 86400
    assert service.install() == before
    backend = service.backend
    function = backend.api.ChangeServiceConfigW
    function.argtypes = [P, D, D, D, ctypes.c_wchar_p, ctypes.c_wchar_p, P,
                         ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p]
    function.restype = D
    with backend._service(service.spec, 2) as handle:
        check(function(handle, 0xFFFFFFFF, 4, 0xFFFFFFFF,
                       None, None, None, None, None, None, None))
    assert service.install().start_type == 4
    with pytest.raises(SecurityError, match="SERVICE_DISABLED"):
        service.start()


def test_scm_start_fails_closed_on_foreground_lock(service, tmp_path, authorities, servers):
    _, origin = servers()
    activate_fixture(service, tmp_path, origin, authorities[0] / "ca.pem")
    with ProtectedState(tmp_path / "state"):
        with pytest.raises(SecurityError, match="SERVICE_START_FAILED"):
            service.start()
        assert service.status().state == "STOPPED"
        assert service.status().exit_code == 1066


def test_binary_acl_validation_is_read_only_and_rejects_user_writable_fixture(tmp_path):
    root = tmp_path / "protected-new-fixture"
    with ProtectedState(root, create=True):
        pass
    _safe_acl(root)
    before = root.stat()
    with pytest.raises(SecurityError, match="UNSAFE_SERVICE_INSTALLATION"):
        _safe_acl(tmp_path)
    assert root.stat() == before


def test_local_system_dpapi_tls_outage_stop_start_and_auth_suspension(
    service, tmp_path, authorities, servers,
):
    server, origin = servers()
    server.reply = {"status": 503}
    # This lifecycle/replay test uses the production-default heartbeat cadence.
    # Five-second pressure remains covered by the dedicated runtime stress test.
    config, box = activate_fixture(
        service, tmp_path, origin, authorities[0] / "ca.pem",
        settings=RuntimeSettings(inventory_seconds=3600, poll_seconds=0.05),
    )
    status = service.start()
    assert principal(status.pid) == "S-1-5-18"
    assert service.start().pid == status.pid
    assert service.install().pid == status.pid
    eventually(lambda: len(server.requests) >= 3)
    assert box.status().pending_count > 0 and not box.status().quarantined_count
    assert box.credential_binding() == config.credential_version
    # Strict TLS and DPAPI succeeded in the actual service account, not a mock.
    assert all(request["authorization"] == "Bearer " + "a" * 43 for request in server.requests)
    started = time.monotonic()
    assert service.stop().state == "STOPPED"
    assert time.monotonic() - started < 35
    sequence = box.checkpoint("windows:heartbeat").value["sequence"]
    inventory = box.checkpoint("windows:inventory")
    assert inventory.value["completed"]
    pending = box.status().pending_count
    config_bytes = (tmp_path / "state" / "config.json").read_bytes()

    def replay_snapshot():
        # Read only synthetic scheduling metadata; never bodies, tokens or paths.
        now = time.time()
        database = tmp_path / "state" / "outbox.sqlite3"
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
            rows = connection.execute(
                "SELECT domain,stream,attempts,error_code,next_attempt,lease_until "
                "FROM batches ORDER BY seq LIMIT 65"
            ).fetchall()
        current = service.status()
        return {
            "pending": box.status().pending_count,
            "quarantine": box.status().quarantined_count,
            "auth_suspended": box.auth_suspended(),
            "heartbeat_sequence": box.checkpoint("windows:heartbeat").value["sequence"],
            "requests": len(server.requests),
            "service_state": current.state,
            "batches": [{
                "domain": domain, "stream": stream, "attempts": attempts, "code": code,
                "retry_wait": round(max(0, retry - now), 3),
                "lease_wait": round(max(0, (lease or 0) - now), 3),
            } for domain, stream, attempts, code, retry, lease in rows[:64]],
            "rows_truncated": len(rows) > 64,
        }

    def snapshot():
        try:
            return replay_snapshot()
        except Exception as error:
            return {"snapshot_error": type(error).__name__}

    stopped = snapshot()
    service.stop()
    # A successful receipt takes longer than five seconds, but remains inside
    # the transport's whole deadline; replay must still drain within 105 seconds.
    server.reply = {"drip": True}
    service.start()
    deadline = time.monotonic() + box.limits.lease_seconds + config.settings.transport_seconds + 30
    restarted = snapshot()
    eventually(lambda: box.status().pending_count == 0 and (
        box.checkpoint("windows:heartbeat").value["sequence"] > sequence
    ), seconds=max(0, deadline - time.monotonic()),
        diagnostics=lambda: {
            "stopped": stopped, "restarted": restarted, "timeout": snapshot(),
        })
    assert pending > 0 and box.credential_binding() == config.credential_version
    assert not box.status().quarantined_count
    assert (tmp_path / "state" / "config.json").read_bytes() == config_bytes
    assert any(json.loads(r["body"])["collector_id"] == str(config.collector_id)
               for r in server.requests)
    server.reply = {"status": 401}
    eventually(box.auth_suspended, seconds=(
        config.settings.heartbeat_seconds + config.settings.transport_seconds + 1
    ))
    service.stop()
    generation = box.credential_generation()
    server.reply = {}
    requests = len(server.requests)
    service.start()
    time.sleep(7)
    assert box.auth_suspended() and box.credential_generation() == generation
    assert len(server.requests) == requests  # No implicit credential reactivation.
    assert service.status().state == "RUNNING"  # Process state is not source health.
    service.stop()


def test_second_crash_also_recovers_with_backoff(service, tmp_path, authorities, servers):
    _, origin = servers()
    config, box = activate_fixture(service, tmp_path, origin, authorities[0] / "ca.pem")
    service.start()
    eventually(lambda: box.checkpoint("windows:heartbeat").revision > 0)
    old_pid = crash(service)
    eventually(lambda: (current := service.status()).state == "RUNNING" and
               current.pid != old_pid, seconds=25)
    assert box.credential_binding() == config.credential_version
    second_pid = crash(service)
    eventually(lambda: service.status().state == "STOPPED")
    time.sleep(15)
    assert service.status().state == "STOPPED"
    eventually(lambda: (current := service.status()).state == "RUNNING" and
               current.pid != second_pid, seconds=30)
    assert box.credential_binding() == config.credential_version
    service.stop()
    service.uninstall()
    assert service.status() is None


def test_uninstall_cancels_queued_recovery_and_keeps_state(service, tmp_path, authorities, servers):
    _, origin = servers()
    config, box = activate_fixture(service, tmp_path, origin, authorities[0] / "ca.pem")
    service.start()
    crash(service)
    eventually(lambda: service.status().state == "STOPPED")
    service.uninstall()
    time.sleep(12)
    assert service.status() is None
    assert box.credential_binding() == config.credential_version
    assert (tmp_path / "state" / "config.json").exists()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required")
def test_native_service_reuses_real_https_postgres_ingest(service, tmp_path, authenticated_setup):
    client, engine, collector, token, _ = authenticated_setup
    data = tmp_path / "data"
    data.mkdir()
    (data / "synthetic.txt").write_bytes(b"synthetic")
    with serving_ingest(client.app, tmp_path / "tls") as (origin, ca):
        with ProtectedState(tmp_path / "state", create=True) as state:
            config = activate(
                state, collector, origin, Scope((str(data),)), token, ca.read_bytes(),
                RuntimeSettings(heartbeat_seconds=5, inventory_seconds=3600, poll_seconds=0.05),
            )
        box = Outbox(tmp_path / "state" / "outbox.sqlite3", collector, read_only=True)
        try:
            status = service.start()
            assert principal(status.pid) == "S-1-5-18"
            def persisted():
                with engine.connect() as connection:
                    return connection.scalar(select(func.count()).select_from(
                        collector_heartbeats,
                    )) >= 2 and connection.scalar(select(func.count()).select_from(
                        filesystem_objects,
                    )) == 2 and box.status().pending_count == 0
            eventually(persisted, seconds=90)
            assert not box.status().quarantined_count
            before = box.checkpoint("windows:heartbeat").value["sequence"]
            service.stop()
            assert box.credential_binding() == config.credential_version
            service.start()
            eventually(lambda: box.checkpoint("windows:heartbeat").value["sequence"] > before)
            assert box.credential_binding() == config.credential_version
        finally:
            service.stop()


@pytest.fixture(scope="module")
def protected_installed_python(installed_python):
    # New owned fixture objects receive private security attributes at creation;
    # no ACL of an existing interpreter, directory or service is changed.
    root = Path(os.environ["ProgramFiles"]) / (SERVICE_NAME + "Test" + uuid4().hex)
    assert root.parent == Path(os.environ["ProgramFiles"]) and not root.exists()
    def copy(source, target, state, *, bare=False, wheel=False):
        if bare and source.parent == Path(sys.base_prefix) and source.name in {
            "python3.exe", f"python{sys.version_info.major}.{sys.version_info.minor}.exe",
        }:
            # setup-python provides reparse-point aliases; this standalone owned
            # interpreter uses python.exe only. Never copy/dereference aliases.
            return
        if source.name in {"__pycache__", "test", "tests"} or source.suffix == ".pth":
            return
        if bare and source.name == "site-packages":
            return
        if not wheel and source.parent == Path(sysconfig.get_path("purelib")) and (
            source.name in {"collectors", "packages", "apps"} or
            source.name.startswith("storage_console")
        ):
            return
        assert not getattr(source.lstat(), "st_file_attributes", 0) & 0x400
        if source.is_dir():
            attributes, descriptor = state._attributes()
            try:
                check(state._api.kernel.CreateDirectoryW(str(target), ctypes.byref(attributes)))
            finally:
                state._api.kernel.LocalFree(descriptor)
            for child in source.iterdir():
                copy(child, target / child.name, state, bare=bare, wheel=wheel)
        else:
            state._write_new(target, source.read_bytes())
    try:
        with ProtectedState(root, create=True) as state:
            for source in Path(sys.base_prefix).iterdir():
                copy(source, root / source.name, state, bare=True)
            packages = root / "Lib" / "site-packages"
            copy(Path(sysconfig.get_path("purelib")), packages, state)
            installed = installed_python.parent.parent / "Lib" / "site-packages"
            for source in installed.iterdir():
                copy(source, packages / source.name, state, wheel=True)
        yield root / "python.exe"
    finally:
        assert root.parent.resolve() == Path(os.environ["ProgramFiles"]).resolve()
        assert root.resolve() == root.parent.resolve() / root.name
        assert root.name.startswith(SERVICE_NAME + "Test") and not root.is_symlink()
        if root.exists():
            shutil.rmtree(root)


@pytest.fixture(scope="module")
def previous_wheel(tmp_path_factory):
    # Immutable accepted Stage A package, fetched as public committed source.
    baseline = "ef78111c0d2e8f971cb16f7b64a40c3f7cffd716"
    root = tmp_path_factory.mktemp("previous-collector")
    repository, source, wheels = root / "repository", root / "source", root / "wheels"
    for arguments in (
        ["git", "init", "--bare", str(repository)],
        ["git", "-C", str(repository), "fetch", "--no-tags", "--depth=1",
         "https://github.com/BorisDruzak/storage-console.git", baseline],
    ):
        result = subprocess.run(arguments, capture_output=True, timeout=90)
        assert result.returncode == 0, "PREVIOUS_SOURCE_FETCH_FAILED"
    actual = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "FETCH_HEAD"])
    assert actual.decode().strip() == baseline
    archive = subprocess.run(
        ["git", "-C", str(repository), "archive", "--format=tar", "FETCH_HEAD"],
        capture_output=True, timeout=30,
    )
    assert archive.returncode == 0 and len(archive.stdout) < 64 * 1024**2
    source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as bundle:
        bundle.extractall(source, filter="data")
    built = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--quiet",
         "--wheel-dir", str(wheels), str(source)], capture_output=True, timeout=120,
    )
    assert built.returncode == 0, "PREVIOUS_WHEEL_BUILD_FAILED"
    return next(wheels.glob("storage_console-*.whl"))


def test_clean_protected_wheel_operator_cli_install_start_status_stop_uninstall(
    protected_installed_python, previous_wheel, tmp_path, authorities, servers,
):
    spec = ServiceSpec(str(protected_installed_python), str(tmp_path / "state"))
    backend = NativeBackend()
    # Never manage an already-existing default service on the test host.
    assert backend.query(spec) is None, "OWNED_DISPOSABLE_HOST_REQUIRED"
    manager = ServiceManager(spec, backend)
    server, origin = servers()
    config, box = activate_fixture(manager, tmp_path, origin, authorities[0] / "ca.pem")
    config_bytes = (tmp_path / "state" / "config.json").read_bytes()
    def command(action):
        arguments = [str(protected_installed_python), "-I", "-m", "collectors.windows.cli",
                     "service", action]
        if action == "install":
            arguments.extend(["--state", str(tmp_path / "state")])
        result = subprocess.run(
            arguments,
            cwd=tmp_path, capture_output=True, timeout=160,
        )
        assert result.returncode == 0, result.stderr.decode("utf-8")
        assert ("a" * 43).encode() not in result.stdout + result.stderr
        return result.stdout
    try:
        command("install")
        command("install")
        command("start")
        assert principal(manager.status().pid) == "S-1-5-18"
        assert "уже работает".encode() in command("start")
        assert b"RUNNING" in command("status")
        eventually(lambda: len(server.requests) >= 3)
        command("stop")
        command("stop")
        command("uninstall")
        command("uninstall")
        assert backend.query(spec) is None
        assert (tmp_path / "state" / "config.json").read_bytes() == config_bytes
        assert box.credential_binding() == config.credential_version
        # Service → previous wheel + foreground rollback, with exactly the same
        # state/identity. No new activation and no editing of credential state.
        installed = subprocess.run(
            [str(protected_installed_python), "-I", "-m", "pip", "install",
             "--no-deps", "--force-reinstall", "--quiet", str(previous_wheel)],
            capture_output=True, timeout=90,
        )
        assert installed.returncode == 0, "PREVIOUS_WHEEL_RESTORE_FAILED"
        help_result = subprocess.run(
            [str(protected_installed_python), "-I", "-m", "collectors.windows.cli", "--help"],
            capture_output=True, timeout=15, cwd=tmp_path,
        )
        assert help_result.returncode == 0 and b"service" not in help_result.stdout
        before_sequence = box.checkpoint("windows:heartbeat").value["sequence"]
        before_requests = len(server.requests)
        script = (
            "import signal,sys,threading; from collectors.windows.cli import main; "
            "timer=threading.Timer(12,lambda:signal.raise_signal(signal.SIGINT)); "
            "timer.daemon=True; timer.start(); "
            "raise SystemExit(main(['run','--state',sys.argv[1]]))"
        )
        foreground = subprocess.run(
            [str(protected_installed_python), "-I", "-c", script, str(tmp_path / "state")],
            capture_output=True, timeout=50, cwd=tmp_path, creationflags=0x08000000,
        )
        assert foreground.returncode == 130, "PREVIOUS_FOREGROUND_ROLLBACK_FAILED"
        assert ("a" * 43).encode() not in foreground.stdout + foreground.stderr
        assert len(server.requests) > before_requests
        assert box.checkpoint("windows:heartbeat").value["sequence"] > before_sequence
        assert box.credential_binding() == config.credential_version
        assert (tmp_path / "state" / "config.json").read_bytes() == config_bytes
    finally:
        current = backend.query(spec)
        if current is not None:
            assert current.command == spec.command
            with backend._service(spec, 0x10000 | 0x20) as handle:
                if handle is not None:
                    native_status = Status()
                    backend.api.ControlService(handle, 1, ctypes.byref(native_status))
                    check(backend.api.DeleteService(handle))
