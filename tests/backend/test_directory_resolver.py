"""DNS/AD correspondence is current observation, with finite negative caching."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from collectors.windows_audit.directory_resolver import (
    ClientResolver,
    Computer,
    DnsRecord,
    LookupError,
    Witnesses,
)
from packages.contracts.directory import DirectoryScope

DOMAIN = "S-1-5-21-10-20-30"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


class Lookup:
    def __init__(self):
        self.calls = 0
        self.error = None
        self.value = Witnesses(
            ptr=[DnsRecord("client.example.test", 300)],
            forward=[DnsRecord("192.0.2.10", 120)],
            computers=[Computer(DOMAIN + "-1001", uuid4(), "CLIENT", "client.example.test", True)],
        )

    def lookup(self, ip, scope):
        self.calls += 1
        if self.error:
            raise LookupError(self.error)
        return self.value


def resolver(lookup, **limits):
    return ClientResolver(
        uuid4(), DirectoryScope(dns_domain="example.test", domain_sid=DOMAIN), lookup, **limits
    )


def test_correspondence_and_positive_ttl_cache_preserve_original_ip():
    lookup = Lookup()
    cache = resolver(lookup)
    value = cache.resolve("::ffff:192.0.2.10", now=NOW)
    assert value.status == "CONFIRMED_CURRENT" and value.client_ip == "::ffff:192.0.2.10"
    assert value.expires_at == NOW + timedelta(seconds=120)
    assert cache.resolve("192.0.2.10", now=NOW + timedelta(seconds=119)).batch_id == value.batch_id
    assert lookup.calls == 1
    assert cache.resolve("192.0.2.10", now=NOW + timedelta(seconds=120)).batch_id != value.batch_id
    assert lookup.calls == 2


@pytest.mark.parametrize(
    "scenario,reason,status",
    [
        ("no_ptr", "PTR_MISSING", "UNKNOWN"),
        ("foreign_ptr", "DOMAIN_MISMATCH", "UNKNOWN"),
        ("forward_mismatch", "FORWARD_MISMATCH", "UNKNOWN"),
        ("no_computer", "COMPUTER_MISSING", "UNKNOWN"),
        ("disabled", "COMPUTER_DISABLED", "UNKNOWN"),
        ("multiple", "MULTIPLE_MATCHES", "AMBIGUOUS"),
    ],
)
def test_missing_disabled_or_ambiguous_witnesses_never_guess(scenario, reason, status):
    lookup = Lookup()
    value = lookup.value
    if scenario == "no_ptr":
        value.ptr.clear()
    elif scenario == "foreign_ptr":
        value.ptr[:] = [DnsRecord("client.other.test", 300)]
    elif scenario == "forward_mismatch":
        value.forward[:] = [DnsRecord("192.0.2.11", 300)]
    elif scenario == "no_computer":
        value.computers.clear()
    elif scenario == "disabled":
        c = value.computers[0]
        value.computers[:] = [Computer(c.sid, c.guid, c.name, c.dns_hostname, False)]
    else:
        value.ptr.append(DnsRecord("another.example.test", 300))
    cache = resolver(lookup)
    result = cache.resolve("192.0.2.10", now=NOW)
    assert (result.status, result.reason) == (status, reason)
    assert result.computer_name is None and result.expires_at == NOW + timedelta(seconds=30)
    cache.resolve("192.0.2.10", now=NOW + timedelta(seconds=29))
    assert lookup.calls == 1
    cache.resolve("192.0.2.10", now=NOW + timedelta(seconds=30))
    assert lookup.calls == 2


def test_outage_and_cache_capacity_are_bounded():
    lookup = Lookup()
    lookup.error = "DNS_UNAVAILABLE"
    cache = resolver(lookup, max_entries=2, max_bytes=8192)
    for ending in range(10, 110):
        assert cache.resolve(f"192.0.2.{ending}", now=NOW).status == "UNKNOWN"
    assert cache.entry_count <= 2 and cache.byte_count <= 8192
    assert cache.resolve("127.0.0.1", now=NOW).reason == "LOCAL_ADDRESS"
    assert lookup.calls == 100
