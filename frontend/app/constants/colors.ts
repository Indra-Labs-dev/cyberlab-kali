// Centralized Tailwind class maps for the badge-like labels scattered
// across the app. Each map below was verified byte-for-byte against every
// page that declared it before being centralized here (18a audit) --
// consolidated only where the values were already identical everywhere,
// never normalized across pages that genuinely differ.
//
// Deliberately NOT one generic map: `severity` (tool-reported), `risk
// priority` (Phase 15 computed score band), `criticality` (Asset,
// human-assigned), `authorization status`, `finding lifecycle status`, and
// `tool risk level` (Tool Registry SAFE/CAUTION/RESTRICTED/MANUAL_ONLY) are
// five distinct domains that happen to reuse similar-looking keys in a
// couple of cases -- collapsing them into one lookup would silently break
// the moment two domains diverge (as FindingStatus already does today, see
// FINDING_STATUS_COLORS below).
import type { AssetCriticality, AuthorizationStatus } from "~/types/asset";
import type { FindingStatus, RiskPriority, Severity } from "~/types/finding";

export const SEVERITY_COLORS: Record<Severity, string> = {
  INFO: "bg-slate-700/50 text-slate-300",
  LOW: "bg-emerald-500/15 text-emerald-400",
  MEDIUM: "bg-amber-500/15 text-amber-400",
  HIGH: "bg-orange-500/15 text-orange-400",
  CRITICAL: "bg-red-500/15 text-red-400",
};

// Same scale/values as SEVERITY_COLORS today (verified identical in
// pages/scans/[id].vue's AI-analysis risk badge) -- kept as its own export
// rather than aliased, since "AI-reported risk" and "tool-reported
// severity" are different concepts that happen to share a palette right
// now, not the same thing.
export const AI_RISK_COLORS: Record<Severity, string> = SEVERITY_COLORS;

export const RISK_PRIORITY_COLORS: Record<RiskPriority, string> = {
  INFORMATIONAL: "bg-slate-700/50 text-slate-300",
  LOW: "bg-emerald-500/15 text-emerald-400",
  MEDIUM: "bg-amber-500/15 text-amber-400",
  HIGH: "bg-orange-500/15 text-orange-400",
  CRITICAL: "bg-red-500/15 text-red-400",
};

export const CRITICALITY_COLORS: Record<AssetCriticality, string> = {
  LOW: "bg-slate-700/50 text-slate-300",
  MEDIUM: "bg-cyan-500/15 text-cyan-400",
  HIGH: "bg-orange-500/15 text-orange-400",
  CRITICAL: "bg-red-500/15 text-red-400",
};

export const AUTHORIZATION_COLORS: Record<AuthorizationStatus, string> = {
  LAB: "bg-emerald-500/15 text-emerald-400",
  AUTHORIZED: "bg-emerald-500/15 text-emerald-400",
  LOCAL: "bg-cyan-500/15 text-cyan-400",
  UNKNOWN: "bg-amber-500/15 text-amber-400",
};

// Base classes only -- does NOT include `line-through` for FALSE_POSITIVE.
// pages/findings/index.vue currently renders FALSE_POSITIVE with an extra
// `line-through` (a compact-list-only visual cue) while
// pages/findings/[id].vue does not. That divergence is preserved
// explicitly via StatusBadge's `strikeFalsePositive` prop rather than
// picked one way and silently applied everywhere -- see
// app/components/StatusBadge.vue.
export const FINDING_STATUS_COLORS: Record<FindingStatus, string> = {
  NEW: "bg-slate-700/50 text-slate-300",
  CONFIRMED: "bg-sky-500/15 text-sky-400",
  IN_REVIEW: "bg-amber-500/15 text-amber-400",
  ACCEPTED_RISK: "bg-purple-500/15 text-purple-400",
  FALSE_POSITIVE: "bg-slate-700/50 text-slate-500",
  REMEDIATED: "bg-emerald-500/15 text-emerald-400",
  REOPENED: "bg-red-500/15 text-red-400",
};

// Tool Registry risk_level (backend/app/tools/definitions/*.yaml) --
// unrelated to Finding/AI severity despite pages/tools/index.vue naming
// its local copy `riskColor` too. Kept separate on purpose (see module
// docstring above).
export type ToolRiskLevel = "SAFE" | "CAUTION" | "RESTRICTED" | "MANUAL_ONLY";
export const TOOL_RISK_LEVEL_COLORS: Record<ToolRiskLevel, string> = {
  SAFE: "bg-emerald-500/15 text-emerald-400",
  CAUTION: "bg-amber-500/15 text-amber-400",
  RESTRICTED: "bg-orange-500/15 text-orange-400",
  MANUAL_ONLY: "bg-red-500/15 text-red-400",
};
