<script setup lang="ts">
// Finding lifecycle status (Phase 16). `strikeFalsePositive` preserves a
// real, pre-existing divergence rather than papering over it: the compact
// findings list (pages/findings/index.vue) strikes through a
// FALSE_POSITIVE label, the finding detail page (pages/findings/[id].vue)
// does not -- both behaviors are intentional call sites, not a bug to fix
// here. See app/constants/colors.ts::FINDING_STATUS_COLORS.
import { computed } from "vue";
import { FINDING_STATUS_COLORS } from "~/constants/colors";
import type { FindingStatus } from "~/types/finding";

const props = withDefaults(
  defineProps<{ status: FindingStatus; size?: "sm" | "md"; bold?: boolean; strikeFalsePositive?: boolean }>(),
  { size: "md", bold: false, strikeFalsePositive: false },
);

const colorClass = computed(() => {
  const base = FINDING_STATUS_COLORS[props.status];
  return props.strikeFalsePositive && props.status === "FALSE_POSITIVE" ? `${base} line-through` : base;
});
</script>

<template>
  <Badge :color-class="colorClass" :size="size" :bold="bold">
    <slot>{{ status }}</slot>
  </Badge>
</template>
