import { ref } from "vue";
import type { Asset } from "~/types/asset";
import type { Finding } from "~/types/finding";
import { useApi } from "./useApi";

// Backs the Topbar's global search. Assets use the backend's real `search`
// query param (GET /api/assets?search=); Findings has no search param
// (verified against the routes audit) so a bounded recent-findings fetch
// is cached once and filtered client-side instead -- still real data, just
// filtered locally rather than server-side. Projects and Tools are small
// enough to cache in full and filter client-side too.
export interface SearchResultItem {
  id: string;
  type: "asset" | "finding" | "project" | "tool";
  label: string;
  detail?: string;
  to: string;
}

interface ProjectLike {
  id: string;
  name: string;
}

interface ToolLike {
  name: string;
  category: string;
}

export function useGlobalSearch() {
  const { apiFetch } = useApi();
  const results = ref<SearchResultItem[]>([]);
  const loading = ref(false);

  let projectsCache: ProjectLike[] | null = null;
  let toolsCache: ToolLike[] | null = null;
  let findingsCache: Finding[] | null = null;

  async function ensureCaches() {
    const tasks: Promise<unknown>[] = [];
    if (!projectsCache) {
      tasks.push(
        apiFetch<ProjectLike[]>("/api/projects")
          .then((r) => (projectsCache = r))
          .catch(() => (projectsCache = [])),
      );
    }
    if (!toolsCache) {
      tasks.push(
        apiFetch<ToolLike[]>("/api/tools")
          .then((r) => (toolsCache = r))
          .catch(() => (toolsCache = [])),
      );
    }
    if (!findingsCache) {
      tasks.push(
        apiFetch<Finding[]>("/api/findings?limit=100")
          .then((r) => (findingsCache = r))
          .catch(() => (findingsCache = [])),
      );
    }
    await Promise.all(tasks);
  }

  async function search(query: string) {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      results.value = [];
      return;
    }
    loading.value = true;
    try {
      await ensureCaches();
      const lower = trimmed.toLowerCase();

      const assets = await apiFetch<Asset[]>(`/api/assets?search=${encodeURIComponent(trimmed)}&limit=5`).catch(() => [] as Asset[]);

      const assetResults: SearchResultItem[] = assets
        .slice(0, 5)
        .map((a) => ({ id: a.id, type: "asset", label: a.name, detail: a.hostname || a.ip_address || a.type, to: `/assets/${a.id}` }));

      const findingResults: SearchResultItem[] = (findingsCache || [])
        .filter((f) => f.title.toLowerCase().includes(lower))
        .slice(0, 5)
        .map((f) => ({ id: f.id, type: "finding", label: f.title, detail: f.severity, to: `/findings/${f.id}` }));

      const projectResults: SearchResultItem[] = (projectsCache || [])
        .filter((p) => p.name.toLowerCase().includes(lower))
        .slice(0, 5)
        .map((p) => ({ id: p.id, type: "project", label: p.name, to: `/projects/${p.id}` }));

      const toolResults: SearchResultItem[] = (toolsCache || [])
        .filter((t) => t.name.toLowerCase().includes(lower))
        .slice(0, 5)
        .map((t) => ({ id: t.name, type: "tool", label: t.name, detail: t.category, to: "/tools" }));

      results.value = [...assetResults, ...findingResults, ...projectResults, ...toolResults];
    } finally {
      loading.value = false;
    }
  }

  function clear() {
    results.value = [];
  }

  return { results, loading, search, clear };
}
