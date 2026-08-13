<script setup lang="ts">
import { SEVERITY_COLORS } from "~/constants/colors";
import type { Severity } from "~/types/finding";

withDefaults(defineProps<{ severity: Severity; size?: "sm" | "md"; bold?: boolean }>(), {
  size: "md",
  bold: false,
});
</script>

<template>
  <Badge :color-class="SEVERITY_COLORS[severity]" :size="size" :bold="bold">
    <slot>{{ severity }}</slot>
  </Badge>
</template>
