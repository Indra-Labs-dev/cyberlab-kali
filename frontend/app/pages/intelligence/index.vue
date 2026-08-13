<script setup lang="ts">
import type { Finding } from "~/types/finding";

const { apiFetch } = useApi();

const cveQuery = ref("");
const cveFindings = ref<Finding[]>([]);
const cveLoading = ref(false);
const cveError = ref("");
const cveSearched = ref(false);

function formatPercent(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

async function searchCve() {
  const cve = cveQuery.value.trim().toUpperCase();
  if (!cve) return;
  cveLoading.value = true;
  cveError.value = "";
  cveSearched.value = false;
  try {
    // No backend endpoint filters findings by CVE (GET /api/findings has no
    // cve_ids param -- backend/app/api/routes/findings.py). cve_ids is
    // already part of every FindingResponse though, so this filters
    // client-side over the same list the Findings page fetches, rather than
    // adding a new backend endpoint (out of scope for 18c).
    const all = await apiFetch<Finding[]>("/api/findings?limit=500");
    cveFindings.value = all.filter((f) => f.cve_ids.includes(cve));
  } catch (err: any) {
    cveError.value = err?.data?.detail || "Failed to search findings";
  } finally {
    cveLoading.value = false;
    cveSearched.value = true;
  }
}
</script>

<template>
  <div>
    <PageHeader
      title="Vulnerability Intelligence"
      subtitle="EPSS, CISA KEV, and NVD sync status for CVEs observed in Findings"
    />

    <div class="space-y-6 px-8 py-6">
      <IntelligenceSyncStatus />

      <div>
        <h2 class="mb-1 text-sm font-semibold text-slate-300">Findings by CVE</h2>
        <p class="mb-3 text-xs text-slate-500">
          Enter a CVE ID to see every Finding in CyberLab that references it, across all assets.
        </p>
        <div class="flex gap-2">
          <label for="cve-search" class="sr-only">CVE ID</label>
          <input
            id="cve-search"
            v-model="cveQuery"
            type="text"
            placeholder="CVE-2021-44228"
            class="w-56 rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200"
            @keydown.enter="searchCve"
          />
          <button
            type="button"
            class="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
            @click="searchCve"
          >
            Search
          </button>
        </div>

        <div class="mt-3">
          <LoadingState v-if="cveLoading" />
          <p v-else-if="cveError" class="text-xs text-red-400" role="alert">{{ cveError }}</p>
          <EmptyState v-else-if="cveSearched && cveFindings.length === 0" message="No findings reference this CVE." />
          <div v-else-if="cveFindings.length" class="space-y-2">
            <NuxtLink
              v-for="f in cveFindings"
              :key="f.id"
              :to="`/findings/${f.id}`"
              class="block rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-xs hover:bg-slate-900"
            >
              <div class="flex flex-wrap items-center gap-1.5">
                <SeverityBadge :severity="f.severity" size="sm" />
                <RiskBadge v-if="f.risk_priority" :priority="f.risk_priority" size="sm" />
                <span class="text-slate-200">{{ f.title }}</span>
              </div>
              <p class="mt-1 text-slate-500">
                Target: <code class="text-slate-400">{{ f.target }}</code> · CVSS {{ f.cvss_score ?? "—" }} · EPSS
                {{ formatPercent(f.epss_score) }} · KEV {{ f.kev === true ? "YES" : f.kev === false ? "NO" : "unknown" }}
              </p>
            </NuxtLink>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
