"""Phase 21 -- Tool Orchestrator (deterministic job chaining). A
`MissionTemplate` is a reusable, human-authored, ordered list of
(tool, profile, condition) -- entirely unrelated to Phase 18's `Mission`
(AI-planned via AIMissionPlanner, human-approved once, then a FIXED step
list executes). The two are deliberately separate systems, per explicit
project decision: never merge this module with app/ai/orchestrator.py, its
Mission/MissionStep models, or its badges. A MissionTemplate has no AI
involvement at all -- a human authors the template once, ahead of time;
running it against a target is itself the human's deliberate action, so
there is no separate DRAFT/APPROVED review step the way a Mission needs
one (an AI-proposed plan needs review; a template a human already wrote
does not).

`MissionTemplateStep` step 0 is always `ALWAYS` (no previous step to
gate on); every later step's condition is evaluated against the
immediately preceding step's Job result at run time (app/chains/service.py).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ChainConditionType(str, enum.Enum):
    ALWAYS = "ALWAYS"  # step 0 only -- no previous step to gate on
    PORT_OPEN = "PORT_OPEN"  # previous step's result (nmap-shaped) has an open port in condition_params["ports"]
    TECHNOLOGY_DETECTED = "TECHNOLOGY_DETECTED"  # previous step's result (whatweb-shaped) identified >=1 technology
    MIN_SEVERITY = "MIN_SEVERITY"  # previous step's result (nuclei-shaped) has a finding >= condition_params["min_severity"]


class MissionTemplate(Base):
    __tablename__ = "mission_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class MissionTemplateStep(Base):
    __tablename__ = "mission_template_steps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mission_templates.id", ondelete="CASCADE"), nullable=False
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    profile: Mapped[str | None] = mapped_column(String(64), nullable=True)
    options: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    condition_type: Mapped[ChainConditionType] = mapped_column(
        Enum(ChainConditionType, name="chain_condition_type"), nullable=False, default=ChainConditionType.ALWAYS
    )
    # e.g. {"ports": [80, 443]} for PORT_OPEN, {"min_severity": "MEDIUM"}
    # for MIN_SEVERITY, {} for ALWAYS/TECHNOLOGY_DETECTED (no params needed).
    condition_params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (UniqueConstraint("template_id", "step_order", name="uq_mission_template_step_order"),)


class ChainRunStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ChainRunStepStatus(str, enum.Enum):
    PENDING = "PENDING"
    # Never got a Job: its condition wasn't met (a normal, expected stop --
    # see ChainRunStatus.COMPLETED), or authorization was revoked, or the
    # tool/profile was rejected by prepare_job() (both of the latter are
    # concerning -- see ChainRunStatus.FAILED). See
    # ck_chain_run_step_job_id_required_when_executed -- SKIPPED is
    # deliberately the only terminal status that doesn't require a job_id,
    # same reasoning as Phase 18's MissionStepStatus.SKIPPED.
    SKIPPED = "SKIPPED"
    QUEUED = "QUEUED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ChainRun(Base):
    __tablename__ = "chain_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # ON DELETE SET NULL: deleting a template must never destroy run
    # history -- ChainRunStep already snapshots its own tool/profile/
    # options/condition at creation time, so a run stays fully meaningful
    # even if its template is later edited or removed.
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mission_templates.id", ondelete="SET NULL"), nullable=True
    )
    # Mandatory and always a real Asset -- same reasoning as Mission.target_id
    # (Phase 18): every step must be re-checkable against is_executable()
    # at execution time. ON DELETE CASCADE: a run has no independent
    # meaning once its target is gone.
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ChainRunStatus] = mapped_column(
        Enum(ChainRunStatus, name="chain_run_status"), nullable=False, default=ChainRunStatus.RUNNING
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChainRunStep(Base):
    __tablename__ = "chain_run_steps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chain_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chain_runs.id", ondelete="CASCADE"), nullable=False
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    # Snapshotted from MissionTemplateStep at run-creation time -- never a
    # live reference back to a (possibly since-edited) template step, same
    # precedent as Phase 18's MissionStep snapshotting the AI's plan.
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    profile: Mapped[str | None] = mapped_column(String(64), nullable=True)
    options: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    condition_type: Mapped[ChainConditionType] = mapped_column(
        Enum(ChainConditionType, name="chain_condition_type"), nullable=False, default=ChainConditionType.ALWAYS
    )
    condition_params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[ChainRunStepStatus] = mapped_column(
        Enum(ChainRunStepStatus, name="chain_run_step_status"), nullable=False, default=ChainRunStepStatus.PENDING
    )
    # The only link between a ChainRun step and a real Job -- deliberately
    # not a column on Job itself, same precedent as Phase 18's
    # MissionStep.job_id.
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("chain_run_id", "step_order", name="uq_chain_run_step_order"),
        # Same reasoning as Phase 18's ck_mission_step_job_id_required_when_executed:
        # a step cannot claim to have reached the queue or a terminal
        # execution state without actually being linked to the Job that
        # produced it.
        CheckConstraint(
            "status NOT IN ('QUEUED', 'SUCCESS', 'FAILED') OR job_id IS NOT NULL",
            name="ck_chain_run_step_job_id_required_when_executed",
        ),
    )
