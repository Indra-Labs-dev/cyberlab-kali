import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.asset import AssetCriticality, AssetType, AuthorizationStatus


class AssetCreateRequest(BaseModel):
    name: str
    hostname: str | None = None
    ip_address: str | None = None
    url: str | None = None
    type: AssetType
    criticality: AssetCriticality = AssetCriticality.MEDIUM
    authorization_status: AuthorizationStatus | None = None  # None -> inferred, see authorization.py
    tags: list[str] = Field(default_factory=list)
    description: str | None = None
    asset_metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_at_least_one_address(self) -> "AssetCreateRequest":
        if not (self.hostname or self.ip_address or self.url):
            raise ValueError("at least one of hostname, ip_address, or url is required")
        return self


class AssetUpdateRequest(BaseModel):
    name: str | None = None
    hostname: str | None = None
    ip_address: str | None = None
    url: str | None = None
    type: AssetType | None = None
    criticality: AssetCriticality | None = None
    authorization_status: AuthorizationStatus | None = None
    tags: list[str] | None = None
    description: str | None = None
    asset_metadata: dict | None = None
    # first_seen/last_seen/technologies are intentionally absent: they're
    # derived from real Job activity (app/assets/activity.py), never
    # directly editable through the API.


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    hostname: str | None
    ip_address: str | None
    url: str | None
    type: AssetType
    criticality: AssetCriticality
    authorization_status: AuthorizationStatus
    tags: list[str]
    technologies: list[str]
    description: str | None
    asset_metadata: dict
    first_seen: datetime | None
    last_seen: datetime | None
    created_at: datetime
    updated_at: datetime
