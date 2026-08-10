<script setup lang="ts">
interface Finding {
  id: string;
  job_id: string;
  target: string;
  source_tool: string;
  title: string;
  description: string;
  severity: "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  confidence: string;
  recommendation: string | null;
  created_at: string;
}

const { apiUrl } = useApi();

const findings = ref<Finding[]>([]);
const loading = ref(true);
const severityFilter = ref<string>("");

const severityColor: Record<string, string> = {
  INFO: "bg-slate-700/50 text-slate-300",
  LOW: "bg-emerald-500/15 text-emerald-400",
  MEDIUM: "bg-amber-500/15 text-amber-400",
  HIGH: "bg-orange-500/15 text-orange-400",
  CRITICAL: "bg-red-500/15 text-red-400",
};

async function loadFindings() {
  loading.value = true;
  try {
    const query = severityFilter.value ? `?severity=${severityFilter.value}&limit=200` : "?limit=200";
    findings.value = await $fetch<Finding[]>(apiUrl(`/api/findings${query}`));
  } finally {
    loading.value = false;
  }
}

watch(severityFilter, loadFindings);
onMounted(loadFindings);
</script>

<template>
  <div>
    <PageHeader title="Findings" subtitle="Normalized results extracted automatically from tool scans" />

    <div class="px-8 py-6">
      <div class="mb-4 flex items-center gap-2">
        <label class="text-xs text-slate-500">Severity</label>
        <select
          v-model="severityFilter"
          class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200"
        >
          <option value="">All</option>
          <option value="INFO">INFO</option>
          <option value="LOW">LOW</option>
          <option value="MEDIUM">MEDIUM</option>
          <option value="HIGH">HIGH</option>
          <option value="CRITICAL">CRITICAL</option>
        </select>
      </div>

      <p v-if="loading" class="text-sm text-slate-600">Loading…</p>
      <p v-else-if="findings.length === 0" class="text-sm text-slate-600">
        No findings yet — findings are extracted automatically when a scan completes successfully.
      </p>

      <div v-else class="space-y-2">
        <div
          v-for="finding in findings"
          :key="finding.id"
          class="rounded-lg border border-slate-800 bg-slate-900/40 p-4"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="flex items-center gap-2">
                <span class="rounded px-2 py-0.5 text-xs font-medium" :class="severityColor[finding.severity]">
                  {{ finding.severity }}
                </span>
                <span class="font-medium text-slate-200">{{ finding.title }}</span>
              </div>
              <p class="mt-1 text-xs text-slate-500">
                Target: <code class="text-slate-400">{{ finding.target }}</code> · Source: {{ finding.source_tool }} ·
                Confidence: {{ finding.confidence }}
              </p>
              <p class="mt-2 text-sm text-slate-400">{{ finding.description }}</p>
              <p v-if="finding.recommendation" class="mt-2 rounded bg-emerald-500/5 px-2 py-1 text-xs text-emerald-400">
                {{ finding.recommendation }}
              </p>
            </div>
            <NuxtLink :to="`/scans/${finding.job_id}`" class="shrink-0 text-xs text-emerald-400 hover:underline">
              View scan
            </NuxtLink>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
