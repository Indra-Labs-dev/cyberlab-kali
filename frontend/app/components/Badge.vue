<script setup lang="ts">
// Generic pill badge -- the two size/weight variants actually in use
// across the app today (verified in the 18a audit): compact list rows use
// `sm` (px-1.5) without bold, detail-page headers use `md` (px-2) with
// bold. Domain-specific badges (SeverityBadge, RiskBadge, ...) wrap this
// with the right color map; this component only ever renders the classes
// it's given, it has no notion of severity/status/etc.
withDefaults(defineProps<{ colorClass: string; size?: "sm" | "md"; bold?: boolean }>(), {
  size: "md",
  bold: false,
});
</script>

<template>
  <span
    class="rounded"
    :class="[colorClass, size === 'sm' ? 'px-1.5 py-0.5 text-xs' : 'px-2 py-0.5 text-xs', bold && 'font-medium']"
  >
    <slot />
  </span>
</template>
