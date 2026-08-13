"""Phase 18 -- AI Mission lifecycle (Level 2: Execute Approved Tasks).

A Mission wraps a Recon Agent (`AIMissionPlanner`, unchanged) plan with
execution state so a human can approve the whole plan once instead of
clicking "Run" per step. Missions never execute anything themselves --
see `app/ai/orchestrator.py::MissionOrchestrator`, which creates a real
`Job` for each step through the exact same `is_executable()` +
`prepare_job()` pair `app/scheduling/ticker.py` already uses for its own,
independent caller. The link back to `Job` is `MissionStep.job_id` only --
`Job` itself is never modified for this phase, so every pre-existing
caller of `Job` stays untouched.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MissionStatus(str, enum.Enum):
    DRAFT = "DRAFT"  # plan proposed, not yet approved -- never auto-starts
    APPROVED = "APPROVED"  # human approved the whole plan, execution not started yet
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"  # a step failed; stop-on-failure, no retry in this phase
    CANCELLED = "CANCELLED"  # human kill switch


class MissionStepStatus(str, enum.Enum):
    PENDING = "PENDING"
    # Never got a Job: authorization was revoked before this step ran, the
    # model's tool choice was rejected (no valid tool), or prepare_job()
    # itself raised (unregistered tool/invalid args). See
    # ck_mission_step_job_id_required_when_executed -- SKIPPED is
    # deliberately the only terminal status that doesn't require a job_id.
    SKIPPED = "SKIPPED"
    QUEUED = "QUEUED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"  # the Job it ran as (job_id) finished with a non-zero exit / tool error
    CANCELLED = "CANCELLED"


class Mission(Base):
    __tablename__ = "missions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    # Mandatory, unlike Job.target -- a Mission always targets a real,
    # re-checkable Asset (never free text) so is_executable() can be
    # re-verified before every step. ON DELETE CASCADE (not SET NULL like
    # Job.target_id): a Mission has no independent meaning once its target
    # is gone, it is not a historical record the way a finished Job is.
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[MissionStatus] = mapped_column(
        Enum(MissionStatus, name="mission_status"), nullable=False, default=MissionStatus.DRAFT
    )
    # Hard cap independent of what the model proposed -- a Level 3+
    # foundation (see docs/phase-18-ai-agents.md), enforced by
    # MissionOrchestrator.advance_mission() regardless of plan length.
    max_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    # Raw provider output kept for debugging, mirrors MissionPlan.raw_response.
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("max_steps > 0", name="ck_mission_max_steps_positive"),
        Index("ix_missions_target_id", "target_id"),
        Index("ix_missions_status", "status"),
    )


class MissionStep(Base):
    __tablename__ = "mission_steps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    tool: Mapped[str | None] = mapped_column(String(64), nullable=True)
    profile: Mapped[str | None] = mapped_column(String(64), nullable=True)
    options: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[MissionStepStatus] = mapped_column(
        Enum(MissionStepStatus, name="mission_step_status"), nullable=False, default=MissionStepStatus.PENDING
    )
    # The only link between a Mission and a real Job -- deliberately not a
    # column on Job itself (Phase 18 does not touch the Job model, see the
    # module docstring). ON DELETE SET NULL: Job rows are never deleted in
    # practice today, but this keeps the same non-destructive precedent as
    # Job.target_id/Job.project_id.
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("mission_id", "step_order", name="uq_mission_step_order"),
        # A step cannot claim to have reached the queue or a terminal
        # execution state without actually being linked to the Job that
        # produced it -- catches an orchestration bug at the DB level
        # rather than silently persisting an inconsistent row.
        CheckConstraint(
            "status NOT IN ('QUEUED', 'SUCCESS', 'FAILED') OR job_id IS NOT NULL",
            name="ck_mission_step_job_id_required_when_executed",
        ),
        Index("ix_mission_steps_mission_id", "mission_id"),
        Index("ix_mission_steps_job_id", "job_id"),
    )
