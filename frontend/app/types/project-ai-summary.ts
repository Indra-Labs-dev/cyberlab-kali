// Mirrors backend/app/schemas/project_ai_summary.py::ProjectAISummaryResponse.
export interface ProjectAISummary {
  id: string;
  project_id: string;
  summary: string;
  based_on_job_id: string | null;
  generated_at: string;
}
