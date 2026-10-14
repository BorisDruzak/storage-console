"""Reuse immutable ABI/SID decoding, never cache security or ancestry decisions."""

import ctypes
from collections import OrderedDict
from types import SimpleNamespace

import pytest

from collectors.windows_audit import native, readiness


def test_typed_ancestry_reader_rechecks_every_parent_and_leaf(monkeypatch):
    calls = []
    blocked = set()

    def attributes(path):
        calls.append(path)
        return 0x410 if path in blocked else 0x10

    monkeypatch.setattr(ctypes, "get_last_error", lambda: 0, raising=False)
    path = r"C:\synthetic\owned\leaf.txt"
    assert native.no_reparse_ancestry(path, attributes=attributes)
    expected = list(calls)
    assert expected == ["C:\\", r"C:\synthetic", r"C:\synthetic\owned", path]
    blocked.add(r"C:\synthetic\owned")
    calls.clear()
    assert not native.no_reparse_ancestry(path, attributes=attributes)
    assert calls == expected[:-1]


@pytest.mark.parametrize("error,allowed", [(2, True), (5, False), (3, False)])
def test_typed_ancestry_reader_keeps_deleted_leaf_privacy_rules(monkeypatch, error, allowed):
    path = r"C:\synthetic\leaf.txt"
    monkeypatch.setattr(ctypes, "get_last_error", lambda: error, raising=False)
    assert (
        native.no_reparse_ancestry(
            path, attributes=lambda name: 0xFFFFFFFF if name == path else 0x10
        )
        is allowed
    )


def test_sacl_uses_its_existing_typed_reader(monkeypatch):
    def reader(_):
        return 0x10

    instance = object.__new__(readiness.Native)
    instance.kernel = SimpleNamespace(GetFileAttributesW=reader)
    instance.api = SimpleNamespace(GetNamedSecurityInfoW=lambda *_: 5)
    used = []

    def guard(path, *, attributes):
        used.append(attributes)
        return True

    monkeypatch.setattr(readiness, "no_reparse_ancestry", guard)
    with pytest.raises(ValueError, match="AUDIT_READINESS_UNKNOWN"):
        instance.sacl_entry(r"C:\synthetic", ["synthetic-sid"], True)
    assert used == [reader]


def sid_fixture():
    instance = object.__new__(readiness.Native)
    instance._sid_cache = OrderedDict()
    calls = []
    buffers = []

    def convert(pointer, output):
        calls.append(ctypes.string_at(pointer, 8))
        text = ctypes.create_unicode_buffer("synthetic-" + calls[-1].hex())
        buffers.append(text)
        ctypes.cast(output, ctypes.POINTER(ctypes.c_wchar_p))[0] = ctypes.cast(
            text, ctypes.c_wchar_p
        )
        return 1

    instance.api = SimpleNamespace(ConvertSidToStringSidW=convert)
    instance.kernel = SimpleNamespace(LocalFree=lambda _: None)
    return instance, calls, buffers


def test_identical_sid_bytes_decode_once_even_at_a_different_address():
    instance, calls, buffers = sid_fixture()
    first = ctypes.create_string_buffer(b"12345678")
    second = ctypes.create_string_buffer(b"12345678")
    assert instance._sid_text(ctypes.addressof(first), 8) == instance._sid_text(
        ctypes.addressof(second), 8
    )
    assert len(calls) == len(buffers) == 1


def test_sid_decoder_is_bounded_and_does_not_cache_pointer_identity():
    instance, calls, _ = sid_fixture()
    memory = ctypes.create_string_buffer(8)
    for number in range(300):
        memory.raw = number.to_bytes(8, "little")
        assert instance._sid_text(ctypes.addressof(memory), 8) == "synthetic-" + memory.raw.hex()
        assert len(instance._sid_cache) <= 256
    memory.raw = (0).to_bytes(8, "little")
    assert instance._sid_text(ctypes.addressof(memory), 8) == "synthetic-" + memory.raw.hex()
    assert len(calls) == 301


def test_failed_sid_conversion_never_becomes_cached_proof():
    instance, calls, _ = sid_fixture()
    memory = ctypes.create_string_buffer(b"12345678")
    convert = instance.api.ConvertSidToStringSidW
    instance.api.ConvertSidToStringSidW = lambda *_: 0
    assert instance._sid_text(ctypes.addressof(memory), 8) is None
    assert not instance._sid_cache
    instance.api.ConvertSidToStringSidW = convert
    assert instance._sid_text(ctypes.addressof(memory), 8) == "synthetic-3132333435363738"
    assert len(calls) == 1
