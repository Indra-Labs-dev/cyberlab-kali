"""Phase 19 -- app/ai/memory.py: cooldown/upsert behavior, project/job
resolution for the execute_job() hook, and isolation from a Job's own
status. Real Postgres sessions (sync), mirrors the style of
tests/ai/test_orchestrator.py.

Deliberately plain `def test_...` (not `async def`) throughout this file:
regenerate_project_summary() bridges its one async call with
asyncio.run(), which raises if called from a context that already has a
running event loop -- exactly what pytest-asyncio's `asyncio_mode = auto`
gives every `async def` test. In real production this function is only
ever called from a sync context with no running loop (execute_job() in
the RQ worker process, or asyncio.to_thread() from the API route) -- so
these tests use sync fixtures (direct ORM inserts, mirroring
tests/ai/test_correlation_report_routes.py's style) to match that reality
exactly, rather than changing the production code to accommodate a
test-only artifact.
"""

import uuid
from unittest.mock import patch

from sqlalchemy import select

from app.ai.memory import regenerate_project_summary, regenerate_project_summary_for_job
from app.ai.provider import AIProvider
from app.db.sync_session import get_sync_session
from app.models.asset import Asset, AssetType
from app.models.finding import Confidence, Finding, Severity
from app.models.job import Job, JobStatus
from app.models.project import Project
from app.models.project_ai_summary import ProjectAISummary


class FakeProvider(AIProvider):
    def __init__(self, response: str = "A short summary.") -> None:
        self.response = response
        self.call_count = 0
        self.last_prompt: str | None = None

    async def generate(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        self.call_count += 1
        self.last_prompt = prompt
        return self.response


def _make_project_with_asset() -> tuple[str, str]:
    session = get_sync_session()
    try:
        project = Project(id=uuid.uuid4(), name="Memory Fixture")
        session.add(project)
        session.flush()
        asset = Asset(id=uuid.uuid4(), project_id=project.id, name="kali", hostname="cyberlab-kali", type=AssetType.CONTAINER)
        session.add(asset)
        session.commit()
        return str(project.id), str(asset.id)
    finally:
        session.close()


def _make_success_job(project_id: str, asset_id: str, tool: str = "nmap") -> str:
    session = get_sync_session()
    try:
        job = Job(
            id=uuid.uuid4(), tool=tool, target="cyberlab-kali", project_id=uuid.UUID(project_id),
            target_id=uuid.UUID(asset_id), params={}, status=JobStatus.SUCCESS,
        )
        session.add(job)
        session.commit()
        return str(job.id)
    finally:
        session.close()


def _make_failed_job(project_id: str, asset_id: str) -> str:
    session = get_sync_session()
    try:
        job = Job(
            id=uuid.uuid4(), tool="nmap", target="cyberlab-kali", project_id=uuid.UUID(project_id),
            target_id=uuid.UUID(asset_id), params={}, status=JobStatus.FAILED,
        )
        session.add(job)
        session.commit()
        return str(job.id)
    finally:
        session.close()


def _make_finding(job_id: str, severity: Severity) -> None:
    session = get_sync_session()
    try:
        session.add(
            Finding(
                id=uuid.uuid4(), job_id=uuid.UUID(job_id), target="cyberlab-kali", source_tool="nmap",
                title="Open port", description="", severity=severity, confidence=Confidence.MEDIUM,
                evidence={}, cve_ids=[],
            )
        )
        session.commit()
    finally:
        session.close()


def _get_summary_row(project_id: str) -> ProjectAISummary | None:
    session = get_sync_session()
    try:
        session.expire_on_commit = False
        return session.execute(
            select(ProjectAISummary).where(ProjectAISummary.project_id == uuid.UUID(project_id))
        ).scalar_one_or_none()
    finally:
        session.close()


def test_regenerate_creates_a_new_row():
    project_id, asset_id = _make_project_with_asset()
    provider = FakeProvider("Project has one lab asset.")

    row = regenerate_project_summary(uuid.UUID(project_id), provider)

    assert row is not None
    assert row.summary == "Project has one lab asset."
    assert provider.call_count == 1
    stored = _get_summary_row(project_id)
    assert stored.summary == "Project has one lab asset."


async def test_regenerate_works_even_when_called_from_a_running_event_loop():
    """The exact scenario that exposed a real bug during Phase 19
    verification: regenerate_project_summary() calling a bare
    asyncio.run() blew up silently (caught by execute_job()'s own outer
    except Exception) whenever execute_job() was invoked synchronously
    from inside an already-async caller -- as several pre-existing tests
    do (tests/assets/test_activity.py, for instance). _run_coro()'s
    thread-fallback must make this actually work instead of no-op'ing.
    This test itself is `async def`, deliberately, to have a real running
    loop in this thread when regenerate_project_summary() is called.
    """
    project_id, asset_id = _make_project_with_asset()
    provider = FakeProvider("Generated from inside a running loop.")

    row = regenerate_project_summary(uuid.UUID(project_id), provider)

    assert row is not None
    assert row.summary == "Generated from inside a running loop."
    assert provider.call_count == 1


def test_regenerate_unknown_project_returns_none():
    provider = FakeProvider()
    row = regenerate_project_summary(uuid.uuid4(), provider)
    assert row is None
    assert provider.call_count == 0


def test_regenerate_within_cooldown_is_a_no_op_unless_forced():
    project_id, asset_id = _make_project_with_asset()
    provider = FakeProvider("First summary.")
    regenerate_project_summary(uuid.UUID(project_id), provider)
    assert provider.call_count == 1

    provider.response = "Second summary."
    second = regenerate_project_summary(uuid.UUID(project_id), provider)
    assert provider.call_count == 1  # never called again -- still within cooldown
    assert second.summary == "First summary."  # unchanged

    forced = regenerate_project_summary(uuid.UUID(project_id), provider, force=True)
    assert provider.call_count == 2
    assert forced.summary == "Second summary."


def test_regenerate_upserts_not_duplicates():
    project_id, asset_id = _make_project_with_asset()
    provider = FakeProvider()
    regenerate_project_summary(uuid.UUID(project_id), provider)
    regenerate_project_summary(uuid.UUID(project_id), provider, force=True)

    session = get_sync_session()
    try:
        rows = list(
            session.execute(
                select(ProjectAISummary).where(ProjectAISummary.project_id == uuid.UUID(project_id))
            ).scalars()
        )
        assert len(rows) == 1
    finally:
        session.close()


def test_regenerate_severity_counts_reflect_real_findings():
    project_id, asset_id = _make_project_with_asset()
    job_id = _make_success_job(project_id, asset_id)
    _make_finding(job_id, Severity.HIGH)
    _make_finding(job_id, Severity.HIGH)
    _make_finding(job_id, Severity.LOW)

    provider = FakeProvider()
    regenerate_project_summary(uuid.UUID(project_id), provider)

    assert provider.call_count == 1
    assert "HIGH" in provider.last_prompt
    assert "LOW" in provider.last_prompt


def test_regenerate_for_job_skips_failed_jobs():
    project_id, asset_id = _make_project_with_asset()
    job_id = _make_failed_job(project_id, asset_id)

    with patch("app.ai.memory.OllamaProvider", return_value=FakeProvider()) as mock_provider:
        regenerate_project_summary_for_job(job_id)
        mock_provider.assert_not_called()  # skipped before any provider was ever constructed

    assert _get_summary_row(project_id) is None


def test_regenerate_for_job_skips_jobs_without_target_id():
    project_id, _ = _make_project_with_asset()
    session = get_sync_session()
    try:
        job = Job(id=uuid.uuid4(), tool="nmap", target="10.0.0.1", project_id=uuid.UUID(project_id), params={}, status=JobStatus.SUCCESS)
        session.add(job)
        session.commit()
        job_id = str(job.id)
    finally:
        session.close()

    with patch("app.ai.memory.OllamaProvider", return_value=FakeProvider()):
        regenerate_project_summary_for_job(job_id)
    assert _get_summary_row(project_id) is None


def test_regenerate_for_job_unknown_job_is_a_no_op():
    # Must not raise -- a job vanishing between commit and hook execution
    # (shouldn't happen in practice) must still be a safe no-op.
    with patch("app.ai.memory.OllamaProvider", return_value=FakeProvider()):
        regenerate_project_summary_for_job(str(uuid.uuid4()))


def test_regenerate_for_job_success_creates_summary_with_provenance():
    project_id, asset_id = _make_project_with_asset()
    job_id = _make_success_job(project_id, asset_id)

    with patch("app.ai.memory.OllamaProvider", return_value=FakeProvider("Real job triggered this.")):
        regenerate_project_summary_for_job(job_id)

    row = _get_summary_row(project_id)
    assert row is not None
    assert str(row.based_on_job_id) == job_id
    assert row.summary == "Real job triggered this."
