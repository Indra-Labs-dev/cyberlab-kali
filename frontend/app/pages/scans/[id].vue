<script setup lang="ts">
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
}

const route = useRoute();
const { apiUrl } = useApi();
const jobId = route.params.id as string;

const job = ref<Job | null>(null);
const loading = ref(true);
const cancelling = ref(false);

async function loadJob() {
  try {
    job.value = await $fetch<Job>(apiUrl(`/api/jobs/${jobId}`));
  } finally {
    loading.value = false;
  }
}

async function cancelJob() {
  cancelling.value = true;
  try {
    job.value = await $fetch<Job>(apiUrl(`/api/jobs/${jobId}/cancel`), { method: "POST" });
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
