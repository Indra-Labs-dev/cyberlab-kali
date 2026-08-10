<script setup lang="ts">
interface Project {
  id: string;
  name: string;
}

interface Target {
  id: string;
  project_id: string;
  name: string;
  hostname: string | null;
  ip_address: string | null;
  url: string | null;
  target_type: string;
  authorization_status: "LAB" | "AUTHORIZED" | "LOCAL" | "UNKNOWN";
  created_at: string;
}

const { apiFetch } = useApi();
const router = useRouter();

const projects = ref<Project[]>([]);
const targets = ref<Target[]>([]);
const loading = ref(true);

const projectFilter = ref("");
const typeFilter = ref("");
const authFilter = ref("");

const showCreateForm = ref(false);
const newTarget = reactive({
  project_id: "",
  name: "",
  hostname: "",
  ip_address: "",
  url: "",
  target_type: "HOST",
  authorization_status: "",
  description: "",
});
const creating = ref(false);
const createError = ref("");

const authColor: Record<string, string> = {
  LAB: "bg-emerald-500/15 text-emerald-400",
  AUTHORIZED: "bg-emerald-500/15 text-emerald-400",
  LOCAL: "bg-cyan-500/15 text-cyan-400",
  UNKNOWN: "bg-amber-500/15 text-amber-400",
};

function projectName(id: string) {
  return projects.value.find((p) => p.id === id)?.name || "—";
}

function address(target: Target) {
  return target.url || target.hostname || target.ip_address || "—";
}

async function loadProjects() {
  projects.value = await apiFetch<Project[]>("/api/projects");
}

async function loadTargets() {
  loading.value = true;
  try {
    const params = new URLSearchParams();
    if (projectFilter.value) params.set("project_id", projectFilter.value);
    if (typeFilter.value) params.set("target_type", typeFilter.value);
    if (authFilter.value) params.set("authorization_status", authFilter.value);
    const query = params.toString() ? `?${params.toString()}` : "";
    targets.value = await apiFetch<Target[]>(`/api/targets${query}`);
  } finally {
    loading.value = false;
  }
}

watch([projectFilter, typeFilter, authFilter], loadTargets);

async function createTarget() {
  if (!newTarget.project_id || !newTarget.name) return;
  creating.value = true;
  createError.value = "";
  try {
    await apiFetch(`/api/projects/${newTarget.project_id}/targets`, {
      method: "POST",
      body: {
        name: newTarget.name,
        hostname: newTarget.hostname || null,
        ip_address: newTarget.ip_address || null,
        url: newTarget.url || null,
        target_type: newTarget.target_type,
        authorization_status: newTarget.authorization_status || null,
        description: newTarget.description || null,
      },
    });
    Object.assign(newTarget, {
      project_id: "",
      name: "",
      hostname: "",
      ip_address: "",
      url: "",
      target_type: "HOST",
      authorization_status: "",
      description: "",
    });
    showCreateForm.value = false;
    await loadTargets();
  } catch (err: any) {
    createError.value = err?.data?.detail || "Failed to create target";
  } finally {
    creating.value = false;
  }
}

onMounted(async () => {
  await loadProjects();
  await loadTargets();
});
</script>

<template>
  <div>
    <PageHeader title="Targets" subtitle="Registered scan targets, grouped by project" />

    <div class="px-8 py-6">
      <div class="mb-4 flex flex-wrap items-center gap-2">
        <select v-model="projectFilter" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200">
          <option value="">All projects</option>
          <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
        <select v-model="typeFilter" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200">
          <option value="">All types</option>
          <option v-for="t in ['HOST', 'IP', 'DOMAIN', 'URL', 'CONTAINER', 'LAB', 'OTHER']" :key="t" :value="t">{{ t }}</option>
        </select>
        <select v-model="authFilter" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200">
          <option value="">All authorization</option>
          <option v-for="a in ['LAB', 'AUTHORIZED', 'LOCAL', 'UNKNOWN']" :key="a" :value="a">{{ a }}</option>
        </select>
        <button
          class="ml-auto rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500"
          @click="showCreateForm = !showCreateForm"
        >
          + New Target
        </button>
      </div>

      <div v-if="showCreateForm" class="mb-6 rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs text-slate-500">Project *</label>
            <select v-model="newTarget.project_id" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200">
              <option value="">Select a project…</option>
              <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-xs text-slate-500">Name *</label>
            <input v-model="newTarget.name" type="text" placeholder="e.g. Juice Shop" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200" />
          </div>
          <div>
            <label class="mb-1 block text-xs text-slate-500">Hostname</label>
            <input v-model="newTarget.hostname" type="text" placeholder="cyberlab-lab-dvwa-xxxx" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200" />
          </div>
          <div>
            <label class="mb-1 block text-xs text-slate-500">IP address</label>
            <input v-model="newTarget.ip_address" type="text" placeholder="10.0.0.5" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200" />
          </div>
          <div>
            <label class="mb-1 block text-xs text-slate-500">URL</label>
            <input v-model="newTarget.url" type="text" placeholder="http://juice-shop:3000" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200" />
          </div>
          <div>
            <label class="mb-1 block text-xs text-slate-500">Type</label>
            <select v-model="newTarget.target_type" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200">
              <option v-for="t in ['HOST', 'IP', 'DOMAIN', 'URL', 'CONTAINER', 'LAB', 'OTHER']" :key="t" :value="t">{{ t }}</option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-xs text-slate-500">Authorization (leave blank to auto-detect)</label>
            <select v-model="newTarget.authorization_status" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200">
              <option value="">Auto-detect</option>
              <option v-for="a in ['LAB', 'AUTHORIZED', 'LOCAL', 'UNKNOWN']" :key="a" :value="a">{{ a }}</option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-xs text-slate-500">Description</label>
            <input v-model="newTarget.description" type="text" class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200" />
          </div>
        </div>
        <p v-if="createError" class="mt-2 text-sm text-red-400">{{ createError }}</p>
        <button
          class="mt-3 rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          :disabled="creating || !newTarget.project_id || !newTarget.name"
          @click="createTarget"
        >
          {{ creating ? "Creating…" : "Create" }}
        </button>
      </div>

      <p v-if="loading" class="text-sm text-slate-600">Loading…</p>
      <p v-else-if="targets.length === 0" class="text-sm text-slate-600">
        No targets yet. Click "+ New Target" to register one.
      </p>

      <div v-else class="overflow-hidden rounded-lg border border-slate-800">
        <table class="w-full text-sm">
          <thead class="bg-slate-900/60 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th class="px-4 py-2">Name</th>
              <th class="px-4 py-2">Address</th>
              <th class="px-4 py-2">Type</th>
              <th class="px-4 py-2">Project</th>
              <th class="px-4 py-2">Authorization</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-800">
            <tr
              v-for="target in targets"
              :key="target.id"
              class="cursor-pointer hover:bg-slate-900/40"
              @click="router.push(`/targets/${target.id}`)"
            >
              <td class="px-4 py-2 font-medium text-slate-200">{{ target.name }}</td>
              <td class="px-4 py-2 text-slate-400">{{ address(target) }}</td>
              <td class="px-4 py-2 text-slate-500">{{ target.target_type }}</td>
              <td class="px-4 py-2 text-slate-500">{{ projectName(target.project_id) }}</td>
              <td class="px-4 py-2">
                <span class="rounded px-1.5 py-0.5 text-xs" :class="authColor[target.authorization_status]">
                  {{ target.authorization_status }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
