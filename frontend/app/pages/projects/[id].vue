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

interface Target {
  id: string;
  name: string;
  hostname: string | null;
  ip_address: string | null;
  url: string | null;
  target_type: string;
  authorization_status: string;
}

interface Job {
  id: string;
  tool: string;
  target: string;
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

interface LabInstance {
  id: string;
  display_name: string;
  status: string;
}

interface ReportMeta {
  id: string;
  title: string;
  format: string;
  job_ids: string[];
  created_at: string;
}

const route = useRoute();
const { apiFetch, downloadUrl } = useApi();
const projectId = route.params.id as string;

const project = ref<ProjectSummary | null>(null);
const targets = ref<Target[]>([]);
const jobs = ref<Job[]>([]);
const findings = ref<Finding[]>([]);
const labs = ref<LabInstance[]>([]);
const reports = ref<ReportMeta[]>([]);
const loading = ref(true);
const tab = ref<"overview" | "targets" | "scans" | "findings" | "labs" | "ai" | "reports">("overview");

const severityColor: Record<string, string> = {
  INFO: "bg-slate-700/50 text-slate-300",
  LOW: "bg-emerald-500/15 text-emerald-400",
  MEDIUM: "bg-amber-500/15 text-amber-400",
  HIGH: "bg-orange-500/15 text-orange-400",
  CRITICAL: "bg-red-500/15 text-red-400",
};

async function loadAll() {
  loading.value = true;
  try {
    const [proj, tgts, jbs, fnds, allReports] = await Promise.all([
      apiFetch<ProjectSummary>(`/api/projects/${projectId}`),
      apiFetch<Target[]>(`/api/projects/${projectId}/targets`),
      apiFetch<Job[]>(`/api/jobs?project_id=${projectId}&limit=100`),
      apiFetch<Finding[]>(`/api/findings?project_id=${projectId}&limit=200`),
      apiFetch<ReportMeta[]>("/api/reports"),
    ]);
    project.value = proj;
    targets.value = tgts;
    jobs.value = jbs;
    findings.value = fnds;
    const jobIdSet = new Set(jbs.map((j) => j.id));
    reports.value = allReports.filter((r) => r.job_ids.some((id) => jobIdSet.has(id)));
  } finally {
    loading.value = false;
  }
}

async function loadLabs() {
  labs.value = await apiFetch<LabInstance[]>("/api/labs");
}

function address(t: Target) {
  return t.url || t.hostname || t.ip_address || "—";
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString();
}

onMounted(async () => {
  await loadAll();
  await loadLabs();
});
</script>

<template>
  <div>
    <PageHeader :title="project?.name || 'Project'" :subtitle="project?.description || ''" />

    <div v-if="loading" class="px-8 py-6 text-sm text-slate-600">Loading…</div>

    <div v-else-if="project">
      <div class="flex gap-1 border-b border-slate-800 px-8">
        <button
          v-for="t in ['overview', 'targets', 'scans', 'findings', 'labs', 'ai', 'reports']"
          :key="t"
          class="border-b-2 px-3 py-2 text-sm capitalize transition-colors"
          :class="tab === t ? 'border-emerald-500 text-emerald-400' : 'border-transparent text-slate-500 hover:text-slate-300'"
          @click="tab = t as typeof tab"
        >
          {{ t }}
        </button>
      </div>

      <!-- Overview -->
      <div v-if="tab === 'overview'" class="grid grid-cols-2 gap-4 px-8 py-6 sm:grid-cols-4">
        <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
          <p class="text-2xl font-semibold text-slate-200">{{ project.target_count }}</p>
          <p class="text-xs text-slate-500">Targets</p>
        </div>
        <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
          <p class="text-2xl font-semibold text-slate-200">{{ project.job_count }}</p>
          <p class="text-xs text-slate-500">Jobs</p>
        </div>
        <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
          <p class="text-2xl font-semibold text-slate-200">{{ project.finding_count }}</p>
          <p class="text-xs text-slate-500">Findings</p>
        </div>
        <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
          <p class="text-2xl font-semibold text-slate-200">{{ project.lab_count }}</p>
          <p class="text-xs text-slate-500">Labs</p>
        </div>
        <div class="col-span-full text-xs text-slate-600">
          Status: {{ project.status }} · Created {{ formatDate(project.created_at) }} · Updated
          {{ formatDate(project.updated_at) }}
        </div>
      </div>

      <!-- Targets -->
      <div v-else-if="tab === 'targets'" class="px-8 py-6">
        <div class="mb-3 flex justify-end">
          <NuxtLink to="/targets" class="text-xs text-emerald-400 hover:underline">Manage targets →</NuxtLink>
        </div>
        <p v-if="targets.length === 0" class="text-sm text-slate-600">No targets in this project yet.</p>
        <div v-else class="space-y-2">
          <NuxtLink
            v-for="t in targets"
            :key="t.id"
            :to="`/targets/${t.id}`"
            class="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/40 p-3 hover:bg-slate-900/70"
          >
            <div>
              <p class="text-sm font-medium text-slate-200">{{ t.name }}</p>
              <p class="text-xs text-slate-500">{{ address(t) }} · {{ t.target_type }}</p>
            </div>
            <span class="rounded px-1.5 py-0.5 text-xs bg-slate-800 text-slate-400">{{ t.authorization_status }}</span>
          </NuxtLink>
        </div>
      </div>

      <!-- Scans -->
      <div v-else-if="tab === 'scans'" class="px-8 py-6">
        <p v-if="jobs.length === 0" class="text-sm text-slate-600">No scans in this project yet.</p>
        <div v-else class="space-y-2">
          <NuxtLink
            v-for="job in jobs"
            :key="job.id"
            :to="`/scans/${job.id}`"
            class="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/40 p-3 hover:bg-slate-900/70"
          >
            <div class="text-sm">
              <span class="font-medium text-slate-200">{{ job.tool }}</span>
              <span class="ml-2 text-slate-500">{{ job.target }}</span>
            </div>
            <JobStatusBadge :status="job.status" />
          </NuxtLink>
        </div>
      </div>

      <!-- Findings -->
      <div v-else-if="tab === 'findings'" class="px-8 py-6">
        <p v-if="findings.length === 0" class="text-sm text-slate-600">No findings in this project yet.</p>
        <div v-else class="space-y-2">
          <NuxtLink
            v-for="f in findings"
            :key="f.id"
            :to="`/scans/${f.job_id}`"
            class="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/40 p-3 hover:bg-slate-900/70"
          >
            <span class="rounded px-1.5 py-0.5 text-xs" :class="severityColor[f.severity]">{{ f.severity }}</span>
            <span class="text-sm text-slate-200">{{ f.title }}</span>
            <span class="ml-auto text-xs text-slate-600">{{ f.source_tool }}</span>
          </NuxtLink>
        </div>
      </div>

      <!-- Labs -->
      <div v-else-if="tab === 'labs'" class="px-8 py-6">
        <p class="mb-3 text-xs text-slate-600">
          Labs aren't scoped to a project yet — this shows all labs running in CyberLab.
          <NuxtLink to="/labs" class="text-emerald-400 hover:underline">Manage labs →</NuxtLink>
        </p>
        <p v-if="labs.length === 0" class="text-sm text-slate-600">No labs running.</p>
        <div v-else class="space-y-2">
          <div v-for="lab in labs" :key="lab.id" class="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/40 p-3">
            <span class="text-sm text-slate-200">{{ lab.display_name }}</span>
            <span class="rounded px-1.5 py-0.5 text-xs bg-slate-800 text-slate-400">{{ lab.status }}</span>
          </div>
        </div>
      </div>

      <!-- AI -->
      <div v-else-if="tab === 'ai'" class="px-8 py-6">
        <p class="text-sm text-slate-600">
          Ask the AI Assistant about this project's targets and findings from the
          <NuxtLink to="/ai" class="text-emerald-400 hover:underline">AI Assistant page →</NuxtLink>
        </p>
      </div>

      <!-- Reports -->
      <div v-else-if="tab === 'reports'" class="px-8 py-6">
        <div class="mb-3 flex justify-end">
          <NuxtLink to="/reports" class="text-xs text-emerald-400 hover:underline">Generate a report →</NuxtLink>
        </div>
        <p v-if="reports.length === 0" class="text-sm text-slate-600">No reports generated for this project's scans yet.</p>
        <div v-else class="space-y-2">
          <div v-for="r in reports" :key="r.id" class="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/40 p-3">
            <div>
              <p class="text-sm text-slate-200">{{ r.title }}</p>
              <p class="text-xs text-slate-500">{{ r.format.toUpperCase() }} · {{ formatDate(r.created_at) }}</p>
            </div>
            <a :href="downloadUrl(`/api/reports/${r.id}/download`)" class="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800">
              Download
            </a>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
