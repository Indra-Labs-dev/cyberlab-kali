import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.asset_change_event import ChangeType
from app.models.finding import Severity


class AssetChangeEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    job_id: uuid.UUID
    previous_job_id: uuid.UUID | None
    change_type: ChangeType
    severity: Severity
    field: str
    # Untrusted: ultimately derived from external tool output (whatweb
    # plugin data, nmap service banners, ...) via app/diff/engine.py. Never
    # rendered as HTML/executed anywhere -- see docs/security.md's Phase 14
    # section. Plain strings, always.
    old_value: str | None
    new_value: str | None
    change_metadata: dict
    detected_at: datetime
