<script setup lang="ts">
import { computed } from "vue";
import { CHAIN_RUN_STEP_STATUS_COLORS } from "~/constants/colors";
import type { ChainRunStepStatus } from "~/types/chain";

const props = withDefaults(defineProps<{ status: ChainRunStepStatus; size?: "sm" | "md"; bold?: boolean }>(), {
  size: "sm",
  bold: false,
});

const colorClass = computed(() => CHAIN_RUN_STEP_STATUS_COLORS[props.status]);
</script>

<template>
  <Badge :color-class="colorClass" :size="size" :bold="bold">
    <slot>{{ status }}</slot>
  </Badge>
</template>
