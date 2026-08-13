<script setup lang="ts">
// Risk Overview section (18d.3) -- fully self-contained: owns its own
// fetch, no filters/interactions. Uses the centralized RiskSummary type
// (18a, ~/types/finding.ts) instead of a local interface. No color-map
// here to reuse from SeverityBadge/RiskBadge/StatusBadge -- the original
// markup uses fixed per-metric Tailwind colors (red/orange/slate), not a
// severity- or priority-keyed lookup, so there is nothing to centralize.
import { onMounted, ref } from "vue";
import { useApi } from "~/composables/useApi";
import type { RiskSummary } from "~/types/finding";

const props = defineProps<{ assetId: string }>();

const { apiFetch } = useApi();

const riskSummary = ref<RiskSummary | null>(null);
const riskSummaryLoading = ref(true);
const riskSummaryError = ref("");

async function loadRiskSummary() {
  riskSummaryLoading.value = true;
  riskSummaryError.value = "";
  try {
    riskSummary.value = await apiFetch<RiskSummary>(`/api/assets/${props.assetId}/risk-summary`);
  } catch (err: any) {
    riskSummaryError.value = err?.data?.detail || "Failed to load risk overview";
  } finally {
    riskSummaryLoading.value = false;
  }
}

onMounted(loadRiskSummary);
</script>

<template>
  <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
    <h2 class="mb-3 text-sm font-semibold text-slate-300">Risk Overview</h2>
    <LoadingState v-if="riskSummaryLoading" />
    <p v-else-if="riskSummaryError" class="text-sm text-red-400">{{ riskSummaryError }}</p>
    <EmptyState
      v-else-if="riskSummary && riskSummary.total_findings === 0"
      message="No findings yet — risk is computed automatically once scans produce findings."
    />
    <div v-else-if="riskSummary" class="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <div>
        <p class="text-2xl font-semibold text-red-400">{{ riskSummary.critical_findings }}</p>
        <p class="text-xs text-slate-500">Critical findings</p>
      </div>
      <div>
        <p class="text-2xl font-semibold text-orange-400">{{ riskSummary.high_findings }}</p>
        <p class="text-xs text-slate-500">High findings</p>
      </div>
      <div>
        <p class="text-2xl font-semibold text-red-400">{{ riskSummary.kev_findings }}</p>
        <p class="text-xs text-slate-500">KEV findings</p>
      </div>
      <div>
        <p class="text-2xl font-semibold text-slate-200">{{ riskSummary.highest_risk_score ?? "—" }}</p>
        <p class="text-xs text-slate-500">Highest risk score</p>
      </div>
    </div>
    <p v-if="riskSummary && riskSummary.unscored_findings > 0" class="mt-2 text-xs text-slate-600">
      {{ riskSummary.unscored_findings }} finding(s) not yet scored.
    </p>
  </div>
</template>
