import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.jobs.pubsub import publish_job_update
from app.jobs.queue import get_queue
from app.jobs.tasks import execute_job
from app.models.job import Job, JobStatus
from app.schemas.job import JobCreateRequest, JobResponse
from app.tools import registry

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(request: JobCreateRequest, db: AsyncSession = Depends(get_db)) -> Job:
    try:
        registry.get_tool(request.tool)
    except registry.ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    full_params = {**request.options, "target": request.target}
    try:
        registry.build_command(request.tool, full_params)
    except registry.ToolValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = Job(
        tool=request.tool,
        target=request.target,
        params=full_params,
        status=JobStatus.QUEUED,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    queue = get_queue()
    queue.enqueue(execute_job, str(job.id), request.tool, full_params, request.timeout, job_id=str(job.id))

    return job


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    status: JobStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[Job]:
    stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(Job.status == status)
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
