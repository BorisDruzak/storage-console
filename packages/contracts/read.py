from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime

from .common import Contract, HealthState, NonNegative, Quality

DOMAINS = (
    "TELEMETRY",
    "CAPACITY",
    "FILESYSTEM",
    "SMB_DFS",
    "ACCESS",
    "VSS",
    "RECOVERY",
    "NETWORK",
    "PVE_ZFS",
    "HYGIENE",
)


class Freshness(Contract):
    state: HealthState
    reason: str
    expected_cadence_seconds: int
    last_success_at: AwareDatetime | None
    last_event_at: AwareDatetime | None
    last_collector_at: AwareDatetime | None
    age_seconds: float | None
    cursor: str | None
    lag_seconds: int | None
    collector_count: NonNegative
    unknown_collector_count: NonNegative
    bottleneck_collector_id: UUID | None


class Source(Contract):
    id: UUID
    source_type: Literal["FILESERVER", "PVE", "PBS"]
    hostname: str
    fqdn: str | None
    instance_id: str
    created_at: AwareDatetime
    freshness: Freshness


class Page[T: Contract](Contract):
    items: list[T]
    total: NonNegative
    limit: int
    offset: int


class DomainHealth(Contract):
    domain: str
    state: HealthState
    source_count: NonNegative
    covered_source_count: NonNegative
    unknown_source_count: NonNegative


class Domains(Contract):
    domains: list[DomainHealth]
    evaluated_at: AwareDatetime


class Counts(Contract):
    sources: NonNegative
    volumes: NonNegative
    shares: NonNegative
    filesystem_objects: NonNegative


class Overview(Domains):
    counts: Counts


class Volume(Contract):
    id: UUID
    source_node_id: UUID
    unique_identity: str
    filesystem: str
    label: str | None
    total_bytes: NonNegative | None
    free_bytes: NonNegative | None
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime
    mount_aliases: list[str]
    quality: Quality


class Share(Contract):
    id: UUID
    source_node_id: UUID
    volume_id: UUID | None
    name: str
    relative_path: str
    protocol: str
    last_seen_at: AwareDatetime
    quality: Quality
