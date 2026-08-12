import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.jobs.pubsub import publish_job_update
from app.jobs.queue import get_queue
from app.jobs.service import prepare_job
from app.jobs.tasks import execute_job
from app.models.job import Job, JobStatus
from app.models.target import Target
from app.schemas.job import JobCreateRequest, JobResponse
from app.targets.authorization import is_executable
from app.tools import registry

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(request: JobCreateRequest, db: AsyncSession = Depends(get_db)) -> Job:
    project_id = None
    target_id = None
    target_address = request.target

    if request.target_id is not None:
        # This is the ONLY enforcement point for target authorization —
        # the AI planner, the frontend, the Phase 14 scheduler (via
        # app.jobs.service.prepare_job + this same is_executable check, see
        # app/scheduling/ticker.py), and every other caller all funnel
        # through here. UNKNOWN is rejected; nothing upstream can bypass it.
        target = await db.get(Target, request.target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="target not found")
        if not is_executable(target):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"target authorization status is {target.authorization_status.value}; "
                    "mark it LAB, AUTHORIZED, or LOCAL before running jobs against it"
                ),
            )
        project_id = target.project_id
        target_id = target.id
        target_address = target.address

    try:
        prepared = prepare_job(request.tool, request.profile, request.options, target_address, request.timeout)
    except registry.ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except registry.ToolValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = Job(
        tool=request.tool,
        profile=request.profile,
        target=target_address,
        project_id=project_id,
        target_id=target_id,
        params=prepared.full_params,
        status=JobStatus.QUEUED,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    queue = get_queue()
    # RQ's own job_timeout defaults to 180s independently of the tool's own
    # timeout budget -- without this, RQ was silently killing the RQ worker
    # process (JobTimeoutException) before a longer-running tool timeout
    # (e.g. nikto's 280s) ever got a chance to fire on its own, and since
    # that exception isn't one execute_job() catches, the job's DB row was
    # never updated to a terminal status -- it stayed RUNNING forever. Found
    # via Phase 12 end-to-end testing against a real (slow) external target.
    queue.enqueue(
        execute_job,
        str(job.id),
        request.tool,
        prepared.full_params,
        prepared.effective_timeout,
        job_id=str(job.id),
        job_timeout=prepared.effective_timeout + 30,
    )

    return job


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    status: JobStatus | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    target_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[Job]:
    stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(Job.status == status)
    if project_id is not None:
        stmt = stmt.where(Job.project_id == project_id)
    if target_id is not None:
        stmt = stmt.where(Job.target_id == target_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Job:
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Job:
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(status_code=400, detail=f"job already {job.status.value.lower()}, cannot cancel")

    queue = get_queue()
    if job.status == JobStatus.QUEUED:
        rq_job = queue.fetch_job(str(job_id))
        if rq_job is not None:
            rq_job.cancel()
    else:
        # Best effort: asks the worker to stop the current job. The remote
        # subprocess on the Kali agent still runs until its own timeout —
        # the agent does not yet expose a way to kill an in-flight scan by id.
        from rq.command import send_stop_job_command

        try:
            send_stop_job_command(queue.connection, str(job_id))
        except Exception:
            pass

    job.status = JobStatus.CANCELLED
    job.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)
    publish_job_update(str(job_id), {"id": str(job_id), "status": JobStatus.CANCELLED.value})
    return job
