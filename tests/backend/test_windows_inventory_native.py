import ctypes
import os
import subprocess

import pytest

from collectors.windows.inventory import Scope
from collectors.windows.native import NativeInventory, _Api

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Actual Windows metadata API")


def records(root):
    values = list(NativeInventory().scan(Scope((str(root),))))
    assert not [v.error_code for v in values if v.error_code], "Unexpected native issue"
    return [v.record for v in values]


def test_native_identity_size_parent_and_rename(tmp_path):
    root = tmp_path / "scoped"
    root.mkdir()
    child = root / "Отчёт😀.txt"
    child.write_bytes(b"synthetic-content")
    before = records(root)
    volume = next(v for v in before if v.kind == "volume")
    directory = next(v for v in before if v.kind == "object" and v.name == "scoped")
    file = next(v for v in before if v.kind == "object" and v.name == child.name)
    assert volume.filesystem in ("NTFS", "ReFS")
    assert volume.unique_identity.startswith("volume:")
    assert 0 <= volume.free_bytes <= volume.total_bytes
    assert file.volume_identity == volume.unique_identity
    assert file.parent_file_id == directory.file_id
    assert len(file.file_id) == 32
    assert file.size_bytes == 17
    assert file.relative_path.endswith("scoped\\" + child.name)
    child.rename(root / "renamed.txt")
    after = records(root)
    renamed = next(v for v in after if v.kind == "object" and v.name == "renamed.txt")
    assert renamed.file_id == file.file_id
    assert renamed.relative_path != file.relative_path


def test_junction_child_and_ancestor_are_never_followed(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "must-not-capture.txt").write_text("synthetic")
    root = tmp_path / "root"
    root.mkdir()
    link = root / "junction"
    subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        values = list(NativeInventory().scan(Scope((str(root),))))
        assert [v.error_code for v in values if v.error_code] == ["REPARSE_POINT"]
        assert not any(
            v.record and v.record.kind == "object" and v.record.name == "must-not-capture.txt"
            for v in values
        )
        ancestor = list(NativeInventory().scan(Scope((str(link),))))
        assert len(ancestor) == 1 and ancestor[0].error_code == "REPARSE_POINT"
    finally:
        link.rmdir()


def test_ancestor_pinned_and_generator_close_releases_handles(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    parent = tmp_path
    scanner = NativeInventory().scan(Scope((str(root),)))
    next(scanner)
    with pytest.raises(OSError):
        parent.rename(parent.with_name(parent.name + "-moved"))
    scanner.close()
    moved = root.with_name("moved")
    root.rename(moved)
    moved.rename(root)


def test_api_metadata_access_flags_and_failed_query_cleanup(tmp_path, monkeypatch):
    api = _Api()
    opened, closed = [], []
    real_open, real_close = api.open, api.close

    def open_handle(path):
        handle = real_open(path)
        opened.append(handle)
        return handle

    def close_handle(handle):
        closed.append(handle)
        real_close(handle)

    monkeypatch.setattr(api, "open", open_handle)
    monkeypatch.setattr(api, "close", close_handle)

    def fail(handle):
        raise OSError("private-path-sensitive-failure")

    monkeypatch.setattr(api, "metadata", fail)
    values = list(NativeInventory(api=api).scan(Scope((str(tmp_path),))))
    assert len(values) == 1
    assert values[0].error_code == "NATIVE_FAILED"
    assert sorted(opened) == sorted(closed)
    assert "private" not in repr(values)
    assert api.functions["CreateFileW"].restype is ctypes.c_void_p


def test_final_path_alias_replacement_is_rejected_before_enumeration(tmp_path, monkeypatch):
    api = _Api()
    real_final = api.final_path
    count = 0

    def replaced(handle):
        nonlocal count
        count += 1
        value = real_final(handle)
        return value + "-outside" if count == 2 else value

    monkeypatch.setattr(api, "final_path", replaced)
    values = list(NativeInventory(api=api).scan(Scope((str(tmp_path),))))
    assert len(values) == 1 and values[0].error_code == "SCOPE_CHANGED"


def test_native_opens_never_request_data_or_delete_sharing(tmp_path, monkeypatch):
    api = _Api()
    real = api.functions["CreateFileW"]
    calls = []

    def opened(*args):
        calls.append(args[1:])
        return real(*args)

    monkeypatch.setitem(api.functions, "CreateFileW", opened)
    values = list(NativeInventory(api=api).scan(Scope((str(tmp_path),))))
    assert not any(v.error_code for v in values)
    assert calls and all(args == (0x80, 0x3, None, 3, 0x02200000, None) for args in calls)


def test_streaming_depth_limit_and_long_paths(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cursor = root
    for _ in range(66):
        cursor = cursor / "abcdefgh"
        cursor.mkdir()
    (cursor / "unseen.txt").write_bytes(b"")
    values = list(NativeInventory().scan(Scope((str(root),))))
    assert "DEPTH_LIMIT" in [v.error_code for v in values]
    assert not any(
        v.record and v.record.kind == "object" and v.record.name == "unseen.txt" for v in values
    )
    assert any(
        v.record and v.record.kind == "object" and len(v.record.relative_path) > 260 for v in values
    )


def test_hard_links_share_identity_but_preserve_each_observed_path(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    first = root / "first.txt"
    first.write_bytes(b"synthetic")
    os.link(first, root / "second.txt")
    files = [v for v in records(root) if v.kind == "object" and v.object_type == "FILE"]
    assert len(files) == 2
    assert files[0].file_id == files[1].file_id
    assert files[0].relative_path != files[1].relative_path


def test_child_metadata_failure_is_partial_and_every_handle_closes(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    (root / "file.txt").write_bytes(b"synthetic")
    api = _Api()
    real_open, real_close, real_metadata = api.open, api.close, api.metadata
    opened, closed = [], []

    def open_handle(path):
        handle = real_open(path)
        opened.append(handle)
        return handle

    def close_handle(handle):
        closed.append(handle)
        real_close(handle)

    def metadata(handle):
        result = real_metadata(handle)
        if not result.directory:
            raise OSError("private-sensitive-path")
        return result

    monkeypatch.setattr(api, "open", open_handle)
    monkeypatch.setattr(api, "close", close_handle)
    monkeypatch.setattr(api, "metadata", metadata)
    values = list(NativeInventory(api=api).scan(Scope((str(root),))))
    assert [v.error_code for v in values if v.error_code] == ["NATIVE_FAILED"]
    assert sorted(opened) == sorted(closed)
    assert any(v.record and v.record.kind == "volume" for v in values)
    assert "private" not in repr(values)


def test_volume_reports_all_mount_aliases_not_only_current_scope_drive(tmp_path, monkeypatch):
    api = _Api()
    aliases = "C:\\\0D:\\\0\0"

    def mounted(root, buffer, capacity, required):
        assert root.startswith("\\\\?\\Volume{")
        buffer.value = aliases
        required._obj.value = len(aliases)
        return 1

    monkeypatch.setitem(api.functions, "GetVolumePathNamesForVolumeNameW", mounted)
    with api.opened(str(tmp_path)) as handle:
        volume = api.volume(handle, api.final_path(handle), str(tmp_path))
    assert volume.mount_aliases == ["C:\\", "D:\\"]


def test_mapped_remote_drive_rejected_before_any_metadata_open(tmp_path, monkeypatch):
    api = _Api()
    opened = []
    real_open = api.open

    def tracked(path):
        opened.append(True)
        return real_open(path)

    monkeypatch.setitem(api.functions, "GetDriveTypeW", lambda root: 4)
    monkeypatch.setattr(api, "open", tracked)
    values = list(NativeInventory(api=api).scan(Scope((str(tmp_path),))))
    assert len(values) == 1 and values[0].error_code == "INVALID_SCOPE"
    assert not opened


def test_every_capture_handle_uses_volume_guid_even_after_drive_alias_changes(
    tmp_path, monkeypatch
):
    api = _Api()
    real_open = api.open
    paths = []

    def tracked(path):
        paths.append(path)
        return real_open(path)

    monkeypatch.setattr(api, "open", tracked)
    values = list(NativeInventory(api=api).scan(Scope((str(tmp_path),))))
    assert not any(v.error_code for v in values)
    assert paths and all(path.startswith("\\\\?\\Volume{") for path in paths)
