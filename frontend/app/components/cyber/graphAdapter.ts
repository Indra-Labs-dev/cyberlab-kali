// Pure data-shaping for the 3D Security Graph -- no Three.js/3d-force-graph
// import here on purpose, so this stays testable in plain Vitest (same
// reasoning as app/utils/activity.ts) and reusable if the render engine
// ever changes. Two responsibilities:
//   1. merge several GraphResponse fetches (one per seed node -- see
//      SecurityGraph3D's caller, which asks the real /api/graph/nodes/{type}/{id}
//      endpoint once per top-risk finding) into one deduped graph.
//   2. reshape that into the {nodes, links} object 3d-force-graph expects.
import type { GraphEdge, GraphNode, GraphNodeType, GraphResponse } from "~/types/graph";

export interface SecurityGraphNode {
  id: string;
  type: GraphNodeType;
  label: string;
  metadata: Record<string, unknown>;
}

export interface SecurityGraphLink {
  id: string;
  source: string;
  target: string;
  relation: string;
}

export interface ForceGraphData {
  nodes: SecurityGraphNode[];
  links: SecurityGraphLink[];
}

// Real API responses only -- never invents a node or edge that wasn't
// actually returned by the backend. Dedupes by id since the same asset can
// legitimately show up as a neighbor of several different seed findings.
export function mergeGraphResponses(responses: GraphResponse[]): GraphResponse {
  const nodesById = new Map<string, GraphNode>();
  const edgesById = new Map<string, GraphEdge>();

  for (const response of responses) {
    for (const node of response.nodes) nodesById.set(node.id, node);
    for (const edge of response.edges) edgesById.set(edge.id, edge);
  }

  return { nodes: [...nodesById.values()], edges: [...edgesById.values()] };
}

// Caps the node count for a given tier (see graphPerformance.ts) by keeping
// the highest-priority nodes first -- `priority` is supplied by the caller
// (e.g. real risk_score for findings) rather than computed here, since this
// module has no opinion on what "important" means for a given node type.
export function capNodes(graph: GraphResponse, maxNodes: number, priority: (node: GraphNode) => number): GraphResponse {
  if (graph.nodes.length <= maxNodes) return graph;
  const kept = [...graph.nodes].sort((a, b) => priority(b) - priority(a)).slice(0, maxNodes);
  const keptIds = new Set(kept.map((n) => n.id));
  const edges = graph.edges.filter((e) => keptIds.has(e.from_id) && keptIds.has(e.to_id));
  return { nodes: kept, edges };
}

export function toForceGraphData(graph: GraphResponse): ForceGraphData {
  const nodeIds = new Set(graph.nodes.map((n) => n.id));
  return {
    nodes: graph.nodes.map((n) => ({ id: n.id, type: n.type, label: n.label, metadata: n.metadata })),
    // Drop any edge pointing at a node that isn't in the (possibly capped)
    // node set -- 3d-force-graph throws if a link references a missing id.
    links: graph.edges
      .filter((e) => nodeIds.has(e.from_id) && nodeIds.has(e.to_id))
      .map((e) => ({ id: e.id, source: e.from_id, target: e.to_id, relation: e.relation })),
  };
}
