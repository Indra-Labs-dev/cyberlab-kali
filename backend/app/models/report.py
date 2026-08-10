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


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    format: Mapped[ReportFormat] = mapped_column(Enum(ReportFormat, name="report_format"), nullable=False)
    job_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Text formats (html/markdown/json) store content directly; pdf stores base64-encoded bytes.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
