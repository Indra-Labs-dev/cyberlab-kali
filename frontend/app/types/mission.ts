// Mirrors backend/app/schemas/mission.py / app/schemas/ai_correlation.py /
// app/ai/schemas.py::ReportProposal field-for-field (Phase 18).
export type MissionStatus = "DRAFT" | "APPROVED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
export type MissionStepStatus = "PENDING" | "SKIPPED" | "QUEUED" | "SUCCESS" | "FAILED" | "CANCELLED";
export type SuggestionStatus = "PENDING" | "ACCEPTED" | "DISMISSED";

export interface MissionStep {
  id: string;
  step_order: number;
  label: string;
  tool: string | null;
  profile: string | null;
  options: Record<string, unknown>;
  rationale: string;
  status: MissionStepStatus;
  job_id: string | null;
  skip_reason: string | null;
  created_at: string;
}

export interface Mission {
  id: string;
  project_id: string | null;
  target_id: string;
  goal: string;
  status: MissionStatus;
  max_steps: number;
  created_at: string;
  approved_at: string | null;
  finished_at: string | null;
  steps: MissionStep[];
}

export interface AICorrelationSuggestion {
  id: string;
  finding_id: string;
  related_finding_id: string;
  rationale: string;
  status: SuggestionStatus;
  created_at: string;
  reviewed_at: string | null;
}

export interface ReportProposal {
  title: string;
  job_ids: string[];
  rationale: string;
}
