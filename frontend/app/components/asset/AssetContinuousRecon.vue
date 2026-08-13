<script setup lang="ts">
// Continuous Recon section (18d.5) -- the most state-sensitive extraction.
// `tools` is a prop (read-only, fetched once by the parent's loadAll())
// rather than its own fetch, to avoid the doubled /api/tools request the
// user explicitly warned against.
//
// `refreshAssetData` is passed as an async function prop (not just an
// event) because the original runScheduleNow() awaited BOTH
// loadSchedules() AND the parent's loadAll() before clearing the row's
// busy state (Promise.all([loadSchedules(), loadAll()])) -- a fire-and-
// forget event can't preserve that same busy-until-both-finish timing
// without duplicating asset/jobs/findings state locally to know when the
// parent is done, which the "single source of truth" rule rules out.
import { onMounted, reactive, ref } from "vue";
import { useApi } from "~/composables/useApi";
import { formatDate, relativeTime } from "~/utils/datetime";

interface ArgumentDef {
  name: string;
  type: "target" | "url" | "string" | "boolean" | "choice" | "integer";
  required: boolean;
  positional: boolean;
  flag: string | null;
  default: boolean | string | number | null;
  choices: string[] | null;
  description: string;
}

interface ProfileDef {
  name: string;
  description: string;
}

interface ToolDef {
  name: string;
  category: string;
  description: string;
  arguments: ArgumentDef[];
  profiles: ProfileDef[];
}

interface ScheduledJob {
  id: string;
  asset_id: string | null;
  tool: string;
  profile: string | null;
  params: Record<string, unknown>;
  interval_seconds: number;
  status: "ACTIVE" | "PAUSED" | "DISABLED";
  next_run_at: string;
  last_run_at: string | null;
  last_job_id: string | null;
  consecutive_failures: number;
  last_error: string | null;
}

const props = defineProps<{
  assetId: string;
  tools: ToolDef[];
  refreshAssetData: () => Promise<void>;
}>();

const INTERVAL_PRESETS = [
  { label: "5 minutes", seconds: 300 },
  { label: "15 minutes", seconds: 900 },
  { label: "1 hour", seconds: 3600 },
  { label: "6 hours", seconds: 21600 },
  { label: "12 hours", seconds: 43200 },
  { label: "24 hours", seconds: 86400 },
];

const { apiFetch } = useApi();

const schedules = ref<ScheduledJob[]>([]);
const schedulesLoading = ref(true);
const schedulesError = ref("");
const showScheduleForm = ref(false);
const newSchedule = reactive({ tool: "", profile: "", intervalSeconds: 3600 });
const creatingSchedule = ref(false);
const createScheduleError = ref("");
const busyScheduleIds = ref<Set<string>>(new Set());

function intervalLabel(seconds: number) {
  const preset = INTERVAL_PRESETS.find((p) => p.seconds === seconds);
  if (preset) return preset.label;
  if (seconds % 3600 === 0) return `${seconds / 3600}h`;
  return `${Math.round(seconds / 60)}m`;
}

async function loadSchedules() {
  schedulesLoading.value = true;
  schedulesError.value = "";
  try {
    schedules.value = await apiFetch<ScheduledJob[]>(`/api/assets/${props.assetId}/schedules`);
  } catch (err: any) {
    schedulesError.value = err?.data?.detail || "Failed to load scheduled scans";
  } finally {
    schedulesLoading.value = false;
  }
}

async function createSchedule() {
  if (!newSchedule.tool) return;
  creatingSchedule.value = true;
  createScheduleError.value = "";
  try {
    await apiFetch(`/api/assets/${props.assetId}/schedules`, {
      method: "POST",
      body: {
        tool: newSchedule.tool,
        profile: newSchedule.profile || null,
        interval_seconds: newSchedule.intervalSeconds,
      },
    });
    Object.assign(newSchedule, { tool: "", profile: "", intervalSeconds: 3600 });
    showScheduleForm.value = false;
    await loadSchedules();
  } catch (err: any) {
    createScheduleError.value = err?.data?.detail || "Failed to create scheduled scan";
  } finally {
    creatingSchedule.value = false;
  }
}

async function setScheduleStatus(schedule: ScheduledJob, status: "ACTIVE" | "PAUSED") {
  busyScheduleIds.value.add(schedule.id);
  try {
    await apiFetch(`/api/schedules/${schedule.id}`, { method: "PATCH", body: { status } });
    await loadSchedules();
  } finally {
    busyScheduleIds.value.delete(schedule.id);
  }
}

async function runScheduleNow(schedule: ScheduledJob) {
  busyScheduleIds.value.add(schedule.id);
  try {
    await apiFetch(`/api/schedules/${schedule.id}/run`, { method: "POST" });
    await Promise.all([loadSchedules(), props.refreshAssetData()]);
  } catch (err: any) {
    schedulesError.value = err?.data?.detail || "Failed to run scheduled scan";
  } finally {
    busyScheduleIds.value.delete(schedule.id);
  }
}

async function deleteScheduleRow(schedule: ScheduledJob) {
  busyScheduleIds.value.add(schedule.id);
  try {
    await apiFetch(`/api/schedules/${schedule.id}`, { method: "DELETE" });
    await loadSchedules();
  } finally {
    busyScheduleIds.value.delete(schedule.id);
  }
}

onMounted(loadSchedules);
</script>

<template>
  <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
    <div class="mb-3 flex items-center justify-between">
      <h2 class="text-sm font-semibold text-slate-300">Continuous Recon</h2>
      <button
        class="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500"
        @click="showScheduleForm = !showScheduleForm"
      >
        + Schedule scan
      </button>
    </div>

    <div v-if="showScheduleForm" class="mb-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div>
          <label class="mb-1 block text-xs text-slate-500">Tool *</label>
          <select
            v-model="newSchedule.tool"
            class="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200"
            @change="newSchedule.profile = ''"
          >
            <option value="">Select a tool…</option>
            <option v-for="t in tools" :key="t.name" :value="t.name">{{ t.name }}</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs text-slate-500">Profile</label>
          <select
            v-model="newSchedule.profile"
            class="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200"
            :disabled="!newSchedule.tool"
          >
            <option value="">(default)</option>
            <option v-for="p in tools.find((t) => t.name === newSchedule.tool)?.profiles || []" :key="p.name" :value="p.name">
              {{ p.name }}
            </option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs text-slate-500">Frequency</label>
          <select
            v-model.number="newSchedule.intervalSeconds"
            class="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200"
          >
            <option v-for="p in INTERVAL_PRESETS" :key="p.seconds" :value="p.seconds">Every {{ p.label }}</option>
          </select>
        </div>
      </div>
      <p v-if="createScheduleError" class="mt-2 text-sm text-red-400">{{ createScheduleError }}</p>
      <button
        class="mt-3 rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        :disabled="creatingSchedule || !newSchedule.tool"
        @click="createSchedule"
      >
        {{ creatingSchedule ? "Creating…" : "Create schedule" }}
      </button>
    </div>

    <LoadingState v-if="schedulesLoading" />
    <p v-else-if="schedulesError" class="text-sm text-red-400">{{ schedulesError }}</p>
    <EmptyState v-else-if="schedules.length === 0" message='No scheduled scans yet. Click "+ Schedule scan" to set up periodic monitoring.' />
    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th class="py-1.5 pr-3">Tool</th>
            <th class="py-1.5 pr-3">Frequency</th>
            <th class="py-1.5 pr-3">Status</th>
            <th class="py-1.5 pr-3">Next run</th>
            <th class="py-1.5 pr-3">Last run</th>
            <th class="py-1.5 pr-3">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-800">
          <tr v-for="s in schedules" :key="s.id">
            <td class="py-2 pr-3 text-slate-200">
              {{ s.tool }}<span v-if="s.profile" class="text-slate-500"> ({{ s.profile }})</span>
            </td>
            <td class="py-2 pr-3 text-slate-400">every {{ intervalLabel(s.interval_seconds) }}</td>
            <td class="py-2 pr-3">
              <span
                class="rounded px-1.5 py-0.5 text-xs"
                :class="{
                  'bg-emerald-500/15 text-emerald-400': s.status === 'ACTIVE',
                  'bg-amber-500/15 text-amber-400': s.status === 'PAUSED',
                  'bg-slate-700/50 text-slate-400': s.status === 'DISABLED',
                }"
              >
                {{ s.status }}
              </span>
              <span v-if="s.consecutive_failures > 0" class="ml-1 text-xs text-red-400" :title="s.last_error || ''">
                ⚠ {{ s.consecutive_failures }}
              </span>
            </td>
            <td class="py-2 pr-3 text-slate-500">{{ s.status === "ACTIVE" ? relativeTime(s.next_run_at) : "—" }}</td>
            <td class="py-2 pr-3 text-slate-500">
              <NuxtLink v-if="s.last_job_id" :to="`/scans/${s.last_job_id}`" class="text-emerald-400 hover:underline">
                {{ formatDate(s.last_run_at) }}
              </NuxtLink>
              <span v-else>never</span>
            </td>
            <td class="py-2 pr-3">
              <div class="flex gap-2 text-xs">
                <button
                  v-if="s.status === 'ACTIVE'"
                  class="text-slate-400 hover:text-amber-400 disabled:opacity-50"
                  :disabled="busyScheduleIds.has(s.id)"
                  @click="setScheduleStatus(s, 'PAUSED')"
                >
                  Pause
                </button>
                <button
                  v-else-if="s.status === 'PAUSED'"
                  class="text-slate-400 hover:text-emerald-400 disabled:opacity-50"
                  :disabled="busyScheduleIds.has(s.id)"
                  @click="setScheduleStatus(s, 'ACTIVE')"
                >
                  Resume
                </button>
                <button
                  v-if="s.status !== 'DISABLED'"
                  class="text-slate-400 hover:text-emerald-400 disabled:opacity-50"
                  :disabled="busyScheduleIds.has(s.id)"
                  @click="runScheduleNow(s)"
                >
                  Run now
                </button>
                <button
                  class="text-slate-400 hover:text-red-400 disabled:opacity-50"
                  :disabled="busyScheduleIds.has(s.id)"
                  @click="deleteScheduleRow(s)"
                >
                  Delete
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
