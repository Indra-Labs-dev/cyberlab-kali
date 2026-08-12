from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IntelSyncStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    details: dict


class IntelSyncTriggerResponse(BaseModel):
    status: str
