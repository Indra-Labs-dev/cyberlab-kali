"""Phase 18 -- Correlation Agent suggestions. Deliberately a separate table
from `FindingRelation` (Phase 16), never a `source` flag added to it:
`FindingRelation` stays reserved for the deterministic, validated
correlations of `app/findings/correlation.py`'s fixed rules. An AI
suggestion is not a relation until a human explicitly accepts it -- see
`app/ai/agents/correlation.py` (read-only, never writes here or to
FindingRelation) and the `/accept`/`/dismiss` routes in
`app/api/routes/ai.py`, which are the only code path that ever creates a
real `FindingRelation` from a suggestion.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SuggestionStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DISMISSED = "DISMISSED"


class AICorrelationSuggestion(Base):
    __tablename__ = "ai_correlation_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
    )
    related_finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
    )
    # The model's reasoning, always populated -- a suggestion with no
    # rationale is not actionable by the human reviewing it.
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SuggestionStatus] = mapped_column(
        Enum(SuggestionStatus, name="ai_suggestion_status"), nullable=False, default=SuggestionStatus.PENDING
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("finding_id != related_finding_id", name="ck_ai_suggestion_distinct_findings"),
        # Same canonical-pair idea as FindingRelation's own uniqueness
        # story (app/findings/correlation.py::_create_relation_if_new sorts
        # by UUID before insert) -- the accept/dismiss route applies the
        # same ordering before insert here, so this constraint is
        # meaningful rather than trivially bypassable by swapping the pair.
        UniqueConstraint("finding_id", "related_finding_id", name="uq_ai_suggestion_pair"),
        Index("ix_ai_suggestions_finding_id", "finding_id"),
        Index("ix_ai_suggestions_status", "status"),
    )
