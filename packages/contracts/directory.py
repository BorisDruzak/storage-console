"""Bounded current directory observations, separate from immutable audit evidence."""

import ipaddress
import re
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, ConfigDict, Field, field_validator, model_validator

from .common import Contract

Sid = Annotated[str, Field(pattern=r"^S-1-5-21-[0-9]{1,10}-[0-9]{1,10}-[0-9]{1,10}-[0-9]{1,10}$")]
DirectoryText = Annotated[str, Field(min_length=1, max_length=1024, strict=True)]
Failure = Literal["LDAP_UNAVAILABLE", "DIRECTORY_LIMIT", "DIRECTORY_STOPPED"]
ClientReason = Literal[
    "DNS_UNAVAILABLE",
    "PTR_MISSING",
    "FORWARD_MISMATCH",
    "DOMAIN_MISMATCH",
    "COMPUTER_MISSING",
    "COMPUTER_DISABLED",
    "MULTIPLE_MATCHES",
    "LDAP_UNAVAILABLE",
    "LOCAL_ADDRESS",
    "LOOKUP_LIMIT",
]


def dns_name(value: str) -> str:
    if not value.isascii() or len(value) > 253 or len(value.split(".")) < 2:
        raise ValueError("DIRECTORY_DNS_INVALID")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise ValueError("DIRECTORY_DNS_INVALID")
    if not all(
        re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
        for label in value.split(".")
    ):
        raise ValueError("DIRECTORY_DNS_INVALID")
    return value.lower()


def normalized_ip(value: str) -> str:
    if "%" in value or len(value) > 45:
        raise ValueError("DIRECTORY_IP_INVALID")
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return str(address.ipv4_mapped)
    return str(address)


class DirectoryScope(Contract):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    dns_domain: Annotated[str, Field(min_length=3, max_length=253, strict=True)]
    domain_sid: Annotated[
        str,
        Field(
            pattern=r"^S-1-5-21-[0-9]{1,10}-[0-9]{1,10}-[0-9]{1,10}$",
            strict=True,
        ),
    ]

    @field_validator("dns_domain")
    @classmethod
    def domain_name(cls, value: str) -> str:
        return dns_name(value)


class DirectoryUser(Contract):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    sid: Sid
    object_guid: UUID
    account: Annotated[str, Field(min_length=1, max_length=255, strict=True)]
    upn: DirectoryText | None = None
    display_name: DirectoryText | None = None
    enabled: Annotated[bool, Field(strict=True)]
    primary_group_id: Annotated[int, Field(ge=1, le=2**32 - 1, strict=True)]

    @field_validator("account", "upn", "display_name")
    @classmethod
    def plain_metadata(cls, value: str | None) -> str | None:
        if value is not None and (not value.isprintable() or len(value.encode("utf8")) > 4096):
            raise ValueError("DIRECTORY_TEXT_INVALID")
        return value


class DirectoryPage(Contract):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    collector_id: UUID
    batch_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    snapshot_id: UUID
    schema_version: Literal[1]
    sent_at: AwareDatetime
    observed_at: AwareDatetime
    scope: DirectoryScope
    page_index: Annotated[int, Field(ge=0, le=511, strict=True)]
    records: Annotated[list[DirectoryUser], Field(max_length=256)]
    finished: Annotated[bool, Field(strict=True)] = False
    complete: Annotated[bool, Field(strict=True)] = False
    total_records: Annotated[int, Field(ge=0, le=100000, strict=True)] | None = None
    error_code: Failure | None = None

    @model_validator(mode="after")
    def coherent_page(self) -> Self:
        if self.observed_at > self.sent_at:
            raise ValueError("DIRECTORY_TIME_INVALID")
        if self.finished:
            if self.total_records is None or self.complete != (self.error_code is None):
                raise ValueError("DIRECTORY_TERMINAL_INVALID")
        elif self.complete or self.error_code or self.total_records is not None:
            raise ValueError("DIRECTORY_TERMINAL_INVALID")
        if any(not row.sid.startswith(self.scope.domain_sid + "-") for row in self.records):
            raise ValueError("DIRECTORY_DOMAIN_CONFLICT")
        if len({row.sid for row in self.records}) != len(self.records) or len(
            {row.object_guid for row in self.records}
        ) != len(self.records):
            raise ValueError("DIRECTORY_IDENTITY_CONFLICT")
        return self


class ClientNameObservation(Contract):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    collector_id: UUID
    batch_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    schema_version: Literal[1]
    sent_at: AwareDatetime
    scope: DirectoryScope
    client_ip: Annotated[str, Field(min_length=1, max_length=45, strict=True)]
    observed_at: AwareDatetime
    expires_at: AwareDatetime
    status: Literal["CONFIRMED_CURRENT", "UNKNOWN", "AMBIGUOUS"]
    reason: ClientReason | None = None
    ptr_name: Annotated[str, Field(min_length=3, max_length=253)] | None = None
    forward_addresses: Annotated[list[str], Field(max_length=16)] = Field(default_factory=list)
    computer_sid: Sid | None = None
    computer_guid: UUID | None = None
    computer_name: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    enabled: Annotated[bool, Field(strict=True)] | None = None

    @model_validator(mode="after")
    def corresponding_witnesses(self) -> Self:
        ip = normalized_ip(self.client_ip)
        addresses = {normalized_ip(value) for value in self.forward_addresses}
        ttl = (self.expires_at - self.observed_at).total_seconds()
        if self.observed_at > self.sent_at or not 0 < ttl <= 900:
            raise ValueError("DIRECTORY_TIME_INVALID")
        if self.status == "CONFIRMED_CURRENT":
            address = ipaddress.ip_address(ip)
            if (
                self.reason is not None
                or ip not in addresses
                or not self.enabled
                or not self.computer_guid
                or not self.computer_name
                or not self.computer_sid
                or not self.computer_sid.startswith(self.scope.domain_sid + "-")
                or self.ptr_name is None
                or not dns_name(self.ptr_name).endswith("." + self.scope.dns_domain)
                or address.is_loopback
                or address.is_unspecified
                or address.is_multicast
            ):
                raise ValueError("DIRECTORY_CLIENT_UNCONFIRMED")
            if not self.computer_name.isprintable():
                raise ValueError("DIRECTORY_TEXT_INVALID")
        elif (
            self.reason is None
            or ttl > 30
            or self.computer_sid
            or self.computer_guid
            or self.computer_name
            or self.enabled is not None
        ):
            raise ValueError("DIRECTORY_CLIENT_UNCONFIRMED")
        return self


class AccountObservation(Contract):
    state: Literal["CURRENT", "STALE", "UNKNOWN", "PARTIAL", "ERROR"]
    observed_at: AwareDatetime | None = None
    snapshot_id: UUID | None = None
    user: DirectoryUser | None = None
    latest_attempt_state: Literal["COLLECTING", "COMPLETE", "ERROR"] | None = None
    valid_for_ms: Annotated[int, Field(ge=0, le=900000)] = 0
    provenance: Literal["LDAP_KERBEROS_SIGNED_SEALED"] = "LDAP_KERBEROS_SIGNED_SEALED"


class ClientObservation(Contract):
    state: Literal["CONFIRMED_CURRENT", "STALE", "UNKNOWN", "AMBIGUOUS"]
    observed_at: AwareDatetime | None = None
    expires_at: AwareDatetime | None = None
    computer_name: str | None = None
    ptr_name: str | None = None
    computer_sid: str | None = None
    computer_guid: UUID | None = None
    reason: ClientReason | None = None
    valid_for_ms: Annotated[int, Field(ge=0, le=900000)] = 0
    provenance: Literal["DNS_PTR_FORWARD_AD_CURRENT"] = "DNS_PTR_FORWARD_AD_CURRENT"
    event_time_confirmed: Literal[False] = False


class DirectoryStream(Contract):
    state: Literal["NOT_CONFIGURED", "CURRENT", "STALE", "UNKNOWN", "PARTIAL", "ERROR"]
    evaluated_at: AwareDatetime
    scope: DirectoryScope | None = None
    observed_at: AwareDatetime | None = None
    latest_attempt_at: AwareDatetime | None = None
    user_count: Annotated[int, Field(ge=0, le=100000)] | None = None
    error_code: Failure | None = None
    valid_for_ms: Annotated[int, Field(ge=0, le=900000)] = 0
