"""Synthetic kernel boot records; changing wall-clock boot estimates are not epochs."""

import ctypes
from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace

import pytest

from collectors.windows_audit import native

PROVIDER = "{a68ca8b7-004f-d7b6-a698-07e2de0f1f5d}"
START = "2026-10-01T00:00:00Z"


def boot_xml(
    record=10, start=START, provider=PROVIDER, channel="System", written="2026-10-01T00:00:01Z"
):
    return (
        '<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">'
        f'<System><Provider Guid="{provider}"/><EventID>12</EventID>'
        f'<TimeCreated SystemTime="{written}"/>'
        f"<EventRecordID>{record}</EventRecordID><Channel>{channel}</Channel></System>"
        f'<EventData><Data Name="StartTime">{start}</Data></EventData></Event>'
    )


def fixture(monkeypatch, value, *, drift=0, available=True):
    closed, queried = [], []

    def next_event(query, size, handles, timeout, flags, count):
        assert size == 1 and timeout == 1000 and flags == 0
        if not available:
            return False
        handles[0], count._obj.value = 2, 1
        return True

    def query(*args):
        queried.append(args)
        return 1

    dll = SimpleNamespace(EvtQuery=query, EvtNext=next_event, EvtClose=closed.append)
    monkeypatch.setattr(native, "api", lambda: dll)
    monkeypatch.setattr(native, "render", lambda *_: value)
    monkeypatch.setattr(native, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 259, raising=False)
    ticks = int(
        (datetime(2026, 10, 1, tzinfo=UTC) - datetime(1601, 1, 1, tzinfo=UTC)).total_seconds()
        * 10**7
    )

    class QueryTime:
        def __call__(self, kind, pointer, size, used):
            assert kind == 3
            pointer._obj.boot = ticks + drift
            return 0

    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *_: SimpleNamespace(NtQuerySystemInformation=QueryTime()),
        raising=False,
    )
    return closed, queried


def test_clock_adjustment_does_not_change_boot_epoch(monkeypatch):
    value = boot_xml()
    closed, queried = fixture(monkeypatch, value)
    first = native.boot_epoch()
    assert first == (
        "kernel-boot:" + sha256(value.encode()).hexdigest(),
        datetime(2026, 10, 1, tzinfo=UTC),
    )
    assert closed == [2, 1]
    assert queried[0][1] == "System" and queried[0][3] == 0x201
    fixture(monkeypatch, value, drift=3820)
    assert native.boot_epoch() == first


def test_actual_new_boot_changes_epoch(monkeypatch):
    fixture(monkeypatch, boot_xml(record=10))
    before = native.boot_epoch()[0]
    fixture(
        monkeypatch,
        boot_xml(record=11, start="2026-10-01T00:10:00Z", written="2026-10-01T00:10:01Z"),
        drift=600 * 10**7,
    )
    assert native.boot_epoch()[0] != before


@pytest.mark.parametrize(
    "value",
    [
        boot_xml(provider="{00000000-0000-0000-0000-000000000000}"),
        boot_xml(channel="Security"),
        boot_xml(start="invalid"),
        boot_xml(start="2026-10-01T00:00:00"),
        boot_xml(record=0),
        "<Event/>",
    ],
)
def test_invalid_boot_witness_fails_closed_and_closes_handles(monkeypatch, value):
    closed, _ = fixture(monkeypatch, value)
    with pytest.raises(native.EventLogError):
        native.boot_epoch()
    assert closed == [2, 1]


def test_missing_or_previous_boot_witness_never_uses_wall_clock_fallback(monkeypatch):
    closed, _ = fixture(monkeypatch, boot_xml(), available=False)
    with pytest.raises(native.EventLogError):
        native.boot_epoch()
    assert closed == [1]
    closed, _ = fixture(monkeypatch, boot_xml(), drift=60 * 10**7)
    with pytest.raises(native.EventLogError):
        native.boot_epoch()
    assert closed == [2, 1]
