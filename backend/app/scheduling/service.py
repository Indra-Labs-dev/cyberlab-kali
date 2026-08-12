"""Async-side ScheduledJob helpers used by the API routes (app/api/routes/
schedules.py, and the asset/target delete routes). The tick loop itself is
sync and lives in app/scheduling/ticker.py (runs in the worker process, see
app/jobs/worker.py) -- same async/sync split as the rest of the Job Engine.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduled_job import ScheduledJob, ScheduledJobStatus


async def disable_schedules_for_asset(db: AsyncSession, asset_id: uuid.UUID) -> None:
    """Called from within the same transaction as an Asset delete (see
    app/api/routes/assets.py and targets.py) so a ScheduledJob never keeps
    pointing at a deleted asset in an ACTIVE state -- "disabled cleanly"
    rather than left dangling for the ticker to discover later.
    """
    result = await db.execute(
        select(ScheduledJob).where(
            ScheduledJob.asset_id == asset_id,
            ScheduledJob.status != ScheduledJobStatus.DISABLED,
        )
    )
    for schedule in result.scalars():
        schedule.status = ScheduledJobStatus.DISABLED
        schedule.last_error = "asset deleted"
