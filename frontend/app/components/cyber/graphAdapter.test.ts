import { describe, expect, it } from "vitest";
import { capNodes, mergeGraphResponses, toForceGraphData } from "./graphAdapter";
import type { GraphResponse } from "~/types/graph";

const node = (id: string, type: GraphResponse["nodes"][number]["type"] = "ASSET") => ({
  id,
  type,
  label: id,
  metadata: {},
});
const edge = (id: string, from: string, to: string) => ({
  id,
  from_type: "ASSET",
  from_id: from,
  to_type: "ASSET",
  to_id: to,
  relation: "RELATED_TO",
  source: "test",
  reason: "test",
  metadata: {},
});

describe("mergeGraphResponses", () => {
  it("dedupes nodes and edges that appear in multiple responses by id", () => {
    const a: GraphResponse = { nodes: [node("n1"), node("n2")], edges: [edge("e1", "n1", "n2")] };
    const b: GraphResponse = { nodes: [node("n2"), node("n3")], edges: [edge("e1", "n1", "n2"), edge("e2", "n2", "n3")] };
    const merged = mergeGraphResponses([a, b]);
    expect(merged.nodes.map((n) => n.id).sort()).toEqual(["n1", "n2", "n3"]);
    expect(merged.edges.map((e) => e.id).sort()).toEqual(["e1", "e2"]);
  });

  it("returns an empty graph for no responses", () => {
    expect(mergeGraphResponses([])).toEqual({ nodes: [], edges: [] });
  });
});

describe("capNodes", () => {
  it("keeps the highest-priority nodes and drops edges that reference a dropped node", () => {
    const graph: GraphResponse = {
      nodes: [node("low"), node("high"), node("mid")],
      edges: [edge("e1", "low", "high"), edge("e2", "high", "mid")],
    };
    const priority: Record<string, number> = { low: 1, mid: 5, high: 9 };
    const capped = capNodes(graph, 2, (n) => priority[n.id] ?? 0);
    expect(capped.nodes.map((n) => n.id).sort()).toEqual(["high", "mid"]);
    // e1 references "low", which got dropped -- gone. e2 connects two
    // surviving nodes -- kept.
    expect(capped.edges.map((e) => e.id)).toEqual(["e2"]);
  });

  it("keeps an edge only when both its endpoints survive the cap", () => {
    const graph: GraphResponse = {
      nodes: [node("a"), node("b"), node("c")],
      edges: [edge("keep", "a", "b"), edge("drop", "b", "c")],
    };
    const priority: Record<string, number> = { a: 3, b: 2, c: 1 };
    const capped = capNodes(graph, 2, (n) => priority[n.id] ?? 0);
    expect(capped.nodes.map((n) => n.id).sort()).toEqual(["a", "b"]);
    expect(capped.edges.map((e) => e.id)).toEqual(["keep"]);
  });

  it("is a no-op when the graph is already within the cap", () => {
    const graph: GraphResponse = { nodes: [node("a")], edges: [] };
    expect(capNodes(graph, 5, () => 0)).toEqual(graph);
  });
});

describe("toForceGraphData", () => {
  it("maps nodes to {id, type, label, metadata}", () => {
    const graph: GraphResponse = { nodes: [{ id: "f1", type: "FINDING", label: "SQLi", metadata: { risk_score: 88 } }], edges: [] };
    const data = toForceGraphData(graph);
    expect(data.nodes).toEqual([{ id: "f1", type: "FINDING", label: "SQLi", metadata: { risk_score: 88 } }]);
  });

  it("maps edges to {source, target} using from_id/to_id", () => {
    const graph: GraphResponse = { nodes: [node("a"), node("b")], edges: [edge("e1", "a", "b")] };
    const data = toForceGraphData(graph);
    expect(data.links).toEqual([{ id: "e1", source: "a", target: "b", relation: "RELATED_TO" }]);
  });

  it("drops a link whose endpoint isn't in the node set (3d-force-graph would throw otherwise)", () => {
    const graph: GraphResponse = { nodes: [node("a")], edges: [edge("dangling", "a", "ghost")] };
    const data = toForceGraphData(graph);
    expect(data.links).toEqual([]);
  });
});
