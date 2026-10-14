"""Bounded indexed current projections; original evidence and correlation stay exact."""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import Connection, String, Uuid, column, select, true, tuple_, values

from packages.contracts.directory import (
    AccountObservation,
    ClientObservation,
    DirectoryScope,
    DirectoryStream,
    DirectoryUser,
    normalized_ip,
)
from packages.shared.models.core import collectors
from packages.shared.models.directory import (
    client_name_observations,
    directory_snapshots,
    directory_users,
)


def scopes(conn: Connection, sources: set[UUID]) -> dict[UUID, tuple[UUID, DirectoryScope]]:
    if len(sources) > 512:
        raise ValueError("DIRECTORY_READ_LIMIT")
    grouped: dict[UUID, list[tuple[UUID, DirectoryScope]]] = defaultdict(list)
    rows = conn.execute(
        select(collectors.c.id, collectors.c.source_node_id, collectors.c.directory_scope).where(
            collectors.c.source_node_id.in_(sources),
            collectors.c.enabled.is_(True),
            collectors.c.collector_type == "AUDIT_WINDOWS",
            collectors.c.directory_scope.is_not(None),
        )
    )
    for identity, source, scope in rows:
        grouped[source].append((identity, DirectoryScope.model_validate(scope)))
    return {source: rows[0] for source, rows in grouped.items() if len(rows) == 1}


def snapshots(
    conn: Connection, configured: dict[UUID, tuple[UUID, DirectoryScope]]
) -> dict[UUID, Any]:
    if not configured:
        return {}
    binding = values(
        column("source", Uuid),
        column("collector", Uuid),
        column("dns_domain", String),
        column("domain_sid", String),
        name="binding",
    ).data(
        [
            (source, identity, scope.dns_domain, scope.domain_sid)
            for source, (identity, scope) in configured.items()
        ]
    )
    base = (
        select(directory_snapshots)
        .where(
            directory_snapshots.c.source_node_id == binding.c.source,
            directory_snapshots.c.collector_id == binding.c.collector,
            directory_snapshots.c.dns_domain == binding.c.dns_domain,
            directory_snapshots.c.domain_sid == binding.c.domain_sid,
        )
        .order_by(directory_snapshots.c.observed_at.desc(), directory_snapshots.c.id.desc())
        .limit(1)
    )
    attempt = base.lateral("attempt")
    complete = base.where(directory_snapshots.c.state == "COMPLETE").lateral("complete")
    query = select(
        binding.c.source,
        attempt.c.state.label("attempt_state"),
        attempt.c.observed_at.label("attempt_at"),
        attempt.c.error_code,
        complete.c.id.label("snapshot_id"),
        complete.c.observed_at.label("observed_at"),
        complete.c.record_count.label("user_count"),
    )
    return {
        row["source"]: row
        for row in conn.execute(
            query.select_from(binding.outerjoin(attempt, true()).outerjoin(complete, true()))
        ).mappings()
    }


def account_state(
    row: Any, now: datetime
) -> Literal["CURRENT", "STALE", "UNKNOWN", "PARTIAL", "ERROR"]:
    if row["attempt_state"] == "ERROR":
        return "ERROR"
    if row["attempt_state"] == "COLLECTING":
        return "PARTIAL"
    at = row["observed_at"]
    if at is None or at > now:
        return "UNKNOWN"
    return "CURRENT" if now - at < timedelta(seconds=900) else "STALE"


def names(
    conn: Connection, keys: list[tuple[UUID, str | None, str | None]], now: datetime
) -> dict[tuple[UUID, str | None, str | None], dict[str, Any]]:
    if len(keys) > 512:
        raise ValueError("DIRECTORY_READ_LIMIT")
    configured = scopes(conn, {source for source, _, _ in keys})
    history = snapshots(conn, configured)
    user_keys = {
        (history[source]["snapshot_id"], sid)
        for source, sid, _ in keys
        if source in history and history[source]["snapshot_id"] is not None and sid is not None
    }
    users = {}
    if user_keys:
        users = {
            (row["snapshot_id"], row["sid"]): DirectoryUser.model_validate(row["payload"])
            for row in conn.execute(
                select(directory_users).where(
                    tuple_(directory_users.c.snapshot_id, directory_users.c.sid).in_(user_keys)
                )
            ).mappings()
        }
    client_keys = set()
    for source, _, ip in keys:
        if source in configured and ip:
            try:
                client_keys.add((source, normalized_ip(ip)))
            except ValueError:
                pass
    clients = {}
    if client_keys:
        binding = values(
            column("source", Uuid),
            column("collector", Uuid),
            column("dns_domain", String),
            column("domain_sid", String),
            column("ip", String),
            name="peer",
        ).data(
            [
                (
                    source,
                    configured[source][0],
                    configured[source][1].dns_domain,
                    configured[source][1].domain_sid,
                    ip,
                )
                for source, ip in client_keys
            ]
        )
        latest = (
            select(client_name_observations)
            .where(
                client_name_observations.c.source_node_id == binding.c.source,
                client_name_observations.c.collector_id == binding.c.collector,
                client_name_observations.c.dns_domain == binding.c.dns_domain,
                client_name_observations.c.domain_sid == binding.c.domain_sid,
                client_name_observations.c.client_ip_key == binding.c.ip,
            )
            .order_by(
                client_name_observations.c.observed_at.desc(), client_name_observations.c.id.desc()
            )
        )
        latest_peer = latest.limit(1).lateral("latest_peer")
        clients = {
            (row["source"], row["ip"]): row
            for row in conn.execute(
                select(
                    binding.c.source,
                    binding.c.ip,
                    latest_peer.c.observed_at,
                    latest_peer.c.expires_at,
                    latest_peer.c.payload,
                ).select_from(binding.outerjoin(latest_peer, true()))
            ).mappings()
        }
    result = {}
    for key in keys:
        source, sid, ip = key
        if source not in configured:
            continue
        item: dict[str, Any] = {}
        row = history[source]
        user = users.get((row["snapshot_id"], sid))
        state = account_state(row, now)
        item["account_observation"] = AccountObservation(
            state=state if user is not None or state != "CURRENT" else "UNKNOWN",
            observed_at=row["observed_at"],
            snapshot_id=row["snapshot_id"],
            user=user,
            latest_attempt_state=row["attempt_state"],
            valid_for_ms=max(
                0,
                min(
                    900000,
                    int((row["observed_at"] + timedelta(seconds=900) - now).total_seconds() * 1000),
                ),
            )
            if row["observed_at"] is not None and state == "CURRENT"
            else 0,
        )
        try:
            peer = clients.get((source, normalized_ip(ip))) if ip else None
        except ValueError:
            peer = None
        if peer is None or peer["payload"] is None:
            item["client_observation"] = ClientObservation(state="UNKNOWN")
        else:
            payload = peer["payload"]
            fresh = peer["observed_at"] <= now < peer["expires_at"]
            item["client_observation"] = ClientObservation(
                state=payload["status"] if fresh else "STALE",
                observed_at=peer["observed_at"],
                expires_at=peer["expires_at"],
                computer_name=payload["computer_name"],
                ptr_name=payload["ptr_name"],
                computer_sid=payload["computer_sid"],
                computer_guid=payload["computer_guid"],
                reason=payload["reason"],
                valid_for_ms=max(
                    0, min(900000, int((peer["expires_at"] - now).total_seconds() * 1000))
                )
                if fresh
                else 0,
            )
        result[key] = item
    return result


def directory_stream(conn: Connection, source: UUID, now: datetime) -> DirectoryStream:
    configured = scopes(conn, {source})
    if source not in configured:
        return DirectoryStream(state="NOT_CONFIGURED", evaluated_at=now)
    row = snapshots(conn, configured)[source]
    state = account_state(row, now)
    return DirectoryStream(
        state=state,
        evaluated_at=now,
        scope=configured[source][1],
        observed_at=row["observed_at"],
        latest_attempt_at=row["attempt_at"],
        user_count=row["user_count"],
        error_code=row["error_code"],
        valid_for_ms=max(
            0,
            min(
                900000,
                int((row["observed_at"] + timedelta(seconds=900) - now).total_seconds() * 1000),
            ),
        )
        if state == "CURRENT"
        else 0,
    )
