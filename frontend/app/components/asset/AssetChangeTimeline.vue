<script setup lang="ts">
// Change Timeline section (18d.2) -- fully self-contained: owns its own
// fetch, filters, and re-fetch-on-filter-change watcher. Nothing else on
// the Asset page reads `changes`, so there is no shared-state risk here
// (unlike Continuous Recon's runScheduleNow, which does need to notify the
// parent).
import { onMounted, ref, watch } from "vue";
import { useApi } from "~/composables/useApi";
import { formatDate, relativeTime } from "~/utils/datetime";

const props = defineProps<{ assetId: string }>();

interface AssetChangeEvent {
  id: string;
  job_id: string;
  previous_job_id: string | null;
  change_type: string;
  severity: "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  field: string;
  old_value: string | null;
  new_value: string | null;
  detected_at: string;
}

const CHANGE_TYPES = [
  "PORT_OPENED",
  "PORT_CLOSED",
  "SERVICE_CHANGED",
  "TECHNOLOGY_ADDED",
  "TECHNOLOGY_REMOVED",
  "TECHNOLOGY_CHANGED",
  "CERTIFICATE_CHANGED",
  "HTTP_CHANGED",
  "OTHER",
];

const { apiFetch } = useApi();

const changes = ref<AssetChangeEvent[]>([]);
const changesLoading = ref(true);
const changesError = ref("");
const changeTypeFilter = ref("");
const changeSeverityFilter = ref("");

const changeIcon: Record<string, string> = {
  INFO: "🟢",
  LOW: "🟢",
  MEDIUM: "🟡",
  HIGH: "🔴",
  CRITICAL: "🔴",
};

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

async function loadChanges() {
  changesLoading.value = true;
  changesError.value = "";
  try {
    const params = new URLSearchParams();
    if (changeTypeFilter.value) params.set("change_type", changeTypeFilter.value);
    if (changeSeverityFilter.value) params.set("severity", changeSeverityFilter.value);
    const query = params.toString() ? `?${params.toString()}` : "";
    changes.value = await apiFetch<AssetChangeEvent[]>(`/api/assets/${props.assetId}/changes${query}`);
  } catch (err: any) {
    changesError.value = err?.data?.detail || "Failed to load the change timeline";
  } finally {
    changesLoading.value = false;
  }
}

watch([changeTypeFilter, changeSeverityFilter], loadChanges);

onMounted(loadChanges);
</script>

<template>
  <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <h2 class="text-sm font-semibold text-slate-300">Change Timeline</h2>
      <div class="flex gap-2">
        <select v-model="changeTypeFilter" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-300">
          <option value="">All change types</option>
          <option v-for="ct in CHANGE_TYPES" :key="ct" :value="ct">{{ ct }}</option>
        </select>
        <select v-model="changeSeverityFilter" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-300">
          <option value="">All severities</option>
          <option v-for="sev in ['INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL']" :key="sev" :value="sev">{{ sev }}</option>
        </select>
      </div>
    </div>

    <LoadingState v-if="changesLoading" />
    <p v-else-if="changesError" class="text-sm text-red-400">{{ changesError }}</p>
    <EmptyState
      v-else-if="changes.length === 0"
      message="No changes detected yet. Run the same scan twice (manually or via a schedule) to start comparing."
    />
    <div v-else class="space-y-3">
      <div v-for="c in changes" :key="c.id" class="flex items-start gap-3 border-b border-slate-800 pb-3 last:border-0 last:pb-0">
        <span class="mt-0.5 text-base leading-none">{{ changeIcon[c.severity] }}</span>
        <div class="min-w-0 flex-1">
          <p class="text-sm text-slate-200">{{ changeSummary(c) }}</p>
          <p v-if="c.old_value || c.new_value" class="truncate text-xs text-slate-500">
            {{ c.old_value || "—" }} → {{ c.new_value || "—" }}
          </p>
          <p class="text-xs text-slate-600">{{ relativeTime(c.detected_at) }} · {{ formatDate(c.detected_at) }}</p>
        </div>
        <NuxtLink :to="`/scans/${c.job_id}`" class="shrink-0 text-xs text-emerald-400 hover:underline">scan</NuxtLink>
      </div>
    </div>
  </div>
</template>
