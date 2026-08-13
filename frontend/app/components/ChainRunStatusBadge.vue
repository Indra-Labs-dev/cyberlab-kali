<script setup lang="ts">
import { computed } from "vue";
import { CHAIN_RUN_STATUS_COLORS } from "~/constants/colors";
import type { ChainRunStatus } from "~/types/chain";

const props = withDefaults(defineProps<{ status: ChainRunStatus; size?: "sm" | "md"; bold?: boolean }>(), {
  size: "md",
  bold: false,
});

const colorClass = computed(() => CHAIN_RUN_STATUS_COLORS[props.status]);
</script>

<template>
  <Badge :color-class="colorClass" :size="size" :bold="bold">
    <slot>{{ status }}</slot>
  </Badge>
</template>
