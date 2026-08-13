<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useApi } from "~/composables/useApi";
import type { Finding } from "~/types/finding";
import type { GraphEdge, GraphNode } from "~/types/graph";

const props = defineProps<{
  cveId: string;
  connections: { edge: GraphEdge; otherEnd: GraphNode | null }[];
}>();

const { apiFetch } = useApi();

// The only edge relation that ever points at a CVE node is
// FINDING -[REFERENCES_CVE]-> CVE (backend/app/graph/builder.py) -- this is
// the complete, honest list of "findings referencing this CVE" as currently
// known to the graph, not every Finding across the whole system (see the
// /intelligence page's own client-side CVE search for that broader view,
// since GET /api/findings has no cve_ids filter to do it server-side).
const findingIds = computed(() =>
  props.connections
    .filter((c) => c.edge.relation === "REFERENCES_CVE" && c.otherEnd?.type === "FINDING")
    .map((c) => c.otherEnd!.id)
);

const findings = ref<Finding[]>([]);
const loading = ref(false);
const error = ref("");

async function loadFindings() {
  if (findingIds.value.length === 0) {
    findings.value = [];
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    findings.value = await Promise.all(findingIds.value.map((id) => apiFetch<Finding>(`/api/findings/${id}`)));
  } catch (err: any) {
    error.value = err?.data?.detail || "Failed to load associated findings";
  } finally {
    loading.value = false;
  }
}

function formatPercent(value: number | null): string {
  return value === null ? "not available" : `${(value * 100).toFixed(1)}%`;
}

watch(() => props.cveId, loadFindings, { immediate: true });
</script>

<template>
  <div class="space-y-3 text-xs">
    <p class="font-medium text-slate-200">{{ cveId }}</p>

    <!-- No endpoint currently exposes vulnerability_intel/cisa_kev_entries
    directly by CVE ID (backend/app/api/routes/intelligence.py only has
    /status and /sync) -- description/references are not fabricated here. -->
    <div class="space-y-0.5 text-slate-500">
      <p>Description: <span class="text-slate-600">Not available from the current API.</span></p>
      <p>References: <span class="text-slate-600">Not available from the current API.</span></p>
    </div>

    <div>
      <p class="mb-1 font-medium text-slate-500">Associated findings ({{ findingIds.length }})</p>
      <LoadingState v-if="loading" />
      <p v-else-if="error" class="text-red-400">{{ error }}</p>
      <EmptyState v-else-if="findings.length === 0" message="No findings in the current graph reference this CVE." />
      <div v-else class="space-y-2">
        <NuxtLink
          v-for="f in findings"
          :key="f.id"
          :to="`/findings/${f.id}`"
          class="block rounded border border-slate-800 bg-slate-950/50 p-2 hover:bg-slate-900"
        >
          <div class="flex flex-wrap items-center gap-1.5">
            <SeverityBadge :severity="f.severity" size="sm" />
            <RiskBadge v-if="f.risk_priority" :priority="f.risk_priority" size="sm" />
            <span class="text-slate-200">{{ f.title }}</span>
          </div>
          <p class="mt-1 text-slate-500">
            CVSS {{ f.cvss_score ?? "not available" }} · EPSS {{ formatPercent(f.epss_score) }} · KEV
            {{ f.kev === true ? "YES" : f.kev === false ? "NO" : "unknown" }}
            <span v-if="f.cve_ids.length > 1"> · also references {{ f.cve_ids.length - 1 }} other CVE(s)</span>
          </p>
        </NuxtLink>
      </div>
    </div>
  </div>
</template>
