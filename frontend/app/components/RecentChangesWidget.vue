<script setup lang="ts">
// SOC-lite (docs/roadmap.md §8) -- the other half of "Findings actifs +
// changements récents". Cross-project (see GET /api/asset-changes in
// backend/app/api/routes/schedules.py), unlike AssetChangeTimeline.vue
// which is scoped to one asset -- the summary/icon logic below is
// deliberately duplicated from that component rather than shared, same
// precedent as similar small pure helpers elsewhere in this codebase.
import { onMounted, ref } from "vue";
import { useApi } from "~/composables/useApi";
import type { AssetChangeEvent } from "~/types/asset-change-event";

const { apiFetch } = useApi();

const changes = ref<AssetChangeEvent[]>([]);
const loading = ref(true);
const error = ref("");

const changeIcon: Record<string, string> = { INFO: "🟢", LOW: "🟢", MEDIUM: "🟡", HIGH: "🔴", CRITICAL: "🔴" };

function changeSummary(change: AssetChangeEvent): string {
  const label = change.field;
  if (change.change_type === "PORT_OPENED") return `Port ${label.replace("port:", "")} opened`;
  if (change.change_type === "PORT_CLOSED") return `Port ${label.replace("port:", "")} closed`;
  if (change.change_type.startsWith("TECHNOLOGY")) {
    const tech = label.replace("technology:", "");
    if (change.change_type === "TECHNOLOGY_ADDED") return `${tech} detected`;
    if (change.change_type === "TECHNOLOGY_REMOVED") return `${tech} no longer detected`;
    return `${tech} changed`;
  }
  if (change.change_type === "CERTIFICATE_CHANGED") return `Certificate changed (${label})`;
  if (change.change_type === "HTTP_CHANGED") return `HTTP status changed`;
  if (change.change_type === "SERVICE_CHANGED") return `Service changed on ${label.replace("port:", "")}`;
  return label;
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    changes.value = await apiFetch<AssetChangeEvent[]>("/api/asset-changes?limit=8");
  } catch (err: any) {
    error.value = err?.data?.detail || "Failed to load recent changes";
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
    <div class="mb-3 flex items-center justify-between">
      <h2 class="text-sm font-semibold text-slate-300">Recent changes</h2>
    </div>
    <LoadingState v-if="loading" />
    <p v-else-if="error" class="text-sm text-red-400">{{ error }}</p>
    <p v-else-if="changes.length === 0" class="text-sm text-slate-600">No changes detected yet across any asset.</p>
    <ul v-else class="space-y-2">
      <li v-for="c in changes" :key="c.id" class="flex items-center gap-3 rounded-md border border-slate-800 bg-slate-950/50 px-3 py-2">
        <span class="text-base leading-none">{{ changeIcon[c.severity] }}</span>
        <NuxtLink :to="`/scans/${c.job_id}`" class="min-w-0 flex-1 text-sm text-slate-200 hover:underline">
          {{ changeSummary(c) }}
        </NuxtLink>
      </li>
    </ul>
  </div>
</template>
