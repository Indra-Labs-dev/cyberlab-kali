<script setup lang="ts">
import type { Asset } from "~/types/asset";
import type { Finding } from "~/types/finding";
import type { Project } from "~/types/project";
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

interface Job {
  id: string;
  tool: string;
  target: string;
  status: string;
  created_at: string;
  finished_at: string | null;
  evidence_sha256: string | null;
}

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

const savingAuth = ref(false);
const savingCriticality = ref(false);
const savingTags = ref(false);
const showScanForm = ref(false);
const selectedTool = ref("");
const scanOptions = reactive<Record<string, string | boolean>>({});
const scanning = ref(false);
const scanError = ref("");

function address(a: Asset) {
  return a.url || a.hostname || a.ip_address || "—";
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

async function addTag(tag: string): Promise<boolean> {
  if (!asset.value) return false;
  savingTags.value = true;
  try {
    asset.value = await apiFetch<Asset>(`/api/assets/${assetId}`, {
      method: "PATCH",
      body: { tags: [...asset.value.tags, tag] },
    });
    return true;
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
      <AssetHeader
        :asset="asset"
        :project="project"
        :asset-id="assetId"
        :saving-auth="savingAuth"
        :saving-criticality="savingCriticality"
        :saving-tags="savingTags"
        :add-tag="addTag"
        @update-authorization="updateAuthorization"
        @update-criticality="updateCriticality"
        @remove-tag="removeTag"
      >
        <template #actions>
          <button
            class="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500"
            @click="showScanForm = !showScanForm"
          >
            Scan Asset
          </button>
        </template>
      </AssetHeader>

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

      <AssetContinuousRecon :asset-id="assetId" :tools="tools" :refresh-asset-data="loadAll" />

      <AssetChangeTimeline :asset-id="assetId" />

      <AssetRiskOverview :asset-id="assetId" />

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

      <AssetFindingsList :findings="findings" />

      <EvidenceTimeline :jobs="jobs" :findings="findings" />
    </div>
  </div>
</template>
