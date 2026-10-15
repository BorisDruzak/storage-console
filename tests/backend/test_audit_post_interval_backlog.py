"""A later delivered queue must not invalidate an earlier fully evidenced interval."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, insert, select, update
from test_windows_audit_backend import csrf, drain, post, seed
from test_windows_audit_backend import setup as setup

from packages.shared.audit.correlation import RULE_VERSION
from packages.shared.models.activity import change_events
from packages.shared.models.audit import (
    audit_candidates,
    audit_correlations,
    audit_evidence,
    audit_health_observations,
    audit_identity_observations,
)
from packages.shared.models.jobs import jobs
from packages.shared.models.security import audit_log, roles


def late_backlog(setup):
    _, engine, _, _, _, audit, _ = setup
    access = seed(setup)
    with engine.begin() as connection:
        row = (
            connection.execute(
                select(audit_health_observations)
                .where(audit_health_observations.c.collector_id == audit)
                .order_by(audit_health_observations.c.occurred_at.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        when = access.occurred_at + timedelta(seconds=5)
        payload = {
            **row["payload"],
            "audit": {
                **row["payload"]["audit"],
                "backlog_count": 1,
                "last_collected_at": when.isoformat(),
            },
        }
        connection.execute(
            insert(audit_health_observations).values(
                id=uuid4(),
                collector_id=audit,
                receipt_id=row["receipt_id"],
                occurred_at=when,
                payload=payload,
            )
        )
    return access


def test_post_interval_backlog_is_settled_by_a_later_dated_empty_queue(setup):
    client, engine, *_ = setup
    late_backlog(setup)
    drain(engine)
    with engine.connect() as connection:
        verdict = connection.execute(select(audit_correlations)).mappings().one()
    assert verdict["class"] == "CORRELATED_HIGH" and verdict["actor"] is not None
    check = client.get(f"/api/v1/audit/changes/{verdict['change_event_id']}/coverage").json()
    assert check["passed"]
    audit = next(x for x in check["collectors"] if x["collector_type"] == "AUDIT_WINDOWS")
    assert audit["post_interval_backlog_count"] == 1
    assert audit["post_interval_backlog_cleared_at"] is not None


def test_exact_change_recheck_is_authenticated_csrf_protected_and_idempotent(setup):
    client, engine, *_ = setup
    seed(setup)
    drain(engine)
    with engine.connect() as connection:
        change = connection.execute(select(audit_correlations.c.change_event_id)).scalar_one()
    url = f"/api/v1/audit/changes/{change}/recheck"
    response = client.post(url, json={"rule_version": RULE_VERSION}, headers=csrf(client))
    assert response.status_code == 202
    again = client.post(url, json={"rule_version": RULE_VERSION}, headers=csrf(client))
    assert again.status_code == 202 and again.json() == response.json()


@pytest.mark.parametrize(
    "fault",
    [
        "inside",
        "at_end",
        "before_start",
        "no_drain",
        "drain_before_backlog",
        "old_drain_proof",
        "future_drain_proof",
        "old_collected",
        "future_collected",
        "missing_collected",
        "invalid_collected",
        "naive_collected",
        "later_backlog",
        "no_start",
        "usn_lag",
        "policy",
        "sacl",
        "gap",
        "quarantine",
        "error",
        "state",
        "host",
        "boot",
        "generation",
    ],
)
def test_late_queue_never_waives_other_or_unsettled_coverage_faults(setup, fault):
    client, engine, usn, _, _, audit, _ = setup
    access = late_backlog(setup)
    with engine.begin() as c:
        rows = (
            c.execute(
                select(audit_health_observations)
                .where(audit_health_observations.c.collector_id == audit)
                .order_by(audit_health_observations.c.occurred_at)
            )
            .mappings()
            .all()
        )
        before, backlog, after = rows
        payload = {**backlog["payload"], "audit": dict(backlog["payload"]["audit"])}
        when = backlog["occurred_at"]
        if fault in ("inside", "at_end", "before_start"):
            when = access.occurred_at + timedelta(
                seconds={"inside": 1, "at_end": 3, "before_start": -11}[fault]
            )
            payload["audit"]["last_collected_at"] = when.isoformat()
        elif fault == "no_drain":
            c.execute(
                delete(audit_health_observations).where(
                    audit_health_observations.c.id == after["id"]
                )
            )
        elif fault in ("drain_before_backlog", "old_drain_proof", "future_drain_proof"):
            health = {**after["payload"], "audit": dict(after["payload"]["audit"])}
            health["audit"]["last_collected_at"] = (
                access.occurred_at + timedelta(seconds=11 if fault == "future_drain_proof" else 4)
            ).isoformat()
            values = {"payload": health}
            if fault == "drain_before_backlog":
                values["occurred_at"] = access.occurred_at + timedelta(seconds=4)
            c.execute(
                update(audit_health_observations)
                .where(audit_health_observations.c.id == after["id"])
                .values(**values)
            )
        elif fault.endswith("collected"):
            value = {
                "old_collected": (access.occurred_at + timedelta(seconds=2)).isoformat(),
                "future_collected": (when + timedelta(seconds=1)).isoformat(),
                "missing_collected": None,
                "invalid_collected": "invalid",
                "naive_collected": when.replace(tzinfo=None).isoformat(),
            }[fault]
            payload["audit"]["last_collected_at"] = value
        elif fault == "later_backlog":
            later = access.occurred_at + timedelta(seconds=12)
            c.execute(
                insert(audit_health_observations).values(
                    id=uuid4(),
                    collector_id=audit,
                    receipt_id=backlog["receipt_id"],
                    occurred_at=later,
                    payload={
                        **payload,
                        "audit": {**payload["audit"], "last_collected_at": later.isoformat()},
                    },
                )
            )
        elif fault == "no_start":
            c.execute(
                delete(audit_health_observations).where(
                    audit_health_observations.c.id == before["id"]
                )
            )
        elif fault == "usn_lag":
            row = (
                c.execute(
                    select(audit_health_observations)
                    .where(audit_health_observations.c.collector_id == usn)
                    .limit(1)
                )
                .mappings()
                .one()
            )
            c.execute(
                update(audit_health_observations)
                .where(audit_health_observations.c.id == row["id"])
                .values(payload={**row["payload"], "lag_seconds": 16})
            )
        else:
            key, value = {
                "policy": ("policy_verified", False),
                "sacl": ("sacl_verified", False),
                "gap": ("gap", "GAP"),
                "quarantine": ("quarantine", True),
                "error": ("error_code", "ERROR"),
                "state": ("state", "OBSERVE"),
                "host": ("host_id", str(uuid4())),
                "boot": ("boot_id", "other"),
                "generation": ("generation", str(uuid4())),
            }[fault]
            payload["audit"][key] = value
        c.execute(
            update(audit_health_observations)
            .where(audit_health_observations.c.id == backlog["id"])
            .values(occurred_at=when, payload=payload)
        )
    drain(engine)
    with engine.connect() as c:
        row = c.execute(select(audit_correlations)).mappings().one()
    assert row["class"] == "ACCESS_OBSERVED" and row["actor"] is None
    explanation = client.get(f"/api/v1/audit/changes/{row['change_event_id']}/coverage").json()
    assert not explanation["passed"]


def test_settled_queue_does_not_hide_a_competing_context(setup):
    client, engine, _, _, _, audit, token = setup
    access = late_backlog(setup)
    other = access.model_copy(
        update={"record_id": 12, "sid": "S-1-5-21-111-222-333-9999", "logon_id": 9999}
    )
    assert (
        post(
            client,
            "audit-events",
            audit,
            token,
            [{**other.model_dump(mode="json"), "digest": other.digest()}],
        ).status_code
        == 202
    )
    drain(engine)
    with engine.connect() as c:
        row = c.execute(select(audit_correlations)).mappings().one()
    assert row["class"] == "AMBIGUOUS" and row["actor"] is None


def test_explicit_recheck_preserves_raw_rows_v1_links_and_other_decisions(setup):
    client, engine, *_ = setup
    access = late_backlog(setup)
    drain(engine)
    with engine.begin() as c:
        change = c.execute(select(change_events)).mappings().one()
        c.execute(
            update(audit_correlations).values(
                rule_version="windows-security-usn-v1",
                **{
                    "class": "ACCESS_OBSERVED",
                    "reason": "INTERVAL_COVERAGE_UNKNOWN",
                    "actor": None,
                },
            )
        )
        c.execute(
            update(audit_candidates).values(
                rule_version="windows-security-usn-v1",
                **{"class": "ACCESS_OBSERVED", "reason": "INTERVAL_COVERAGE_UNKNOWN"},
            )
        )
        noise = uuid4()
        c.execute(
            insert(change_events).values(
                id=noise,
                source_node_id=change["source_node_id"],
                volume_identity="volume-a",
                file_id="unrelated",
                event_type="WRITE",
                new_relative_path="Unrelated/keep.txt",
                occurred_at=access.occurred_at + timedelta(hours=1),
            )
        )
        c.execute(
            insert(audit_correlations).values(
                change_event_id=noise,
                rule_version="windows-security-usn-v1",
                **{"class": "UNKNOWN", "reason": "NO_SCOPED_ACCESS", "actor": None},
            )
        )
    tables = (change_events, audit_evidence, audit_identity_observations, audit_health_observations)

    def snapshot(c):
        return {
            t.name: sorted([dict(r) for r in c.execute(select(t)).mappings()], key=str)
            for t in tables
        }

    with engine.connect() as c:
        raw = snapshot(c)
        old_links = [dict(r) for r in c.execute(select(audit_candidates)).mappings()]
        untouched = dict(
            c.execute(
                select(audit_correlations).where(audit_correlations.c.change_event_id == noise)
            )
            .mappings()
            .one()
        )
    url = f"/api/v1/audit/changes/{change['id']}/recheck"
    response = client.post(url, json={"rule_version": RULE_VERSION}, headers=csrf(client))
    assert response.status_code == 202 and response.headers["Cache-Control"] == "no-store"
    drain(engine)
    detail = client.get(f"/api/v1/audit/changes/{change['id']}").json()
    assert detail["classification"] == "CORRELATED_HIGH" and detail["rule_version"] == RULE_VERSION
    assert (
        len(detail["candidates"]) == len({x["evidence"]["id"] for x in detail["candidates"]}) == 3
    )
    assert all(x["rule_version"] == RULE_VERSION for x in detail["candidates"])
    with engine.connect() as c:
        assert snapshot(c) == raw
        assert [
            dict(r)
            for r in c.execute(
                select(audit_candidates).where(
                    audit_candidates.c.rule_version == "windows-security-usn-v1"
                )
            ).mappings()
        ] == old_links
        assert (
            dict(
                c.execute(
                    select(audit_correlations).where(audit_correlations.c.change_event_id == noise)
                )
                .mappings()
                .one()
            )
            == untouched
        )
        logs = (
            c.execute(select(audit_log).where(audit_log.c.action.like("audit.recheck_%")))
            .mappings()
            .all()
        )
        assert len(logs) == 2 and {x["result"] for x in logs} == {"QUEUED", "COMPLETE"}
        assert (
            c.scalar(select(func.count()).select_from(jobs).where(jobs.c.kind == "audit_recheck"))
            == 1
        )
    again = client.post(url, json={"rule_version": RULE_VERSION}, headers=csrf(client))
    assert (
        again.json()["job_id"] == response.json()["job_id"] and again.json()["status"] == "COMPLETE"
    )


@pytest.mark.parametrize(
    "role", ["viewer", "storage_operator", "analyst", "auditor"]
)
def test_all_nonadmin_roles_cannot_enqueue_a_recheck(setup, role):
    client, engine, *_ = setup
    seed(setup)
    drain(engine)
    with engine.begin() as c:
        c.execute(update(roles).where(roles.c.code == "storage_admin").values(code=role))
    response = client.post(
        f"/api/v1/audit/changes/{uuid4()}/recheck",
        json={"rule_version": RULE_VERSION},
        headers=csrf(client),
    )
    assert response.status_code == 403 and "job_id" not in response.text
    with engine.connect() as c:
        assert (
            c.scalar(select(func.count()).select_from(jobs).where(jobs.c.kind == "audit_recheck"))
            == 0
        )


@pytest.mark.parametrize(
    "fault,status",
    [
        ("anonymous", 401),
        ("csrf", 403),
        ("origin", 403),
        ("version", 409),
        ("missing", 404),
        ("override", 422),
        ("body", 422),
    ],
)
def test_recheck_denials_cannot_change_derived_state(setup, fault, status):
    client, engine, *_ = setup
    seed(setup)
    drain(engine)
    with engine.connect() as c:
        change = c.execute(select(change_events.c.id)).scalar_one()
    headers = csrf(client)
    body = {"rule_version": RULE_VERSION}
    if fault == "anonymous":
        client.cookies.clear()
    elif fault == "csrf":
        headers.pop("X-CSRF-Token")
    elif fault == "origin":
        headers["Origin"] = "https://other.example.test"
    elif fault == "version":
        body["rule_version"] = "windows-security-usn-v1"
    elif fault == "missing":
        change = uuid4()
    elif fault == "override":
        body["actor"] = {"account": "forged"}
    else:
        body = {}
    response = client.post(f"/api/v1/audit/changes/{change}/recheck", json=body, headers=headers)
    assert response.status_code == status
    with engine.connect() as c:
        assert (
            c.scalar(select(func.count()).select_from(jobs).where(jobs.c.kind == "audit_recheck"))
            == 0
        )
