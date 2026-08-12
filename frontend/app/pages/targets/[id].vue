<script setup lang="ts">
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

interface Asset {
  id: string;
  project_id: string;
  name: string;
  hostname: string | null;
  ip_address: string | null;
  url: string | null;
  type: string;
  criticality: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  authorization_status: "LAB" | "AUTHORIZED" | "LOCAL" | "UNKNOWN";
  tags: string[];
  technologies: string[];
  description: string | null;
  first_seen: string | null;
  last_seen: string | null;
  created_at: string;
}

interface Project {
  id: string;
  name: string;
}

interface Job {
  id: string;
  tool: string;
  status: string;
  created_at: string;
}

interface Finding {
  id: string;
  job_id: string;
  title: string;
  severity: string;
  source_tool: string;
  risk_score: number | null;
  risk_priority: "INFORMATIONAL" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | null;
}

interface RiskSummary {
  total_findings: number;
  critical_findings: number;
  high_findings: number;
  medium_findings: number;
  low_findings: number;
  informational_findings: number;
  kev_findings: number;
  highest_risk_score: number | null;
  unscored_findings: number;
}

const CRITICALITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;
const AUTH_STATUSES = ["LAB", "AUTHORIZED", "LOCAL", "UNKNOWN"] as const;
const INTERVAL_PRESETS = [
  { label: "5 minutes", seconds: 300 },
  { label: "15 minutes", seconds: 900 },
  { label: "1 hour", seconds: 3600 },
  { label: "6 hours", seconds: 21600 },
  { label: "12 hours", seconds: 43200 },
  { label: "24 hours", seconds: 86400 },
];
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

const route = useRoute();
const router = useRouter();
const { apiFetch } = useApi();
const assetId = route.params.id as string;

const asset = ref<Asset | null>(null);
const project = ref<Project | null>(null);
const jobs = ref<Job[]>([]);
const findings = ref<Finding[]>([]);
const tools = ref<ToolDef[]>([]);
const loading = ref(true);
const loadError = ref("");

const schedules = ref<ScheduledJob[]>([]);
const schedulesLoading = ref(true);
const schedulesError = ref("");
const showScheduleForm = ref(false);
const newSchedule = reactive({ tool: "", profile: "", intervalSeconds: 3600 });
const creatingSchedule = ref(false);
const createScheduleError = ref("");
const busyScheduleIds = ref<Set<string>>(new Set());

const changes = ref<AssetChangeEvent[]>([]);
const changesLoading = ref(true);
const changesError = ref("");
const changeTypeFilter = ref("");
const changeSeverityFilter = ref("");

const riskSummary = ref<RiskSummary | null>(null);
const riskSummaryLoading = ref(true);
const riskSummaryError = ref("");

const authColor: Record<string, string> = {
  LAB: "bg-emerald-500/15 text-emerald-400",
  AUTHORIZED: "bg-emerald-500/15 text-emerald-400",
  LOCAL: "bg-cyan-500/15 text-cyan-400",
  UNKNOWN: "bg-amber-500/15 text-amber-400",
};
const criticalityColor: Record<string, string> = {
  LOW: "bg-slate-700/50 text-slate-300",
  MEDIUM: "bg-cyan-500/15 text-cyan-400",
  HIGH: "bg-orange-500/15 text-orange-400",
  CRITICAL: "bg-red-500/15 text-red-400",
};
const severityColor: Record<string, string> = {
  INFO: "bg-slate-700/50 text-slate-300",
  LOW: "bg-emerald-500/15 text-emerald-400",
  MEDIUM: "bg-amber-500/15 text-amber-400",
  HIGH: "bg-orange-500/15 text-orange-400",
  CRITICAL: "bg-red-500/15 text-red-400",
};
const priorityColor: Record<string, string> = {
  INFORMATIONAL: "bg-slate-700/50 text-slate-300",
  LOW: "bg-emerald-500/15 text-emerald-400",
  MEDIUM: "bg-amber-500/15 text-amber-400",
  HIGH: "bg-orange-500/15 text-orange-400",
  CRITICAL: "bg-red-500/15 text-red-400",
};

const savingAuth = ref(false);
const savingCriticality = ref(false);
const newTag = ref("");
const savingTags = ref(false);
const showScanForm = ref(false);
const selectedTool = ref("");
const scanOptions = reactive<Record<string, string | boolean>>({});
const scanning = ref(false);
const scanError = ref("");

function address(a: Asset) {
  return a.url || a.hostname || a.ip_address || "—";
}

function formatDate(iso: string | null) {
  if (!iso) return "never";
  return new Date(iso).toLocaleString();
}

function relativeTime(iso: string) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function intervalLabel(seconds: number) {
  const preset = INTERVAL_PRESETS.find((p) => p.seconds === seconds);
  if (preset) return preset.label;
  if (seconds % 3600 === 0) return `${seconds / 3600}h`;
  return `${Math.round(seconds / 60)}m`;
}

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

async function loadAll() {
  loading.value = true;
  loadError.value = "";
  try {
    asset.value = await apiFetch<Asset>(`/api/assets/${assetId}`);
    const [proj, jbs, fnds, allTools] = await Promise.all([
      apiFetch<Project>(`/api/projects/${asset.value.project_id}`),
      apiFetch<Job[]>(`/api/jobs?target_id=${assetId}&limit=100`),
      apiFetch<Finding[]>(`/api/findings?target_id=${assetId}&limit=200`),
      apiFetch<ToolDef[]>("/api/tools"),
    ]);
    project.value = proj;
    jobs.value = jbs;
    findings.value = fnds;
    tools.value = allTools;
  } catch (err: any) {
    loadError.value = err?.data?.detail || "Failed to load asset";
  } finally {
    loading.value = false;
  }
}

async function loadSchedules() {
  schedulesLoading.value = true;
  schedulesError.value = "";
  try {
    schedules.value = await apiFetch<ScheduledJob[]>(`/api/assets/${assetId}/schedules`);
  } catch (err: any) {
    schedulesError.value = err?.data?.detail || "Failed to load scheduled scans";
  } finally {
    schedulesLoading.value = false;
  }
}

async function loadChanges() {
  changesLoading.value = true;
  changesError.value = "";
  try {
    const params = new URLSearchParams();
    if (changeTypeFilter.value) params.set("change_type", changeTypeFilter.value);
    if (changeSeverityFilter.value) params.set("severity", changeSeverityFilter.value);
    const query = params.toString() ? `?${params.toString()}` : "";
    changes.value = await apiFetch<AssetChangeEvent[]>(`/api/assets/${assetId}/changes${query}`);
  } catch (err: any) {
    changesError.value = err?.data?.detail || "Failed to load the change timeline";
  } finally {
    changesLoading.value = false;
  }
}

watch([changeTypeFilter, changeSeverityFilter], loadChanges);

async function loadRiskSummary() {
  riskSummaryLoading.value = true;
  riskSummaryError.value = "";
  try {
    riskSummary.value = await apiFetch<RiskSummary>(`/api/assets/${assetId}/risk-summary`);
  } catch (err: any) {
    riskSummaryError.value = err?.data?.detail || "Failed to load risk overview";
  } finally {
    riskSummaryLoading.value = false;
  }
}

async function createSchedule() {
  if (!newSchedule.tool) return;
  creatingSchedule.value = true;
  createScheduleError.value = "";
  try {
    await apiFetch(`/api/assets/${assetId}/schedules`, {
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
    await Promise.all([loadSchedules(), loadAll()]);
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

async function updateAuthorization(status: string) {
  savingAuth.value = true;
  try {
    asset.value = await apiFetch<Asset>(`/api/assets/${assetId}`, {
      method: "PATCH",
      body: { authorization_status: status },
    });
  } finally {
    savingAuth.value = false;
  }
}

async function updateCriticality(criticality: string) {
  savingCriticality.value = true;
  try {
    asset.value = await apiFetch<Asset>(`/api/assets/${assetId}`, {
      method: "PATCH",
      body: { criticality },
    });
  } finally {
    savingCriticality.value = false;
  }
}

async function addTag() {
  const tag = newTag.value.trim();
  if (!tag || !asset.value || asset.value.tags.includes(tag)) {
    newTag.value = "";
    return;
  }
  savingTags.value = true;
  try {
    asset.value = await apiFetch<Asset>(`/api/assets/${assetId}`, {
      method: "PATCH",
      body: { tags: [...asset.value.tags, tag] },
    });
    newTag.value = "";
  } finally {
    savingTags.value = false;
  }
}

async function removeTag(tag: string) {
  if (!asset.value) return;
  savingTags.value = true;
  try {
    asset.value = await apiFetch<Asset>(`/api/assets/${assetId}`, {
      method: "PATCH",
      body: { tags: asset.value.tags.filter((t) => t !== tag) },
    });
  } finally {
    savingTags.value = false;
  }
}

function selectToolForScan(toolName: string) {
  selectedTool.value = toolName;
  const tool = tools.value.find((t) => t.name === toolName);
  Object.keys(scanOptions).forEach((k) => delete scanOptions[k]);
  tool?.arguments.forEach((arg) => {
    if (arg.type === "target" || arg.type === "url") return; // fixed to this asset
    scanOptions[arg.name] = arg.type === "boolean" ? Boolean(arg.default) : "";
  });
}

async function runScan() {
  if (!selectedTool.value) return;
  scanning.value = true;
  scanError.value = "";
  const options: Record<string, string | boolean> = {};
  Object.entries(scanOptions).forEach(([k, v]) => {
    if (v) options[k] = v;
  });
  try {
    const job = await apiFetch<{ id: string }>("/api/jobs", {
      method: "POST",
      body: { tool: selectedTool.value, target_id: assetId, options },
    });
    router.push(`/scans/${job.id}`);
  } catch (err: any) {
    scanError.value = err?.data?.detail || "Failed to start scan";
  } finally {
    scanning.value = false;
  }
}

onMounted(() => {
  loadAll();
  loadSchedules();
  loadChanges();
  loadRiskSummary();
});
</script>

<template>
  <div>
    <PageHeader :title="asset?.name || 'Asset'" :subtitle="asset ? address(asset) : ''" />

    <div v-if="loading" class="px-8 py-6 text-sm text-slate-600">Loading…</div>
    <div v-else-if="loadError" class="px-8 py-6 text-sm text-red-400">{{ loadError }}</div>

    <div v-else-if="asset" class="space-y-6 px-8 py-6">
      <div class="flex flex-wrap items-center gap-3">
        <span class="rounded px-2 py-0.5 text-xs" :class="authColor[asset.authorization_status]">
          {{ asset.authorization_status }}
        </span>
        <span class="rounded px-2 py-0.5 text-xs" :class="criticalityColor[asset.criticality]">
          {{ asset.criticality }}
        </span>
        <span class="text-xs text-slate-500">{{ asset.type }}</span>
        <NuxtLink v-if="project" :to="`/projects/${project.id}`" class="text-xs text-emerald-400 hover:underline">
          {{ project.name }}
        </NuxtLink>
        <NuxtLink :to="`/ai?target_id=${assetId}`" class="ml-auto text-xs text-emerald-400 hover:underline">
          Ask AI about this asset
        </NuxtLink>
        <button
          class="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500"
          @click="showScanForm = !showScanForm"
        >
          Scan Asset
        </button>
      </div>

      <div v-if="asset.authorization_status === 'UNKNOWN'" class="rounded-lg border border-amber-900 bg-amber-950/20 p-3 text-sm text-amber-400">
        This asset's authorization status is UNKNOWN — jobs will be rejected until you mark it LAB, AUTHORIZED, or LOCAL.
      </div>

      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
          <p class="mb-2 text-xs font-medium text-slate-500">Authorization status</p>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="status in AUTH_STATUSES"
              :key="status"
              class="rounded-md border px-3 py-1 text-xs disabled:opacity-50"
              :class="
                asset.authorization_status === status
                  ? 'border-emerald-600 bg-emerald-500/10 text-emerald-400'
                  : 'border-slate-700 text-slate-400 hover:bg-slate-800'
              "
              :disabled="savingAuth"
              @click="updateAuthorization(status)"
            >
              {{ status }}
            </button>
          </div>
          <p v-if="asset.description" class="mt-3 text-sm text-slate-400">{{ asset.description }}</p>
        </div>

        <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
          <p class="mb-2 text-xs font-medium text-slate-500">Criticality</p>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="c in CRITICALITIES"
              :key="c"
              class="rounded-md border px-3 py-1 text-xs disabled:opacity-50"
              :class="
                asset.criticality === c
                  ? 'border-emerald-600 bg-emerald-500/10 text-emerald-400'
                  : 'border-slate-700 text-slate-400 hover:bg-slate-800'
              "
              :disabled="savingCriticality"
              @click="updateCriticality(c)"
            >
              {{ c }}
            </button>
          </div>
          <p class="mt-3 text-xs text-slate-500">
            Manually assigned — used by future risk scoring, not auto-computed yet.
          </p>
        </div>
      </div>

      <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
          <p class="mb-2 text-xs font-medium text-slate-500">Tags</p>
          <div class="mb-2 flex flex-wrap gap-1.5">
            <span
              v-for="tag in asset.tags"
              :key="tag"
              class="flex items-center gap-1 rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300"
            >
              {{ tag }}
              <button class="text-slate-500 hover:text-red-400" :disabled="savingTags" @click="removeTag(tag)">×</button>
            </span>
            <span v-if="asset.tags.length === 0" class="text-xs text-slate-600">No tags yet</span>
          </div>
          <div class="flex gap-1.5">
            <input
              v-model="newTag"
              type="text"
              placeholder="add tag…"
              class="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200"
              @keyup.enter="addTag"
            />
            <button class="rounded-md bg-slate-800 px-2 py-1 text-xs text-slate-300 hover:bg-slate-700" :disabled="savingTags" @click="addTag">
              Add
            </button>
          </div>
        </div>

        <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
          <p class="mb-2 text-xs font-medium text-slate-500">Technologies</p>
          <div class="flex flex-wrap gap-1.5">
            <span v-for="tech in asset.technologies" :key="tech" class="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
              {{ tech }}
            </span>
            <span v-if="asset.technologies.length === 0" class="text-xs text-slate-600">
              None detected yet — populated automatically from whatweb scans.
            </span>
          </div>
        </div>

        <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
          <p class="mb-2 text-xs font-medium text-slate-500">Activity</p>
          <p class="text-xs text-slate-400">First seen: <span class="text-slate-300">{{ formatDate(asset.first_seen) }}</span></p>
          <p class="mt-1 text-xs text-slate-400">Last seen: <span class="text-slate-300">{{ formatDate(asset.last_seen) }}</span></p>
          <p class="mt-2 text-xs text-slate-600">Derived from real job activity, not editable.</p>
        </div>
      </div>

      <div v-if="showScanForm" class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <label class="mb-1 block text-xs text-slate-500">Tool</label>
        <select
          :value="selectedTool"
          class="mb-3 w-full max-w-xs rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200"
          @change="selectToolForScan(($event.target as HTMLSelectElement).value)"
        >
          <option value="">Select a tool…</option>
          <option v-for="t in tools" :key="t.name" :value="t.name">{{ t.name }}</option>
        </select>

        <div v-if="selectedTool" class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div v-for="arg in tools.find((t) => t.name === selectedTool)?.arguments || []" :key="arg.name">
            <template v-if="arg.type !== 'target' && arg.type !== 'url'">
              <label class="mb-1 block text-xs font-medium text-slate-400">{{ arg.name }}</label>
              <select
                v-if="arg.type === 'choice'"
                v-model="scanOptions[arg.name]"
                class="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200"
              >
                <option value="">—</option>
                <option v-for="c in arg.choices" :key="c" :value="c">{{ c }}</option>
              </select>
              <label v-else-if="arg.type === 'boolean'" class="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" v-model="scanOptions[arg.name]" class="accent-emerald-500" /> enabled
              </label>
              <input
                v-else
                type="text"
                v-model="scanOptions[arg.name]"
                class="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200"
              />
            </template>
          </div>
        </div>

        <p v-if="scanError" class="mt-3 text-sm text-red-400">{{ scanError }}</p>
        <button
          v-if="selectedTool"
          class="mt-3 rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          :disabled="scanning"
          @click="runScan"
        >
          {{ scanning ? "Starting…" : "Run" }}
        </button>
      </div>

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
                <option
                  v-for="p in tools.find((t) => t.name === newSchedule.tool)?.profiles || []"
                  :key="p.name"
                  :value="p.name"
                >
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

        <p v-if="schedulesLoading" class="text-sm text-slate-600">Loading…</p>
        <p v-else-if="schedulesError" class="text-sm text-red-400">{{ schedulesError }}</p>
        <p v-else-if="schedules.length === 0" class="text-sm text-slate-600">
          No scheduled scans yet. Click "+ Schedule scan" to set up periodic monitoring.
        </p>
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

      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-sm font-semibold text-slate-300">Change Timeline</h2>
          <div class="flex gap-2">
            <select
              v-model="changeTypeFilter"
              class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-300"
            >
              <option value="">All change types</option>
              <option v-for="ct in CHANGE_TYPES" :key="ct" :value="ct">{{ ct }}</option>
            </select>
            <select
              v-model="changeSeverityFilter"
              class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-300"
            >
              <option value="">All severities</option>
              <option v-for="sev in ['INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL']" :key="sev" :value="sev">{{ sev }}</option>
            </select>
          </div>
        </div>

        <p v-if="changesLoading" class="text-sm text-slate-600">Loading…</p>
        <p v-else-if="changesError" class="text-sm text-red-400">{{ changesError }}</p>
        <p v-else-if="changes.length === 0" class="text-sm text-slate-600">
          No changes detected yet. Run the same scan twice (manually or via a schedule) to start comparing.
        </p>
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

      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-3 text-sm font-semibold text-slate-300">Risk Overview</h2>
        <p v-if="riskSummaryLoading" class="text-sm text-slate-600">Loading…</p>
        <p v-else-if="riskSummaryError" class="text-sm text-red-400">{{ riskSummaryError }}</p>
        <p v-else-if="riskSummary && riskSummary.total_findings === 0" class="text-sm text-slate-600">
          No findings yet — risk is computed automatically once scans produce findings.
        </p>
        <div v-else-if="riskSummary" class="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <p class="text-2xl font-semibold text-red-400">{{ riskSummary.critical_findings }}</p>
            <p class="text-xs text-slate-500">Critical findings</p>
          </div>
          <div>
            <p class="text-2xl font-semibold text-orange-400">{{ riskSummary.high_findings }}</p>
            <p class="text-xs text-slate-500">High findings</p>
          </div>
          <div>
            <p class="text-2xl font-semibold text-red-400">{{ riskSummary.kev_findings }}</p>
            <p class="text-xs text-slate-500">KEV findings</p>
          </div>
          <div>
            <p class="text-2xl font-semibold text-slate-200">{{ riskSummary.highest_risk_score ?? "—" }}</p>
            <p class="text-xs text-slate-500">Highest risk score</p>
          </div>
        </div>
        <p v-if="riskSummary && riskSummary.unscored_findings > 0" class="mt-2 text-xs text-slate-600">
          {{ riskSummary.unscored_findings }} finding(s) not yet scored.
        </p>
      </div>

      <SecurityGraph v-if="asset" :base-url="`/api/graph/assets/${assetId}`" />

      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-2 text-sm font-semibold text-slate-300">Scan history</h2>
        <p v-if="jobs.length === 0" class="text-sm text-slate-600">No scans against this asset yet.</p>
        <div v-else class="space-y-2">
          <NuxtLink
            v-for="job in jobs"
            :key="job.id"
            :to="`/scans/${job.id}`"
            class="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/50 p-2.5 hover:bg-slate-900"
          >
            <span class="text-sm text-slate-200">{{ job.tool }}</span>
            <JobStatusBadge :status="job.status" />
          </NuxtLink>
        </div>
      </div>

      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-2 text-sm font-semibold text-slate-300">Findings</h2>
        <p v-if="findings.length === 0" class="text-sm text-slate-600">No findings for this asset yet.</p>
        <div v-else class="space-y-2">
          <NuxtLink
            v-for="f in findings"
            :key="f.id"
            :to="`/findings/${f.id}`"
            class="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-950/50 p-2.5 hover:bg-slate-900"
          >
            <span class="rounded px-1.5 py-0.5 text-xs" :class="severityColor[f.severity]">{{ f.severity }}</span>
            <span
              v-if="f.risk_priority"
              class="rounded px-1.5 py-0.5 text-xs"
              :class="priorityColor[f.risk_priority]"
            >
              Risk {{ f.risk_score }}
            </span>
            <span class="text-sm text-slate-200">{{ f.title }}</span>
          </NuxtLink>
        </div>
      </div>
    </div>
  </div>
</template>
