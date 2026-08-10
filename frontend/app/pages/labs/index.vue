<script setup lang="ts">
interface LabDefinition {
  name: string;
  display_name: string;
  description: string;
  image: string;
  internal_port: number;
}

interface LabInstance {
  id: string;
  definition: string;
  display_name: string;
  status: string;
  container_name: string;
  host_port: number | null;
  internal_port: number | null;
  network: string | null;
  created_at: string | null;
}

const { apiFetch } = useApi();

const definitions = ref<LabDefinition[]>([]);
const labs = ref<LabInstance[]>([]);
const loading = ref(true);
const busy = ref<string | null>(null); // lab id currently being acted on, or "create:<definition>"

async function loadAll() {
  loading.value = true;
  try {
    [definitions.value, labs.value] = await Promise.all([
      apiFetch<LabDefinition[]>("/api/labs/definitions"),
      apiFetch<LabInstance[]>("/api/labs"),
    ]);
  } finally {
    loading.value = false;
  }
}

async function createLab(definitionName: string) {
  busy.value = `create:${definitionName}`;
  try {
    await apiFetch(`/api/labs?definition=${definitionName}`, { method: "POST" });
    await loadAll();
  } finally {
    busy.value = null;
  }
}

async function labAction(labId: string, action: "start" | "stop" | "reset") {
  busy.value = labId;
  try {
    await apiFetch(`/api/labs/${labId}/${action}`, { method: "POST" });
    await loadAll();
  } finally {
    busy.value = null;
  }
}

async function deleteLab(labId: string) {
  busy.value = labId;
  try {
    await apiFetch(`/api/labs/${labId}`, { method: "DELETE" });
    await loadAll();
  } finally {
    busy.value = null;
  }
}

onMounted(loadAll);
</script>

<template>
  <div>
    <PageHeader title="Labs" subtitle="Isolated Docker lab environments for hands-on practice" />

    <div class="space-y-8 px-8 py-6">
      <section>
        <h2 class="mb-3 text-sm font-semibold text-slate-300">Running labs</h2>
        <p v-if="loading" class="text-sm text-slate-600">Loading…</p>
        <p v-else-if="labs.length === 0" class="text-sm text-slate-600">
          No labs running. Launch one from the catalog below.
        </p>
        <div v-else class="space-y-2">
          <div
            v-for="lab in labs"
            :key="lab.id"
            class="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/40 p-4"
          >
            <div>
              <div class="flex items-center gap-2">
                <span class="font-medium text-slate-200">{{ lab.display_name }}</span>
                <span
                  class="rounded px-1.5 py-0.5 text-xs"
                  :class="lab.status === 'running' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-slate-700/50 text-slate-400'"
                >
                  {{ lab.status }}
                </span>
              </div>
              <p class="mt-1 text-xs text-slate-500">
                <a
                  v-if="lab.status === 'running' && lab.host_port"
                  :href="`http://localhost:${lab.host_port}`"
                  target="_blank"
                  class="text-emerald-400 hover:underline"
                >
                  http://localhost:{{ lab.host_port }}
                </a>
                <span v-else>not published — start the lab to get a URL</span>
                <span class="ml-2 text-slate-600">· {{ lab.container_name }}</span>
              </p>
            </div>
            <div class="flex gap-2">
              <button
                v-if="lab.status !== 'running'"
                class="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800"
                :disabled="busy === lab.id"
                @click="labAction(lab.id, 'start')"
              >
                Start
              </button>
              <button
                v-else
                class="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800"
                :disabled="busy === lab.id"
                @click="labAction(lab.id, 'stop')"
              >
                Stop
              </button>
              <button
                class="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800"
                :disabled="busy === lab.id"
                @click="labAction(lab.id, 'reset')"
              >
                Reset
              </button>
              <button
                class="rounded-md border border-red-900 px-2.5 py-1 text-xs text-red-400 hover:bg-red-900/30"
                :disabled="busy === lab.id"
                @click="deleteLab(lab.id)"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      </section>

      <section>
        <h2 class="mb-3 text-sm font-semibold text-slate-300">Catalog</h2>
        <div class="space-y-2">
          <div
            v-for="def in definitions"
            :key="def.name"
            class="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/40 p-4"
          >
            <div>
              <p class="font-medium text-slate-200">{{ def.display_name }}</p>
              <p class="mt-1 max-w-2xl text-xs text-slate-500">{{ def.description }}</p>
              <p class="mt-1 text-xs text-slate-600">{{ def.image }}</p>
            </div>
            <button
              class="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
              :disabled="busy === `create:${def.name}`"
              @click="createLab(def.name)"
            >
              {{ busy === `create:${def.name}` ? "Launching…" : "Launch" }}
            </button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
