<script setup lang="ts">
import { CRITICALITY_COLORS } from "~/constants/colors";
import type { AssetCriticality } from "~/types/asset";

withDefaults(defineProps<{ criticality: AssetCriticality; size?: "sm" | "md"; bold?: boolean }>(), {
  size: "md",
  bold: false,
});
</script>

<template>
  <Badge :color-class="CRITICALITY_COLORS[criticality]" :size="size" :bold="bold">
    <slot>{{ criticality }}</slot>
  </Badge>
</template>
