from typing import cast

from sqlalchemy import case, func, or_, select
from sqlalchemy.engine import Connection

from packages.contracts.common import HealthState
from packages.contracts.read import DOMAINS, DomainHealth
from packages.shared.models.core import source_nodes
from packages.shared.models.health import health_findings, health_policies, health_signals

from .sources import source_data

STATES = ("NOT_APPLICABLE", "HEALTHY", "OBSERVE", "UNKNOWN", "WARNING", "CRITICAL")
UNKNOWN = STATES.index("UNKNOWN") + 1


def domain_health(connection: Connection) -> list[DomainHealth]:
    sources = source_data()
    latest = (
        select(
            health_findings.c.state,
            health_findings.c.evaluated_at,
            health_signals.c.occurred_at,
            health_signals.c.source_node_id,
            health_signals.c.domain,
            health_policies.c.domain.label("policy_domain"),
            func.row_number()
            .over(
                partition_by=(
                    health_signals.c.source_node_id,
                    health_signals.c.domain,
                    health_findings.c.policy_id,
                    health_findings.c.fingerprint,
                ),
                order_by=(health_findings.c.evaluated_at.desc(), health_findings.c.id.desc()),
            )
            .label("position"),
        )
        .join(health_signals, health_signals.c.id == health_findings.c.signal_id)
        .join(health_policies, health_policies.c.id == health_findings.c.policy_id)
        .subquery()
    )
    invalid = or_(
        sources.c.freshness_state != "HEALTHY",
        latest.c.domain != latest.c.policy_domain,
        latest.c.occurred_at > func.now(),
        latest.c.evaluated_at > func.now(),
        func.extract("epoch", func.now() - latest.c.occurred_at)
        > sources.c.expected_cadence_seconds,
        func.extract("epoch", func.now() - latest.c.evaluated_at)
        > sources.c.expected_cadence_seconds,
    )
    rank = case(
        (invalid, UNKNOWN),
        else_=case(
            *[(latest.c.state == state, index) for index, state in enumerate(STATES, 1)],
            else_=UNKNOWN,
        ),
    )
    per_source = (
        select(
            latest.c.domain,
            latest.c.source_node_id,
            func.max(rank).label("rank"),
            func.bool_or(rank == UNKNOWN).label("has_unknown"),
        )
        .join(sources, sources.c.id == latest.c.source_node_id)
        .where(latest.c.position == 1)
        .group_by(latest.c.domain, latest.c.source_node_id)
        .subquery()
    )
    grouped = (
        connection.execute(
            select(
                per_source.c.domain,
                func.count().label("covered"),
                func.max(per_source.c.rank).label("worst"),
                func.count().filter(per_source.c.has_unknown.is_(True)).label("unknown"),
            ).group_by(per_source.c.domain)
        )
        .mappings()
        .all()
    )
    total = connection.scalar(select(func.count()).select_from(source_nodes)) or 0
    by_domain = {row["domain"]: row for row in grouped}
    result = []
    for domain in DOMAINS:
        row = by_domain.get(domain)
        covered = row["covered"] if row else 0
        unknown = (row["unknown"] if row else 0) + total - covered
        worst = max(row["worst"] if row else UNKNOWN, UNKNOWN if unknown or not total else 1)
        result.append(
            DomainHealth(
                domain=domain,
                state=cast(HealthState, STATES[worst - 1]),
                source_count=total,
                covered_source_count=covered,
                unknown_source_count=unknown,
            )
        )
    return result
