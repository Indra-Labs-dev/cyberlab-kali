import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, text
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


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
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

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
