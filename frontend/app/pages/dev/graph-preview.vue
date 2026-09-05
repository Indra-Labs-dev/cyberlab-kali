<script setup lang="ts">
// TEMPORARY -- not linked from the sidebar, exists only to evaluate the
// SecurityGraph3D prototype against real data in isolation before wiring
// it into the Dashboard (per the two-step "prototype, then evaluate, then
// integrate" process). Safe to delete once that evaluation is done, or
// keep as a standing dev harness -- either way, not part of the product
// surface.
import type { GraphNodeType } from "~/types/graph";

const unavailable = ref(false);
const lastSelected = ref<{ id: string; type: GraphNodeType } | null>(null);

function onSelect(node: { id: string; type: GraphNodeType }) {
  lastSelected.value = node;
}
</script>

<template>
  <div class="p-8">
    <PageHeader title="Security Graph 3D — dev preview" subtitle="Temporary harness, not part of the app's navigation." />
    <div class="mt-6 max-w-3xl">
      <UiCard title="CyberSecurityGraph3D" glow="ai" glass>
        <p v-if="unavailable" class="text-sm text-warning-400">
          Quality tier resolved to "fallback" (small viewport, no WebGL, or otherwise unsupported) — the Dashboard would render
          UiHeroRadar here instead.
        </p>
        <CyberSecurityGraph3D v-else height="420px" @unavailable="unavailable = true" @select-node="onSelect" />
      </UiCard>
      <p v-if="lastSelected" class="mt-4 text-sm text-slate-400">
        Last clicked: <span class="text-slate-200">{{ lastSelected.type }}</span> / {{ lastSelected.id }}
      </p>
    </div>
  </div>
</template>
