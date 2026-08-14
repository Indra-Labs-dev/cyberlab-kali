"""Phase 19 -- proves execute_job() and AI Memory regeneration are wired
together correctly and safely: a real Job finishing SUCCESS triggers a
real summary regeneration, and a failure in that hook can never affect
the Job's own already-committed status. Mirrors
tests/jobs/test_mission_integration.py's structure/reasoning; plain sync
throughout (see tests/ai/test_memory_service.py's module docstring for
why -- asyncio.run() inside the hook needs no already-running event loop,
exactly the real execute_job()/RQ-worker context).
"""

import uuid
from unittest.mock import patch

from sqlalchemy import select

from app.ai.provider import AIProvider
from app.db.sync_session import get_sync_session
from app.jobs.tasks import execute_job
from app.models.asset import Asset, AssetType, AuthorizationStatus
from app.models.job import Job, JobStatus
from app.models.project import Project
from app.models.project_ai_summary import ProjectAISummary


class FakeProvider(AIProvider):
    def __init__(self, response: str = "Summary text.") -> None:
        self.response = response

    async def generate(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        return self.response


def _make_project_asset_and_job() -> tuple[str, str]:
    session = get_sync_session()
    try:
        project = Project(id=uuid.uuid4(), name="Memory Integration Fixture")
        session.add(project)
        session.flush()
        # Phase 23: execute_job() now re-verifies is_executable() at
        # execution time -- a directly-ORM-inserted Asset doesn't go
        # through infer_default_authorization() the way the real
        # POST /api/projects/{id}/assets route does, so authorization_status
        # must be set explicitly here (same fixture gap already found and
        # fixed for tests/chains/test_service.py in Phase 21).
        asset = Asset(
            id=uuid.uuid4(),
            project_id=project.id,
            name="kali",
            hostname="cyberlab-kali",
            type=AssetType.CONTAINER,
            authorization_status=AuthorizationStatus.LAB,
        )
        session.add(asset)
        session.flush()
        job = Job(
            id=uuid.uuid4(), tool="nmap", target="cyberlab-kali", project_id=project.id,
            target_id=asset.id, params={"target": "cyberlab-kali"}, status=JobStatus.QUEUED,
        )
        session.add(job)
        session.commit()
        return str(project.id), str(job.id)
    finally:
        session.close()


def _get_summary(project_id: str) -> ProjectAISummary | None:
    session = get_sync_session()
    try:
        session.expire_on_commit = False
        return session.execute(
            select(ProjectAISummary).where(ProjectAISummary.project_id == uuid.UUID(project_id))
        ).scalar_one_or_none()
    finally:
        session.close()


def test_execute_job_success_regenerates_project_summary():
    project_id, job_id = _make_project_asset_and_job()

    with patch("app.jobs.tasks.run_tool", return_value={"stdout": "", "stderr": "", "exit_code": 0}):
        with patch("app.ai.memory.OllamaProvider", return_value=FakeProvider("Nmap scan completed cleanly.")):
            execute_job(job_id, "nmap", {"target": "cyberlab-kali"}, 60)

    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.SUCCESS
    finally:
        session.close()

    # The post-completion hook must have regenerated the summary
    # automatically -- no explicit call from this test.
    summary = _get_summary(project_id)
    assert summary is not None
    assert summary.summary == "Nmap scan completed cleanly."
    assert str(summary.based_on_job_id) == job_id


def test_job_stays_success_even_if_summary_regeneration_fails():
    project_id, job_id = _make_project_asset_and_job()

    with patch("app.jobs.tasks.run_tool", return_value={"stdout": "", "stderr": "", "exit_code": 0}):
        with patch("app.ai.memory.regenerate_project_summary_for_job", side_effect=RuntimeError("boom")):
            # execute_job() must not raise even though the memory hook blew
            # up -- swallowed (and logged) by its own isolated try/except.
            execute_job(job_id, "nmap", {"target": "cyberlab-kali"}, 60)

    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.SUCCESS
        assert job.exit_code == 0
    finally:
        session.close()

    assert _get_summary(project_id) is None  # the hook never got to write anything


def test_mission_hook_and_memory_hook_are_independent():
    """A failure in one post-completion hook must never suppress the
    other -- both are separate try/except blocks in execute_job()'s
    finally. Here the mission hook is forced to fail; the memory hook
    must still run and succeed."""
    project_id, job_id = _make_project_asset_and_job()

    with patch("app.jobs.tasks.run_tool", return_value={"stdout": "", "stderr": "", "exit_code": 0}):
        with patch("app.ai.orchestrator.advance_mission_for_job", side_effect=RuntimeError("mission hook boom")):
            with patch("app.ai.memory.OllamaProvider", return_value=FakeProvider("Still generated.")):
                execute_job(job_id, "nmap", {"target": "cyberlab-kali"}, 60)

    summary = _get_summary(project_id)
    assert summary is not None
    assert summary.summary == "Still generated."
