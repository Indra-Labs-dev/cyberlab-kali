import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    # Name of the Tool Registry profile used to seed `params`, if any -- kept
    # only for display (scan history, reports); execution never re-resolves
    # it, `params` already holds the fully-resolved argument values.
    profile: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Free-text target string -- kept for backward compatibility and for
    # quick ad-hoc scans that don't need a registered Target. When a job is
    # created from a real Target (project_id/target_id set), this still
    # holds the resolved address string, so existing code reading `target`
    # directly (parsers, findings extraction, reports) needs no changes.
    target: Mapped[str] = mapped_column(String(512), nullable=False)
    # ON DELETE SET NULL: deleting a Project/Target must never destroy job
    # history. The `target` string above keeps the human-readable record
    # regardless of whether the Target it came from still exists.
    # Phase 23 -- indexed: the single most-referenced table in the schema
    # (7 other tables FK into it) had zero secondary indexes despite
    # project_id/target_id/status all being routine filter columns and
    # created_at being the standard sort key for job history (GET
    # /api/jobs, the ticker, reports, the risk service all filter/order on
    # these). See migration e5f1a9c7d3b2.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), nullable=False, default=JobStatus.QUEUED, index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Phase 20 -- SHA-256 hex digest of `stdout` exactly as received from
    # the Kali agent, computed once at the same point `stdout` itself is
    # set (app/jobs/tasks.py::_execute_job) -- minimal integrity proof, not
    # a cryptographic vault. Same column shape as Finding.signature
    # (String(64), a hex digest). NULL whenever `stdout` itself is NULL --
    # a job that never actually ran (rejected before the Kali agent call)
    # has no output to prove the integrity of.
    evidence_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
