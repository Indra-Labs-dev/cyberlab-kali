<script setup lang="ts">
// For the Phase 15 Risk Score priority band (risk_priority), not to be
// confused with the Tool Registry's risk_level (SAFE/CAUTION/...) -- see
// app/constants/colors.ts module docstring.
import { RISK_PRIORITY_COLORS } from "~/constants/colors";
import type { RiskPriority } from "~/types/finding";

withDefaults(defineProps<{ priority: RiskPriority; size?: "sm" | "md"; bold?: boolean }>(), {
  size: "md",
  bold: false,
});
</script>

<template>
  <Badge :color-class="RISK_PRIORITY_COLORS[priority]" :size="size" :bold="bold">
    <slot>{{ priority }}</slot>
  </Badge>
</template>
