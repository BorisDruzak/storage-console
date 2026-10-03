import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, insert, select, update

from packages.shared.models.jobs import jobs
from packages.shared.models.security import audit_log

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL required")


def api():
    from packages.shared.jobs import JobConflict, enqueue, lock_key, process_one

    return JobConflict, enqueue, lock_key, process_one


def effect(connection, job):
    connection.execute(
        insert(audit_log).values(
            action="SYNTHETIC_EFFECT",
            resource_type="job",
            resource_identity=str(job["id"]),
            result="COMPLETE",
            details={},
        )
    )


def test_enqueue_replay_conflict_and_two_workers_produce_one_effect(ingest_setup):
    _, engine, _, _, _ = ingest_setup
    conflict, enqueue, _, process = api()

    def create(_):
        with engine.begin() as connection:
            return enqueue(connection, "synthetic", {"value": 1}, "same")

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(create, range(2)))
    assert ids[0] == ids[1]
    with engine.begin() as connection, pytest.raises(conflict):
        enqueue(connection, "synthetic", {"value": 2}, "same")
    with engine.begin() as connection, pytest.raises(conflict):
        enqueue(connection, "synthetic", {"value": True}, "same")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: process(engine, {"synthetic": effect}), range(2)))
    assert sorted(results) == [False, True]
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(audit_log)) == 1
        job = connection.execute(select(jobs)).mappings().one()
        assert job["status"] == "COMPLETE" and job["attempts"] == 1
        assert job["completed_at"].tzinfo is not None


def test_locked_job_does_not_block_another_due_job(ingest_setup):
    _, engine, _, _, _ = ingest_setup
    _, enqueue, _, process = api()
    with engine.begin() as connection:
        enqueue(connection, "synthetic", {}, "first")
        enqueue(connection, "synthetic", {}, "second")
    entered, release = threading.Event(), threading.Event()

    def slow(connection, job):
        entered.set()
        assert release.wait(10)
        effect(connection, job)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(process, engine, {"synthetic": slow})
        try:
            assert entered.wait(10)
            assert pool.submit(process, engine, {"synthetic": effect}).result(timeout=5)
        finally:
            release.set()
        assert pending.result(timeout=5)
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(audit_log)) == 2


def test_retry_rolls_back_handler_effect_and_stops_at_limit(ingest_setup):
    _, engine, _, _, _ = ingest_setup
    _, enqueue, _, process = api()
    with engine.begin() as connection:
        identity = enqueue(connection, "synthetic", {}, "failure", max_attempts=2)

    def fail(connection, job):
        effect(connection, job)
        # Real PostgreSQL error aborts only the handler savepoint.
        connection.execute(
            insert(jobs).values(
                kind="invalid",
                idempotency_key="bad",
                payload={},
                status="INVALID",
            )
        )

    assert process(engine, {"synthetic": fail})
    with engine.connect() as connection:
        job = connection.execute(select(jobs)).mappings().one()
        assert job["status"] == "RETRY" and job["attempts"] == 1
        assert job["error_code"] == "HANDLER_FAILED"
        assert job["next_attempt_at"] > datetime.now(UTC)
        assert connection.scalar(select(func.count()).select_from(audit_log)) == 0
    assert not process(engine, {"synthetic": fail})
    with engine.begin() as connection:
        connection.execute(
            update(jobs)
            .where(jobs.c.id == identity)
            .values(
                next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
    assert process(engine, {"synthetic": fail})
    assert not process(engine, {"synthetic": effect})
    with engine.connect() as connection:
        job = connection.execute(select(jobs)).mappings().one()
        assert job["status"] == "FAILED" and job["attempts"] == 2
        assert connection.scalar(select(func.count()).select_from(audit_log)) == 0


def test_advisory_contention_defers_without_attempt_and_unknown_kind_fails(ingest_setup):
    _, engine, _, _, _ = ingest_setup
    _, enqueue, key, process = api()
    with engine.begin() as connection:
        enqueue(connection, "missing", {}, "locked")
    with engine.begin() as holder:
        holder.execute(select(func.pg_advisory_xact_lock(key("locked"))))
        assert not process(engine, {})
    with engine.connect() as connection:
        assert connection.scalar(select(jobs.c.attempts)) == 0
    with engine.begin() as connection:
        connection.execute(update(jobs).values(next_attempt_at=datetime.now(UTC)))
    assert process(engine, {})
    with engine.connect() as connection:
        job = connection.execute(select(jobs)).mappings().one()
        assert job["status"] == "FAILED" and job["error_code"] == "UNKNOWN_JOB_KIND"


def test_interrupted_handler_leaves_job_available_without_partial_effect(ingest_setup):
    _, engine, _, _, _ = ingest_setup
    _, enqueue, _, process = api()
    with engine.begin() as connection:
        enqueue(connection, "synthetic", {}, "interrupted")

    def interrupt(connection, job):
        effect(connection, job)
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        process(engine, {"synthetic": interrupt})
    with engine.connect() as connection:
        assert connection.scalar(select(jobs.c.status)) == "PENDING"
        assert connection.scalar(select(jobs.c.attempts)) == 0
        assert connection.scalar(select(func.count()).select_from(audit_log)) == 0
    assert process(engine, {"synthetic": effect})


def test_ingest_enqueues_once_and_worker_records_postprocessing(ingest_setup):
    from packages.shared.models.jobs import ingest_batches
    from tests.backend.test_ingest import batch

    client, engine, collector, token, _ = ingest_setup
    payload = batch(collector, [dict(version="synthetic")])
    headers = {"Authorization": "Bearer " + token}
    for _ in range(2):
        assert (
            client.post("/api/v1/ingest/heartbeat", json=payload, headers=headers).status_code
            == 202
        )
    with engine.connect() as connection:
        job = connection.execute(select(jobs)).mappings().one()
        receipt = connection.scalar(select(ingest_batches.c.id))
        assert job["payload"] == {"receipt_id": str(receipt)}
    from apps.worker.processor import HANDLERS

    _, _, _, process = api()
    assert process(engine, HANDLERS)
    assert not process(engine, HANDLERS)
    with engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(audit_log)
                .where(
                    audit_log.c.action == "INGEST_POSTPROCESSED",
                )
            )
            == 1
        )
        assert connection.scalar(select(jobs.c.status)) == "COMPLETE"
