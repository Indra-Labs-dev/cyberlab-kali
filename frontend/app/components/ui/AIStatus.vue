<script setup lang="ts">
// Chip marking the AI layer as its own visual identity (violet halo, not
// just a purple card). `state` reflects real data the caller passes in
// (e.g. `runningMissions.length > 0`) -- never an invented "thinking"
// state with nothing backing it.
withDefaults(defineProps<{ state?: "idle" | "active"; label?: string }>(), { state: "idle" });

const stateLabel: Record<string, string> = { idle: "AI idle", active: "AI active" };
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 rounded-full border border-ai-500/30 bg-ai-500/10 px-2.5 py-1 text-xs font-medium text-ai-400"
    :class="state === 'active' && 'shadow-glow-ai'"
  >
    <UiPulseIndicator tone="ai" :active="state === 'active'" size="sm" />
    {{ label ?? stateLabel[state] }}
  </span>
</template>
