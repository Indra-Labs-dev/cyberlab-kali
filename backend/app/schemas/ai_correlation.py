import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.ai_correlation_suggestion import SuggestionStatus


class GenerateCorrelationSuggestionsRequest(BaseModel):
    target_id: uuid.UUID


class AICorrelationSuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    finding_id: uuid.UUID
    related_finding_id: uuid.UUID
    rationale: str
    status: SuggestionStatus
    created_at: datetime
    reviewed_at: datetime | None
