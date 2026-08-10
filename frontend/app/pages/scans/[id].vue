<script setup lang="ts">
interface AnalysisResult {
  risk: "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  summary: string;
  findings: string[];
  recommendations: string[];
  next_steps: string[];
  raw_response: string | null;
}

interface Job {
  id: string;
  tool: string;
  target: string;
  params: Record<string, unknown>;
  status: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  stdout: string | null;
  stderr: string | null;
  exit_code: number | null;
  result: unknown;
  error: string | null;
  ai_analysis: AnalysisResult | null;
}

const route = useRoute();
const { apiFetch } = useApi();
const jobId = route.params.id as string;

const job = ref<Job | null>(null);
const loading = ref(true);
const cancelling = ref(false);
const analyzing = ref(false);
const analyzeError = ref("");

const riskColor: Record<string, string> = {
  INFO: "bg-slate-700/50 text-slate-300",
  LOW: "bg-emerald-500/15 text-emerald-400",
  MEDIUM: "bg-amber-500/15 text-amber-400",
  HIGH: "bg-orange-500/15 text-orange-400",
  CRITICAL: "bg-red-500/15 text-red-400",
};

async function analyzeWithAI() {
  analyzing.value = true;
  analyzeError.value = "";
  try {
    const analysis = await apiFetch<AnalysisResult>(`/api/ai/analyze/${jobId}`, { method: "POST" });
    if (job.value) job.value.ai_analysis = analysis;
  } catch (err: any) {
    analyzeError.value = err?.data?.detail || "AI analysis failed";
  } finally {
    analyzing.value = false;
  }
}

async function loadJob() {
  try {
    job.value = await apiFetch<Job>(`/api/jobs/${jobId}`);
  } finally {
    loading.value = false;
  }
}

async function cancelJob() {
  cancelling.value = true;
  try {
    job.value = await apiFetch<Job>(`/api/jobs/${jobId}/cancel`, { method: "POST" });
  } finally {
    cancelling.value = false;
  }
}

const isTerminal = computed(() =>
  job.value ? ["SUCCESS", "FAILED", "CANCELLED"].includes(job.value.status) : false
);

useJobSocket(jobId, (update) => {
  if (!job.value) return;
  Object.assign(job.value, update);
  if (update.status && ["SUCCESS", "FAILED"].includes(update.status)) {
    loadJob();
  }
});

onMounted(loadJob);
</script>

<template>
  <div>
    <PageHeader :title="job ? `${job.tool} → ${job.target}` : 'Scan'" subtitle="Live job status" />

    <div v-if="loading" class="px-8 py-6 text-sm text-slate-600">Loading…</div>

    <div v-else-if="job" class="space-y-6 px-8 py-6">
      <div class="flex items-center gap-4">
        <JobStatusBadge :status="job.status" />
        <span v-if="job.exit_code !== null" class="text-xs text-slate-500">exit code {{ job.exit_code }}</span>
        <button
          v-if="!isTerminal"
          class="ml-auto rounded-md border border-red-800 px-3 py-1 text-xs font-medium text-red-400 hover:bg-red-900/30"
          :disabled="cancelling"
          @click="cancelJob"
        >
          {{ cancelling ? "Cancelling…" : "Cancel" }}
        </button>
      </div>

      <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
          <p class="text-xs text-slate-500">Created</p>
          <p class="text-sm text-slate-300">{{ job.created_at ? new Date(job.created_at).toLocaleString() : "—" }}</p>
        </div>
        <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
          <p class="text-xs text-slate-500">Started</p>
          <p class="text-sm text-slate-300">{{ job.started_at ? new Date(job.started_at).toLocaleString() : "—" }}</p>
        </div>
        <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
          <p class="text-xs text-slate-500">Finished</p>
          <p class="text-sm text-slate-300">{{ job.finished_at ? new Date(job.finished_at).toLocaleString() : "—" }}</p>
        </div>
      </div>

      <div v-if="job.error" class="rounded-lg border border-red-900 bg-red-950/30 p-3 text-sm text-red-400">
        {{ job.error }}
      </div>

      <div v-if="isTerminal" class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <div class="mb-2 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-slate-300">AI analysis</h2>
          <button
            class="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
            :disabled="analyzing"
            @click="analyzeWithAI"
          >
            {{ analyzing ? "Analyzing…" : job.ai_analysis ? "Re-analyze" : "Analyze with AI" }}
          </button>
        </div>
        <p v-if="analyzeError" class="text-sm text-red-400">{{ analyzeError }}</p>
        <p v-else-if="!job.ai_analysis" class="text-sm text-slate-600">Not analyzed yet.</p>
        <div v-else class="space-y-3">
          <div class="flex items-center gap-2">
            <span class="rounded px-2 py-0.5 text-xs font-medium" :class="riskColor[job.ai_analysis.risk]">
              {{ job.ai_analysis.risk }}
            </span>
            <p class="text-sm text-slate-300">{{ job.ai_analysis.summary }}</p>
          </div>
          <div v-if="job.ai_analysis.findings.length" class="text-sm">
            <p class="mb-1 text-xs font-medium text-slate-500">Findings</p>
            <ul class="list-inside list-disc space-y-0.5 text-slate-400">
              <li v-for="(f, i) in job.ai_analysis.findings" :key="i">{{ f }}</li>
            </ul>
          </div>
          <div v-if="job.ai_analysis.recommendations.length" class="text-sm">
            <p class="mb-1 text-xs font-medium text-slate-500">Recommendations</p>
            <ul class="list-inside list-disc space-y-0.5 text-slate-400">
              <li v-for="(r, i) in job.ai_analysis.recommendations" :key="i">{{ r }}</li>
            </ul>
          </div>
          <div v-if="job.ai_analysis.next_steps.length" class="text-sm">
            <p class="mb-1 text-xs font-medium text-slate-500">Suggested next steps</p>
            <ul class="list-inside list-disc space-y-0.5 text-slate-400">
              <li v-for="(s, i) in job.ai_analysis.next_steps" :key="i">{{ s }}</li>
            </ul>
          </div>
        </div>
      </div>

      <div v-if="job.result" class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-2 text-sm font-semibold text-slate-300">Parsed result</h2>
        <pre class="overflow-x-auto whitespace-pre-wrap break-words text-xs text-slate-400">{{ JSON.stringify(job.result, null, 2) }}</pre>
      </div>

      <div v-if="job.stdout" class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-2 text-sm font-semibold text-slate-300">stdout</h2>
        <pre class="max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-500">{{ job.stdout }}</pre>
      </div>

      <div v-if="job.stderr" class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-2 text-sm font-semibold text-slate-300">stderr</h2>
        <pre class="max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs text-red-400/80">{{ job.stderr }}</pre>
      </div>
    </div>
  </div>
</template>
