"""Fresh heartbeat arrival cannot refresh an old Audit scope proof."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import Response

from apps.api import audit_read
from packages.contracts.audit import AuditHealth, AuditStream


@pytest.mark.parametrize("age,duration", [(600, 16), (45, 20), (-10, 0)])
@pytest.mark.parametrize("gap", [None, "AUDIT_CONFIGURATION_CHANGED"])
def test_response_expires_frozen_readiness_without_rewriting_received_payload(
    monkeypatch, age, duration, gap
):
    now = datetime.now(UTC)
    health = AuditHealth(
        configured=True, state="HEALTHY", host_id=UUID(int=1), gap=gap,
        last_collected_at=now, policy_verified=True, sacl_verified=True,
        readiness_complete=True, readiness_stale=False,
        readiness_checked_at=now - timedelta(seconds=age),
        readiness_age_seconds=16, readiness_duration_seconds=duration,
    ).model_dump(mode="json")
    before = dict(health)
    row = {
        "id": UUID(int=2), "health": health, "reported_at": now,
        "accepted_at": now, "expected_cadence_seconds": 30,
    }

    class Connection:
        def execute(self, _statement):
            return self

        def mappings(self):
            return self

        def all(self):
            return [row]

    monkeypatch.setattr(audit_read, "database_time", lambda _: now)
    result = audit_read.stream(Connection(), UUID(int=3))
    assert result.state == ("GAP" if gap else "OBSERVE")
    assert result.diagnostics.readiness_stale is True
    assert result.diagnostics.policy_verified is False
    assert result.diagnostics.sacl_verified is False
    assert health == before


def test_healthy_response_validity_cannot_outlive_scope_proof():
    now = datetime.now(UTC)
    health = AuditHealth(
        configured=True, state="HEALTHY", host_id=UUID(int=1),
        last_collected_at=now, policy_verified=True, sacl_verified=True,
        readiness_complete=True, readiness_stale=False,
        readiness_checked_at=now - timedelta(seconds=35),
        readiness_age_seconds=55, readiness_duration_seconds=20,
    )

    class Connection:
        def execute(self, _statement):
            return self

        def scalar_one(self):
            return 30

    value = AuditStream(
        state="HEALTHY", evaluated_at=now, reported_at=now, diagnostics=health
    )
    response = Response()
    audit_read.stamp_stream(Connection(), response, UUID(int=3), value)
    assert int(response.headers["X-Evidence-Valid-For-Ms"]) <= 5000


def test_projection_keeps_fresh_boundary_and_never_mutates_model():
    now = datetime.now(UTC)
    health = AuditHealth(
        configured=True, state="HEALTHY", host_id=UUID(int=1),
        last_collected_at=now, policy_verified=True, sacl_verified=True,
        readiness_complete=True, readiness_stale=False,
        readiness_checked_at=now - timedelta(seconds=40),
        readiness_age_seconds=20, readiness_duration_seconds=20,
    )
    result = audit_read.readiness_projection(health, now)
    assert result.readiness_age_seconds == 60
    assert result.readiness_stale is False and result.sacl_verified
    assert health.readiness_age_seconds == 20


def test_incomplete_scope_cannot_keep_positive_proof_even_with_fresh_timestamp():
    now = datetime.now(UTC)
    health = AuditHealth(
        configured=True, state="HEALTHY", host_id=UUID(int=1),
        policy_verified=True, sacl_verified=True, readiness_complete=False,
        readiness_stale=False, readiness_checked_at=now,
    )
    result = audit_read.readiness_projection(health, now)
    assert result.readiness_stale and not result.policy_verified and not result.sacl_verified
