import type { Project } from "~/types/project";
import { useApi } from "./useApi";

// PATCH /api/projects/{id} (backend/app/schemas/project.py::ProjectResponse)
// returns more than the minimal Project type below carries -- declared here,
// not added to Project, since ProjectResponse's full shape (description/
// notes/status/timestamps) has exactly one current consumer (the Notes tab).
export interface ProjectPatchResponse extends Project {
  description: string | null;
  notes: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

// Same rationale as useAssets(): encapsulates the endpoint + shared type,
// no cache. pages/projects/index.vue's richer ProjectSummary (with
// counts/search/status filters) is a different shape for a different use
// case and is not wrapped here. See useAssets.ts for why useApi is
// imported explicitly rather than relied on as a Nuxt auto-import.
export function useProjects() {
  const { apiFetch } = useApi();

  function listProjects() {
    return apiFetch<Project[]>("/api/projects");
  }

  function updateProject(id: string, patch: { name?: string; description?: string; status?: string; notes?: string }) {
    return apiFetch<ProjectPatchResponse>(`/api/projects/${id}`, { method: "PATCH", body: patch });
  }

  return { listProjects, updateProject };
}
