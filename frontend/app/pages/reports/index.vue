<script setup lang="ts">
interface Job {
  id: string;
  tool: string;
  target: string;
  status: string;
  created_at: string;
}

interface ReportMeta {
  id: string;
  title: string;
  format: string;
  job_ids: string[];
  created_at: string;
}

const { apiFetch, downloadUrl } = useApi();

const jobs = ref<Job[]>([]);
const reports = ref<ReportMeta[]>([]);
const selectedJobIds = ref<Set<string>>(new Set());
const title = ref("CyberLab Assessment Report");
const format = ref<"html" | "markdown" | "json" | "pdf">("html");
const generating = ref(false);
const generateError = ref("");
const loading = ref(true);

const completedJobs = computed(() => jobs.value.filter((j) => j.status === "SUCCESS" || j.status === "FAILED"));

async function loadAll() {
  loading.value = true;
  try {
    [jobs.value, reports.value] = await Promise.all([
      apiFetch<Job[]>("/api/jobs?limit=100"),
      apiFetch<ReportMeta[]>("/api/reports"),
    ]);
  } finally {
    loading.value = false;
  }
}

function toggleJob(id: string) {
  if (selectedJobIds.value.has(id)) selectedJobIds.value.delete(id);
  else selectedJobIds.value.add(id);
}

async function generateReport() {
  if (selectedJobIds.value.size === 0) return;
  generating.value = true;
  generateError.value = "";
  try {
    await apiFetch("/api/reports", {
      method: "POST",
      body: { title: title.value, job_ids: Array.from(selectedJobIds.value), format: format.value },
    });
    selectedJobIds.value = new Set();
    await loadAll();
  } catch (err: any) {
    generateError.value = err?.data?.detail || "Failed to generate report";
  } finally {
    generating.value = false;
  }
}

function reportDownloadUrl(reportId: string) {
  return downloadUrl(`/api/reports/${reportId}/download`);
}

onMounted(loadAll);
</script>

<template>
  <div>
    <PageHeader title="Reports" subtitle="Export scan results and findings" />

    <div class="grid grid-cols-1 gap-6 px-8 py-6 lg:grid-cols-2">
      <section class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-3 text-sm font-semibold text-slate-300">Generate a report</h2>

        <label class="mb-1 block text-xs text-slate-500">Title</label>
        <input
          v-model="title"
          type="text"
          class="mb-3 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200"
        />

        <label class="mb-1 block text-xs text-slate-500">Format</label>
        <select
          v-model="format"
          class="mb-3 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200"
        >
          <option value="html">HTML</option>
          <option value="markdown">Markdown</option>
          <option value="json">JSON</option>
          <option value="pdf">PDF</option>
        </select>

        <label class="mb-1 block text-xs text-slate-500">Scans to include</label>
        <div class="mb-3 max-h-56 space-y-1 overflow-y-auto rounded-md border border-slate-800 p-2">
          <p v-if="completedJobs.length === 0" class="text-xs text-slate-600">No completed scans yet.</p>
          <label
            v-for="job in completedJobs"
            :key="job.id"
            class="flex items-center gap-2 rounded px-1.5 py-1 text-sm text-slate-300 hover:bg-slate-800/50"
          >
            <input type="checkbox" :checked="selectedJobIds.has(job.id)" @change="toggleJob(job.id)" class="accent-emerald-500" />
            <span>{{ job.tool }} → {{ job.target }}</span>
            <JobStatusBadge :status="job.status" />
          </label>
        </div>

        <p v-if="generateError" class="mb-2 text-sm text-red-400">{{ generateError }}</p>
        <button
          class="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          :disabled="generating || selectedJobIds.size === 0"
          @click="generateReport"
        >
          {{ generating ? "Generating…" : "Generate report" }}
        </button>
      </section>

      <section class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-3 text-sm font-semibold text-slate-300">Past reports</h2>
        <p v-if="loading" class="text-sm text-slate-600">Loading…</p>
        <p v-else-if="reports.length === 0" class="text-sm text-slate-600">No reports generated yet.</p>
        <div v-else class="space-y-2">
          <div
            v-for="report in reports"
            :key="report.id"
            class="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/50 p-3"
          >
            <div>
              <p class="text-sm font-medium text-slate-200">{{ report.title }}</p>
              <p class="text-xs text-slate-500">
                {{ report.format.toUpperCase() }} · {{ report.job_ids.length }} scan(s) ·
                {{ new Date(report.created_at).toLocaleString() }}
              </p>
            </div>
            <a
              :href="reportDownloadUrl(report.id)"
              class="shrink-0 rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800"
            >
              Download
            </a>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
