import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.target import AuthorizationStatus, TargetType


class TargetCreateRequest(BaseModel):
    name: str
    hostname: str | None = None
    ip_address: str | None = None
    url: str | None = None
    target_type: TargetType
    authorization_status: AuthorizationStatus | None = None  # None -> inferred, see authorization.py
    description: str | None = None
    target_metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_at_least_one_address(self) -> "TargetCreateRequest":
        if not (self.hostname or self.ip_address or self.url):
            raise ValueError("at least one of hostname, ip_address, or url is required")
        return self


class TargetUpdateRequest(BaseModel):
    name: str | None = None
    hostname: str | None = None
    ip_address: str | None = None
    url: str | None = None
    target_type: TargetType | None = None
    authorization_status: AuthorizationStatus | None = None
    description: str | None = None
    target_metadata: dict | None = None


class TargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    hostname: str | None
    ip_address: str | None
    url: str | None
    target_type: TargetType
    authorization_status: AuthorizationStatus
    description: str | None
    target_metadata: dict
    created_at: datetime
    updated_at: datetime
