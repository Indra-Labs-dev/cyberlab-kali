<script setup lang="ts">
import type { GraphSearchResult } from "~/composables/useGraph";

const selected = ref<GraphSearchResult | null>(null);

// SecurityGraph fetches once on mount and never watches its own baseUrl
// prop (it never needed to before -- the two existing usages on
// assets/[id].vue and projects/[id].vue each set it once per page load).
// This page changes it repeatedly without a route change, so :key forces a
// clean remount per selection instead of modifying SecurityGraph itself.
const baseUrl = computed(() =>
  selected.value ? `/api/graph/nodes/${selected.value.type}/${encodeURIComponent(selected.value.id)}` : ""
);

function onSelect(result: GraphSearchResult) {
  selected.value = result;
}
</script>

<template>
  <div>
    <PageHeader
      title="Security Graph"
      subtitle="Search an asset, finding, CVE, service, or technology to explore how it connects to the rest of the attack surface"
    />

    <div class="space-y-4 px-8 py-6">
      <GraphSearchBar @select="onSelect" />

      <EmptyState
        v-if="!selected"
        message="Search above for an asset or finding, or enter an exact CVE / service / technology identifier, to load its graph."
      />

      <div v-else>
        <p class="mb-2 text-xs text-slate-500">
          Showing: <span class="text-slate-300">{{ selected.label }}</span>
          <span class="ml-1 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">{{ selected.type }}</span>
        </p>
        <SecurityGraph :key="baseUrl" :base-url="baseUrl" />
      </div>
    </div>
  </div>
</template>
