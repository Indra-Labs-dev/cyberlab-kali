from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.sync_session import get_sync_session
from app.jobs.tasks import execute_job
from app.main import app
from app.models.job import Job, JobStatus


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
