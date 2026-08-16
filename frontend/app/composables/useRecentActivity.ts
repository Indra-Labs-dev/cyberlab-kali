import { ref } from "vue";
import { mergeActivity } from "~/utils/activity";
import type { ActivityItem } from "~/components/ui/ActivityFeed.vue";
import { useApi } from "./useApi";

// Backs both the Topbar activity popover and the Dashboard activity
// section -- one shared fetch instead of two, cached after first load
// (call load(true) to force a refresh, e.g. after opening the popover
// again later).
export function useRecentActivity() {
  const { apiFetch } = useApi();
  const items = ref<ActivityItem[]>([]);
  const loading = ref(false);
  const error = ref("");
  let loaded = false;

  async function load(force = false) {
    if (loaded && !force) return;
    loading.value = true;
    error.value = "";
    try {
      const [jobs, findings, changes] = await Promise.all([
        apiFetch<any[]>("/api/jobs?limit=6"),
        apiFetch<any[]>("/api/findings?limit=6"),
        apiFetch<any[]>("/api/asset-changes?limit=6"),
      ]);
      items.value = mergeActivity(jobs, findings, changes);
      loaded = true;
    } catch (err: any) {
      error.value = err?.data?.detail || "Failed to load activity";
    } finally {
      loading.value = false;
    }
  }

  return { items, loading, error, load };
}
