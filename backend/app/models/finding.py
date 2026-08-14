import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Severity(str, enum.Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Confidence(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RiskPriority(str, enum.Enum):
    """Phase 15 -- aggregate Risk Score priority band. Deliberately distinct
    from Severity (a tool's raw rating): this is the output of
    app/risk/calculator.py, not something a parser ever sets directly."""

    INFORMATIONAL = "INFORMATIONAL"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingStatus(str, enum.Enum):
    """Phase 16 -- Finding lifecycle. Transitions enforced exclusively by
    app/findings/lifecycle.py::transition_status -- never assigned directly
    by an API route or a parser."""

    NEW = "NEW"
    CONFIRMED = "CONFIRMED"
    IN_REVIEW = "IN_REVIEW"
    ACCEPTED_RISK = "ACCEPTED_RISK"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    REMEDIATED = "REMEDIATED"
    REOPENED = "REOPENED"


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        # Mirrors alembic/versions/3cbc3564e708_..._finding_.py exactly (same
        # name, same partial WHERE) -- this is the constraint the whole
        # concurrent-upsert-safety design in app/findings/service.py relies
        # on. It must be declared here, not only in the migration: SQLAlchemy
        # Column-level `unique=True` can't express a partial index, and
        # without it here, Base.metadata.create_all() (used by
        # tests/conftest.py to build the test database) silently omits it --
        # which would let tests/findings/test_concurrency.py create two
        # Finding rows for the same signature and never notice, since
        # nothing in a from-scratch test schema would reject the second
        # INSERT.
        Index("uq_findings_signature", "signature", unique=True, postgresql_where=text("signature IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Phase 23 -- indexed: joined/filtered on constantly (report building,
    # risk recalculation, the Asset detail page) with no supporting index.
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(512), nullable=False)
    source_tool: Mapped[str] = mapped_column(String(64), nullable=False)

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[Severity] = mapped_column(Enum(Severity, name="finding_severity"), nullable=False)
    confidence: Mapped[Confidence] = mapped_column(
        Enum(Confidence, name="finding_confidence"), nullable=False, default=Confidence.MEDIUM
    )
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Phase 15 -- CVE identifiers extracted at parse time (currently only
    # nuclei's `info.classification.cve-id`, see
    # app/tools/parsers/nuclei.py::parse_nuclei). Empty list, never null --
    # "no CVE" is the common case (an open port has no CVE), not an error.
    cve_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # Materialized Risk Score cache -- always recomputable from cve_ids +
    # app/models/vulnerability_intel.py + the linked Asset's criticality +
    # `confidence` above via app/risk/calculator.py. Kept in sync by
    # app/risk/service.py on finding creation, on relevant intelligence
    # sync, and on Asset criticality change (see docs/phase-15-risk-score.md)
    # -- never written directly by an API route. NULL until first computed.
    cvss_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    epss_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    kev: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # NULL = unknown, not "false"
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_priority: Mapped[RiskPriority | None] = mapped_column(Enum(RiskPriority, name="risk_priority"), nullable=True)
    risk_calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Phase 16 -- deduplication identity. NULL when the originating Job has
    # no target_id (free-text target, no Asset) -- those findings stay
    # outside dedup/lifecycle/correlation entirely, same precedent as the
    # Diff Engine (Phase 14) and Risk Score (Phase 15) both already
    # skipping target_id-less jobs. See app/findings/signature.py for the
    # exact algorithm. Enforced unique via a partial index
    # (WHERE signature IS NOT NULL) in the Phase 16 migration, not here --
    # SQLAlchemy Column-level uniqueness can't express the partial WHERE.
    signature: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[FindingStatus] = mapped_column(
        Enum(FindingStatus, name="finding_status"), nullable=False, default=FindingStatus.NEW
    )

    # Observation tracking -- one logical Finding can be confirmed by many
    # Jobs (repeated scans, or several tools). Always initialized at
    # creation (first_seen == last_seen == created_at), advanced only by
    # app/findings/service.py::upsert_finding, never by an API route.
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_tools: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    observation_job_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
