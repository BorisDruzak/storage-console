"""Current DNS/AD correspondence only; no native evidence or confidence changes."""

import ipaddress
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from packages.contracts.directory import (
    ClientNameObservation,
    ClientReason,
    DirectoryScope,
    dns_name,
    normalized_ip,
)


class LookupError(Exception):
    def __init__(self, code: ClientReason) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DnsRecord:
    value: str
    ttl: int


@dataclass(frozen=True)
class Computer:
    sid: str
    guid: UUID
    name: str
    dns_hostname: str
    enabled: bool


@dataclass(frozen=True)
class Witnesses:
    ptr: list[DnsRecord]
    forward: list[DnsRecord]
    computers: list[Computer]


class Lookup(Protocol):
    def lookup(self, ip: str, scope: DirectoryScope) -> Witnesses: ...


class ClientResolver:
    def __init__(
        self,
        collector_id: UUID,
        scope: DirectoryScope,
        lookup: Lookup,
        *,
        max_entries: int = 512,
        max_bytes: int = 1024**2,
    ) -> None:
        if not 1 <= max_entries <= 512 or not 4096 <= max_bytes <= 1024**2:
            raise ValueError("DIRECTORY_CACHE_LIMIT_INVALID")
        self.collector_id, self.scope, self.lookup = collector_id, scope, lookup
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self._entries: OrderedDict[str, bytes] = OrderedDict()
        self._bytes = 0

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def byte_count(self) -> int:
        return self._bytes

    def _unknown(
        self, original: str, now: datetime, reason: ClientReason, *, ambiguous: bool = False
    ) -> ClientNameObservation:
        return ClientNameObservation(
            collector_id=self.collector_id,
            batch_id=uuid4().hex,
            schema_version=1,
            scope=self.scope,
            client_ip=original,
            observed_at=now,
            sent_at=now,
            expires_at=now + timedelta(seconds=30),
            status="AMBIGUOUS" if ambiguous else "UNKNOWN",
            reason=reason,
        )

    def resolve(self, original: str, *, now: datetime | None = None) -> ClientNameObservation:
        at = now or datetime.now(UTC)
        if at.tzinfo is None:
            raise ValueError("DIRECTORY_TIME_INVALID")
        key = normalized_ip(original)
        cached = self._entries.get(key)
        if cached is not None:
            value = ClientNameObservation.model_validate_json(cached)
            if value.observed_at <= at < value.expires_at:
                self._entries.move_to_end(key)
                return value
            self._bytes -= len(self._entries.pop(key))
        address = ipaddress.ip_address(key)
        if address.is_loopback or address.is_unspecified or address.is_multicast:
            value = self._unknown(original, at, "LOCAL_ADDRESS")
        else:
            try:
                value = self._correspondence(original, key, at, self.lookup.lookup(key, self.scope))
            except LookupError as error:
                value = self._unknown(
                    original, at, error.code, ambiguous=error.code == "MULTIPLE_MATCHES"
                )
            except (ValueError, TypeError, AttributeError):
                value = self._unknown(original, at, "LOOKUP_LIMIT")
        raw = value.model_dump_json().encode()
        if len(raw) <= self.max_bytes:
            self._entries[key] = raw
            self._bytes += len(raw)
            while len(self._entries) > self.max_entries or self._bytes > self.max_bytes:
                _, removed = self._entries.popitem(last=False)
                self._bytes -= len(removed)
        return value

    def _correspondence(
        self, original: str, key: str, now: datetime, witnesses: Witnesses
    ) -> ClientNameObservation:
        if len(witnesses.ptr) > 2 or len(witnesses.forward) > 16 or len(witnesses.computers) > 2:
            return self._unknown(original, now, "LOOKUP_LIMIT")
        if not witnesses.ptr:
            return self._unknown(original, now, "PTR_MISSING")
        names = {dns_name(record.value.rstrip(".")) for record in witnesses.ptr}
        if len(names) != 1:
            return self._unknown(original, now, "MULTIPLE_MATCHES", ambiguous=True)
        name = next(iter(names))
        if not name.endswith("." + self.scope.dns_domain):
            return self._unknown(original, now, "DOMAIN_MISMATCH")
        forwards = {normalized_ip(record.value) for record in witnesses.forward}
        if key not in forwards:
            return self._unknown(original, now, "FORWARD_MISMATCH")
        if not witnesses.computers:
            return self._unknown(original, now, "COMPUTER_MISSING")
        enabled = [computer for computer in witnesses.computers if computer.enabled]
        if not enabled:
            return self._unknown(original, now, "COMPUTER_DISABLED")
        if len(enabled) != 1:
            return self._unknown(original, now, "MULTIPLE_MATCHES", ambiguous=True)
        computer = enabled[0]
        if dns_name(computer.dns_hostname.rstrip(".")) != name or not computer.sid.startswith(
            self.scope.domain_sid + "-"
        ):
            return self._unknown(original, now, "DOMAIN_MISMATCH")
        ttls = [record.ttl for record in witnesses.ptr + witnesses.forward]
        if any(type(ttl) is not int or ttl <= 0 for ttl in ttls):
            return self._unknown(original, now, "LOOKUP_LIMIT")
        return ClientNameObservation(
            collector_id=self.collector_id,
            batch_id=uuid4().hex,
            schema_version=1,
            scope=self.scope,
            client_ip=original,
            observed_at=now,
            sent_at=now,
            expires_at=now + timedelta(seconds=min(900, *ttls)),
            status="CONFIRMED_CURRENT",
            ptr_name=name,
            forward_addresses=sorted(forwards),
            computer_sid=computer.sid,
            computer_guid=computer.guid,
            computer_name=computer.name,
            enabled=True,
        )
