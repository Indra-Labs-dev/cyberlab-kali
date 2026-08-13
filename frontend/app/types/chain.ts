// Mirrors backend/app/schemas/mission_template.py field-for-field (Phase
// 21). Deliberately distinct from types/mission.ts (Phase 18) -- a
// MissionTemplate has no AI involvement at all, see
// backend/app/chains/service.py's module docstring.
export type ChainConditionType = "ALWAYS" | "PORT_OPEN" | "TECHNOLOGY_DETECTED" | "MIN_SEVERITY";
export type ChainRunStatus = "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
export type ChainRunStepStatus = "PENDING" | "SKIPPED" | "QUEUED" | "SUCCESS" | "FAILED" | "CANCELLED";

export interface MissionTemplateStep {
  id: string;
  step_order: number;
  tool: string;
  profile: string | null;
  options: Record<string, unknown>;
  condition_type: ChainConditionType;
  condition_params: Record<string, unknown>;
}

export interface MissionTemplate {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  steps: MissionTemplateStep[];
}

export interface ChainRunStep {
  id: string;
  step_order: number;
  tool: string;
  profile: string | null;
  options: Record<string, unknown>;
  condition_type: ChainConditionType;
  condition_params: Record<string, unknown>;
  status: ChainRunStepStatus;
  job_id: string | null;
  skip_reason: string | null;
  created_at: string;
}

export interface ChainRun {
  id: string;
  template_id: string | null;
  target_id: string;
  project_id: string | null;
  status: ChainRunStatus;
  created_at: string;
  finished_at: string | null;
  steps: ChainRunStep[];
}
