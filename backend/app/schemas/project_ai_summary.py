import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProjectAISummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    summary: str
    based_on_job_id: uuid.UUID | None
    generated_at: datetime
