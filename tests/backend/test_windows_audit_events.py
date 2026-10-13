"""Synthetic named-field fixtures; never production Security XML."""

import importlib
from datetime import UTC, datetime
from uuid import UUID

import pytest

HOST = UUID(int=1)
GEN = UUID(int=2)
PROVIDER = "{54849625-5478-4994-a5ba-3e3b0328c30d}"


def module(name):
    try:
        result = importlib.import_module("collectors.windows_audit." + name)
    except ModuleNotFoundError:
        result = None
    assert result is not None, "independent Audit collector module is missing"
    return result


def xml(kind=4663, record=10, version=0, provider=PROVIDER, **fields):
    from xml.sax.saxutils import escape

    defaults = {
        "SubjectUserSid": "S-1-5-21-100-200-300-1001",
        "SubjectUserName": "UserA",
        "SubjectDomainName": "SYNTHETIC",
        "SubjectLogonId": "0x101",
        "HandleId": "0x31",
        "ProcessId": "0x40",
    }
    if kind == 4663:
        defaults.update(ObjectType="File", ObjectName=r"C:\Pilot\Отчёт.txt", AccessMask="0x6")
    if kind == 4624:
        defaults = {
            "TargetUserSid": "S-1-5-21-100-200-300-1001",
            "TargetUserName": "UserA",
            "TargetDomainName": "SYNTHETIC",
            "TargetLogonId": "0x101",
            "LogonType": "3",
            "IpAddress": "-",
            "WorkstationName": "-",
        }
    defaults.update(fields)
    data = "".join(
        f'<Data Name="{key}">{escape(value)}</Data>'
        for key, value in reversed(list(defaults.items()))
    )
    return (
        f'<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">'
        f'<System><Provider Guid="{provider}"/><EventID>{kind}</EventID>'
        f'<Version>{version}</Version><TimeCreated SystemTime="2026-10-13T00:00:00Z"/>'
        f"<EventRecordID>{record}</EventRecordID><Channel>Security</Channel></System>"
        f"<EventData>{data}</EventData><RenderingInfo><Message>ignored</Message>"
        "</RenderingInfo></Event>"
    )


def parse(value):
    return module("events").parse_event(value, host_id=HOST, boot_id="boot-a", generation=GEN)


def test_4663_named_fields_hex_cyrillic_not_localized_message():
    event = parse(xml(version=1))
    assert event.event_id == 4663 and event.record_id == 10
    assert event.path == r"C:\Pilot\Отчёт.txt"
    assert event.logon_id == 257 and event.handle_id == 49 and event.process_id == 64
    assert event.access_mask == 6 and event.account == "UserA"
    assert event.occurred_at == datetime(2026, 10, 13, tzinfo=UTC)
    assert "ignored" not in event.model_dump_json()


def test_4660_has_no_fabricated_path_zero_handle_is_null():
    event = parse(xml(4660, HandleId="0x0"))
    assert event.path is None and event.handle_id is None


@pytest.mark.parametrize("version", [0, 1, 2, 3])
def test_network_session_versions_missing_client_stays_null(version):
    event = parse(xml(4624, version=version))
    assert event.logon_type == 3 and event.logon_id == 257
    assert event.client_ip is None and event.workstation is None


def test_network_session_version_3_preserves_named_identity_and_minimal_contract():
    from packages.contracts.audit import AuditInput

    event = parse(xml(
        4624, record=1, version=3, IpAddress="192.0.2.10",
        RemoteCredentialGuard="-", TargetLinkedLogonId="0x0",
    ))
    assert event is not None
    assert event.version == 3 and event.logon_type == 3 and event.logon_id == 257
    assert event.client_ip == "192.0.2.10" and event.workstation is None
    payload = event.model_dump(mode="json")
    assert "RemoteCredentialGuard" not in payload and "TargetLinkedLogonId" not in payload
    assert AuditInput.model_validate({**payload, "digest": event.digest()}).event() == event
    selector = module("scope").Selector(module("scope").AuditScope({r"C:\Pilot": "volume-a"}))
    assert selector.process(event) == []
    linked = selector.process(parse(xml(record=2)))
    assert [e.event_id for e in linked] == [4624, 4663]


def test_unknown_logon_version_4_and_other_version_3_events_stay_rejected():
    from packages.contracts.audit import AuditEvent

    assert parse(xml(4624, version=4)) is None
    for kind in (4663, 4660, 1102):
        assert parse(xml(kind, version=3)) is None
    with pytest.raises(ValueError, match="AUDIT_EVENT_VERSION_UNSUPPORTED"):
        AuditEvent.model_validate({**parse(xml()).model_dump(), "version": 3})


@pytest.mark.parametrize(
    "value",
    [
        xml(version=99),
        xml(provider=str(UUID(int=3))),
        xml(5145),
        xml().replace("Security</Channel", "Application</Channel"),
        '<!DOCTYPE Event [<!ENTITY x "unsafe">]><Event/>',
    ],
)
def test_unknown_schema_channel_provider_and_entities_are_rejected(value):
    assert parse(value) is None


def test_clear_signal_uses_eventlog_provider_not_auditing_provider():
    event = parse(xml(1102, provider="{fc65ddd8-d6ef-4962-83d5-6e5cfe9ce148}"))
    assert event.event_id == 1102


def test_bad_optional_integer_does_not_kill_service_or_invent_evidence():
    event = parse(xml(AccessMask="invalid", ProcessId="-"))
    assert event.access_mask is None and event.process_id is None and event.quality == "PARTIAL"


def test_scope_boundary_aliases_registry_traversal_ads_are_not_leaked():
    scope = module("scope").AuditScope({r"C:\Pilot": "volume-a", r"D:\Alias": "volume-a"})
    assert scope.select(parse(xml())).volume_id == "volume-a"
    assert scope.select(parse(xml(ObjectName=r"d:\alias\a.txt"))).path_quality == "UNKNOWN"
    for path in (
        r"C:\PilotSibling\a.txt",
        r"C:\Pilot\..\private\a.txt",
        r"C:\Pilot\a.txt:secret",
        r"\\server\Pilot\a.txt",
    ):
        assert scope.select(parse(xml(ObjectName=path))) is None
    assert scope.select(parse(xml(ObjectType="Key"))) is None


def test_session_and_delete_only_leave_machine_when_linked_to_scoped_access():
    selector = module("scope").Selector(module("scope").AuditScope({r"C:\Pilot": "volume-a"}))
    assert selector.process(parse(xml(4624, record=1))) == []
    assert selector.process(parse(xml(4660, record=2))) == []
    accepted = selector.process(parse(xml(record=3, AccessMask="0x10000")))
    assert {e.event_id for e in accepted} == {4624, 4663}
    deleted = selector.process(parse(xml(4660, record=4)))
    assert [e.event_id for e in deleted] == [4660]
    assert deleted[0].path is None and deleted[0].linked_record_ids == [3]


def test_reused_handle_boot_process_sid_and_ambiguous_paths_do_not_leak_delete():
    selector = module("scope").Selector(module("scope").AuditScope({r"C:\Pilot": "volume-a"}))
    selector.process(parse(xml(record=1, AccessMask="0x10000")))
    selector.process(parse(xml(record=2, ObjectName=r"C:\Pilot\other.txt", AccessMask="0x10000")))
    assert selector.process(parse(xml(4660, record=3))) == []
    assert selector.process(parse(xml(4660, record=4, ProcessId="0x41"))) == []


def test_out_of_order_delete_is_released_only_after_earlier_scoped_access():
    selector = module("scope").Selector(module("scope").AuditScope({r"C:\Pilot": "volume-a"}))
    assert selector.process(parse(xml(4660, record=4))) == []
    assert {e.event_id for e in selector.process(parse(xml(record=3, AccessMask="0x10000")))} == {
        4663,
        4660,
    }


def test_naive_timestamp_never_assumes_collector_local_timezone():
    assert parse(xml().replace("2026-10-13T00:00:00Z", "2026-10-13T00:00:00")) is None


def test_session_identity_is_immutable_across_two_different_scoped_accesses():
    api = module("scope")
    selector = api.Selector(api.AuditScope({r"C:\Pilot": "volume-a"}))
    selector.process(parse(xml(4624, record=1)))
    first = [e for e in selector.process(parse(xml(record=3))) if e.event_id == 4624][0]
    second = [e for e in selector.process(parse(xml(record=4))) if e.event_id == 4624][0]
    assert first.digest() == second.digest()


def test_outside_scope_handle_reuse_cannot_release_unrelated_delete():
    api = module("scope")
    selector = api.Selector(api.AuditScope({r"C:\Pilot": "volume-a"}))
    selector.process(parse(xml(record=1, AccessMask="0x10000")))
    selector.process(parse(xml(record=2, ObjectName=r"C:\Private\outside.txt")))
    assert selector.process(parse(xml(4660, record=3))) == []
    assert "Private" not in str(selector.snapshot())


def test_unicode_linguistic_fold_does_not_merge_distinct_windows_names():
    api = module("scope")
    scope = api.AuditScope({r"C:\Pilot\Straße": "volume-a"})
    assert scope.select(parse(xml(ObjectName=r"C:\Pilot\STRASSE\outside.txt"))) is None
    assert scope.select(parse(xml(ObjectName=r"c:\PILOT\straße\inside.txt"))) is not None


def test_tombstone_eviction_cannot_resurrect_invalidated_scoped_handle():
    api = module("scope")
    selector = api.Selector(api.AuditScope({r"C:\Pilot": "volume-a"}), capacity=2)
    selector.process(parse(xml(record=1, AccessMask="0x10000")))
    selector.process(parse(xml(record=2, ObjectName=r"C:\Private\outside.txt")))
    for i in range(3, 6):
        selector.process(
            parse(xml(record=i, ObjectName=r"C:\Private\outside.txt", HandleId=hex(i)))
        )
    assert selector.process(parse(xml(4660, record=6))) == []
