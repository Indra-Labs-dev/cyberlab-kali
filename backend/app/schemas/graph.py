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


# Phase 24 -- Attack Path Analysis. No exploitability/probability score
# anywhere in this shape, deliberately: `disclaimer` is the one thing every
# caller (API consumer or frontend) is guaranteed to see alongside the
# paths themselves.
class AttackPath(BaseModel):
    hops: int
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]


class AttackPathsResponse(BaseModel):
    disclaimer: str
    seed: GraphNodeResponse
    truncated: bool
    paths: list[AttackPath]
