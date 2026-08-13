<script setup lang="ts">
import { computed } from "vue";
import { MISSION_STATUS_COLORS } from "~/constants/colors";
import type { MissionStatus } from "~/types/mission";

const props = withDefaults(defineProps<{ status: MissionStatus; size?: "sm" | "md"; bold?: boolean }>(), {
  size: "md",
  bold: false,
});

const colorClass = computed(() => MISSION_STATUS_COLORS[props.status]);
</script>

<template>
  <Badge :color-class="colorClass" :size="size" :bold="bold">
    <slot>{{ status }}</slot>
  </Badge>
</template>
