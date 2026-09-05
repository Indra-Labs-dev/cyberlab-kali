// Visual language for the 3D Security Graph -- pure color/size mapping,
// no Three.js import here (kept testable, and reusable if the renderer
// changes). Real fields only: FINDING nodes carry `risk_priority`/
// `risk_score` in metadata (backend/app/graph/queries.py::_hydrate_nodes),
// ASSET nodes carry `criticality` -- both already verified against the
// actual hydration code, nothing here is invented.
import type { AssetCriticality } from "~/types/asset";
import type { RiskPriority } from "~/types/finding";
import type { GraphNodeType } from "~/types/graph";

export interface ThemedNode {
  type: GraphNodeType;
  metadata: Record<string, unknown>;
}

// Same semantic palette as the existing 2D Security Graph (SecurityGraph.vue)
// -- one visual language across both renderers, not two competing ones.
export const NODE_TYPE_COLOR: Record<GraphNodeType, string> = {
  ASSET: "#38bdf8", // sky-400
  FINDING: "#f59e0b", // amber-500 -- overridden per-node by real risk below when known
  CVE: "#f87171", // red-400
  SERVICE: "#34d399", // emerald-400
  TECHNOLOGY: "#a78bfa", // violet-400
};

const RISK_COLOR: Record<RiskPriority, string> = {
  CRITICAL: "#f87171", // red-400
  HIGH: "#fb923c", // orange-400
  MEDIUM: "#fbbf24", // amber-400
  LOW: "#34d399", // emerald-400
  INFORMATIONAL: "#94a3b8", // slate-400
};

const CRITICALITY_SCALE: Record<AssetCriticality, number> = {
  CRITICAL: 1.6,
  HIGH: 1.3,
  MEDIUM: 1,
  LOW: 0.8,
};

function riskPriorityOf(node: ThemedNode): RiskPriority | null {
  const value = node.metadata.risk_priority;
  return typeof value === "string" && value in RISK_COLOR ? (value as RiskPriority) : null;
}

function criticalityOf(node: ThemedNode): AssetCriticality | null {
  const value = node.metadata.criticality;
  return typeof value === "string" && value in CRITICALITY_SCALE ? (value as AssetCriticality) : null;
}

function riskScoreOf(node: ThemedNode): number | null {
  const value = node.metadata.risk_score;
  return typeof value === "number" ? value : null;
}

// Findings are colored by their real computed risk when known (matches the
// RiskBadge/severity color language used everywhere else in the app);
// falls back to the type color for findings not yet risk-scored.
export function nodeColor(node: ThemedNode): string {
  if (node.type === "FINDING") {
    const priority = riskPriorityOf(node);
    if (priority) return RISK_COLOR[priority];
  }
  return NODE_TYPE_COLOR[node.type] ?? "#64748b";
}

const BASE_RADIUS = 3.2;

// Findings and Assets are the two node types this graph actually treats as
// focal points (bigger = more real risk/importance); CVE/SERVICE/TECHNOLOGY
// are context nodes, rendered smaller so the eye goes to what matters.
export function nodeRadius(node: ThemedNode): number {
  if (node.type === "ASSET") {
    const criticality = criticalityOf(node);
    return BASE_RADIUS * (criticality ? CRITICALITY_SCALE[criticality] : 1);
  }
  if (node.type === "FINDING") {
    const score = riskScoreOf(node);
    return score !== null ? BASE_RADIUS * (0.8 + Math.min(score, 100) / 100) : BASE_RADIUS;
  }
  return BASE_RADIUS * 0.7;
}

// Feeds graphAdapter.capNodes() when a lower quality tier needs to trim the
// node set -- higher real risk/criticality survives the cut first.
export function nodePriority(node: ThemedNode): number {
  if (node.type === "FINDING") return 100 + (riskScoreOf(node) ?? 0);
  if (node.type === "ASSET") return 10 * CRITICALITY_SCALE[criticalityOf(node) ?? "LOW"];
  return 1;
}

export const LINK_COLOR = "rgba(100, 116, 139, 0.35)"; // slate-500, low opacity
export const LINK_PARTICLE_COLOR = "rgba(148, 163, 184, 0.9)"; // slate-400, brighter for the flow effect
export const BACKGROUND_COLOR = "rgba(0,0,0,0)";

export const BLOOM = { strength: 1.1, radius: 0.5, threshold: 0.15 };
