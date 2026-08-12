import uuid

from pydantic import BaseModel


class GraphNodeResponse(BaseModel):
    id: str
    type: str
    label: str
    metadata: dict


class GraphEdgeResponse(BaseModel):
    id: str
    from_type: str
    from_id: str
    to_type: str
    to_id: str
    relation: str
    source: str
    reason: str
    metadata: dict


class GraphResponse(BaseModel):
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]


class GraphRebuildRequest(BaseModel):
    project_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None


class GraphRebuildTriggerResponse(BaseModel):
    status: str
