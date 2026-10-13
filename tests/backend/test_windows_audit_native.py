"""Native acceptance on disposable GitHub Windows runner, never a user workstation."""

import ctypes
import json
import os
import re
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from test_collector_transport import authorities as authorities
from test_windows_runtime_native import installed_python as installed_python
from test_windows_service_native import eventually, principal

from collectors.windows._scm_native import NativeBackend, Status, check
from collectors.windows.scm import ServiceManager, ServiceSpec
from collectors.windows.security import ProtectedState

pytestmark = pytest.mark.skipif(
    os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true",
    reason="Owned disposable Windows runner required; no SCM mutations on user workstation",
)


def test_native_dpapi_large_cache_and_protected_state(tmp_path):
    from collectors.windows_audit.configuration import MachineCipher

    with ProtectedState(tmp_path / "audit", create=True) as state:
        cipher = MachineCipher()
        payload = b"synthetic-sensitive-evidence" * 10000
        encrypted = cipher.protect(payload)
        assert payload[:100] not in encrypted, "DPAPI_PLAINTEXT_LEAK"
        assert cipher.unprotect(encrypted) == payload, "DPAPI_ROUNDTRIP_FAILED"
        state.write("evidence.dpapi", encrypted[:48000])
        state.validate_file("evidence.dpapi")


def test_native_security_strict_bookmark_resume_and_anchor_reject():
    from collectors.windows_audit.native import EventLogError, SecurityReader

    with SecurityReader(None, initial_baseline=True) as reader:
        row = reader.next()
        assert row is not None, "DISPOSABLE_SECURITY_FIXTURE_REQUIRED"
        xml, bookmark = row
        digest = sha256(xml.encode()).hexdigest()
    with SecurityReader(bookmark, anchor_digest=digest) as resumed:
        later = resumed.next()
        assert later is None or later[1] != bookmark, "BOOKMARK_REPLAYED_LAST_EVENT"
    with pytest.raises(EventLogError, match="AUDIT_BOOKMARK_STALE"):
        SecurityReader(bookmark, anchor_digest="0" * 64)
    from xml.etree import ElementTree as ET

    altered = ET.fromstring(bookmark)
    altered[0].set("RecordId", "9223372036854775800")
    absent = ET.tostring(altered, encoding="unicode")
    assert absent != bookmark, "NATIVE_BOOKMARK_SCHEMA_CHANGED"
    with pytest.raises(EventLogError, match="AUDIT_BOOKMARK_STALE"):
        SecurityReader(absent)


def test_native_bounds_and_reparse_privacy(tmp_path):
    from collectors.windows_audit.native import SecurityReader, no_reparse_ancestry

    with SecurityReader(None, initial_baseline=True) as reader:
        bounds = reader.bounds()
        assert bounds["record_count"] > 0 and bounds["maximum_bytes"] > 0
        assert bounds["newest_record_id"] >= bounds["oldest_record_id"]
    owned = tmp_path / "owned"
    outside = tmp_path / "outside"
    owned.mkdir()
    outside.mkdir()
    (owned / "escape").symlink_to(outside, target_is_directory=True)
    assert not no_reparse_ancestry(str(owned / "escape" / "absent.txt"))


def test_owned_security_evtx_fixture_replacement_is_strict_miss(tmp_path):
    """Replace ONLY a private exported fixture, never clear the real Security channel."""
    from collectors.windows_audit.native import D, P, api, render

    dll = api()
    dll.EvtExportLog.argtypes = [P, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p, D]
    dll.EvtExportLog.restype = D
    query = dll.EvtQuery(None, "Security", "*", 0x201)
    assert query, "OWNED_SECURITY_QUERY_FAILED"
    handles, count = (P * 2)(), D()
    bookmark = None
    fixture = tmp_path / "owned-security.evtx"
    try:
        assert dll.EvtNext(query, 2, handles, 0, 0, ctypes.byref(count)) and count.value == 2
        from xml.etree import ElementTree as ET

        from collectors.windows_audit.events import NS

        first_id = int(
            ET.fromstring(render(dll, handles[0])).findtext(NS + "System/" + NS + "EventRecordID")
        )
        second_id = int(
            ET.fromstring(render(dll, handles[1])).findtext(NS + "System/" + NS + "EventRecordID")
        )
        assert dll.EvtExportLog(
            None, "Security", f"*[System[EventRecordID={first_id}]]", str(fixture), 1
        ), "OWNED_SECURITY_EXPORT_FAILED"
        owned = dll.EvtQuery(None, str(fixture), "*", 2)
        assert owned, "OWNED_FIXTURE_QUERY_FAILED"
        fixture_handles, returned = (P * 1)(), D()
        try:
            assert dll.EvtNext(owned, 1, fixture_handles, 0, 0, ctypes.byref(returned))
            bookmark = dll.EvtCreateBookmark(None)
            assert dll.EvtUpdateBookmark(bookmark, fixture_handles[0])
            anchor = sha256(render(dll, fixture_handles[0]).encode()).hexdigest()
            assert dll.EvtSeek(owned, 0, bookmark, 0, 0x10004), "OWNED_FIXTURE_ANCHOR_FAILED"
        finally:
            if fixture_handles[0]:
                dll.EvtClose(fixture_handles[0])
            dll.EvtClose(owned)
        fixture.unlink()
        assert dll.EvtExportLog(
            None, "Security", f"*[System[EventRecordID={second_id}]]", str(fixture), 1
        ), "OWNED_SECURITY_REPLACEMENT_FAILED"
        owned = dll.EvtQuery(None, str(fixture), "*", 2)
        assert owned
        fixture_handles, returned = (P * 1)(), D()
        try:
            seek = dll.EvtSeek(owned, 0, bookmark, 0, 0x10004)
            if seek:
                assert dll.EvtNext(owned, 1, fixture_handles, 0, 0, ctypes.byref(returned))
                changed = sha256(render(dll, fixture_handles[0]).encode()).hexdigest() != anchor
                assert changed, "REPLACED_GENERATION_WAS_TOLERATED"
        finally:
            if fixture_handles[0]:
                dll.EvtClose(fixture_handles[0])
            dll.EvtClose(owned)
    finally:
        for handle in (*handles, bookmark, query):
            if handle:
                dll.EvtClose(handle)
        if fixture.exists():
            fixture.unlink()


def test_installed_dpapi_queue_crash_rolls_back_bookmark_and_body(installed_python, tmp_path):
    import subprocess
    from uuid import UUID

    from collectors.windows_audit.configuration import MachineCipher
    from collectors.windows_audit.store import AuditStore

    identity = uuid4()
    with ProtectedState(tmp_path / "atomic", create=True) as state:
        state.create_file("audit.sqlite3")
        store = AuditStore(state.root / "audit.sqlite3", identity, MachineCipher())
        store.commit("before", {}, b"synthetic retained body")
        before = store.peek()
        code = """import os,sys
from pathlib import Path
from uuid import UUID
from collectors.windows_audit.store import AuditStore
from collectors.windows_audit.configuration import MachineCipher
store=AuditStore(Path(sys.argv[1]),UUID(sys.argv[2]),MachineCipher())
with store._transaction() as db:
 db.execute("UPDATE state SET checkpoint=? WHERE id=1", (store.cipher.protect(b'{}'),))
 db.execute("DELETE FROM queue")
 os._exit(23)
"""
        result = subprocess.run(
            [
                str(installed_python),
                "-I",
                "-c",
                code,
                str(state.root / "audit.sqlite3"),
                str(identity),
            ],
            capture_output=True,
            timeout=20,
        )
        assert result.returncode == 23 and not result.stderr, "OWNED_CRASH_PROBE_FAILED"
        recovered = AuditStore(state.root / "audit.sqlite3", UUID(str(identity)), MachineCipher())
        assert recovered.checkpoint()[0] == "before", "CRASH_ADVANCED_BOOKMARK"
        assert recovered.peek() == before, "CRASH_CHANGED_REPLAY_BODY"


@pytest.fixture
def owned_security_scope(tmp_path):
    """Temporary narrow SACL on a disposable runner only; restore its audit policy."""
    import subprocess

    root = tmp_path / "owned-security-fixture"
    root.mkdir()
    backup = tmp_path / "owned-policy-backup.csv"
    result = subprocess.run(
        ["auditpol.exe", "/backup", "/file:" + str(backup)], capture_output=True, timeout=15
    )
    assert result.returncode == 0, "DISPOSABLE_POLICY_BACKUP_FAILED"
    try:
        result = subprocess.run(
            [
                "auditpol.exe",
                "/set",
                "/subcategory:{0CCE921D-69AE-11D9-BED3-505054503030}",
                "/success:enable",
            ],
            capture_output=True,
            timeout=15,
        )
        assert result.returncode == 0, "DISPOSABLE_AUDIT_POLICY_FAILED"
        script = """$ErrorActionPreference='Stop';
$acl=Get-Acl -LiteralPath $args[0] -Audit;
$sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User;
$rule=[System.Security.AccessControl.FileSystemAuditRule]::new($sid,
 [System.Security.AccessControl.FileSystemRights]'Write,Delete',
 [System.Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit',
 [System.Security.AccessControl.PropagationFlags]::None,
 [System.Security.AccessControl.AuditFlags]::Success);
$acl.AddAuditRule($rule);Set-Acl -LiteralPath $args[0] -AclObject $acl;"""
        result = subprocess.run(
            [
                "pwsh.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "& {" + script + "}",
                str(root),
            ],
            capture_output=True,
            timeout=15,
        )
        assert result.returncode == 0, "OWNED_SYNTHETIC_SACL_FAILED"
        yield root
    finally:
        result = subprocess.run(
            ["auditpol.exe", "/restore", "/file:" + str(backup)], capture_output=True, timeout=15
        )
        assert result.returncode == 0, "DISPOSABLE_POLICY_RESTORE_FAILED"


@pytest.mark.parametrize("mode", ["capture_only", "deliver"])
def test_installed_wheel_own_scm_system_dpapi_and_restart(
    installed_python,
    tmp_path,
    authorities,
    owned_security_scope,
    authenticated_setup,
    mode,
):
    if mode == "capture_only":
        _installed_wheel_scm(installed_python, tmp_path, authorities, owned_security_scope)
        return
    from sqlalchemy import func, insert, select, update

    from packages.shared.models.audit import audit_evidence
    from packages.shared.models.core import collectors, volumes
    from tests.deployment.collector_delivery import serving_ingest

    client, engine, collector, token, source = authenticated_setup
    with engine.begin() as conn:
        conn.execute(
            update(collectors)
            .where(collectors.c.id == collector)
            .values(collector_type="AUDIT_WINDOWS")
        )
        conn.execute(
            insert(volumes).values(
                source_node_id=source, unique_identity="synthetic-volume", filesystem="NTFS"
            )
        )

    def received():
        with engine.connect() as conn:
            return conn.scalar(select(func.count()).select_from(audit_evidence)) >= 2

    codes = []
    lost_acks = []

    async def observed_app(scope, receive, send):
        async def observed_send(message):
            if message["type"] == "http.response.start" and len(codes) < 16:
                codes.append(message["status"])
            if (
                scope["path"] == "/api/v1/ingest/audit-events"
                and message["type"] == "http.response.start"
                and message["status"] == 202
                and received()
            ):
                # Persist the actual receipt, but withhold the successful ACK.
                # Restart must retain the queued body; successful ACKs may remove it.
                if len(lost_acks) < 16:
                    lost_acks.append(True)
                message = {**message, "status": 503}
            await send(message)

        await client.app(scope, receive, observed_send)

    with serving_ingest(observed_app, tmp_path / "tls") as (origin, ca):
        _installed_wheel_scm(
            installed_python,
            tmp_path,
            authorities,
            owned_security_scope,
            {
                "mode": "deliver",
                "audit_sids": [principal(os.getpid())],
                "collector_id": str(collector),
                "source_id": str(source),
                "origin": origin,
                "ca_file": str(ca),
                "token": token,
            },
            received,
            lambda: {"http_status_codes": codes},
        )
        assert lost_acks, "NATIVE_LOST_ACK_NOT_EXERCISED"


def _installed_wheel_scm(
    installed_python,
    tmp_path,
    authorities,
    owned_security_scope,
    config_override=None,
    received=None,
    extra_diagnostics=None,
):
    import subprocess

    from collectors.windows_audit.scm import AuditBackend, AuditServiceSpec

    spec = AuditServiceSpec(
        str(installed_python), str(tmp_path / "audit"), "SosnadminStorageAuditTest" + uuid4().hex
    )
    # Installed wheel probe, native machine DPAPI config; no credentials in argv/output.
    config = {
        "collector_id": str(uuid4()),
        "host_id": str(uuid4()),
        "source_id": str(uuid4()),
        "generation": str(uuid4()),
        "roots": {str(owned_security_scope): "synthetic-volume"},
        "origin": "https://storage.example.test",
        "ca_file": str(tmp_path / "ca.pem"),
        "token": "a" * 43,
        "configured": True,
        "initial_baseline": True,
    }
    config["ca_file"] = str(authorities[0] / "ca.pem")
    if config_override:
        config.update(config_override)
    probe = subprocess.run(
        [
            str(installed_python),
            "-I",
            "-m",
            "collectors.windows_audit.cli",
            "initialize",
            "--state",
            spec.state_path,
        ],
        input=json.dumps(config).encode(),
        capture_output=True,
        timeout=30,
    )
    assert probe.returncode == 0 and not probe.stderr, "AUDIT_WHEEL_INITIALIZATION_FAILED"
    legacy_spec = ServiceSpec(
        str(installed_python),
        str(tmp_path / "legacy-unused"),
        "SosnadminStorageCollectorTest" + uuid4().hex,
    )
    legacy = NativeBackend()
    legacy_manager = ServiceManager(legacy_spec, legacy, timeout=40)
    legacy_manager.install()
    original_legacy = legacy_manager.status()
    native = AuditBackend()
    manager = ServiceManager(cast(ServiceSpec, spec), native, timeout=40)
    manager.install()
    try:
        manager.start()
        status = manager.status()
        assert status.pid != os.getpid(), "AUDIT_MUST_OWN_PROCESS"
        assert principal(status.pid) == "S-1-5-18", "AUDIT_MUST_BE_LOCAL_SYSTEM"
        eventually(lambda: (Path(spec.state_path) / "audit-status.json").exists())
        target = owned_security_scope / "synthetic.txt"
        target.write_text("synthetic", encoding="utf-8")
        target.write_text("synthetic rewrite", encoding="utf-8")
        target.unlink()

        def accepted():
            if received:
                return received()
            value = json.loads((Path(spec.state_path) / "audit-status.json").read_bytes())
            return value.get("backlog", 0) >= 2

        def safe_diagnostics():
            value = json.loads((Path(spec.state_path) / "audit-status.json").read_bytes())
            result = {
                key: value.get(key)
                for key in (
                    "health",
                    "mode",
                    "backlog",
                    "gap",
                    "policy_verified",
                    "sacl_verified",
                    "bounds_error",
                    "read_errors",
                    "counters",
                    "delivery",
                )
            }
            if extra_diagnostics:
                result.update(extra_diagnostics())
            scm = manager.status()
            result.update(
                scm_state=scm.state, scm_exit_code=scm.exit_code, same_pid=scm.pid == status.pid
            )
            import sqlite3

            from collectors.windows_audit.configuration import MachineCipher

            database = (Path(spec.state_path) / "audit.sqlite3").as_uri() + "?mode=ro"
            with sqlite3.connect(database, uri=True, timeout=2) as connection:
                row = connection.execute("SELECT payload FROM delivery WHERE id=1").fetchone()
            if row:
                result["retained_delivery"] = json.loads(MachineCipher().unprotect(row[0]))
            from collectors.windows.diagnostics import valid_detail

            script = (
                '$events=@(Get-WinEvent -LogName Application -FilterXPath "'
                "*[System[Provider[@Name='"
                + spec.name
                + "']]]\" -MaxEvents 8 -ErrorAction SilentlyContinue);"
                "$values=@($events|ForEach-Object {"
                "$_.Properties|ForEach-Object {[string]$_.Value}});"
                "ConvertTo-Json -InputObject $values -Compress"
            )
            events = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", script],
                capture_output=True,
                timeout=10,
            )
            if events.returncode == 0:
                values = json.loads(events.stdout.decode())
                result["service_diagnostics"] = [
                    value
                    for value in values
                    if valid_detail(value)
                    or (value.isascii() and all(c.isupper() or c == "_" for c in value))
                    or re.fullmatch(r"AUDIT_WIN32_[0-9]{1,10}", value)
                ]
            return result

        eventually(accepted, seconds=45, diagnostics=safe_diagnostics)
        manager.stop()
        from collectors.windows_audit.configuration import MachineCipher
        from collectors.windows_audit.store import AuditStore

        with ProtectedState(Path(spec.state_path)) as state:
            queue = AuditStore(
                state.root / "audit.sqlite3", uuid4_from(config["collector_id"]), MachineCipher()
            )
            before = queue.peek()
            bookmark, cache = queue.checkpoint()
            assert (received is not None or before is not None) and cache["counters"][
                "accepted"
            ] > 0
            assert queue.peek() == before, "LOST_ACK_CHANGED_BODY"
        manager.start()
        restarted_pid = manager.status().pid
        eventually(
            lambda: (
                json.loads((Path(spec.state_path) / "audit-status.json").read_bytes()).get("pid")
                == restarted_pid
            )
        )
        manager.stop()
        with ProtectedState(Path(spec.state_path)) as state:
            state.validate_file("audit.sqlite3")
            queue = AuditStore(
                state.root / "audit.sqlite3", uuid4_from(config["collector_id"]), MachineCipher()
            )
            assert queue.peek() == before, "RESTART_CHANGED_QUEUED_BODY"
            assert queue.checkpoint()[0] == bookmark, "IDLE_RESTART_CHANGED_BOOKMARK"
    finally:
        with native._service(cast(ServiceSpec, spec), 0x10000 | 0x20 | 4) as handle:
            if handle is not None:
                native.api.ControlService(handle, 1, ctypes.byref(Status()))
                check(native.api.DeleteService(handle))
        try:
            assert legacy_manager.status() == original_legacy, "AUDIT_CHANGED_USN_REGISTRATION"
        finally:
            legacy_manager.uninstall()


def uuid4_from(value):
    from uuid import UUID

    return UUID(value)


def test_native_read_only_policy_and_sacl_cover_owned_runner_sid(owned_security_scope):
    from collectors.windows_audit.readiness import readiness

    assert readiness([str(owned_security_scope)], [principal(os.getpid())]) == (True, True)
