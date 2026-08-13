// Phase 21 -- thin wrapper around /api/chains/templates and
// /api/chains/runs. Mirrors useMissions.ts's shape: no cache, no state,
// just typed fetch calls -- and useApi is imported explicitly for the
// same reason (mockable in tests without a running Nuxt build).
import type { ChainRun, MissionTemplate } from "~/types/chain";
import { useApi } from "./useApi";

export interface MissionTemplateStepInput {
  tool: string;
  profile?: string | null;
  options?: Record<string, unknown>;
  condition_type?: string;
  condition_params?: Record<string, unknown>;
}

export function useChains() {
  const { apiFetch } = useApi();

  function listTemplates() {
    return apiFetch<MissionTemplate[]>("/api/chains/templates");
  }

  function getTemplate(id: string) {
    return apiFetch<MissionTemplate>(`/api/chains/templates/${id}`);
  }

  function createTemplate(name: string, description: string, steps: MissionTemplateStepInput[]) {
    return apiFetch<MissionTemplate>("/api/chains/templates", {
      method: "POST",
      body: { name, description: description || null, steps },
    });
  }

  function deleteTemplate(id: string) {
    return apiFetch<void>(`/api/chains/templates/${id}`, { method: "DELETE" });
  }

  function createRun(templateId: string, targetId: string) {
    return apiFetch<ChainRun>("/api/chains/runs", {
      method: "POST",
      body: { template_id: templateId, target_id: targetId },
    });
  }

  function listRuns(params?: { target_id?: string; project_id?: string; template_id?: string }) {
    const query = params ? `?${new URLSearchParams(params as Record<string, string>).toString()}` : "";
    return apiFetch<ChainRun[]>(`/api/chains/runs${query}`);
  }

  function getRun(id: string) {
    return apiFetch<ChainRun>(`/api/chains/runs/${id}`);
  }

  function cancelRun(id: string) {
    return apiFetch<ChainRun>(`/api/chains/runs/${id}/cancel`, { method: "POST" });
  }

  return { listTemplates, getTemplate, createTemplate, deleteTemplate, createRun, listRuns, getRun, cancelRun };
}
