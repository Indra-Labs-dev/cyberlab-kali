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

interface ToolDef {
  name: string;
  category: string;
  description: string;
  arguments: ArgumentDef[];
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
}

const CRITICALITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;
const AUTH_STATUSES = ["LAB", "AUTHORIZED", "LOCAL", "UNKNOWN"] as const;

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

onMounted(loadAll);
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
            :to="`/scans/${f.job_id}`"
            class="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-950/50 p-2.5 hover:bg-slate-900"
          >
            <span class="rounded px-1.5 py-0.5 text-xs" :class="severityColor[f.severity]">{{ f.severity }}</span>
            <span class="text-sm text-slate-200">{{ f.title }}</span>
          </NuxtLink>
        </div>
      </div>
    </div>
  </div>
</template>
