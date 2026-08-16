import { reactive } from "vue";
import { useApi } from "./useApi";

// Extracted from pages/index.vue's original inline health-check logic so
// the new Topbar system-status pill and the Dashboard's status tiles hit
// the same four endpoints once each, with one shared refresh() instead of
// two independent onMounted fetch blocks.
export type HealthStatus = "checking" | "ok" | "error" | "unreachable";

export interface SystemStatusState {
  api: HealthStatus;
  db: HealthStatus;
  kali: HealthStatus;
  kaliDetail?: string;
  ai: HealthStatus;
  aiDetail?: string;
}

export function useSystemStatus() {
  const { apiFetch } = useApi();

  const status = reactive<SystemStatusState>({
    api: "checking",
    db: "checking",
    kali: "checking",
    ai: "checking",
  });

  async function refresh() {
    status.api = "checking";
    status.db = "checking";
    status.kali = "checking";
    status.ai = "checking";

    try {
      await apiFetch("/api/health");
      status.api = "ok";
    } catch {
      status.api = "error";
    }
    try {
      await apiFetch("/api/health/db");
      status.db = "ok";
    } catch {
      status.db = "error";
    }
    try {
      const res = await apiFetch<{ status: string; tools_available?: string[] }>("/api/health/kali");
      status.kali = res.status === "ok" ? "ok" : "unreachable";
      status.kaliDetail = res.tools_available?.join(", ");
    } catch {
      status.kali = "unreachable";
    }
    try {
      const res = await apiFetch<{ status: string; models?: string[] }>("/api/health/ollama");
      status.ai = res.status === "ok" ? "ok" : "unreachable";
      status.aiDetail = res.models?.join(", ");
    } catch {
      status.ai = "unreachable";
    }
  }

  return { status, refresh };
}
