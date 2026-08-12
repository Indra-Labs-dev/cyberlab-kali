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
  evidence: Record<string, unknown>;
  recommendation: string | null;
  created_at: string;
  cve_ids: string[];
}

interface RiskInputs {
  severity: string;
  confidence: string;
  cvss_score: number | null;
  cvss_version: string | null;
  epss_score: number | null;
  epss_percentile: number | null;
  kev: boolean | null;
  asset_criticality: string | null;
}

interface RiskComponent {
  name: string;
  value: number;
  weight: number;
  available: boolean;
}

interface RiskDetail {
  finding_id: string;
  score: number;
  priority: "INFORMATIONAL" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  raw_score: number;
  criticality_multiplier: number;
  confidence_multiplier: number;
  inputs: RiskInputs;
  components: RiskComponent[];
  explanation: string[];
  calculated_at: string;
}

const route = useRoute();
const { apiFetch } = useApi();
const findingId = route.params.id as string;

const finding = ref<Finding | null>(null);
const risk = ref<RiskDetail | null>(null);
const loading = ref(true);
const loadError = ref("");

const priorityColor: Record<string, string> = {
  INFORMATIONAL: "bg-slate-700/50 text-slate-300",
  LOW: "bg-emerald-500/15 text-emerald-400",
  MEDIUM: "bg-amber-500/15 text-amber-400",
  HIGH: "bg-orange-500/15 text-orange-400",
  CRITICAL: "bg-red-500/15 text-red-400",
};
const severityColor: Record<string, string> = {
  INFO: "bg-slate-700/50 text-slate-300",
  LOW: "bg-emerald-500/15 text-emerald-400",
  MEDIUM: "bg-amber-500/15 text-amber-400",
  HIGH: "bg-orange-500/15 text-orange-400",
  CRITICAL: "bg-red-500/15 text-red-400",
};

function formatPercent(value: number | null): string {
  return value === null ? "N/A" : `${(value * 100).toFixed(1)}%`;
}

async function loadAll() {
  loading.value = true;
  loadError.value = "";
  try {
    const [f, r] = await Promise.all([
      apiFetch<Finding>(`/api/findings/${findingId}`),
      apiFetch<RiskDetail>(`/api/findings/${findingId}/risk`),
    ]);
    finding.value = f;
    risk.value = r;
  } catch (err: any) {
    loadError.value = err?.data?.detail || "Failed to load finding";
  } finally {
    loading.value = false;
  }
}

onMounted(loadAll);
</script>

<template>
  <div>
    <PageHeader :title="finding?.title || 'Finding'" :subtitle="finding ? `${finding.source_tool} · ${finding.target}` : ''" />

    <div v-if="loading" class="px-8 py-6 text-sm text-slate-600">Loading…</div>
    <div v-else-if="loadError" class="px-8 py-6 text-sm text-red-400">{{ loadError }}</div>

    <div v-else-if="finding && risk" class="space-y-6 px-8 py-6">
      <div class="flex flex-wrap items-center gap-3">
        <span class="rounded px-2 py-0.5 text-xs" :class="severityColor[finding.severity]">{{ finding.severity }}</span>
        <span class="text-xs text-slate-500">Confidence: {{ finding.confidence }}</span>
        <NuxtLink :to="`/scans/${finding.job_id}`" class="ml-auto text-xs text-emerald-400 hover:underline">
          View source scan →
        </NuxtLink>
      </div>

      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-5">
        <h2 class="mb-4 text-sm font-semibold text-slate-300">Risk Analysis</h2>
        <div class="flex flex-wrap items-center gap-6">
          <div class="flex items-center gap-3">
            <span
              class="flex h-16 w-16 items-center justify-center rounded-full text-2xl font-bold"
              :class="priorityColor[risk.priority]"
            >
              {{ risk.score }}
            </span>
            <div>
              <p class="text-xs text-slate-500">Risk Score / 100</p>
              <p class="text-lg font-semibold" :class="priorityColor[risk.priority].split(' ')[1]">{{ risk.priority }}</p>
            </div>
          </div>

          <div class="grid flex-1 grid-cols-2 gap-x-8 gap-y-2 text-sm sm:grid-cols-3">
            <div>
              <p class="text-xs text-slate-500">CVSS</p>
              <p class="text-slate-200">
                {{ risk.inputs.cvss_score !== null ? `${risk.inputs.cvss_score} (${risk.inputs.cvss_version || "?"})` : "N/A" }}
              </p>
            </div>
            <div>
              <p class="text-xs text-slate-500">EPSS</p>
              <p class="text-slate-200">{{ formatPercent(risk.inputs.epss_score) }}</p>
              <p v-if="risk.inputs.epss_percentile !== null" class="text-xs text-slate-500">
                Percentile {{ (risk.inputs.epss_percentile * 100).toFixed(1) }}
              </p>
            </div>
            <div>
              <p class="text-xs text-slate-500">CISA KEV</p>
              <p class="text-slate-200">
                {{ risk.inputs.kev === true ? "YES" : risk.inputs.kev === false ? "NO" : "UNKNOWN" }}
              </p>
            </div>
            <div>
              <p class="text-xs text-slate-500">Asset criticality</p>
              <p class="text-slate-200">{{ risk.inputs.asset_criticality || "unknown" }}</p>
            </div>
            <div>
              <p class="text-xs text-slate-500">Finding confidence</p>
              <p class="text-slate-200">{{ risk.inputs.confidence }}</p>
            </div>
            <div v-if="finding.cve_ids.length">
              <p class="text-xs text-slate-500">CVE</p>
              <p class="text-slate-200">{{ finding.cve_ids.join(", ") }}</p>
            </div>
          </div>
        </div>

        <div class="mt-5 border-t border-slate-800 pt-4">
          <p class="mb-2 text-xs font-medium text-slate-500">Why this score?</p>
          <ul class="space-y-1 text-sm text-slate-300">
            <li v-for="(line, i) in risk.explanation" :key="i" class="flex items-start gap-2">
              <span class="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-600"></span>
              {{ line }}
            </li>
          </ul>
        </div>
      </div>

      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-2 text-sm font-semibold text-slate-300">Description</h2>
        <p class="text-sm text-slate-400">{{ finding.description }}</p>
        <p v-if="finding.recommendation" class="mt-3 rounded bg-emerald-500/5 px-3 py-2 text-sm text-emerald-400">
          {{ finding.recommendation }}
        </p>
      </div>

      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-2 text-sm font-semibold text-slate-300">Evidence</h2>
        <pre class="overflow-x-auto whitespace-pre-wrap break-words text-xs text-slate-400">{{ JSON.stringify(finding.evidence, null, 2) }}</pre>
      </div>
    </div>
  </div>
</template>
