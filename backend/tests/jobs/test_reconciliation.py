"""Phase 23 P1.4 -- app/jobs/reconciliation.py. Real Postgres + real Redis
(RQ) throughout: a Job's "orphaned" signal is genuinely nothing left for
its id in Redis, so the strongest test is simply never enqueueing anything
for it, rather than mocking queue.fetch_job()'s return value.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.db.sync_session import get_sync_session
from app.jobs.queue import get_queue
from app.jobs.reconciliation import reconcile_stuck_jobs
from app.jobs.tasks import execute_job
from app.models.job import Job, JobStatus


def _make_job(status: JobStatus, age: timedelta) -> str:
    session = get_sync_session()
    try:
        job = Job(id=uuid.uuid4(), tool="nmap", target="127.0.0.1", params={}, status=status)
        session.add(job)
        session.flush()
        job.created_at = datetime.now(timezone.utc) - age
        session.commit()
        return str(job.id)
    finally:
        session.close()


def _get_job(job_id: str) -> Job:
    session = get_sync_session()
    try:
        session.expire_on_commit = False
        return session.get(Job, uuid.UUID(job_id))
    finally:
        session.close()


def test_reconcile_marks_orphaned_queued_job_as_failed():
    job_id = _make_job(JobStatus.QUEUED, age=timedelta(hours=1))

    session = get_sync_session()
    try:
        reconciled = reconcile_stuck_jobs(session, stuck_after=timedelta(minutes=30))
    finally:
        session.close()

    assert uuid.UUID(job_id) in reconciled
    job = _get_job(job_id)
    assert job.status == JobStatus.FAILED
    assert "stuck at queued" in job.error.lower()
    assert job.finished_at is not None


def test_reconcile_marks_orphaned_running_job_as_failed():
    job_id = _make_job(JobStatus.RUNNING, age=timedelta(hours=1))

    session = get_sync_session()
    try:
        reconciled = reconcile_stuck_jobs(session, stuck_after=timedelta(minutes=30))
    finally:
        session.close()

    assert uuid.UUID(job_id) in reconciled
    assert _get_job(job_id).status == JobStatus.FAILED


def test_reconcile_leaves_recent_queued_job_alone():
    job_id = _make_job(JobStatus.QUEUED, age=timedelta(minutes=1))

    session = get_sync_session()
    try:
        reconciled = reconcile_stuck_jobs(session, stuck_after=timedelta(minutes=30))
    finally:
        session.close()

    assert reconciled == []
    assert _get_job(job_id).status == JobStatus.QUEUED


def test_reconcile_leaves_job_alone_when_rq_entry_still_exists():
    job_id = _make_job(JobStatus.QUEUED, age=timedelta(hours=1))
    queue = get_queue()
    queue.enqueue(execute_job, job_id, "nmap", {"target": "127.0.0.1"}, 60, job_id=job_id)

    session = get_sync_session()
    try:
        reconciled = reconcile_stuck_jobs(session, stuck_after=timedelta(minutes=30))
    finally:
        session.close()

    assert reconciled == []
    assert _get_job(job_id).status == JobStatus.QUEUED


def test_reconcile_is_idempotent_on_repeated_calls():
    job_id = _make_job(JobStatus.QUEUED, age=timedelta(hours=1))

    session = get_sync_session()
    try:
        first = reconcile_stuck_jobs(session, stuck_after=timedelta(minutes=30))
    finally:
        session.close()
    assert uuid.UUID(job_id) in first
    first_error = _get_job(job_id).error

    session = get_sync_session()
    try:
        second = reconcile_stuck_jobs(session, stuck_after=timedelta(minutes=30))
    finally:
        session.close()

    assert second == []  # already FAILED, no longer a candidate
    assert _get_job(job_id).error == first_error  # untouched, not re-appended


def test_reconcile_with_no_candidates_returns_empty_list():
    session = get_sync_session()
    try:
        assert reconcile_stuck_jobs(session, stuck_after=timedelta(minutes=30)) == []
    finally:
        session.close()
