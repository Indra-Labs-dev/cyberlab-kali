// Phase 19 -- thin wrapper around /api/ai/projects/{id}/summary(/regenerate).
// Mirrors useMissions.ts's shape: no cache, no state, just typed fetch
// calls, useApi imported explicitly so this stays mockable in plain Vitest.
import type { ProjectAISummary } from "~/types/project-ai-summary";
import { useApi } from "./useApi";

export function useProjectMemory() {
  const { apiFetch } = useApi();

  function getProjectSummary(projectId: string) {
    return apiFetch<ProjectAISummary>(`/api/ai/projects/${projectId}/summary`);
  }

  function regenerateProjectSummary(projectId: string) {
    return apiFetch<ProjectAISummary>(`/api/ai/projects/${projectId}/summary/regenerate`, { method: "POST" });
  }

  return { getProjectSummary, regenerateProjectSummary };
}
