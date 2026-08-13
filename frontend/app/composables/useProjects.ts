import type { Project } from "~/types/project";
import { useApi } from "./useApi";

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

  return { listProjects };
}
