<script setup lang="ts">
import { SEVERITY_COLORS } from "~/constants/colors";
import type { Asset } from "~/types/asset";
import type { ProjectAISummary } from "~/types/project-ai-summary";

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

interface Job {
  id: string;
  tool: string;
  target: string;
  status: string;
  created_at: string;
  finished_at: string | null;
  evidence_sha256: string | null;
}

interface Finding {
  id: string;
  job_id: string;
  title: string;
  severity: string;
  source_tool: string;
  first_seen: string;
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
const { listAssets } = useAssets();
const { getProjectSummary, regenerateProjectSummary } = useProjectMemory();
const projectId = route.params.id as string;

const project = ref<ProjectSummary | null>(null);
const assets = ref<Asset[]>([]);
const jobs = ref<Job[]>([]);
const findings = ref<Finding[]>([]);
const labs = ref<LabInstance[]>([]);
const reports = ref<ReportMeta[]>([]);
const loading = ref(true);
const tab = ref<"overview" | "assets" | "scans" | "findings" | "timeline" | "labs" | "ai" | "reports" | "graph">(
  "overview",
);

async function loadAll() {
  loading.value = true;
  try {
    const [proj, assetList, jbs, fnds, allReports] = await Promise.all([
      apiFetch<ProjectSummary>(`/api/projects/${projectId}`),
      listAssets({ project_id: projectId }),
      apiFetch<Job[]>(`/api/jobs?project_id=${projectId}&limit=100`),
      apiFetch<Finding[]>(`/api/findings?project_id=${projectId}&limit=200`),
      apiFetch<ReportMeta[]>("/api/reports"),
    ]);
    project.value = proj;
    assets.value = assetList;
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

function address(t: Asset) {
  return t.url || t.hostname || t.ip_address || "—";
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString();
}

// --- AI Memory (Phase 19) ---
// Lazy-loaded only when the ai tab is first opened -- the summary is
// stored, not recalculated on every question, so there's no reason to
// fetch it on every project page load regardless of which tab is active.
const summary = ref<ProjectAISummary | null>(null);
const summaryLoading = ref(false);
const summaryLoaded = ref(false);
const regenerating = ref(false);
const memoryError = ref("");

async function loadSummary() {
  if (summaryLoaded.value) return;
  summaryLoading.value = true;
  memoryError.value = "";
  try {
    summary.value = await getProjectSummary(projectId);
  } catch (err: any) {
    if (err?.response?.status !== 404) {
      memoryError.value = err?.data?.detail || "Failed to load the project summary";
    }
    // 404 means no summary generated yet -- not an error, just an empty state.
  } finally {
    summaryLoading.value = false;
    summaryLoaded.value = true;
  }
}

async function onRegenerateSummary() {
  regenerating.value = true;
  memoryError.value = "";
  try {
    summary.value = await regenerateProjectSummary(projectId);
  } catch (err: any) {
    memoryError.value = err?.data?.detail || "Failed to regenerate the project summary";
  } finally {
    regenerating.value = false;
  }
}

watch(tab, (value) => {
  if (value === "ai") loadSummary();
});

// --- Ask about this project (Phase 19) ---
// Single-turn, no persisted conversation history -- the AI Memory context
// (stored summary + recent AssetChangeEvents) is what grounds the answer,
// not a chat log. See backend/app/api/routes/ai.py::chat's project_id handling.
const question = ref("");
const answer = ref("");
const asking = ref(false);
const askError = ref("");

async function askAboutProject() {
  const message = question.value.trim();
  if (!message || asking.value) return;
  asking.value = true;
  askError.value = "";
  answer.value = "";
  try {
    const res = await apiFetch<{ reply: string }>("/api/ai/chat", {
      method: "POST",
      body: { message, project_id: projectId },
    });
    answer.value = res.reply;
  } catch (err: any) {
    askError.value = err?.data?.detail || "Failed to get an answer";
  } finally {
    asking.value = false;
  }
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
          v-for="t in ['overview', 'assets', 'scans', 'findings', 'timeline', 'labs', 'ai', 'reports', 'graph']"
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
          <p class="text-xs text-slate-500">Assets</p>
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

      <!-- Assets -->
      <div v-else-if="tab === 'assets'" class="px-8 py-6">
        <div class="mb-3 flex justify-end">
          <NuxtLink to="/assets" class="text-xs text-emerald-400 hover:underline">Manage assets →</NuxtLink>
        </div>
        <p v-if="assets.length === 0" class="text-sm text-slate-600">No assets in this project yet.</p>
        <div v-else class="space-y-2">
          <NuxtLink
            v-for="t in assets"
            :key="t.id"
            :to="`/assets/${t.id}`"
            class="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/40 p-3 hover:bg-slate-900/70"
          >
            <div>
              <p class="text-sm font-medium text-slate-200">{{ t.name }}</p>
              <p class="text-xs text-slate-500">{{ address(t) }} · {{ t.type }}</p>
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
            <span class="rounded px-1.5 py-0.5 text-xs" :class="SEVERITY_COLORS[f.severity as keyof typeof SEVERITY_COLORS]">{{ f.severity }}</span>
            <span class="text-sm text-slate-200">{{ f.title }}</span>
            <span class="ml-auto text-xs text-slate-600">{{ f.source_tool }}</span>
          </NuxtLink>
        </div>
      </div>

      <!-- Evidence Timeline (Phase 20) -->
      <div v-else-if="tab === 'timeline'" class="px-8 py-6">
        <EvidenceTimeline :jobs="jobs" :findings="findings" />
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

      <!-- AI Memory (Phase 19) -->
      <div v-else-if="tab === 'ai'" class="grid grid-cols-1 gap-6 px-8 py-6 lg:grid-cols-2">
        <section class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
          <div class="mb-3 flex items-center justify-between">
            <h2 class="text-sm font-semibold text-slate-300">Project Summary</h2>
            <button
              class="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
              :disabled="regenerating"
              @click="onRegenerateSummary"
            >
              {{ regenerating ? "Regenerating…" : "Regenerate" }}
            </button>
          </div>
          <p class="mb-3 text-xs text-slate-500">
            Stored after scan activity, not recalculated on every visit — click Regenerate for the latest state.
          </p>

          <p v-if="memoryError" class="mb-2 text-sm text-red-400">{{ memoryError }}</p>
          <LoadingState v-if="summaryLoading" />
          <EmptyState v-else-if="summaryLoaded && !summary" message="No summary generated yet — run a scan, or click Regenerate." />
          <div v-else-if="summary" class="rounded-md border border-slate-800 bg-slate-950/50 p-3">
            <p class="whitespace-pre-wrap text-sm text-slate-300">{{ summary.summary }}</p>
            <p class="mt-2 text-xs text-slate-600">Generated {{ formatDate(summary.generated_at) }}</p>
          </div>
        </section>

        <section class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
          <h2 class="mb-3 text-sm font-semibold text-slate-300">Ask about this project</h2>
          <p class="mb-3 text-xs text-slate-500">
            Grounded in the stored summary and this project's most recent detected changes — e.g. "what changed
            since the last audit?" For general questions, use the
            <NuxtLink to="/ai" class="text-emerald-400 hover:underline">AI Assistant page →</NuxtLink>.
          </p>
          <form class="flex gap-2" @submit.prevent="askAboutProject">
            <input
              v-model="question"
              type="text"
              placeholder="What changed since the last audit?"
              class="flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600"
            />
            <button
              type="submit"
              class="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
              :disabled="asking || !question.trim()"
            >
              {{ asking ? "Asking…" : "Ask" }}
            </button>
          </form>
          <p v-if="askError" class="mt-2 text-sm text-red-400">{{ askError }}</p>
          <p v-if="answer" class="mt-3 whitespace-pre-wrap rounded-md border border-slate-800 bg-slate-950/50 p-3 text-sm text-slate-300">
            {{ answer }}
          </p>
        </section>
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

      <div v-else-if="tab === 'graph'" class="px-8 py-6">
        <SecurityGraph :base-url="`/api/graph/projects/${projectId}`" />
      </div>
    </div>
  </div>
</template>
