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
  evidence: Record<string, unknown>;
  recommendation: string | null;
  created_at: string;
  cve_ids: string[];
  // Phase 16 -- deduplication/lifecycle.
  status: FindingStatus;
  first_seen: string;
  last_seen: string;
  observation_count: number;
  source_tools: string[];
}

interface StatusHistoryEntry {
  id: string;
  finding_id: string;
  old_status: FindingStatus | null;
  new_status: FindingStatus;
  reason: string | null;
  triggered_by: string;
  created_at: string;
}

interface FindingRelation {
  id: string;
  finding_id: string;
  related_finding_id: string;
  rule: string;
  reason: string;
  created_at: string;
}

// Mirrors backend/app/findings/lifecycle.py::VALID_TRANSITIONS -- used only
// to decide which action buttons to show; the backend is the actual
// enforcement authority (PATCH .../status re-validates independently).
const VALID_TRANSITIONS: Record<FindingStatus, FindingStatus[]> = {
  NEW: ["CONFIRMED"],
  CONFIRMED: ["IN_REVIEW"],
  IN_REVIEW: ["ACCEPTED_RISK", "FALSE_POSITIVE", "REMEDIATED"],
  ACCEPTED_RISK: ["REOPENED"],
  FALSE_POSITIVE: ["REOPENED"],
  REMEDIATED: ["REOPENED"],
  REOPENED: ["CONFIRMED", "IN_REVIEW"],
};

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
const history = ref<StatusHistoryEntry[]>([]);
const relations = ref<FindingRelation[]>([]);
const loading = ref(true);
const loadError = ref("");
const historyLoading = ref(true);
const relationsLoading = ref(true);
const statusUpdating = ref(false);
const statusError = ref("");
const statusReason = ref("");

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
const statusColor: Record<FindingStatus, string> = {
  NEW: "bg-slate-700/50 text-slate-300",
  CONFIRMED: "bg-sky-500/15 text-sky-400",
  IN_REVIEW: "bg-amber-500/15 text-amber-400",
  ACCEPTED_RISK: "bg-purple-500/15 text-purple-400",
  FALSE_POSITIVE: "bg-slate-700/50 text-slate-500",
  REMEDIATED: "bg-emerald-500/15 text-emerald-400",
  REOPENED: "bg-red-500/15 text-red-400",
};

const nextStatuses = computed(() => (finding.value ? VALID_TRANSITIONS[finding.value.status] : []));

function formatPercent(value: number | null): string {
  return value === null ? "N/A" : `${(value * 100).toFixed(1)}%`;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
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

async function loadHistory() {
  historyLoading.value = true;
  try {
    history.value = await apiFetch<StatusHistoryEntry[]>(`/api/findings/${findingId}/history`);
  } finally {
    historyLoading.value = false;
  }
}

async function loadRelations() {
  relationsLoading.value = true;
  try {
    relations.value = await apiFetch<FindingRelation[]>(`/api/findings/${findingId}/relations`);
  } finally {
    relationsLoading.value = false;
  }
}

async function updateStatus(newStatus: FindingStatus) {
  statusUpdating.value = true;
  statusError.value = "";
  try {
    finding.value = await apiFetch<Finding>(`/api/findings/${findingId}/status`, {
      method: "PATCH",
      body: { status: newStatus, reason: statusReason.value || null },
    });
    statusReason.value = "";
    await loadHistory();
  } catch (err: any) {
    statusError.value = err?.data?.detail || "Failed to update status";
  } finally {
    statusUpdating.value = false;
  }
}

onMounted(() => {
  loadAll();
  loadHistory();
  loadRelations();
});
</script>

<template>
  <div>
    <PageHeader :title="finding?.title || 'Finding'" :subtitle="finding ? `${finding.source_tool} · ${finding.target}` : ''" />

    <div v-if="loading" class="px-8 py-6 text-sm text-slate-600">Loading…</div>
    <div v-else-if="loadError" class="px-8 py-6 text-sm text-red-400">{{ loadError }}</div>

    <div v-else-if="finding && risk" class="space-y-6 px-8 py-6">
      <div class="flex flex-wrap items-center gap-3">
        <span class="rounded px-2 py-0.5 text-xs" :class="severityColor[finding.severity]">{{ finding.severity }}</span>
        <span class="rounded px-2 py-0.5 text-xs font-medium" :class="statusColor[finding.status]">
          {{ finding.status.replace("_", " ") }}
        </span>
        <span class="text-xs text-slate-500">Confidence: {{ finding.confidence }}</span>
        <NuxtLink :to="`/scans/${finding.job_id}`" class="ml-auto text-xs text-emerald-400 hover:underline">
          View source scan →
        </NuxtLink>
      </div>

      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-sm font-semibold text-slate-300">Lifecycle</h2>
          <p class="text-xs text-slate-500">
            First seen {{ formatDate(finding.first_seen) }} · Last seen {{ formatDate(finding.last_seen) }} ·
            Observed {{ finding.observation_count }}×
          </p>
        </div>
        <p class="mb-3 text-xs text-slate-500">
          Reported by:
          <span v-for="t in finding.source_tools" :key="t" class="ml-1 rounded bg-slate-800 px-1.5 py-0.5 text-slate-300">{{ t }}</span>
        </p>

        <div v-if="nextStatuses.length" class="flex flex-wrap items-center gap-2">
          <input
            v-model="statusReason"
            type="text"
            placeholder="Reason (optional)"
            class="min-w-48 flex-1 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200"
          />
          <button
            v-for="s in nextStatuses"
            :key="s"
            :disabled="statusUpdating"
            class="rounded-md border border-slate-700 px-3 py-1 text-xs font-medium text-slate-200 hover:bg-slate-800 disabled:opacity-50"
            @click="updateStatus(s)"
          >
            Mark {{ s.replace("_", " ") }}
          </button>
        </div>
        <p v-else class="text-xs text-slate-600">No further transitions from {{ finding.status.replace("_", " ") }}.</p>
        <p v-if="statusError" class="mt-2 text-xs text-red-400">{{ statusError }}</p>

        <div class="mt-4 border-t border-slate-800 pt-3">
          <p class="mb-2 text-xs font-medium text-slate-500">History</p>
          <p v-if="historyLoading" class="text-xs text-slate-600">Loading…</p>
          <p v-else-if="history.length === 0" class="text-xs text-slate-600">No status changes yet.</p>
          <div v-else class="space-y-2">
            <div v-for="h in history" :key="h.id" class="flex items-start gap-2 text-xs">
              <span class="mt-1 h-1 w-1 shrink-0 rounded-full bg-slate-600"></span>
              <div class="min-w-0 flex-1">
                <p class="text-slate-300">
                  <span v-if="h.old_status">{{ h.old_status.replace("_", " ") }} → </span>{{ h.new_status.replace("_", " ") }}
                  <span class="text-slate-600">({{ h.triggered_by }})</span>
                </p>
                <p v-if="h.reason" class="text-slate-500">{{ h.reason }}</p>
                <p class="text-slate-600">{{ formatDate(h.created_at) }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="!relationsLoading && relations.length > 0" class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-3 text-sm font-semibold text-slate-300">Related Findings</h2>
        <div class="space-y-2">
          <NuxtLink
            v-for="r in relations"
            :key="r.id"
            :to="`/findings/${r.related_finding_id}`"
            class="block rounded-md border border-slate-800 bg-slate-950/50 p-3 hover:bg-slate-900"
          >
            <p class="text-xs font-medium text-slate-400">{{ r.rule }}</p>
            <p class="mt-1 text-sm text-slate-300">{{ r.reason }}</p>
          </NuxtLink>
        </div>
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
