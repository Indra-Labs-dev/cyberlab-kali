// Mirrors backend/app/schemas/graph.py exactly. Moved out of
// SecurityGraph.vue so the same shapes are available to future consumers
// (e.g. a global /graph search page in 18c) without re-declaring them.
export type GraphNodeType = "ASSET" | "FINDING" | "CVE" | "SERVICE" | "TECHNOLOGY";

export interface GraphNode {
  id: string;
  type: GraphNodeType;
  label: string;
  metadata: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  from_type: string;
  from_id: string;
  to_type: string;
  to_id: string;
  relation: string;
  source: string;
  reason: string;
  metadata: Record<string, unknown>;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// Phase 24 -- Attack Path Analysis. Mirrors backend/app/schemas/graph.py's
// AttackPath/AttackPathsResponse exactly. `disclaimer` is always present
// on the response, deliberately -- never trimmed on the assumption the UI
// already shows one of its own.
export interface AttackPath {
  hops: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface AttackPathsResponse {
  disclaimer: string;
  seed: GraphNode;
  truncated: boolean;
  paths: AttackPath[];
}
