import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.jobs.queue import get_queue
from app.jobs.service import prepare_job
from app.jobs.tasks import execute_job
from app.models.asset import Asset
from app.models.asset_change_event import AssetChangeEvent, ChangeType
from app.models.finding import Severity
from app.models.job import Job, JobStatus
from app.models.scheduled_job import ScheduledJob, ScheduledJobStatus
from app.schemas.asset_change_event import AssetChangeEventResponse
from app.schemas.scheduled_job import ScheduledJobCreateRequest, ScheduledJobResponse, ScheduledJobUpdateRequest
from app.targets.authorization import is_executable
from app.tools import registry

router = APIRouter(tags=["schedules"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/assets/{asset_id}/schedules", response_model=list[ScheduledJobResponse])
async def list_asset_schedules(asset_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[ScheduledJob]:
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    result = await db.execute(
        select(ScheduledJob).where(ScheduledJob.asset_id == asset_id).order_by(ScheduledJob.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/assets/{asset_id}/schedules", response_model=ScheduledJobResponse, status_code=201)
async def create_asset_schedule(
    asset_id: uuid.UUID, request: ScheduledJobCreateRequest, db: AsyncSession = Depends(get_db)
) -> ScheduledJob:
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    # Same Policy Engine check as a manual job -- a schedule cannot be
    # created against an asset that couldn't be scanned manually right now.
    # The ticker (app/scheduling/ticker.py) re-checks this on every future
    # run, since authorization can change after creation.
    if not is_executable(asset):
        raise HTTPException(
            status_code=403,
            detail=(
                f"asset authorization status is {asset.authorization_status.value}; "
                "mark it LAB, AUTHORIZED, or LOCAL before scheduling jobs against it"
            ),
        )

    try:
        prepare_job(request.tool, request.profile, request.params, asset.address)
    except registry.ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except registry.ToolValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    schedule = ScheduledJob(
        project_id=asset.project_id,
        asset_id=asset.id,
        tool=request.tool,
        profile=request.profile,
        params=request.params,
        interval_seconds=request.interval_seconds,
        status=ScheduledJobStatus.ACTIVE,
        # First run happens promptly (establishes the baseline) rather than
        # waiting a full interval -- same "activity should reflect reality
        # quickly" choice made for Asset.first_seen in Phase 13.
        next_run_at=_now(),
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.get("/schedules/{schedule_id}", response_model=ScheduledJobResponse)
async def get_schedule(schedule_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ScheduledJob:
    schedule = await db.get(ScheduledJob, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    return schedule


@router.patch("/schedules/{schedule_id}", response_model=ScheduledJobResponse)
async def update_schedule(
    schedule_id: uuid.UUID, request: ScheduledJobUpdateRequest, db: AsyncSession = Depends(get_db)
) -> ScheduledJob:
    schedule = await db.get(ScheduledJob, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="schedule not found")

    updates = request.model_dump(exclude_unset=True)
    resuming = updates.get("status") == ScheduledJobStatus.ACTIVE and schedule.status != ScheduledJobStatus.ACTIVE

    for field, value in updates.items():
        setattr(schedule, field, value)

    if resuming:
        # A human just fixed whatever was wrong (or simply wants it back
        # on) -- give it a clean slate and run it again promptly rather
        # than waiting out whatever next_run_at happened to be paused at.
        schedule.next_run_at = _now()
        schedule.consecutive_failures = 0
        schedule.last_error = None

    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    schedule = await db.get(ScheduledJob, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    await db.delete(schedule)
    await db.commit()


@router.post("/schedules/{schedule_id}/run", response_model=ScheduledJobResponse)
async def run_schedule_now(schedule_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ScheduledJob:
    """Runs a schedule immediately, through the exact same authorization and
    Tool Registry validation as its automatic ticks -- it just skips waiting
    for next_run_at. Does not itself change next_run_at (the periodic
    cadence is unaffected by an ad hoc manual run), mirroring PAUSED
    schedules still being runnable this way if desired.
    """
    schedule = await db.get(ScheduledJob, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    if schedule.status == ScheduledJobStatus.DISABLED:
        raise HTTPException(status_code=400, detail="schedule is disabled and cannot be run")
    if schedule.asset_id is None:
        raise HTTPException(status_code=400, detail="schedule has no asset")

    asset = await db.get(Asset, schedule.asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    if not is_executable(asset):
        raise HTTPException(
            status_code=403,
            detail=f"asset authorization status is {asset.authorization_status.value}",
        )

    try:
        prepared = prepare_job(schedule.tool, schedule.profile, schedule.params, asset.address)
    except registry.ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except registry.ToolValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = Job(
        tool=schedule.tool,
        profile=schedule.profile,
        target=asset.address,
        project_id=asset.project_id,
        target_id=asset.id,
        params=prepared.full_params,
        status=JobStatus.QUEUED,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    queue = get_queue()
    queue.enqueue(
        execute_job,
        str(job.id),
        schedule.tool,
        prepared.full_params,
        prepared.effective_timeout,
        job_id=str(job.id),
        job_timeout=prepared.effective_timeout + 30,
    )

    schedule.last_run_at = _now()
    schedule.last_job_id = job.id
    schedule.consecutive_failures = 0
    schedule.last_error = None
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.get("/assets/{asset_id}/changes", response_model=list[AssetChangeEventResponse])
async def list_asset_changes(
    asset_id: uuid.UUID,
    change_type: ChangeType | None = Query(default=None),
    severity: Severity | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    before: datetime | None = Query(default=None, description="Only events detected strictly before this timestamp"),
    db: AsyncSession = Depends(get_db),
) -> list[AssetChangeEvent]:
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")

    stmt = select(AssetChangeEvent).where(AssetChangeEvent.asset_id == asset_id)
    if change_type is not None:
        stmt = stmt.where(AssetChangeEvent.change_type == change_type)
    if severity is not None:
        stmt = stmt.where(AssetChangeEvent.severity == severity)
    if before is not None:
        stmt = stmt.where(AssetChangeEvent.detected_at < before)
    stmt = stmt.order_by(AssetChangeEvent.detected_at.desc()).limit(limit)

    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/asset-changes", response_model=list[AssetChangeEventResponse])
async def list_all_asset_changes(
    project_id: uuid.UUID | None = Query(default=None),
    change_type: ChangeType | None = Query(default=None),
    severity: Severity | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    before: datetime | None = Query(default=None, description="Only events detected strictly before this timestamp"),
    db: AsyncSession = Depends(get_db),
) -> list[AssetChangeEvent]:
    """SOC-lite -- the cross-project "recent changes" half of the roadmap's
    "Findings actifs + changements récents" view. `list_asset_changes()`
    above already covers a single asset; this is the same query pattern
    already used privately inside POST /api/ai/chat (project-scoped change
    enrichment) generalized to every asset and made an optional filter
    rather than a requirement -- no new table, no new model. `project_id`
    that matches nothing (or doesn't exist) is not a 404: it's a filter on
    a list endpoint, same convention as GET /api/findings?project_id=.
    """
    stmt = select(AssetChangeEvent).join(Asset, AssetChangeEvent.asset_id == Asset.id)
    if project_id is not None:
        stmt = stmt.where(Asset.project_id == project_id)
    if change_type is not None:
        stmt = stmt.where(AssetChangeEvent.change_type == change_type)
    if severity is not None:
        stmt = stmt.where(AssetChangeEvent.severity == severity)
    if before is not None:
        stmt = stmt.where(AssetChangeEvent.detected_at < before)
    stmt = stmt.order_by(AssetChangeEvent.detected_at.desc()).limit(limit)

    result = await db.execute(stmt)
    return list(result.scalars().all())
