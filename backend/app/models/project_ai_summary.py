"""Phase 19 -- AI Memory per Project. A stored, natural-language summary of
a Project's current state -- regenerated after scan activity, never
recalculated on every question (see app/ai/memory.py). Deliberately a
dedicated table, not a `Finding` of some "SUMMARY" type: `Finding` has no
discriminator column and its entire shape (severity/CVE/risk
score/lifecycle status) is about vulnerability findings, not free-text AI
prose -- the roadmap explicitly left this as an open choice, and a
dedicated table matches the precedent of every other phase (Mission,
GraphEdge, VulnerabilityIntel).

Named `ProjectAISummary`, not `ProjectSummary` -- that name is already
taken by an unrelated rollup-counts schema (app/schemas/project.py).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ProjectAISummary(Base):
    __tablename__ = "project_ai_summaries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # One row per Project -- regeneration upserts this row rather than
    # accumulating history, matching "stored, not recalculated on every
    # question" (a rolling current-state summary, not a log).
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # Provenance: which Job's completion triggered this regeneration, if
    # any (null for a manually-triggered regeneration with no specific
    # Job behind it). ON DELETE SET NULL: losing a Job's history must never
    # delete the summary it once triggered.
    based_on_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )

    __table_args__ = (UniqueConstraint("project_id", name="uq_project_ai_summary_project"),)
