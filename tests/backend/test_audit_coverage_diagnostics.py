"""Read-only explanation must retain the engine's conservative historical rule."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, update
from test_windows_audit_backend import drain, post, seed
from test_windows_audit_backend import setup as setup
from test_windows_audit_correlation import inputs

from packages.shared.audit.engine import _witness
from packages.shared.models.audit import audit_correlations, audit_health_observations


def test_exact_change_coverage_explanation_is_bounded_private_and_read_only(setup):
    client, engine, *_ = setup
    seed(setup)
    drain(engine)
    with engine.connect() as connection:
        original = dict(connection.execute(select(audit_correlations)).mappings().one())
    response = client.get(f"/api/v1/audit/changes/{original['change_event_id']}/coverage")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    result = response.json()
    assert result["passed"] is True and result["reason"] == "COMPLETE"
    assert result["change_id"] == str(original["change_event_id"])
    assert result["identity_reason"] == "PROVEN_PRIOR_IDENTITY"
    assert len(result["collectors"]) == 2
    for check in result["collectors"]:
        assert check["witness_count"] == 2 and not check["overflow"]
        assert check["covers_start"] and check["covers_end"]
        assert check["failures"] == []
    assert "UserA" not in response.text and "Pilot/" not in response.text
    with engine.connect() as connection:
        assert dict(connection.execute(select(audit_correlations)).mappings().one()) == original


def test_old_bad_witness_is_explained_without_lending_current_health(setup):
    client, engine, _, _, _, audit, _ = setup
    access = seed(setup)
    # The earlier witness is outside the deletion itself, within the existing
    # conservative 120s guard band. Explanation must not silently exclude it.
    with engine.begin() as connection:
        row = (
            connection.execute(
                select(audit_health_observations).where(
                    audit_health_observations.c.collector_id == audit,
                    audit_health_observations.c.occurred_at < access.occurred_at,
                )
            )
            .mappings()
            .one()
        )
        payload = {**row["payload"], "audit": {**row["payload"]["audit"], "backlog_count": 1}}
        connection.execute(
            update(audit_health_observations)
            .where(audit_health_observations.c.id == row["id"])
            .values(payload=payload)
        )
    drain(engine)
    with engine.connect() as connection:
        verdict = connection.execute(select(audit_correlations)).mappings().one()
    assert verdict["class"] == "ACCESS_OBSERVED" and verdict["actor"] is None
    result = client.get(f"/api/v1/audit/changes/{verdict['change_event_id']}/coverage").json()
    assert not result["passed"]
    audit_check = next(r for r in result["collectors"] if r["collector_type"] == "AUDIT_WINDOWS")
    assert "AUDIT_BACKLOG" in audit_check["failures"]
    expected = (access.occurred_at - timedelta(seconds=10)).isoformat().replace("+00:00", "Z")
    assert audit_check["first_bad_at"] == expected


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("configured", False, "AUDIT_CONFIGURATION"),
        ("policy_verified", False, "AUDIT_POLICY"),
        ("sacl_verified", False, "AUDIT_SACL"),
        ("gap", "GAP", "AUDIT_GAP"),
        ("backlog_count", 1, "AUDIT_BACKLOG"),
        ("quarantine", True, "AUDIT_QUARANTINE"),
        ("error_code", "ERROR", "AUDIT_ERROR"),
        ("state", "OBSERVE", "AUDIT_STATE"),
        ("boot_id", "other", "AUDIT_BOOT"),
        ("host_id", "other", "AUDIT_HOST"),
        ("generation", "other", "AUDIT_GENERATION"),
    ],
)
def test_each_audit_predicate_retains_its_original_rejection(field, value, code):
    _, events = inputs()
    access = events[0]
    health = dict(
        configured=True,
        policy_verified=True,
        sacl_verified=True,
        state="HEALTHY",
        host_id=str(access.host_id),
        boot_id=access.boot_id,
        generation=str(access.generation),
        last_collected_at=access.occurred_at.isoformat(),
    )
    health[field] = value
    failures, proof = _witness({"audit": health}, "AUDIT_WINDOWS", access, access.occurred_at)
    assert failures == [code] and proof is None


@pytest.mark.parametrize(
    "age,lag,error,cursor,code",
    [
        (-1, 0, None, "valid", "USN_PROOF_AGE"),
        (15, 0, None, "valid", "USN_PROOF_AGE"),
        (0, 16, None, "valid", "USN_LAG"),
        (0, 0, "ERROR", "valid", "USN_ERROR"),
        (0, 0, None, "unknown", "USN_CURSOR"),
        pytest.param(0, 0, None, "ntfs-usn:continuous:²:x", "USN_CURSOR", id="non-decimal"),
        pytest.param(
            0, 0, None, "ntfs-usn:continuous:" + "9" * 1000 + ":x", "USN_CURSOR", id="overflow"
        ),
        (14.999, 15, None, "valid", None),
    ],
)
def test_usn_proof_age_lag_and_format_boundaries(age, lag, error, cursor, code):
    _, events = inputs()
    access = events[0]
    progress = access.occurred_at - timedelta(seconds=age)
    value = "ntfs-usn:continuous:" + str(int(progress.timestamp() * 1000)) + ":" + "a" * 64
    failures, proof = _witness(
        {"cursor": value if cursor == "valid" else cursor, "lag_seconds": lag, "error_code": error},
        "WINDOWS",
        access,
        access.occurred_at,
    )
    assert failures == ([code] if code else [])
    assert (proof is None) == (code is not None)


def test_overflow_is_explicit_and_read_does_not_change_verdict(setup):
    client, engine, usn, *_ = setup
    seed(setup)
    with engine.begin() as connection:
        row = (
            connection.execute(
                select(audit_health_observations)
                .where(audit_health_observations.c.collector_id == usn)
                .order_by(audit_health_observations.c.occurred_at)
                .limit(1)
            )
            .mappings()
            .one()
        )
        connection.execute(
            insert(audit_health_observations),
            [
                dict(
                    id=uuid4(),
                    collector_id=usn,
                    receipt_id=row["receipt_id"],
                    occurred_at=row["occurred_at"] + timedelta(milliseconds=i + 1),
                    payload=row["payload"],
                )
                for i in range(127)
            ],
        )
    drain(engine)
    with engine.connect() as connection:
        verdict = dict(connection.execute(select(audit_correlations)).mappings().one())
    result = client.get(f"/api/v1/audit/changes/{verdict['change_event_id']}/coverage").json()
    check = next(r for r in result["collectors"] if r["collector_type"] == "WINDOWS")
    assert not result["passed"] and check["overflow"] and check["witness_count"] == 129
    assert check["failures"] == ["WITNESS_LIMIT"]
    with engine.connect() as connection:
        assert dict(connection.execute(select(audit_correlations)).mappings().one()) == verdict


def test_unknown_change_and_anonymous_read_have_existing_denial_boundaries(setup):
    client, *_ = setup
    path = f"/api/v1/audit/changes/{uuid4()}/coverage"
    assert client.get(path).status_code == 404
    client.cookies.clear()
    assert client.get(path).status_code == 401


def test_diagnostic_does_not_choose_one_of_multiple_access_candidates(setup):
    client, engine, _, _, _, audit, token = setup
    access = seed(setup)
    drain(engine)
    second = access.model_copy(
        update={
            "record_id": 12,
            "logon_id": 258,
            "sid": "S-1-5-21-100-200-300-1002",
            "account": "UserB",
        }
    )
    assert (
        post(
            client,
            "audit-events",
            audit,
            token,
            [{**second.model_dump(mode="json"), "digest": second.digest()}],
        ).status_code
        == 202
    )
    drain(engine)
    with engine.connect() as connection:
        verdict = dict(connection.execute(select(audit_correlations)).mappings().one())
    result = client.get(f"/api/v1/audit/changes/{verdict['change_event_id']}/coverage").json()
    assert result["reason"] == "NO_UNIQUE_ACCESS" and not result["passed"]
    assert result["collectors"] == [] and result["identity_reason"] is None


def test_no_persisted_candidate_is_not_synchronously_correlated_on_read(setup):
    client, engine, *_ = setup
    seed(setup, late_alias=True)
    drain(engine)
    with engine.connect() as connection:
        verdict = dict(connection.execute(select(audit_correlations)).mappings().one())
    result = client.get(f"/api/v1/audit/changes/{verdict['change_event_id']}/coverage").json()
    assert result["reason"] == "NO_UNIQUE_ACCESS" and not result["passed"]
    with engine.connect() as connection:
        assert dict(connection.execute(select(audit_correlations)).mappings().one()) == verdict
