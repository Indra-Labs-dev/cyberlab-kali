import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ReportFormat(str, enum.Enum):
    HTML = "html"
    MARKDOWN = "markdown"
    JSON = "json"
    PDF = "pdf"


class ReportTemplate(str, enum.Enum):
    # TECHNICAL matches the report content shipped since Phase 9 (full jobs +
    # findings + AI analysis) -- it is the default so existing report-generation
    # behavior is unchanged for callers that don't pick a template explicitly.
    EXECUTIVE = "executive"
    TECHNICAL = "technical"
    EVIDENCE_PACKAGE = "evidence_package"


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    format: Mapped[ReportFormat] = mapped_column(Enum(ReportFormat, name="report_format"), nullable=False)
    template: Mapped[ReportTemplate] = mapped_column(
        Enum(ReportTemplate, name="report_template"), nullable=False, default=ReportTemplate.TECHNICAL
    )
    job_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Text formats (html/markdown/json) store content directly; pdf stores base64-encoded bytes.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
