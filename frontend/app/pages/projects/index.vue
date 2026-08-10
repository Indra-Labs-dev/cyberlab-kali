<script setup lang="ts">
interface ProjectSummary {
  id: string;
  name: string;
  description: string | null;
  status: "ACTIVE" | "ARCHIVED";
  created_at: string;
  updated_at: string;
  target_count: number;
  job_count: number;
  finding_count: number;
  lab_count: number;
}

const { apiFetch } = useApi();
const router = useRouter();

const projects = ref<ProjectSummary[]>([]);
const loading = ref(true);
const search = ref("");
const statusFilter = ref<"" | "ACTIVE" | "ARCHIVED">("");

const showCreateForm = ref(false);
const newName = ref("");
const newDescription = ref("");
const creating = ref(false);
const createError = ref("");

const busy = ref<string | null>(null);

async function loadProjects() {
  loading.value = true;
  try {
    const params = new URLSearchParams();
    if (search.value) params.set("search", search.value);
    if (statusFilter.value) params.set("status", statusFilter.value);
    const query = params.toString() ? `?${params.toString()}` : "";
    projects.value = await apiFetch<ProjectSummary[]>(`/api/projects${query}`);
  } finally {
    loading.value = false;
  }
}

let searchDebounce: ReturnType<typeof setTimeout> | undefined;
watch(search, () => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(loadProjects, 300);
});
watch(statusFilter, loadProjects);

async function createProject() {
  if (!newName.value.trim()) return;
  creating.value = true;
  createError.value = "";
  try {
    const project = await apiFetch<{ id: string }>("/api/projects", {
      method: "POST",
      body: { name: newName.value, description: newDescription.value || null },
    });
    newName.value = "";
    newDescription.value = "";
    showCreateForm.value = false;
    router.push(`/projects/${project.id}`);
  } catch (err: any) {
    createError.value = err?.data?.detail || "Failed to create project";
  } finally {
    creating.value = false;
  }
}

async function toggleArchive(project: ProjectSummary) {
  busy.value = project.id;
  try {
    await apiFetch(`/api/projects/${project.id}`, {
      method: "PATCH",
      body: { status: project.status === "ACTIVE" ? "ARCHIVED" : "ACTIVE" },
    });
    await loadProjects();
  } finally {
    busy.value = null;
  }
}

async function deleteProject(project: ProjectSummary) {
  busy.value = project.id;
  try {
    await apiFetch(`/api/projects/${project.id}`, { method: "DELETE" });
    await loadProjects();
  } catch (err: any) {
    alert(err?.data?.detail || "Failed to delete project");
  } finally {
    busy.value = null;
  }
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString();
}

onMounted(loadProjects);
</script>

<template>
  <div>
    <PageHeader title="Projects" subtitle="Group targets, scans, findings, and reports into independent workspaces" />

    <div class="px-8 py-6">
      <div class="mb-4 flex flex-wrap items-center gap-2">
        <input
          v-model="search"
          type="text"
          placeholder="Search projects…"
          class="w-64 rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-600"
        />
        <select
          v-model="statusFilter"
          class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200"
        >
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="ARCHIVED">Archived</option>
        </select>
        <button
          class="ml-auto rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500"
          @click="showCreateForm = !showCreateForm"
        >
          + New Project
        </button>
      </div>

      <div v-if="showCreateForm" class="mb-6 rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs text-slate-500">Name</label>
            <input
              v-model="newName"
              type="text"
              placeholder="e.g. Web Security Lab"
              class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs text-slate-500">Description (optional)</label>
            <input
              v-model="newDescription"
              type="text"
              class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200"
            />
          </div>
        </div>
        <p v-if="createError" class="mt-2 text-sm text-red-400">{{ createError }}</p>
        <button
          class="mt-3 rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          :disabled="creating || !newName.trim()"
          @click="createProject"
        >
          {{ creating ? "Creating…" : "Create" }}
        </button>
      </div>

      <p v-if="loading" class="text-sm text-slate-600">Loading…</p>
      <p v-else-if="projects.length === 0" class="text-sm text-slate-600">
        No projects yet. Click "+ New Project" to create one.
      </p>

      <div v-else class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div
          v-for="project in projects"
          :key="project.id"
          class="rounded-lg border border-slate-800 bg-slate-900/40 p-4"
        >
          <div class="flex items-start justify-between gap-2">
            <NuxtLink :to="`/projects/${project.id}`" class="font-medium text-slate-200 hover:underline">
              {{ project.name }}
            </NuxtLink>
            <span
              class="shrink-0 rounded px-1.5 py-0.5 text-xs"
              :class="project.status === 'ACTIVE' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-slate-700/50 text-slate-400'"
            >
              {{ project.status }}
            </span>
          </div>
          <p v-if="project.description" class="mt-1 text-xs text-slate-500">{{ project.description }}</p>

          <div class="mt-3 grid grid-cols-4 gap-1 text-center text-xs text-slate-500">
            <div><span class="block text-sm font-medium text-slate-300">{{ project.target_count }}</span>targets</div>
            <div><span class="block text-sm font-medium text-slate-300">{{ project.job_count }}</span>jobs</div>
            <div><span class="block text-sm font-medium text-slate-300">{{ project.finding_count }}</span>findings</div>
            <div><span class="block text-sm font-medium text-slate-300">{{ project.lab_count }}</span>labs</div>
          </div>

          <p class="mt-3 text-xs text-slate-600">Updated {{ formatDate(project.updated_at) }}</p>

          <div class="mt-3 flex gap-2">
            <button
              class="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
              :disabled="busy === project.id"
              @click="toggleArchive(project)"
            >
              {{ project.status === "ACTIVE" ? "Archive" : "Reactivate" }}
            </button>
            <button
              class="rounded-md border border-red-900 px-2 py-1 text-xs text-red-400 hover:bg-red-900/30 disabled:opacity-50"
              :disabled="busy === project.id"
              @click="deleteProject(project)"
            >
              Delete
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
