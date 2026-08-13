<script setup lang="ts">
import type { Asset } from "~/types/asset";
import type { Project } from "~/types/project";

const ASSET_TYPES = ["HOST", "IP", "DOMAIN", "SUBDOMAIN", "URL", "SERVICE", "CONTAINER", "LAB", "LAB_RESOURCE", "OTHER"];
const CRITICALITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const AUTH_STATUSES = ["LAB", "AUTHORIZED", "LOCAL", "UNKNOWN"];

const { apiFetch } = useApi();
const { listProjects } = useProjects();
const { listAssets } = useAssets();
const router = useRouter();

const projects = ref<Project[]>([]);
const assets = ref<Asset[]>([]);
const loading = ref(true);

const projectFilter = ref("");
const typeFilter = ref("");
const authFilter = ref("");
const criticalityFilter = ref("");

const showCreateForm = ref(false);
const newAsset = reactive({
  project_id: "",
  name: "",
  hostname: "",
  ip_address: "",
  url: "",
  type: "HOST",
  criticality: "MEDIUM",
  authorization_status: "",
  tags: "",
  description: "",
});
const creating = ref(false);
const createError = ref("");

function projectName(id: string) {
  return projects.value.find((p) => p.id === id)?.name || "—";
}

function address(asset: Asset) {
  return asset.url || asset.hostname || asset.ip_address || "—";
}

function relativeTime(iso: string | null) {
  if (!iso) return "never";
  const diffMs = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diffMs / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}

async function loadProjects() {
  projects.value = await listProjects();
}

async function loadAssets() {
  loading.value = true;
  try {
    const params: Record<string, string> = {};
    if (projectFilter.value) params.project_id = projectFilter.value;
    if (typeFilter.value) params.type = typeFilter.value;
    if (authFilter.value) params.authorization_status = authFilter.value;
    if (criticalityFilter.value) params.criticality = criticalityFilter.value;
    assets.value = await listAssets(params);
  } finally {
    loading.value = false;
  }
}

watch([projectFilter, typeFilter, authFilter, criticalityFilter], loadAssets);

async function createAsset() {
  if (!newAsset.project_id || !newAsset.name) return;
  creating.value = true;
  createError.value = "";
  try {
    await apiFetch(`/api/projects/${newAsset.project_id}/assets`, {
      method: "POST",
      body: {
        name: newAsset.name,
        hostname: newAsset.hostname || null,
        ip_address: newAsset.ip_address || null,
        url: newAsset.url || null,
        type: newAsset.type,
        criticality: newAsset.criticality,
        authorization_status: newAsset.authorization_status || null,
        tags: newAsset.tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        description: newAsset.description || null,
      },
    });
    Object.assign(newAsset, {
      project_id: "",
      name: "",
      hostname: "",
      ip_address: "",
      url: "",
      type: "HOST",
      criticality: "MEDIUM",
      authorization_status: "",
      tags: "",
      description: "",
    });
    showCreateForm.value = false;
    await loadAssets();
  } catch (err: any) {
    createError.value = err?.data?.detail || "Failed to create asset";
  } finally {
    creating.value = false;
  }
}

onMounted(async () => {
  await loadProjects();
  await loadAssets();
});
</script>

<template>
  <div>
    <PageHeader title="Assets" subtitle="Hosts, domains, URLs, and other tracked assets, grouped by project" />

    <div class="px-8 py-6">
      <div class="mb-4 flex flex-wrap items-center gap-2">
        <select v-model="projectFilter" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200">
          <option value="">All projects</option>
          <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
        <select v-model="typeFilter" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200">
          <option value="">All types</option>
          <option v-for="t in ASSET_TYPES" :key="t" :value="t">{{ t }}</option>
        </select>
        <select v-model="criticalityFilter" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200">
          <option value="">All criticality</option>
          <option v-for="c in CRITICALITIES" :key="c" :value="c">{{ c }}</option>
        </select>
        <select v-model="authFilter" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200">
          <option value="">All authorization</option>
          <option v-for="a in AUTH_STATUSES" :key="a" :value="a">{{ a }}</option>
        </select>
        <button
          class="ml-auto rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500"
          @click="showCreateForm = !showCreateForm"
        >
          + New Asset
        </button>
      </div>

      <div v-if="showCreateForm" class="mb-6 rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs text-slate-500">Project *</label>
            <select v-model="newAsset.project_id" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200">
              <option value="">Select a project…</option>
              <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-xs text-slate-500">Name *</label>
            <input v-model="newAsset.name" type="text" placeholder="e.g. Juice Shop" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200" />
          </div>
          <div>
            <label class="mb-1 block text-xs text-slate-500">Hostname</label>
            <input v-model="newAsset.hostname" type="text" placeholder="cyberlab-lab-dvwa-xxxx" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200" />
          </div>
          <div>
            <label class="mb-1 block text-xs text-slate-500">IP address</label>
            <input v-model="newAsset.ip_address" type="text" placeholder="10.0.0.5" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200" />
          </div>
          <div>
            <label class="mb-1 block text-xs text-slate-500">URL</label>
            <input v-model="newAsset.url" type="text" placeholder="http://juice-shop:3000" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200" />
          </div>
          <div>
            <label class="mb-1 block text-xs text-slate-500">Type</label>
            <select v-model="newAsset.type" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200">
              <option v-for="t in ASSET_TYPES" :key="t" :value="t">{{ t }}</option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-xs text-slate-500">Criticality</label>
            <select v-model="newAsset.criticality" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200">
              <option v-for="c in CRITICALITIES" :key="c" :value="c">{{ c }}</option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-xs text-slate-500">Authorization (leave blank to auto-detect)</label>
            <select v-model="newAsset.authorization_status" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200">
              <option value="">Auto-detect</option>
              <option v-for="a in AUTH_STATUSES" :key="a" :value="a">{{ a }}</option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-xs text-slate-500">Tags (comma-separated)</label>
            <input v-model="newAsset.tags" type="text" placeholder="prod, external" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200" />
          </div>
          <div>
            <label class="mb-1 block text-xs text-slate-500">Description</label>
            <input v-model="newAsset.description" type="text" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200" />
          </div>
        </div>
        <p v-if="createError" class="mt-2 text-sm text-red-400">{{ createError }}</p>
        <button
          class="mt-3 rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          :disabled="creating || !newAsset.project_id || !newAsset.name"
          @click="createAsset"
        >
          {{ creating ? "Creating…" : "Create" }}
        </button>
      </div>

      <LoadingState v-if="loading" />
      <EmptyState v-else-if="assets.length === 0" message='No assets yet. Click "+ New Asset" to register one.' />

      <div v-else class="overflow-x-auto rounded-lg border border-slate-800">
        <table class="w-full text-sm">
          <thead class="bg-slate-900/60 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th class="px-4 py-2">Name</th>
              <th class="px-4 py-2">Address</th>
              <th class="px-4 py-2">Type</th>
              <th class="px-4 py-2">Criticality</th>
              <th class="px-4 py-2">Project</th>
              <th class="px-4 py-2">Authorization</th>
              <th class="px-4 py-2">Last seen</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-800">
            <tr
              v-for="asset in assets"
              :key="asset.id"
              class="cursor-pointer hover:bg-slate-900/40"
              @click="router.push(`/assets/${asset.id}`)"
            >
              <td class="px-4 py-2 font-medium text-slate-200">{{ asset.name }}</td>
              <td class="px-4 py-2 text-slate-400">{{ address(asset) }}</td>
              <td class="px-4 py-2 text-slate-500">{{ asset.type }}</td>
              <td class="px-4 py-2">
                <CriticalityBadge :criticality="asset.criticality" size="sm" />
              </td>
              <td class="px-4 py-2 text-slate-500">{{ projectName(asset.project_id) }}</td>
              <td class="px-4 py-2">
                <AuthorizationBadge :status="asset.authorization_status" size="sm" />
              </td>
              <td class="px-4 py-2 text-slate-500">{{ relativeTime(asset.last_seen) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
