import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TargetType(str, enum.Enum):
    HOST = "HOST"
    IP = "IP"
    DOMAIN = "DOMAIN"
    URL = "URL"
    CONTAINER = "CONTAINER"
    LAB = "LAB"
    OTHER = "OTHER"


class AuthorizationStatus(str, enum.Enum):
    LAB = "LAB"
    AUTHORIZED = "AUTHORIZED"
    LOCAL = "LOCAL"
    UNKNOWN = "UNKNOWN"


class Target(Base):
    __tablename__ = "targets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    target_type: Mapped[TargetType] = mapped_column(Enum(TargetType, name="target_type"), nullable=False)
    authorization_status: Mapped[AuthorizationStatus] = mapped_column(
        Enum(AuthorizationStatus, name="target_authorization_status"),
        nullable=False,
        default=AuthorizationStatus.UNKNOWN,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )

    @property
    def address(self) -> str:
        """The actual string passed to the Tool Registry as the scan target:
        whichever of url/hostname/ip_address is set, in that preference order
        (a URL is the most specific form for web-oriented tools).
        """
        return self.url or self.hostname or self.ip_address or self.name
