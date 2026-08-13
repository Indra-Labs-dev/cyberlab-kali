<script setup lang="ts">
// Phase 21 -- Tool Orchestrator section on the Asset page. Fully
// self-contained: owns its own fetch/create/cancel/polling, same pattern
// as AssetChangeTimeline.vue. Deliberately does not import anything from
// app/ai/ or the Mission badges (Phase 18) -- a MissionTemplate has no AI
// involvement at all, see backend/app/chains/service.py's module docstring.
import { onBeforeUnmount, onMounted, ref } from "vue";
import { useChains } from "~/composables/useChains";
import type { ChainRun, MissionTemplate } from "~/types/chain";

const props = defineProps<{ assetId: string }>();

const { listTemplates, createRun, listRuns, cancelRun, getRun } = useChains();

const templates = ref<MissionTemplate[]>([]);
const selectedTemplateId = ref("");
const runs = ref<ChainRun[]>([]);
const loading = ref(true);
const loadError = ref("");
const starting = ref(false);
const busyRunId = ref<string | null>(null);

// Bounded polling, same idiom as pages/ai/missions/index.vue -- a run can
// stay RUNNING for a while (each step is a real tool run), no push
// channel for chain-run progress.
const MAX_POLLS = 30;
const POLL_INTERVAL_MS = 4000;
const pollTimers = new Map<string, ReturnType<typeof setTimeout>>();
const pollCounts = new Map<string, number>();

function stopPolling(runId: string) {
  const timer = pollTimers.get(runId);
  if (timer) clearTimeout(timer);
  pollTimers.delete(runId);
  pollCounts.delete(runId);
}

function pollRun(runId: string) {
  stopPolling(runId);
  const tick = async () => {
    const count = (pollCounts.get(runId) || 0) + 1;
    pollCounts.set(runId, count);
    try {
      const updated = await getRun(runId);
      const index = runs.value.findIndex((r) => r.id === runId);
      if (index !== -1) runs.value[index] = updated;
      if (updated.status !== "RUNNING" || count >= MAX_POLLS) {
        stopPolling(runId);
        return;
      }
    } catch {
      stopPolling(runId);
      return;
    }
    pollTimers.set(runId, setTimeout(tick, POLL_INTERVAL_MS));
  };
  pollTimers.set(runId, setTimeout(tick, POLL_INTERVAL_MS));
}

async function loadAll() {
  loading.value = true;
  loadError.value = "";
  try {
    [templates.value, runs.value] = await Promise.all([listTemplates(), listRuns({ target_id: props.assetId })]);
    for (const run of runs.value) {
      if (run.status === "RUNNING") pollRun(run.id);
    }
  } catch (err: any) {
    loadError.value = err?.data?.detail || "Failed to load chain runs";
  } finally {
    loading.value = false;
  }
}

async function onStartRun() {
  if (!selectedTemplateId.value) return;
  starting.value = true;
  loadError.value = "";
  try {
    const run = await createRun(selectedTemplateId.value, props.assetId);
    runs.value.unshift(run);
    if (run.status === "RUNNING") pollRun(run.id);
  } catch (err: any) {
    loadError.value = err?.data?.detail || "Failed to start chain run";
  } finally {
    starting.value = false;
  }
}

async function onCancel(run: ChainRun) {
  busyRunId.value = run.id;
  try {
    const updated = await cancelRun(run.id);
    const index = runs.value.findIndex((r) => r.id === run.id);
    if (index !== -1) runs.value[index] = updated;
    stopPolling(run.id);
  } catch (err: any) {
    loadError.value = err?.data?.detail || "Failed to cancel run";
  } finally {
    busyRunId.value = null;
  }
}

onMounted(loadAll);
onBeforeUnmount(() => {
  for (const runId of Array.from(pollTimers.keys())) stopPolling(runId);
});
</script>

<template>
  <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
    <h2 class="mb-1 text-sm font-semibold text-slate-300">Tool Orchestrator</h2>
    <p class="mb-3 text-xs text-slate-500">
      Run a predefined, deterministic chain of tools against this asset — each step re-validated by the same
      Policy Engine as any other scan.
      <NuxtLink to="/chains" class="text-emerald-400 hover:underline">Manage templates →</NuxtLink>
    </p>

    <div class="mb-4 flex items-center gap-2">
      <select
        v-model="selectedTemplateId"
        class="flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200"
      >
        <option value="">Select a template…</option>
        <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}</option>
      </select>
      <button
        class="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        :disabled="!selectedTemplateId || starting"
        @click="onStartRun"
      >
        {{ starting ? "Starting…" : "Run chain" }}
      </button>
    </div>

    <p v-if="loadError" class="mb-2 text-sm text-red-400">{{ loadError }}</p>
    <LoadingState v-if="loading" />
    <EmptyState v-else-if="runs.length === 0" message="No chain runs against this asset yet." />

    <div v-if="runs.length" class="space-y-3">
      <div v-for="run in runs" :key="run.id" class="rounded-md border border-slate-800 bg-slate-950/50 p-3">
        <div class="flex items-center justify-between gap-3">
          <p class="text-xs text-slate-500">{{ new Date(run.created_at).toLocaleString() }}</p>
          <div class="flex items-center gap-2">
            <ChainRunStatusBadge :status="run.status" />
            <button
              v-if="run.status === 'RUNNING'"
              class="rounded-md border border-red-800 px-2.5 py-1 text-xs text-red-400 hover:bg-red-500/10 disabled:opacity-50"
              :disabled="busyRunId === run.id"
              @click="onCancel(run)"
            >
              Cancel
            </button>
          </div>
        </div>
        <ol class="mt-2 space-y-1.5">
          <li
            v-for="step in run.steps"
            :key="step.id"
            class="flex items-start justify-between gap-2 rounded border border-slate-800/70 bg-slate-900/40 px-2 py-1.5"
          >
            <div class="min-w-0">
              <p class="truncate text-xs text-slate-300">
                {{ step.step_order + 1 }}. {{ step.tool }}<span v-if="step.profile"> ({{ step.profile }})</span>
              </p>
              <p v-if="step.skip_reason" class="mt-0.5 text-xs text-slate-600">{{ step.skip_reason }}</p>
            </div>
            <ChainRunStepStatusBadge :status="step.status" />
          </li>
        </ol>
      </div>
    </div>
  </div>
</template>
