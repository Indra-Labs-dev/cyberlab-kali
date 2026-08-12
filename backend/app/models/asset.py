"""Phase 13 -- Asset Model. Generalizes the Phase 11 `Target` concept: an
Asset is anything CyberLab has observed or been told to track (a host, a
domain, a URL, a running lab container...), of which a "scan target" was
always a special case. See docs/phase-13-asset-model.md for the migration
rationale.

`Target`/`TargetType` (app/models/target.py) are kept as plain aliases to
this module so every existing import, route, and test keeps working
unchanged -- this is additive, not a breaking rename from the outside.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AssetType(str, enum.Enum):
    HOST = "HOST"
    IP = "IP"
    DOMAIN = "DOMAIN"
    SUBDOMAIN = "SUBDOMAIN"
    URL = "URL"
    SERVICE = "SERVICE"
    CONTAINER = "CONTAINER"
    LAB = "LAB"  # legacy value from Phase 11 Target.target_type, kept for existing rows
    LAB_RESOURCE = "LAB_RESOURCE"
    OTHER = "OTHER"


class AssetCriticality(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AuthorizationStatus(str, enum.Enum):
    LAB = "LAB"
    AUTHORIZED = "AUTHORIZED"
    LOCAL = "LOCAL"
    UNKNOWN = "UNKNOWN"


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    type: Mapped[AssetType] = mapped_column(Enum(AssetType, name="asset_type"), nullable=False)
    criticality: Mapped[AssetCriticality] = mapped_column(
        Enum(AssetCriticality, name="asset_criticality"),
        nullable=False,
        default=AssetCriticality.MEDIUM,
    )
    # authorization_status keeps the Phase 11 enum name/values unchanged --
    # same security boundary, same DB type (target_authorization_status),
    # just now attached to the generalized Asset row.
    authorization_status: Mapped[AuthorizationStatus] = mapped_column(
        Enum(AuthorizationStatus, name="target_authorization_status"),
        nullable=False,
        default=AuthorizationStatus.UNKNOWN,
    )
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Populated opportunistically from parsed job results (e.g. whatweb
    # plugin names) -- never user-editable directly, see app/assets/activity.py.
    technologies: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Derived from real Job activity (app/assets/activity.py), never a
    # directly-editable API field -- NULL means "never scanned yet".
    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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

    # --- Target compatibility shim (Phase 11 field names) ---------------
    # SQLAlchemy's default declarative __init__ does setattr() per kwarg,
    # so `Target(target_type=..., target_metadata=...)` keeps working
    # through these properties without any change to callers.
    @property
    def target_type(self) -> AssetType:
        return self.type

    @target_type.setter
    def target_type(self, value: AssetType) -> None:
        self.type = value

    @property
    def target_metadata(self) -> dict:
        return self.asset_metadata

    @target_metadata.setter
    def target_metadata(self, value: dict) -> None:
        self.asset_metadata = value
