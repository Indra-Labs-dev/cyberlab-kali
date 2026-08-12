from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.intel.sync import run_full_sync
from app.jobs.queue import get_queue
from app.models.vulnerability_intel import IntelSyncState
from app.schemas.intelligence import IntelSyncStateResponse, IntelSyncTriggerResponse

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.post("/sync", response_model=IntelSyncTriggerResponse, status_code=202)
async def trigger_intel_sync() -> IntelSyncTriggerResponse:
    """Manually triggers an immediate EPSS/CISA KEV/NVD sync instead of
    waiting for the daily background cycle (app/intel/sync.py). Runs
    through the existing RQ queue/worker -- same execution substrate as a
    Job, not a new one -- so this endpoint returns immediately (202) rather
    than blocking on real network calls.
    """
    queue = get_queue()
    queue.enqueue(run_full_sync, job_timeout=300)
    return IntelSyncTriggerResponse(status="queued")


@router.get("/status", response_model=list[IntelSyncStateResponse])
async def get_intel_sync_status(db: AsyncSession = Depends(get_db)) -> list[IntelSyncState]:
    result = await db.execute(select(IntelSyncState).order_by(IntelSyncState.source))
    return list(result.scalars().all())
