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
            # 127.0.0.1 classifies as LOCAL (app/targets/authorization.py) so
            # this free-text job passes the Phase 23 authorization gate.
            response = await ac.post("/api/jobs", json={"tool": "nmap", "target": "127.0.0.1"})
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


# --- Phase 23 P0.2: authorization re-verified at execution time ---


async def _create_queued_job_for_lab_asset() -> tuple[str, str]:
    """A real target_id-linked Job against a real, LAB-authorized Asset --
    unlike _create_queued_job()'s free-text target, this one has a mutable
    authorization_status that can be revoked after creation."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        project = (await ac.post("/api/projects", json={"name": "Revocation Test Project"})).json()
        asset = (
            await ac.post(
                f"/api/projects/{project['id']}/assets",
                json={"name": "kali", "hostname": "cyberlab-kali", "type": "CONTAINER"},
            )
        ).json()
        assert asset["authorization_status"] == "LAB"

        with patch("app.api.routes.jobs.get_queue") as mock_get_queue:
            mock_get_queue.return_value = MagicMock()
            response = await ac.post("/api/jobs", json={"tool": "nmap", "target_id": asset["id"]})
    assert response.status_code == 201
    return response.json()["id"], asset["id"]


def _revoke_authorization(asset_id: str) -> None:
    from app.models.asset import Asset, AuthorizationStatus

    session = get_sync_session()
    try:
        asset = session.get(Asset, asset_id)
        asset.authorization_status = AuthorizationStatus.UNKNOWN
        session.commit()
    finally:
        session.close()


async def test_execute_job_refuses_when_authorization_revoked_after_creation():
    """The TOCTOU window this closes: is_executable() passed at Job creation
    (POST /api/jobs), but authorization is revoked (e.g. PATCH
    /api/assets/{id}) before the worker actually picks the Job up. The tool
    must never run against a target that is no longer authorized."""
    job_id, asset_id = await _create_queued_job_for_lab_asset()
    _revoke_authorization(asset_id)

    with patch("app.jobs.tasks.run_tool") as mock_run_tool:
        execute_job(job_id, "nmap", {"target": "cyberlab-kali"}, 60)
        mock_run_tool.assert_not_called()

    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.FAILED
        assert "authorization status is UNKNOWN" in job.error
        assert job.stdout is None
        assert job.evidence_sha256 is None
    finally:
        session.close()


async def test_execute_job_still_runs_when_authorization_remains_valid():
    """Non-regression: the new re-check must not refuse a Job whose
    authorization is still valid at execution time -- this is the ordinary,
    overwhelmingly common case."""
    job_id, _asset_id = await _create_queued_job_for_lab_asset()

    with patch("app.jobs.tasks.run_tool", return_value={"stdout": "ok", "stderr": "", "exit_code": 0}) as mock_run_tool:
        execute_job(job_id, "nmap", {"target": "cyberlab-kali"}, 60)
        mock_run_tool.assert_called_once()

    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.SUCCESS
    finally:
        session.close()
