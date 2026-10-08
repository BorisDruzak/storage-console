import struct
from datetime import UTC, datetime

import pytest

from collectors.windows.usn import UsnError, parse_buffer


def record(version=2, *, name="Отчёт.txt", usn=32, reason=0x80000100):
    ids = (17).to_bytes(8 if version == 2 else 16, "little")
    parent = (9).to_bytes(len(ids), "little")
    offset = 60 if version == 2 else 76
    encoded = name.encode("utf-16-le")
    length = (offset + len(encoded) + 7) & ~7
    stamp = 134358912000000000  # 2026-10-08 UTC FILETIME.
    header = struct.pack("<IHH", length, version, 0) + ids + parent
    header += struct.pack("<qqIIIIHH", usn, stamp, reason, 0, 0, 0, len(encoded), offset)
    return header + encoded + bytes(length - offset - len(encoded))


@pytest.mark.parametrize("version", [2, 3])
def test_versions_preserve_inventory_id_reason_and_utc(version):
    cursor, records = parse_buffer(struct.pack("<q", 128) + record(version))
    assert cursor == 128
    assert len(records) == 1
    item = records[0]
    assert item.file_id == (17).to_bytes(16, "little").hex()
    assert item.parent_id == (9).to_bytes(16, "little").hex()
    assert item.name == "Отчёт.txt"
    assert item.reason == 0x80000100 and item.usn == 32
    assert item.occurred_at == datetime(2026, 10, 8, tzinfo=UTC)


@pytest.mark.parametrize("data", [b"", bytes(7), struct.pack("<q", -1),
    struct.pack("<q", 128) + record()[:-1],
    struct.pack("<q", 128) + struct.pack("<IHH", 8, 2, 0),
    struct.pack("<q", 128) + record(name="../outside"),
    struct.pack("<q", 128) + record(name="bad\\outside"),
    struct.pack("<q", 128) + record(name="\0secret")])
def test_malformed_buffers_never_return_partial_records(data):
    with pytest.raises(UsnError, match="^USN_MALFORMED$"):
        parse_buffer(data)


def test_unsupported_record_is_explicit_and_no_partial_success():
    bad = bytearray(record())
    struct.pack_into("<H", bad, 4, 4)
    with pytest.raises(UsnError, match="^USN_UNSUPPORTED$"):
        parse_buffer(struct.pack("<q", 256) + record() + bad)


def test_offsets_utf16_order_and_size_are_strict():
    valid = record()
    for offset, fmt, value in [(56, "H", 3), (58, "H", 2), (0, "I", 61)]:
        bad = bytearray(valid)
        struct.pack_into("<" + fmt, bad, offset, value)
        with pytest.raises(UsnError, match="^USN_MALFORMED$"):
            parse_buffer(struct.pack("<q", 128) + bad)
    with pytest.raises(UsnError, match="^USN_MALFORMED$"):
        parse_buffer(struct.pack("<q", 32) + valid)
    with pytest.raises(UsnError, match="^USN_MALFORMED$"):
        parse_buffer(struct.pack("<q", 256) + record(usn=64) + record(usn=32))


def test_largest_legal_component_and_128_bit_v3_id():
    value = bytearray(record(3, name="я" * 255))
    value[8:24] = bytes(range(16))
    _, records = parse_buffer(struct.pack("<q", 128) + value)
    assert records[0].file_id == bytes(range(16)).hex()
    assert records[0].name == "я" * 255


def test_empty_end_of_journal_and_bounded_output():
    assert parse_buffer(struct.pack("<q", 128)) == (128, ())
    with pytest.raises(UsnError, match="^USN_MALFORMED$"):
        parse_buffer(bytes(1024 * 1024 + 1))
