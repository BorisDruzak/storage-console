import os
from datetime import UTC, datetime

import pytest

from collectors.windows.inventory import CaptureError, Observation, Scope
from collectors.windows.native import NativeInventory
from packages.contracts.inventory import VolumeRecord


@pytest.mark.parametrize(
    "roots",
    [
        (),
        ("relative",),
        ("C:relative",),
        ("\\\\server\\share",),
        ("\\\\?\\C:\\data",),
        ("C:\\a\\..\\b",),
        ("C:\\a\\.\\b",),
        ("C:\\a:stream",),
        ("C:\\a\n",),
        ("C:\\a ",),
        ("C:\\CON",),
        ("C:\\a", "c:\\A\\child"),
        ("C:\\a", "c:\\a"),
        tuple(f"C:\\root{i}" for i in range(33)),
        ("C:\\" + "x" * 32700,),
    ],
)
def test_scope_rejects_unsafe_or_overlapping_configuration(roots):
    with pytest.raises(CaptureError, match="^INVALID_SCOPE$"):
        Scope(roots)


def test_scope_normalization_fingerprint_and_repr():
    first = Scope(("c:\\private\\Reports\\", "D:\\data"))
    second = Scope(("d:\\data", "C:\\private\\Reports"))
    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64
    assert first.roots == ("C:\\private\\Reports", "D:\\data")
    assert "Reports" not in repr(first)
    assert Scope(("C:\\private\\Reports2",)).fingerprint != first.fingerprint


def test_observation_hides_metadata_and_restricts_issue_codes():
    record = VolumeRecord(
        occurred_at=datetime.now(UTC),
        unique_identity="private-id",
        filesystem="NTFS",
        label="private-label",
    )
    value = Observation(record=record)
    assert "private" not in repr(value)
    assert value.record == record
    assert Observation(error_code="ACCESS_DENIED").error_code == "ACCESS_DENIED"
    for kwargs in [
        {},
        {"record": record, "error_code": "ACCESS_DENIED"},
        {"error_code": "private-message"},
        {"record": object()},
    ]:
        with pytest.raises(CaptureError, match="^METADATA_INVALID$"):
            Observation(**kwargs)
    assert str(CaptureError("private-message")) == "NATIVE_FAILED"


@pytest.mark.skipif(os.name == "nt", reason="Unsupported platform gate")
def test_windows_provider_imports_safely_and_rejects_unsupported_runtime():
    with pytest.raises(CaptureError, match="^PLATFORM_UNSUPPORTED$"):
        list(NativeInventory().scan(Scope(("C:\\data",))))


def test_non_adjacent_overlapping_roots_are_rejected():
    with pytest.raises(CaptureError, match="^INVALID_SCOPE$"):
        Scope(("C:\\a", "C:\\a-other", "C:\\a\\child"))


def test_scope_fingerprint_preserves_case_sensitive_directory_identity():
    assert Scope(("C:\\CaseSensitive",)).fingerprint != Scope(("C:\\casesensitive",)).fingerprint


def test_scope_ancestor_handle_depth_is_bounded_before_native_access():
    with pytest.raises(CaptureError, match='^INVALID_SCOPE$'):
        Scope(('C:\\' + '\\'.join(['level']*65),))
