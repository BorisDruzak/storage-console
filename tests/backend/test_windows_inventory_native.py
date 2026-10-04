import ctypes
import os
import struct
import subprocess
from datetime import UTC, datetime

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
    assert file.link_count == 1
    assert directory.link_count is None
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
    (tmp_path / "leaf.txt").write_bytes(b"synthetic")
    api = _Api()
    real = api.functions["CreateFileW"]
    real_relative = api.functions["NtCreateFile"]
    calls, relative_calls = [], []

    def opened(*args):
        calls.append(args[1:])
        return real(*args)

    def relative(*args):
        relative_calls.append((args[1], args[6], args[8]))
        return real_relative(*args)

    monkeypatch.setitem(api.functions, "CreateFileW", opened)
    monkeypatch.setitem(api.functions, "NtCreateFile", relative)
    values = list(NativeInventory(api=api).scan(Scope((str(tmp_path),))))
    assert not any(v.error_code for v in values)
    # Path open is only the local volume root: bit 1 is directory listing.
    assert calls and all(args == (0x81, 0x3, None, 3, 0x02200000, None) for args in calls)
    assert relative_calls and any(options & 0x40 for _, _, options in relative_calls)
    for access, sharing, options in relative_calls:
        assert sharing == 3 and options & 0x200000
        if options & 0x40:  # FILE_NON_DIRECTORY_FILE: never read file data.
            assert access == 0x100080
        else:
            assert options & 1 and access == 0x100081  # Directory listing only.


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


def test_hard_links_preserve_identity_paths_and_actual_count(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    first = root / "first.txt"
    first.write_bytes(b"synthetic")
    second = root / "second.txt"
    os.link(first, second)
    values = records(root)
    files = [
        record for record in values if record.kind == "object" and record.object_type == "FILE"
    ]
    assert {record.name for record in files} == {"first.txt", "second.txt"}
    assert len({record.file_id for record in files}) == 1
    assert len({record.relative_path for record in files}) == 2
    assert {record.link_count for record in files} == {2}
    second.unlink()
    after = [
        record
        for record in records(root)
        if record.kind == "object" and record.object_type == "FILE"
    ]
    assert len(after) == 1
    assert after[0].file_id == files[0].file_id
    assert after[0].link_count == 1


def test_zero_file_link_count_is_explicit_metadata_failure(tmp_path, monkeypatch):
    (tmp_path / "leaf.txt").write_bytes(b"synthetic")
    api = _Api()
    real_query = api._query

    def query(handle, kind, value):
        real_query(handle, kind, value)
        if kind == 1 and not value.directory:
            value.links = 0

    monkeypatch.setattr(api, "_query", query)
    values = list(NativeInventory(api=api).scan(Scope((str(tmp_path),))))
    assert [value.error_code for value in values if value.error_code] == ["METADATA_INVALID"]
    assert not any(
        value.record and value.record.kind == "object" and value.record.object_type == "FILE"
        for value in values
    )


def test_link_count_timestamp_precedes_deferred_record_publication(tmp_path, monkeypatch):
    first, second = tmp_path / "first.txt", tmp_path / "second.txt"
    first.write_bytes(b"synthetic")
    real_record = NativeInventory._record
    added_at = None

    def record(path, metadata, parent):
        nonlocal added_at
        if not metadata.directory and metadata.link_count == 1 and added_at is None:
            added_at = datetime.now(UTC)
            os.link(first, second)
        return real_record(path, metadata, parent)

    monkeypatch.setattr(NativeInventory, "_record", staticmethod(record))
    values = records(tmp_path)
    captured = next(
        value for value in values if value.kind == "object" and value.name == first.name
    )
    assert added_at is not None
    assert captured.link_count == 1
    assert captured.occurred_at < added_at


def test_child_metadata_failure_is_partial_and_every_handle_closes(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    (root / "file.txt").write_bytes(b"synthetic")
    api = _Api()
    real_open, real_close, real_metadata = api.open, api.close, api.metadata
    real_relative = api.open_relative
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

    def relative(parent, name, *, directory=False):
        handle = real_relative(parent, name, directory=directory)
        opened.append(handle)
        return handle

    monkeypatch.setattr(api, "open", open_handle)
    monkeypatch.setattr(api, "close", close_handle)
    monkeypatch.setattr(api, "metadata", metadata)
    monkeypatch.setattr(api, "open_relative", relative)
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


def test_directory_enumeration_never_reopens_a_path(tmp_path, monkeypatch):
    (tmp_path / "leaf.txt").write_bytes(b"synthetic")

    def forbidden(path):
        raise AssertionError("Path-based enumeration crosses the handle boundary")

    monkeypatch.setattr(os, "scandir", forbidden)
    values = list(NativeInventory().scan(Scope((str(tmp_path),))))
    assert not any(v.error_code for v in values)
    assert any(
        v.record and v.record.kind == "object" and v.record.name == "leaf.txt" for v in values
    )


def set_junction(api, root, outside):
    ioctl = api._dll.DeviceIoControl
    ioctl.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_void_p,
    ]
    ioctl.restype = ctypes.c_int
    target, printable = (
        ("\\??\\" + str(outside)).encode("utf-16-le"),
        str(outside).encode("utf-16-le"),
    )
    names = target + b"\0\0" + printable + b"\0\0"
    data = (
        struct.pack(
            "<IHHHHHH",
            0xA0000003,
            8 + len(names),
            0,
            0,
            len(target),
            len(target) + 2,
            len(printable),
        )
        + names
    )
    handle = api.functions["CreateFileW"](str(root), 0x100, 3, None, 3, 0x02200000, None)
    assert handle != ctypes.c_void_p(-1).value
    try:
        result, buffer = ctypes.c_uint32(), ctypes.create_string_buffer(data)
        assert ioctl(handle, 0x900A4, buffer, len(data), None, 0, ctypes.byref(result), None)
    finally:
        api.close(handle)


@pytest.mark.parametrize("stage", ["enumeration", "ancestor"])
def test_actual_reparse_mutation_cannot_enumerate_or_open_outside(tmp_path, monkeypatch, stage):
    anchor, outside = tmp_path / "anchor", tmp_path / "outside"
    anchor.mkdir()
    outside.mkdir()
    leaf = anchor / "leaf"
    if stage == "ancestor":
        leaf.mkdir()
        (outside / "leaf").mkdir()
        marker = outside / "leaf" / "outside-marker.txt"
    else:
        marker = outside / "outside-marker.txt"
    marker.write_bytes(b"synthetic")
    api = _Api()
    scan = NativeInventory(api=api).scan(Scope((str(leaf if stage == "ancestor" else anchor),)))
    linked = False
    real_metadata, real_scandir = api.metadata, os.scandir
    outside_reads = []

    def metadata(handle):
        nonlocal linked
        path = api.final_path(handle)
        if "outside" in path:
            outside_reads.append(path)
        value = real_metadata(handle)
        if stage == "ancestor" and not linked and path.endswith("\\anchor"):
            leaf.rmdir()
            set_junction(api, anchor, outside)
            linked = True
        return value

    def scandir(path):
        with real_scandir(path) as entries:
            outside_reads.extend(entry.name for entry in entries)
        return real_scandir(path)

    monkeypatch.setattr(api, "metadata", metadata)
    monkeypatch.setattr(os, "scandir", scandir)
    try:
        if stage == "enumeration":
            next(scan)
            set_junction(api, anchor, outside)
            linked = True
        values = list(scan)
        assert linked
        assert not outside_reads
        assert any(value.error_code for value in values)
    finally:
        scan.close()
        if linked:
            anchor.rmdir()
