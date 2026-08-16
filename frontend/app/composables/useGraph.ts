import type { Asset } from "~/types/asset";
import type { Finding } from "~/types/finding";
import type { AttackPathsResponse, GraphNodeType, GraphResponse } from "~/types/graph";
import { useApi } from "./useApi";

export interface GraphSearchResult {
  id: string;
  type: GraphNodeType;
  label: string;
}

// useApi is imported explicitly (not just relied on via Nuxt auto-import)
// for the same reason as useAssets.ts: keeps this composable a plain,
// mockable ES module for useGraph.test.ts.
//
// Search behavior genuinely differs by node type because the backend does
// too (verified in backend/app/api/routes -- confirmed 18c):
//  - ASSET has a real `?search=` query param (GET /api/assets).
//  - FINDING has no search/filter-by-text param at all (GET /api/findings
//    only filters by severity/job/project/target/priority/kev/status/
//    source_tool), so this filters client-side over the same title field
//    the Findings page already renders, capped to a readable number of
//    results.
//  - CVE/SERVICE/TECHNOLOGY are virtual node types with no backing table
//    and no list endpoint anywhere (backend/app/graph/queries.py::
//    _hydrate_nodes has nothing to query for them) -- GET
//    /api/graph/nodes/{type}/{id} accepts any identifier and returns a
//    (possibly empty) graph rather than 404ing, so "search" for these three
//    types is really just confirming the exact identifier the user typed.
export function useGraph() {
  const { apiFetch } = useApi();

  async function searchNodes(type: GraphNodeType, query: string): Promise<GraphSearchResult[]> {
    const q = query.trim();
    if (!q) return [];

    if (type === "ASSET") {
      const assets = await apiFetch<Asset[]>(`/api/assets?search=${encodeURIComponent(q)}`);
      return assets.map((a) => ({ id: a.id, type: "ASSET" as const, label: a.name }));
    }

    if (type === "FINDING") {
      const findings = await apiFetch<Finding[]>("/api/findings?limit=500");
      const needle = q.toLowerCase();
      return findings
        .filter((f) => f.title.toLowerCase().includes(needle))
        .slice(0, 20)
        .map((f) => ({ id: f.id, type: "FINDING" as const, label: f.title }));
    }

    return [{ id: q, type, label: q }];
  }

  // Node + its relations are always returned together by this one endpoint
  // (backend/app/graph/queries.py::local_graph) -- no separate "load
  // relations" call exists or is needed.
  function loadNode(type: GraphNodeType, id: string, depth = 1) {
    return apiFetch<GraphResponse>(`/api/graph/nodes/${type}/${encodeURIComponent(id)}?depth=${depth}`);
  }

  // Phase 24 -- Attack Path Analysis. Both endpoints always return a
  // `disclaimer` (see AttackPathsResponse) -- callers must render it
  // alongside the paths, never fetch-and-discard it.
  function loadAttackPathsToCriticalAssets(type: GraphNodeType, id: string, maxHops = 4) {
    return apiFetch<AttackPathsResponse>(
      `/api/graph/attack-paths/critical/${type}/${encodeURIComponent(id)}?max_hops=${maxHops}`
    );
  }

  function loadAttackPathsBetween(fromType: GraphNodeType, fromId: string, toType: GraphNodeType, toId: string, maxHops = 4) {
    return apiFetch<AttackPathsResponse>(
      `/api/graph/attack-paths/between/${fromType}/${encodeURIComponent(fromId)}/${toType}/${encodeURIComponent(toId)}?max_hops=${maxHops}`
    );
  }

  return { searchNodes, loadNode, loadAttackPathsToCriticalAssets, loadAttackPathsBetween };
}
