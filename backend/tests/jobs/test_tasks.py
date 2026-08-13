import hashlib
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.sync_session import get_sync_session
from app.jobs.tasks import execute_job
from app.main import app
from app.models.job import Job, JobStatus
from app.tools import registry


async def _create_queued_job() -> str:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch("app.api.routes.jobs.get_queue") as mock_get_queue:
            mock_get_queue.return_value = MagicMock()
            response = await ac.post("/api/jobs", json={"tool": "nmap", "target": "10.0.0.1"})
    assert response.status_code == 201
    return response.json()["id"]


async def test_execute_job_marks_failed_on_unexpected_exception():
    """Regression test: before Phase 12, execute_job() only caught
    (ToolValidationError, ToolNotFoundError, KaliAgentError) -- any other
    exception (e.g. RQ's own JobTimeoutException firing before the tool's
    timeout did, see app/api/routes/jobs.py::create_job) propagated
    uncaught, leaving the job's DB row stuck at RUNNING forever with no
    failure ever recorded. The catch-all handler must still resolve the job
    to FAILED with a useful error message, then re-raise so RQ's own
    failed-job bookkeeping still sees it too.
    """
    job_id = await _create_queued_job()

    with patch("app.jobs.tasks.run_tool", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            execute_job(job_id, "nmap", {"target": "10.0.0.1"}, 60)

    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.FAILED
        assert job.error is not None
        assert "unexpected error" in job.error
        assert "boom" in job.error
        assert job.finished_at is not None
    finally:
        session.close()


async def test_execute_job_computes_evidence_hash_on_success():
    job_id = await _create_queued_job()
    stdout = "Nmap scan report for 10.0.0.1\nPORT 80/tcp open\n"

    with patch("app.jobs.tasks.run_tool", return_value={"stdout": stdout, "stderr": "", "exit_code": 0}):
        execute_job(job_id, "nmap", {"target": "10.0.0.1"}, 60)

    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.SUCCESS
        assert job.evidence_sha256 == hashlib.sha256(stdout.encode("utf-8")).hexdigest()
        assert len(job.evidence_sha256) == 64  # sha256 hex digest, matches Finding.signature's own precedent
    finally:
        session.close()


async def test_execute_job_computes_evidence_hash_even_on_nonzero_exit_code():
    """A FAILED-by-exit-code job still produced real stdout -- it still
    gets a hash, exactly like a SUCCESS job. Only the two exception-handler
    paths (tool never ran at all) leave it NULL, see the next two tests."""
    job_id = await _create_queued_job()
    stdout = "some partial output before the tool errored out\n"

    with patch("app.jobs.tasks.run_tool", return_value={"stdout": stdout, "stderr": "boom", "exit_code": 1}):
        execute_job(job_id, "nmap", {"target": "10.0.0.1"}, 60)

    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.FAILED
        assert job.evidence_sha256 == hashlib.sha256(stdout.encode("utf-8")).hexdigest()
    finally:
        session.close()


async def test_execute_job_hash_of_empty_stdout_is_well_defined_not_none():
    job_id = await _create_queued_job()

    with patch("app.jobs.tasks.run_tool", return_value={"stdout": "", "stderr": "", "exit_code": 0}):
        execute_job(job_id, "nmap", {"target": "10.0.0.1"}, 60)

    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        assert job.evidence_sha256 == hashlib.sha256(b"").hexdigest()
        assert job.evidence_sha256 is not None
    finally:
        session.close()


async def test_execute_job_hash_stays_none_when_tool_never_ran():
    """The tool-not-found/validation-error/KaliAgentError exception
    handlers never set job.stdout at all -- there is no output to prove
    the integrity of, so evidence_sha256 must stay NULL, not some hash of
    an empty/placeholder value."""
    job_id = await _create_queued_job()

    with patch.object(registry, "get_tool", side_effect=registry.ToolNotFoundError("nmap was removed")):
        execute_job(job_id, "nmap", {"target": "10.0.0.1"}, 60)

    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.FAILED
        assert job.stdout is None
        assert job.evidence_sha256 is None
    finally:
        session.close()


async def test_execute_job_hash_stays_none_on_unexpected_exception():
    job_id = await _create_queued_job()

    with patch("app.jobs.tasks.run_tool", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            execute_job(job_id, "nmap", {"target": "10.0.0.1"}, 60)

    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        assert job.stdout is None
        assert job.evidence_sha256 is None
    finally:
        session.close()
