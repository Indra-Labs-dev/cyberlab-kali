<script setup lang="ts">
// Findings section of the Asset detail page (18d.4). Purely presentational
// -- `findings` is fetched by the parent's loadAll() alongside asset/
// project/jobs/tools (one coordinated Promise.all, not duplicated here),
// and passed down as a read-only prop. Uses the centralized Finding type
// (18a, ~/types/finding.ts) and SeverityBadge/RiskBadge instead of the
// page's former local severityColor/priorityColor maps -- `size="sm"`
// matches the original inline `px-1.5 py-0.5 text-xs` classes exactly.
import type { Finding } from "~/types/finding";

defineProps<{ findings: Finding[] }>();
</script>

<template>
  <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
    <h2 class="mb-2 text-sm font-semibold text-slate-300">Findings</h2>
    <EmptyState v-if="findings.length === 0" message="No findings for this asset yet." />
    <div v-else class="space-y-2">
      <NuxtLink
        v-for="f in findings"
        :key="f.id"
        :to="`/findings/${f.id}`"
        class="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-950/50 p-2.5 hover:bg-slate-900"
      >
        <SeverityBadge :severity="f.severity" size="sm" />
        <RiskBadge v-if="f.risk_priority" :priority="f.risk_priority" size="sm">Risk {{ f.risk_score }}</RiskBadge>
        <span class="text-sm text-slate-200">{{ f.title }}</span>
      </NuxtLink>
    </div>
  </div>
</template>
