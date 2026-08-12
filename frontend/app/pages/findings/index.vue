<script setup lang="ts">
type FindingStatus = "NEW" | "CONFIRMED" | "IN_REVIEW" | "ACCEPTED_RISK" | "FALSE_POSITIVE" | "REMEDIATED" | "REOPENED";

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
  cve_ids: string[];
  cvss_score: number | null;
  epss_score: number | null;
  kev: boolean | null;
  risk_score: number | null;
  risk_priority: "INFORMATIONAL" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | null;
  // Phase 16 -- deduplication/lifecycle.
  status: FindingStatus;
  observation_count: number;
  source_tools: string[];
}

const PRIORITIES = ["INFORMATIONAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;
const STATUSES: FindingStatus[] = ["NEW", "CONFIRMED", "IN_REVIEW", "ACCEPTED_RISK", "FALSE_POSITIVE", "REMEDIATED", "REOPENED"];
const SOURCE_TOOLS = ["nmap", "masscan", "whatweb", "nuclei", "sslscan", "gobuster", "searchsploit", "nikto"];

const statusColor: Record<FindingStatus, string> = {
  NEW: "bg-slate-700/50 text-slate-300",
  CONFIRMED: "bg-sky-500/15 text-sky-400",
  IN_REVIEW: "bg-amber-500/15 text-amber-400",
  ACCEPTED_RISK: "bg-purple-500/15 text-purple-400",
  FALSE_POSITIVE: "bg-slate-700/50 text-slate-500 line-through",
  REMEDIATED: "bg-emerald-500/15 text-emerald-400",
  REOPENED: "bg-red-500/15 text-red-400",
};

const { apiFetch } = useApi();

const findings = ref<Finding[]>([]);
const topRisks = ref<Finding[]>([]);
const loading = ref(true);
const topRisksLoading = ref(true);
const error = ref("");

const severityFilter = ref<string>("");
const priorityFilter = ref<string>("");
const kevOnly = ref(false);
const minRiskScore = ref<string>("");
const statusFilter = ref<string>("");
const sourceToolFilter = ref<string>("");
const sortBy = ref<"created_at_desc" | "risk_score_desc" | "risk_score_asc">("created_at_desc");

const severityColor: Record<string, string> = {
  INFO: "bg-slate-700/50 text-slate-300",
  LOW: "bg-emerald-500/15 text-emerald-400",
  MEDIUM: "bg-amber-500/15 text-amber-400",
  HIGH: "bg-orange-500/15 text-orange-400",
  CRITICAL: "bg-red-500/15 text-red-400",
};
const priorityColor: Record<string, string> = {
  INFORMATIONAL: "bg-slate-700/50 text-slate-300",
  LOW: "bg-emerald-500/15 text-emerald-400",
  MEDIUM: "bg-amber-500/15 text-amber-400",
  HIGH: "bg-orange-500/15 text-orange-400",
  CRITICAL: "bg-red-500/15 text-red-400",
};

function formatPercent(value: number | null): string {
  return value === null ? "N/A" : `${(value * 100).toFixed(1)}%`;
}

async function loadTopRisks() {
  topRisksLoading.value = true;
  try {
    topRisks.value = await apiFetch<Finding[]>("/api/findings?sort=risk_score_desc&limit=5");
  } finally {
    topRisksLoading.value = false;
  }
}

async function loadFindings() {
  loading.value = true;
  error.value = "";
  try {
    const params = new URLSearchParams();
    if (severityFilter.value) params.set("severity", severityFilter.value);
    if (priorityFilter.value) params.set("priority", priorityFilter.value);
    if (kevOnly.value) params.set("kev", "true");
    if (minRiskScore.value) params.set("min_risk_score", minRiskScore.value);
    if (statusFilter.value) params.set("status", statusFilter.value);
    if (sourceToolFilter.value) params.set("source_tool", sourceToolFilter.value);
    params.set("sort", sortBy.value);
    params.set("limit", "200");
    findings.value = await apiFetch<Finding[]>(`/api/findings?${params.toString()}`);
  } catch (err: any) {
    error.value = err?.data?.detail || "Failed to load findings";
  } finally {
    loading.value = false;
  }
}

watch([severityFilter, priorityFilter, kevOnly, minRiskScore, statusFilter, sourceToolFilter, sortBy], loadFindings);
onMounted(() => {
  loadFindings();
  loadTopRisks();
});
</script>

<template>
  <div>
    <PageHeader title="Findings" subtitle="Normalized results extracted automatically from tool scans, prioritized by Risk Score" />

    <div class="px-8 py-6">
      <div class="mb-6 rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-3 text-sm font-semibold text-slate-300">Top Risks</h2>
        <p v-if="topRisksLoading" class="text-sm text-slate-600">Loading…</p>
        <p v-else-if="topRisks.length === 0" class="text-sm text-slate-600">No scored findings yet.</p>
        <div v-else class="space-y-2">
          <NuxtLink
            v-for="f in topRisks"
            :key="f.id"
            :to="`/findings/${f.id}`"
            class="flex items-center gap-3 rounded-md border border-slate-800 bg-slate-950/50 p-3 hover:bg-slate-900"
          >
            <span
              class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-bold"
              :class="priorityColor[f.risk_priority || 'INFORMATIONAL']"
            >
              {{ f.risk_score ?? "—" }}
            </span>
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2">
                <span class="rounded px-1.5 py-0.5 text-xs" :class="priorityColor[f.risk_priority || 'INFORMATIONAL']">
                  {{ f.risk_priority || "UNSCORED" }}
                </span>
                <span class="truncate font-medium text-slate-200">{{ f.title }}</span>
              </div>
              <p class="mt-1 truncate text-xs text-slate-500">
                Asset: <code class="text-slate-400">{{ f.target }}</code>
                <span v-if="f.cve_ids.length"> · {{ f.cve_ids.join(", ") }}</span>
                <span v-if="f.kev === true" class="text-red-400"> · KEV: YES</span>
                <span v-if="f.epss_score !== null"> · EPSS: {{ formatPercent(f.epss_score) }}</span>
                <span v-if="f.cvss_score !== null"> · CVSS: {{ f.cvss_score }}</span>
              </p>
            </div>
          </NuxtLink>
        </div>
      </div>

      <div class="mb-4 flex flex-wrap items-center gap-2">
        <label class="text-xs text-slate-500">Severity</label>
        <select v-model="severityFilter" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200">
          <option value="">All</option>
          <option v-for="s in ['INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL']" :key="s" :value="s">{{ s }}</option>
        </select>

        <label class="ml-2 text-xs text-slate-500">Priority</label>
        <select v-model="priorityFilter" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200">
          <option value="">All</option>
          <option v-for="p in PRIORITIES" :key="p" :value="p">{{ p }}</option>
        </select>

        <label class="ml-2 flex items-center gap-1.5 text-xs text-slate-500">
          <input type="checkbox" v-model="kevOnly" class="accent-emerald-500" /> KEV only
        </label>

        <label class="ml-2 text-xs text-slate-500">Min. risk score</label>
        <input
          v-model="minRiskScore"
          type="number"
          min="0"
          max="100"
          placeholder="0-100"
          class="w-20 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200"
        />

        <label class="ml-2 text-xs text-slate-500">Status</label>
        <select v-model="statusFilter" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200">
          <option value="">All</option>
          <option v-for="s in STATUSES" :key="s" :value="s">{{ s }}</option>
        </select>

        <label class="ml-2 text-xs text-slate-500">Source tool</label>
        <select v-model="sourceToolFilter" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200">
          <option value="">All</option>
          <option v-for="t in SOURCE_TOOLS" :key="t" :value="t">{{ t }}</option>
        </select>

        <label class="ml-2 text-xs text-slate-500">Sort</label>
        <select v-model="sortBy" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200">
          <option value="created_at_desc">Newest first</option>
          <option value="risk_score_desc">Risk Score ↓</option>
          <option value="risk_score_asc">Risk Score ↑</option>
        </select>
      </div>

      <p v-if="loading" class="text-sm text-slate-600">Loading…</p>
      <p v-else-if="error" class="text-sm text-red-400">{{ error }}</p>
      <p v-else-if="findings.length === 0" class="text-sm text-slate-600">
        No findings match these filters.
      </p>

      <div v-else class="space-y-2">
        <NuxtLink
          v-for="finding in findings"
          :key="finding.id"
          :to="`/findings/${finding.id}`"
          class="block rounded-lg border border-slate-800 bg-slate-900/40 p-4 hover:bg-slate-900"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded px-2 py-0.5 text-xs font-medium" :class="severityColor[finding.severity]">
                  {{ finding.severity }}
                </span>
                <span
                  v-if="finding.risk_priority"
                  class="rounded px-2 py-0.5 text-xs font-medium"
                  :class="priorityColor[finding.risk_priority]"
                >
                  Risk {{ finding.risk_score }} · {{ finding.risk_priority }}
                </span>
                <span v-if="finding.kev === true" class="rounded bg-red-500/15 px-2 py-0.5 text-xs font-medium text-red-400">
                  KEV
                </span>
                <span class="rounded px-2 py-0.5 text-xs font-medium" :class="statusColor[finding.status]">
                  {{ finding.status.replace("_", " ") }}
                </span>
                <span class="font-medium text-slate-200">{{ finding.title }}</span>
              </div>
              <p class="mt-1 text-xs text-slate-500">
                Target: <code class="text-slate-400">{{ finding.target }}</code> · Source:
                {{ finding.source_tools.length > 1 ? finding.source_tools.join(", ") : finding.source_tool }} ·
                Confidence: {{ finding.confidence }}
                <span v-if="finding.observation_count > 1"> · Seen {{ finding.observation_count }}× </span>
                <span v-if="finding.cve_ids.length"> · {{ finding.cve_ids.join(", ") }}</span>
                <span v-if="finding.cvss_score !== null"> · CVSS {{ finding.cvss_score }}</span>
                <span v-if="finding.epss_score !== null"> · EPSS {{ formatPercent(finding.epss_score) }}</span>
              </p>
              <p class="mt-2 text-sm text-slate-400">{{ finding.description }}</p>
              <p v-if="finding.recommendation" class="mt-2 rounded bg-emerald-500/5 px-2 py-1 text-xs text-emerald-400">
                {{ finding.recommendation }}
              </p>
            </div>
            <span class="shrink-0 text-xs text-emerald-400 hover:underline">View details →</span>
          </div>
        </NuxtLink>
      </div>
    </div>
  </div>
</template>
