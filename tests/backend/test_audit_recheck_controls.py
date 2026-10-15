"""Explicit rechecks remain version-fenced, idempotent and bounded under contention."""

import time
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from test_windows_audit_backend import csrf, drain, seed
from test_windows_audit_backend import setup as setup

from packages.shared.audit.correlation import RULE_VERSION
from packages.shared.audit.recheck import process
from packages.shared.jobs import lock_key
from packages.shared.models.activity import change_events
from packages.shared.models.audit import audit_correlations
from packages.shared.models.jobs import jobs


def target(setup):
    _, engine, *_ = setup
    seed(setup)
    drain(engine)
    with engine.connect() as c:
        return c.execute(select(change_events.c.id)).scalar_one()


def test_recheck_lock_contention_is_bounded_and_leaks_no_data(setup):
    client, engine, *_ = setup
    change = target(setup)
    key = "audit-recheck:" + RULE_VERSION + ":" + str(change)
    with engine.begin() as holder:
        holder.execute(select(func.pg_advisory_xact_lock(lock_key(key))))
        started = time.monotonic()
        response = client.post(
            f"/api/v1/audit/changes/{change}/recheck",
            json={"rule_version": RULE_VERSION},
            headers=csrf(client),
        )
        assert (
            response.status_code == 503 and response.json()["detail"] == "AUDIT_CONTROL_UNAVAILABLE"
        )
        assert time.monotonic() - started < 6
    with engine.connect() as c:
        assert (
            c.scalar(select(func.count()).select_from(jobs).where(jobs.c.kind == "audit_recheck"))
            == 0
        )


@pytest.mark.parametrize("fault", ["wrong_kind", "wrong_change", "wrong_rule", "extra_payload"])
def test_existing_conflicting_job_is_not_accepted_as_a_recheck(setup, fault):
    client, engine, *_ = setup
    change = target(setup)
    url = f"/api/v1/audit/changes/{change}/recheck"
    original = client.post(url, json={"rule_version": RULE_VERSION}, headers=csrf(client)).json()
    with engine.begin() as c:
        row = c.execute(select(jobs).where(jobs.c.id == original["job_id"])).mappings().one()
        payload = dict(row["payload"])
        values = {}
        if fault == "wrong_kind":
            values["kind"] = "other"
        elif fault == "wrong_change":
            payload["change_id"] = str(uuid4())
        elif fault == "wrong_rule":
            payload["rule_version"] = "windows-security-usn-v1"
        else:
            payload["actor"] = "forged"
        c.execute(update(jobs).where(jobs.c.id == row["id"]).values(payload=payload, **values))
    response = client.post(url, json={"rule_version": RULE_VERSION}, headers=csrf(client))
    assert response.status_code == 409 and response.json()["detail"] == "AUDIT_RECHECK_CONFLICT"


@pytest.mark.parametrize("fault", ["version", "shape"])
def test_worker_rejects_unexpected_rule_or_override_before_any_effect(setup, fault):
    client, engine, *_ = setup
    change = target(setup)
    result = client.post(
        f"/api/v1/audit/changes/{change}/recheck",
        json={"rule_version": RULE_VERSION},
        headers=csrf(client),
    ).json()
    with engine.begin() as c:
        job = dict(c.execute(select(jobs).where(jobs.c.id == result["job_id"])).mappings().one())
        before = [dict(r) for r in c.execute(select(audit_correlations)).mappings()]
        if fault == "version":
            job["payload"] = {**job["payload"], "rule_version": "windows-security-usn-v1"}
        else:
            job["payload"] = {**job["payload"], "actor": "forged"}
        with pytest.raises(ValueError):
            process(c, job)
        assert [dict(r) for r in c.execute(select(audit_correlations)).mappings()] == before
