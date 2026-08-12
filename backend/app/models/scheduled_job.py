"""Phase 14 -- Continuous Recon. A ScheduledJob periodically recreates a
normal Job (same tool/profile/params) against an Asset -- it is a
convenience that calls the exact same job-creation path as a manual scan
(see app/jobs/service.py), never a parallel execution mechanism. The ticker
that fires these (app/scheduling/ticker.py) enforces the same Policy Engine
authorization check on every single run, not just at creation time.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# Below this, a schedule is rejected at creation time -- prevents a
# misconfigured or abusive schedule from hammering a target or flooding the
# Job Engine (see "cron abuse" in the Phase 14 security audit).
MIN_INTERVAL_SECONDS = 300


class ScheduledJobStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Denormalized from asset_id at creation time (same pattern as
    # Job.project_id) so schedules can be filtered/listed without a join,
    # and so the row still identifies "whose" schedule this was after the
    # asset itself is deleted.
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    # Nullable + SET NULL (not CASCADE): deleting an Asset must not silently
    # delete the schedule's history -- app/scheduling/service.py explicitly
    # flips status to DISABLED first, in the same transaction as the asset
    # delete, so the row survives as a clearly-labeled disabled record.
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )

    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    profile: Mapped[str | None] = mapped_column(String(64), nullable=True)
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ScheduledJobStatus] = mapped_column(
        Enum(ScheduledJobStatus, name="scheduled_job_status"),
        nullable=False,
        default=ScheduledJobStatus.ACTIVE,
    )

    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )

    # Consecutive *scheduling* failures (couldn't even create/enqueue a Job:
    # asset deleted/unauthorized, tool/profile no longer valid) -- not scan
    # failures (a Job that ran and came back FAILED still counts as the
    # schedule having successfully done its job of firing). See
    # app/scheduling/ticker.py for the auto-pause threshold.
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )
