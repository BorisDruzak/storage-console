"""Own native process/packaged script boundaries, without an operator credential."""

import os
from pathlib import Path
from threading import Event

import pytest
from pydantic import ValidationError
from test_windows_runtime_native import installed_python as installed_python

from collectors.windows_audit.directory_native import (
    DirectoryError,
    DirectorySettings,
    read_frames,
)


def settings():
    return dict(
        scope={"dns_domain": "example.test", "domain_sid": "S-1-5-21-10-20-30"},
        ldap_server="dc.example.test",
    )


def test_settings_have_finite_limits_and_no_credentials():
    value = DirectorySettings.model_validate(settings())
    assert value.refresh_seconds >= 900 and value.max_seconds <= 60
    assert not {"username", "password", "token", "credentials"} & value.model_dump().keys()
    for changed in (
        dict(settings(), password="forbidden"),
        dict(settings(), ldap_server="dc.other.test"),
        dict(settings(), max_seconds=61),
        dict(settings(), page_size=257),
    ):
        with pytest.raises(ValidationError):
            DirectorySettings.model_validate(changed)


def test_bounded_frame_reader_rejects_duplicate_keys_and_missing_terminal():
    import io

    with pytest.raises(DirectoryError):
        list(read_frames(io.BytesIO(b'{"type":"page","type":"lookup"}\n')))
    with pytest.raises(DirectoryError):
        list(read_frames(io.BytesIO(b'{"type":"page","records":[]}\n')))
    with pytest.raises(DirectoryError):
        list(read_frames(io.BytesIO(b"x" * (4 * 1024**2 + 1))))


@pytest.mark.skipif(os.name != "nt", reason="Own Windows child only")
def test_native_child_requires_system_before_any_directory_access():
    import ctypes

    from collectors.windows_audit.directory_native import NativeDirectory

    # This caller is an operator process, never an installed LocalSystem service.
    assert ctypes.windll.shell32.IsUserAnAdmin()
    native = NativeDirectory(DirectorySettings.model_validate(settings()))
    with pytest.raises(DirectoryError) as captured:
        list(native.users(Event()))
    assert captured.value.code == "MACHINE_IDENTITY_REQUIRED"


def test_fixed_native_script_declares_machine_kerberos_and_critical_paging():
    from collectors.windows_audit.directory_native import SCRIPT

    source = Path(SCRIPT).read_text(encoding="utf8")
    assert "S-1-5-18" in source and "AuthType]::Kerberos" in source
    assert "Signing = $true" in source and "Sealing = $true" in source
    assert "PageResultRequestControl" in source and "IsCritical = $true" in source
    assert "DnsOnly" in source and "NoHostsFile" in source
    assert "PSCredential" not in source and "Invoke-Expression" not in source


@pytest.mark.skipif(os.name != "nt", reason="Packaged PowerShell AST only")
def test_packaged_domain_and_required_numeric_helpers_fail_closed(tmp_path):
    import json
    import subprocess

    from collectors.windows_audit.directory_native import SCRIPT

    # Evaluate only packaged helper declarations, never the LDAP/script body.
    program = r"""
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($args[0],[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'PARSE_ERROR' }
$functions=$ast.FindAll({param($node)
  $node -is [Management.Automation.Language.FunctionDefinitionAst]},$false)
foreach($function in $functions) { . ([scriptblock]::Create($function.Extent.Text)) }
$rejected=0
foreach($values in @(@(),@('512','514'),@('bad'),@('4294967296'))) {
  $entry=@{Attributes=@{userAccountControl=$values}}
  try { $null=Directory-UInt32 $entry 'userAccountControl' } catch { $rejected++ }
}
$on=Directory-UInt32 @{Attributes=@{userAccountControl=@('512')}} 'userAccountControl'
$off=Directory-UInt32 @{Attributes=@{userAccountControl=@('514')}} 'userAccountControl'
@{base=(Directory-ExpectedBase 'example.test'); rejected=$rejected;
  enabled=($on -band 2) -eq 0; disabled=($off -band 2) -ne 0} | ConvertTo-Json -Compress
"""
    harness = tmp_path / "helpers.ps1"
    harness.write_text(program, encoding="utf8")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(harness), str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "base": "DC=example,DC=test",
        "rejected": 4,
        "enabled": True,
        "disabled": True,
    }


@pytest.mark.skipif(os.name != "nt", reason="Own installed wheel")
def test_installed_wheel_contains_fixed_native_directory_script(installed_python, tmp_path):
    import subprocess

    result = subprocess.run(
        [
            str(installed_python),
            "-I",
            "-B",
            "-c",
            "from collectors.windows_audit.directory_native import SCRIPT;"
            "assert SCRIPT.is_file();"
            "assert 'Directory-ExpectedBase' in SCRIPT.read_text();print('PACKAGED_SCRIPT_OK')",
        ],
        cwd=tmp_path,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0 and result.stdout.strip() == b"PACKAGED_SCRIPT_OK"


@pytest.mark.skipif(os.name != "nt", reason="Own Windows child only")
@pytest.mark.parametrize("stopped", [False, True])
def test_native_hung_child_is_killed_on_deadline_or_stop(tmp_path, monkeypatch, stopped):
    import time

    from collectors.windows_audit import directory_native

    script = tmp_path / "owned-hung.ps1"
    script.write_text("$null=[Console]::In.ReadLine(); Start-Sleep -Seconds 60", encoding="utf8")
    monkeypatch.setattr(directory_native, "SCRIPT", script)
    stop = Event()
    if stopped:
        stop.set()
    native = directory_native.NativeDirectory(
        DirectorySettings.model_validate(settings() | {"max_seconds": 1})
    )
    started = time.monotonic()
    with pytest.raises(DirectoryError) as failure:
        list(native.users(stop))
    assert failure.value.code == ("DIRECTORY_STOPPED" if stopped else "LOOKUP_LIMIT")
    assert time.monotonic() - started < 5
