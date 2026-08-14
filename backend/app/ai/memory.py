"""Phase 19 -- AI Memory per Project. Regenerates and persists the stored
`ProjectAISummary` a human reads instead of the model recalculating a
summary on every question (see docs/phase-19-ai-memory.md).

Sync, module-level functions -- mirrors app/ai/orchestrator.py's Phase 18
pattern (approve_mission/advance_mission/cancel_mission), not a class:
regeneration needs the AI provider (an async call), but the *caller*
(execute_job()'s isolated post-completion hook, itself fully sync) must
never be forced to juggle an event loop or fake provider dependency
injection -- `_run_coro()` bridges the one async call this module makes.
In real production this is always asyncio.run() (execute_job() runs in
the RQ worker process, never inside an already-running event loop) --
but a bare asyncio.run() raises if a loop somehow *is* already running,
and that exception would otherwise be silently absorbed by
execute_job()'s own outer `except Exception: logger.exception(...)`,
leaving the summary silently never regenerated with only a "coroutine was
never awaited" ResourceWarning as a clue. `_run_coro()` falls back to
running the coroutine on a separate thread with its own fresh loop in
that case, so regeneration still actually happens instead of silently
no-op'ing.

Deliberately NOT hooked into the same transaction as Diff Engine/
Correlation/Graph (app/jobs/tasks.py::_execute_job, all fast, synchronous,
DB-only work) -- an LLM call is slow and network-bound (10-30s observed
with the local Ollama model in Phase 18 testing), so it follows Phase
18's `advance_mission_for_job` isolation instead: a brand new session,
called from execute_job()'s outermost `finally`, after the Job's own
session has already closed and its terminal status already committed. A
bug or timeout here can never affect `job.status`.
"""

import asyncio
import logging
import threading
import uuid
from collections.abc import Coroutine
from datetime import datetime, timedelta, timezone
from typing import Any, TypeVar

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.ai.agents.summary import SummaryAgent
from app.ai.ollama import OllamaProvider
from app.ai.provider import AIProvider
from app.db.sync_session import get_sync_session
from app.models.asset import Asset
from app.models.asset_change_event import AssetChangeEvent
from app.models.finding import Finding
from app.models.job import Job, JobStatus
from app.models.project import Project
from app.models.project_ai_summary import ProjectAISummary

logger = logging.getLogger("cyberlab.ai.memory")

# Approximates "after each batch of scans" (docs/roadmap.md) without a new
# batch-tracking mechanism: several jobs finishing in quick succession
# (e.g. a Mission's several steps, or a ScheduledJob tick touching several
# assets) regenerate the summary once, not once per job. A manual
# regenerate (POST /api/ai/projects/{id}/summary/regenerate) bypasses this
# via `force=True` -- explicit human intent overrides the heuristic.
_REGEN_COOLDOWN = timedelta(seconds=300)

_RECENT_CHANGES_LIMIT = 20


def _now() -> datetime:
    return datetime.now(timezone.utc)


_T = TypeVar("_T")


def _run_coro(coro: Coroutine[Any, Any, _T]) -> _T:
    """Runs `coro` to completion regardless of whether the calling thread
    already has an active event loop -- see module docstring."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, _T] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 -- re-raised on the calling thread below
            error["value"] = exc

    thread = threading.Thread(target=_runner)
    thread.start()
    thread.join()
    if "value" in error:
        raise error["value"]
    return result["value"]


def regenerate_project_summary(
    project_id: uuid.UUID, provider: AIProvider | None = None, *, force: bool = False, based_on_job_id: uuid.UUID | None = None
) -> ProjectAISummary | None:
    """Sync, self-opening. Returns None if the Project doesn't exist, or if
    a summary already exists and was generated within the cooldown window
    and `force` is False (a no-op, not an error -- this is what makes the
    per-job hook cheap when several jobs finish close together).
    """
    provider = provider or OllamaProvider()
    session = get_sync_session()
    try:
        project = session.get(Project, project_id)
        if project is None:
            return None

        existing = session.execute(
            select(ProjectAISummary).where(ProjectAISummary.project_id == project_id)
        ).scalar_one_or_none()
        if existing is not None and not force and _now() - existing.generated_at < _REGEN_COOLDOWN:
            return existing

        assets = list(session.execute(select(Asset).where(Asset.project_id == project_id)).scalars())

        severity_rows = session.execute(
            select(Finding.severity, func.count())
            .join(Job, Finding.job_id == Job.id)
            .where(Job.project_id == project_id)
            .group_by(Finding.severity)
        ).all()
        severity_counts = {severity.value: count for severity, count in severity_rows}

        recent_changes = list(
            session.execute(
                select(AssetChangeEvent)
                .join(Asset, AssetChangeEvent.asset_id == Asset.id)
                .where(Asset.project_id == project_id)
                .order_by(AssetChangeEvent.detected_at.desc())
                .limit(_RECENT_CHANGES_LIMIT)
            ).scalars()
        )

        agent = SummaryAgent(provider)
        text = _run_coro(agent.summarize(project.name, assets, severity_counts, recent_changes))

        # Phase 23 -- the read above (`existing = ...`) is a plain,
        # unlocked SELECT: it only decides whether to skip the (slow) LLM
        # call under the cooldown, never gates correctness. The actual
        # write is a single atomic INSERT ... ON CONFLICT (project_id) DO
        # UPDATE, so two calls racing past the cooldown check concurrently
        # (e.g. two Jobs from the same project finishing seconds apart)
        # can never both attempt a plain INSERT and hit the unique
        # constraint (uq_project_ai_summary_project) as an unhandled
        # IntegrityError -- Postgres serializes the two upserts itself,
        # and exactly one row survives with whichever write committed
        # last. No SELECT ... FOR UPDATE is needed here (unlike
        # Mission/ChainRun advancement): those hold a lock across a
        # multi-statement decision; this is a single, already-atomic
        # statement.
        generated_at = _now()
        stmt = (
            pg_insert(ProjectAISummary)
            .values(
                id=uuid.uuid4(),
                project_id=project_id,
                summary=text,
                based_on_job_id=based_on_job_id,
                generated_at=generated_at,
            )
            .on_conflict_do_update(
                index_elements=[ProjectAISummary.project_id],
                set_={
                    "summary": text,
                    "based_on_job_id": based_on_job_id,
                    "generated_at": generated_at,
                },
            )
        )
        session.execute(stmt)
        session.commit()

        # populate_existing=True: `existing` (if not None) is already in
        # this session's identity map from the read above, with its
        # pre-write attribute values -- a plain select() would return that
        # same cached Python object as-is rather than the row this INSERT
        # ... ON CONFLICT just wrote, since Core-level DML doesn't sync back
        # to already-loaded ORM instances on its own.
        row = session.execute(
            select(ProjectAISummary)
            .where(ProjectAISummary.project_id == project_id)
            .execution_options(populate_existing=True)
        ).scalar_one()
        return row
    finally:
        session.close()


def regenerate_project_summary_for_job(job_id: uuid.UUID | str) -> None:
    """Called by app/jobs/tasks.py::execute_job() strictly after that
    job's own session has already closed and its terminal status already
    committed -- see this module's docstring for why. A Job that isn't
    SUCCESS, has no target_id, or whose Asset has no project_id is a cheap
    no-op.
    """
    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        if job is None or job.status != JobStatus.SUCCESS or job.target_id is None:
            return
        asset = session.get(Asset, job.target_id)
        if asset is None:
            return
        project_id = asset.project_id
        resolved_job_id = job.id
    finally:
        session.close()

    regenerate_project_summary(project_id, based_on_job_id=resolved_job_id)
