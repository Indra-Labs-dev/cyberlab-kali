<script setup lang="ts">
interface Job {
  id: string;
  tool: string;
  target: string;
  status: string;
  created_at: string;
}

const { apiUrl } = useApi();

const apiStatus = ref<"checking" | "ok" | "error">("checking");
const dbStatus = ref<"checking" | "ok" | "error">("checking");
const kaliStatus = ref<"checking" | "ok" | "unreachable">("checking");
const kaliDetail = ref<string>();
const aiStatus = ref<"checking" | "ok" | "unreachable">("checking");
const aiDetail = ref<string>();

const recentJobs = ref<Job[]>([]);
const activeJobs = computed(() => recentJobs.value.filter((j) => j.status === "QUEUED" || j.status === "RUNNING"));

async function loadStatus() {
  try {
    await $fetch(apiUrl("/api/health"));
    apiStatus.value = "ok";
  } catch {
    apiStatus.value = "error";
  }
  try {
    await $fetch(apiUrl("/api/health/db"));
    dbStatus.value = "ok";
  } catch {
    dbStatus.value = "error";
  }
  try {
    const res = await $fetch<{ status: string; tools_available?: string[] }>(apiUrl("/api/health/kali"));
    kaliStatus.value = res.status === "ok" ? "ok" : "unreachable";
    kaliDetail.value = res.tools_available?.join(", ");
  } catch {
    kaliStatus.value = "unreachable";
  }
  try {
    const res = await $fetch<{ status: string; models?: string[] }>(apiUrl("/api/health/ollama"));
    aiStatus.value = res.status === "ok" ? "ok" : "unreachable";
    aiDetail.value = res.models?.join(", ");
  } catch {
    aiStatus.value = "unreachable";
  }
}

async function loadJobs() {
  try {
    recentJobs.value = await $fetch<Job[]>(apiUrl("/api/jobs?limit=8"));
  } catch {
    recentJobs.value = [];
  }
}

onMounted(() => {
  loadStatus();
  loadJobs();
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
