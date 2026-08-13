// Phase 18 -- thin wrapper around /api/ai/missions, /api/ai/correlation-
// suggestions, and /api/ai/reports/propose. Mirrors useAssets.ts's shape:
// no cache, no state, just typed fetch calls -- and useApi is imported
// explicitly for the same reason (mockable in tests without a running
// Nuxt build).
import type { AICorrelationSuggestion, Mission, ReportProposal } from "~/types/mission";
import { useApi } from "./useApi";

export function useMissions() {
  const { apiFetch } = useApi();

  function listMissions(targetId?: string) {
    const query = targetId ? `?target_id=${encodeURIComponent(targetId)}` : "";
    return apiFetch<Mission[]>(`/api/ai/missions${query}`);
  }

  function getMission(id: string) {
    return apiFetch<Mission>(`/api/ai/missions/${id}`);
  }

  function createMission(targetId: string, goal: string, maxSteps: number) {
    return apiFetch<Mission>("/api/ai/missions", {
      method: "POST",
      body: { target_id: targetId, goal, max_steps: maxSteps },
    });
  }

  function approveMission(id: string) {
    return apiFetch<Mission>(`/api/ai/missions/${id}/approve`, { method: "POST" });
  }

  function cancelMission(id: string) {
    return apiFetch<Mission>(`/api/ai/missions/${id}/cancel`, { method: "POST" });
  }

  function generateCorrelationSuggestions(targetId: string) {
    return apiFetch<AICorrelationSuggestion[]>("/api/ai/correlation-suggestions", {
      method: "POST",
      body: { target_id: targetId },
    });
  }

  function listCorrelationSuggestions(targetId: string) {
    return apiFetch<AICorrelationSuggestion[]>(`/api/ai/correlation-suggestions?target_id=${encodeURIComponent(targetId)}`);
  }

  function acceptCorrelationSuggestion(id: string) {
    return apiFetch<AICorrelationSuggestion>(`/api/ai/correlation-suggestions/${id}/accept`, { method: "POST" });
  }

  function dismissCorrelationSuggestion(id: string) {
    return apiFetch<AICorrelationSuggestion>(`/api/ai/correlation-suggestions/${id}/dismiss`, { method: "POST" });
  }

  function proposeReport(projectId: string) {
    return apiFetch<ReportProposal>("/api/ai/reports/propose", { method: "POST", body: { project_id: projectId } });
  }

  return {
    listMissions,
    getMission,
    createMission,
    approveMission,
    cancelMission,
    generateCorrelationSuggestions,
    listCorrelationSuggestions,
    acceptCorrelationSuggestion,
    dismissCorrelationSuggestion,
    proposeReport,
  };
}
