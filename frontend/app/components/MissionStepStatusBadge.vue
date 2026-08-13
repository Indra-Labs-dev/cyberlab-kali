<script setup lang="ts">
import { computed } from "vue";
import { MISSION_STEP_STATUS_COLORS } from "~/constants/colors";
import type { MissionStepStatus } from "~/types/mission";

const props = withDefaults(defineProps<{ status: MissionStepStatus; size?: "sm" | "md"; bold?: boolean }>(), {
  size: "sm",
  bold: false,
});

const colorClass = computed(() => MISSION_STEP_STATUS_COLORS[props.status]);
</script>

<template>
  <Badge :color-class="colorClass" :size="size" :bold="bold">
    <slot>{{ status }}</slot>
  </Badge>
</template>
