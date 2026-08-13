// Mirrors backend/app/schemas/finding.py::FindingResponse field-for-field --
// every page that reads a Finding gets the full real shape, whether or not
// it uses every field. Narrower per-page views (e.g. a list row that only
// needs id/title/severity) can still declare `Pick<Finding, ...>` locally
// rather than re-declaring the whole interface by hand.
export type FindingStatus = "NEW" | "CONFIRMED" | "IN_REVIEW" | "ACCEPTED_RISK" | "FALSE_POSITIVE" | "REMEDIATED" | "REOPENED";

export type Severity = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type Confidence = "LOW" | "MEDIUM" | "HIGH";
export type RiskPriority = "INFORMATIONAL" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface Finding {
  id: string;
  job_id: string;
  target: string;
  source_tool: string;
  title: string;
  description: string;
  severity: Severity;
  confidence: Confidence;
  evidence: Record<string, unknown>;
  recommendation: string | null;
  created_at: string;

  // Phase 15 -- materialized Risk Score cache, null until first computed.
  cve_ids: string[];
  cvss_score: number | null;
  epss_score: number | null;
  kev: boolean | null;
  risk_score: number | null;
  risk_priority: RiskPriority | null;
  risk_calculated_at: string | null;

  // Phase 16 -- deduplication/lifecycle.
  status: FindingStatus;
  first_seen: string;
  last_seen: string;
  observation_count: number;
  source_tools: string[];
}

// Mirrors backend/app/schemas/finding.py::FindingStatusHistoryResponse.
export interface FindingStatusHistoryEntry {
  id: string;
  finding_id: string;
  old_status: FindingStatus | null;
  new_status: FindingStatus;
  reason: string | null;
  triggered_by: string;
  created_at: string;
}

// Mirrors backend/app/schemas/finding.py::FindingRelationResponse.
export interface FindingRelation {
  id: string;
  finding_id: string;
  related_finding_id: string;
  rule: string;
  reason: string;
  relation_metadata: Record<string, unknown>;
  created_at: string;
}

// Mirrors backend/app/schemas/risk.py::AssetRiskSummaryResponse.
export interface RiskSummary {
  asset_id: string;
  total_findings: number;
  critical_findings: number;
  high_findings: number;
  medium_findings: number;
  low_findings: number;
  informational_findings: number;
  kev_findings: number;
  highest_risk_score: number | null;
  unscored_findings: number;
}
