"""Minimal named-field Security evidence. No localized Message or raw XML retention."""

import ipaddress
import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated, Literal, cast
from uuid import UUID
from xml.etree import ElementTree as ET

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

Text = Annotated[str, Field(min_length=1, max_length=32768)]
Number = Annotated[int, Field(ge=0, le=2**64 - 1, strict=True)]
NS = "{http://schemas.microsoft.com/win/2004/08/events/event}"
AUDITING = UUID("54849625-5478-4994-a5ba-3e3b0328c30d")
EVENTLOG = UUID("fc65ddd8-d6ef-4962-83d5-6e5cfe9ce148")
VERSIONS = {4663: {0, 1}, 4660: {0}, 4624: {0, 1, 2}, 1102: {0}}


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    host_id: UUID
    boot_id: Text
    generation: UUID
    channel: Literal["Security"] = "Security"
    record_id: Annotated[int, Field(gt=0, le=2**63 - 1)]
    provider: UUID
    event_id: Literal[4663, 4660, 4624, 1102]
    version: Annotated[int, Field(ge=0, le=2)]
    occurred_at: AwareDatetime
    sid: Text | None = None
    domain: Text | None = None
    account: Text | None = None
    logon_id: Number | None = None
    handle_id: Number | None = None
    process_id: Number | None = None
    process_name: Text | None = None
    object_type: Text | None = None
    path: Text | None = None
    access_mask: Number | None = None
    logon_type: Number | None = None
    client_ip: Text | None = None
    workstation: Text | None = None
    quality: Literal["COMPLETE", "PARTIAL"] = "PARTIAL"
    volume_id: Text | None = None
    path_quality: Literal["UNKNOWN"] = "UNKNOWN"
    linked_record_ids: list[int] = Field(default_factory=list, max_length=8)

    def digest(self) -> str:
        return sha256(
            json.dumps(
                self.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()


def parse_event(
    xml: str,
    *,
    host_id: UUID,
    boot_id: str,
    generation: UUID,
) -> AuditEvent | None:
    if len(xml) > 262144 or "<!" in xml:
        return None
    try:
        root = ET.fromstring(xml)
        if root.tag != NS + "Event":
            return None
        system = root.find(NS + "System")
        if system is None or system.findtext(NS + "Channel") != "Security":
            return None
        event_id = int(system.findtext(NS + "EventID", "0"))
        version = int(system.findtext(NS + "Version", "0"))
        provider_node, time_node = system.find(NS + "Provider"), system.find(NS + "TimeCreated")
        if provider_node is None or time_node is None:
            return None
        timestamp = datetime.fromisoformat(time_node.attrib["SystemTime"])
        if timestamp.tzinfo is None:
            return None
        provider = UUID(provider_node.attrib["Guid"].strip("{}"))
        if version not in VERSIONS.get(event_id, set()) or provider != (
            EVENTLOG if event_id == 1102 else AUDITING
        ):
            return None
        fields: dict[str, str | None] = {}
        for node in root.findall(f"{NS}EventData/{NS}Data"):
            name = node.attrib.get("Name", "")
            if name in fields:
                return None
            fields[name] = node.text if node.text not in {None, "", "-"} else None
        partial = False

        def number(name: str) -> int | None:
            nonlocal partial
            value = fields.get(name)
            try:
                result = int(value, 16 if value.lower().startswith("0x") else 10) if value else 0
                if not 0 < result < 2**64:
                    partial = True
                    return None
                return result
            except ValueError:
                partial = True
                return None

        prefix = "Target" if event_id == 4624 else "Subject"
        sid, logon = fields.get(prefix + "UserSid"), number(prefix + "LogonId")
        ip = fields.get("IpAddress") if event_id == 4624 else None
        if ip:
            try:
                address = ipaddress.ip_address(ip)
                ip = None if address.is_unspecified or address.is_loopback else str(address)
            except ValueError:
                ip, partial = None, True
        handle = number("HandleId") if event_id in {4663, 4660} else None
        process = number("ProcessId") if event_id in {4663, 4660} else None
        mask = number("AccessMask") if event_id == 4663 else None
        kind = number("LogonType") if event_id == 4624 else None
        path = fields.get("ObjectName") if event_id == 4663 else None
        partial |= (
            not sid
            or not logon
            or (event_id in {4663, 4660} and (handle is None or process is None))
            or (event_id == 4663 and (mask is None or path is None))
        )
        return AuditEvent(
            host_id=host_id,
            boot_id=boot_id,
            generation=generation,
            provider=provider,
            record_id=int(system.findtext(NS + "EventRecordID", "0")),
            event_id=cast(Literal[4663, 4660, 4624, 1102], event_id),
            version=version,
            occurred_at=timestamp.astimezone(UTC),
            sid=sid,
            domain=fields.get(prefix + "DomainName"),
            account=fields.get(prefix + "UserName"),
            logon_id=logon,
            handle_id=handle,
            process_id=process,
            process_name=fields.get("ProcessName") if event_id != 4624 else None,
            object_type=fields.get("ObjectType") if event_id == 4663 else None,
            path=path,
            access_mask=mask,
            logon_type=kind,
            client_ip=ip,
            workstation=fields.get("WorkstationName") if event_id == 4624 else None,
            quality="PARTIAL" if partial else "COMPLETE",
        )
    except (ET.ParseError, KeyError, ValueError, OverflowError, ValidationError):
        return None
