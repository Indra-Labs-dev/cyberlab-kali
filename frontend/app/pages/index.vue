<script setup lang="ts">
interface Job {
  id: string;
  tool: string;
  target: string;
  status: string;
  created_at: string;
}

interface ToolDef {
  name: string;
  category: string;
  ai_allowed: boolean;
}

const { apiFetch } = useApi();

const apiStatus = ref<"checking" | "ok" | "error">("checking");
const dbStatus = ref<"checking" | "ok" | "error">("checking");
const kaliStatus = ref<"checking" | "ok" | "unreachable">("checking");
const kaliDetail = ref<string>();
const aiStatus = ref<"checking" | "ok" | "unreachable">("checking");
const aiDetail = ref<string>();

const recentJobs = ref<Job[]>([]);
const activeJobs = computed(() => recentJobs.value.filter((j) => j.status === "QUEUED" || j.status === "RUNNING"));

const toolStats = reactive({ total: 0, installed: 0, aiEnabled: 0, byCategory: {} as Record<string, number> });

async function loadToolStats() {
  try {
    const [tools, health] = await Promise.all([
      apiFetch<ToolDef[]>("/api/tools"),
      apiFetch<{ name: string; status: string }[]>("/api/tools/health"),
    ]);
    const readyNames = new Set(health.filter((h) => h.status === "ready").map((h) => h.name));
    toolStats.total = tools.length;
    toolStats.installed = tools.filter((t) => readyNames.has(t.name)).length;
    toolStats.aiEnabled = tools.filter((t) => t.ai_allowed).length;
    const byCategory: Record<string, number> = {};
    tools.forEach((t) => {
      byCategory[t.category] = (byCategory[t.category] || 0) + 1;
    });
    toolStats.byCategory = byCategory;
  } catch {
    // Leave defaults (0) -- the tile below only renders once total > 0.
  }
}

async function loadStatus() {
  try {
    await apiFetch("/api/health");
    apiStatus.value = "ok";
  } catch {
    apiStatus.value = "error";
  }
  try {
    await apiFetch("/api/health/db");
    dbStatus.value = "ok";
  } catch {
    dbStatus.value = "error";
  }
  try {
    const res = await apiFetch<{ status: string; tools_available?: string[] }>("/api/health/kali");
    kaliStatus.value = res.status === "ok" ? "ok" : "unreachable";
    kaliDetail.value = res.tools_available?.join(", ");
  } catch {
    kaliStatus.value = "unreachable";
  }
  try {
    const res = await apiFetch<{ status: string; models?: string[] }>("/api/health/ollama");
    aiStatus.value = res.status === "ok" ? "ok" : "unreachable";
    aiDetail.value = res.models?.join(", ");
  } catch {
    aiStatus.value = "unreachable";
  }
}

async function loadJobs() {
  try {
    recentJobs.value = await apiFetch<Job[]>("/api/jobs?limit=8");
  } catch {
    recentJobs.value = [];
  }
}

onMounted(() => {
  loadStatus();
  loadJobs();
  loadToolStats();
});
</script>

<template>
  <div>
    <PageHeader title="Dashboard" subtitle="System status and recent activity" />

    <div class="grid grid-cols-2 gap-4 px-8 pt-6 sm:grid-cols-4">
      <StatusTile label="API" :status="apiStatus" />
      <StatusTile label="Database" :status="dbStatus" />
      <StatusTile label="Kali" :status="kaliStatus" :detail="kaliDetail" />
      <StatusTile label="AI (Ollama)" :status="aiStatus" :detail="aiDetail" />
    </div>

    <div v-if="toolStats.total > 0" class="px-8 pt-6">
      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-slate-300">Tool Arsenal</h2>
          <NuxtLink to="/tools" class="text-xs text-emerald-400 hover:underline">Open Tools</NuxtLink>
        </div>
        <div class="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <div class="text-lg font-semibold text-slate-100">{{ toolStats.total }}</div>
            <div class="text-xs text-slate-500">Tools</div>
          </div>
          <div>
            <div class="text-lg font-semibold text-emerald-400">{{ toolStats.installed }}</div>
            <div class="text-xs text-slate-500">Installed</div>
          </div>
          <div>
            <div class="text-lg font-semibold text-cyan-400">{{ toolStats.aiEnabled }}</div>
            <div class="text-xs text-slate-500">AI-enabled</div>
          </div>
          <div>
            <div class="text-lg font-semibold text-slate-400">{{ toolStats.total - toolStats.aiEnabled }}</div>
            <div class="text-xs text-slate-500">Manual-only</div>
          </div>
        </div>
        <div class="flex flex-wrap gap-1.5 text-xs text-slate-500">
          <span v-for="(count, category) in toolStats.byCategory" :key="category" class="rounded bg-slate-800/60 px-1.5 py-0.5">
            {{ category }}: {{ count }}
          </span>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 gap-6 px-8 py-6 lg:grid-cols-2">
      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-slate-300">Active jobs</h2>
          <span class="text-xs text-slate-600">{{ activeJobs.length }}</span>
        </div>
        <p v-if="activeJobs.length === 0" class="text-sm text-slate-600">No job currently running.</p>
        <ul v-else class="space-y-2">
          <li
            v-for="job in activeJobs"
            :key="job.id"
            class="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/50 px-3 py-2"
          >
            <div class="text-sm">
              <span class="font-medium text-slate-200">{{ job.tool }}</span>
              <span class="ml-2 text-slate-500">{{ job.target }}</span>
            </div>
            <JobStatusBadge :status="job.status" />
          </li>
        </ul>
      </div>

      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-slate-300">Recent scans</h2>
          <NuxtLink to="/scans" class="text-xs text-emerald-400 hover:underline">View all</NuxtLink>
        </div>
        <p v-if="recentJobs.length === 0" class="text-sm text-slate-600">No scans yet — run one from the Tools page.</p>
        <ul v-else class="space-y-2">
          <li
            v-for="job in recentJobs.slice(0, 6)"
            :key="job.id"
            class="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/50 px-3 py-2"
          >
            <NuxtLink :to="`/scans/${job.id}`" class="text-sm hover:underline">
              <span class="font-medium text-slate-200">{{ job.tool }}</span>
              <span class="ml-2 text-slate-500">{{ job.target }}</span>
            </NuxtLink>
            <JobStatusBadge :status="job.status" />
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
