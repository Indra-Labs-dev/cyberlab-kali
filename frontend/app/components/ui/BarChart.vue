<script setup lang="ts">
// Simple horizontal-bar distribution (assets by criticality, etc). Same
// no-dependency reasoning as DonutChart.vue.
import { computed } from "vue";

export interface Bar {
  label: string;
  value: number;
  color: string;
}

const props = defineProps<{ data: Bar[] }>();
const max = computed(() => Math.max(1, ...props.data.map((d) => d.value)));
</script>

<template>
  <div class="space-y-2.5">
    <div v-for="bar in data" :key="bar.label" class="flex items-center gap-3 text-xs">
      <span class="w-24 shrink-0 truncate text-slate-400">{{ bar.label }}</span>
      <div class="h-2 flex-1 overflow-hidden rounded-full bg-slate-800">
        <div
          class="h-full rounded-full transition-[width] duration-700 ease-out"
          :class="bar.color"
          :style="{ width: `${(bar.value / max) * 100}%` }"
        />
      </div>
      <span class="w-6 shrink-0 text-right font-medium text-slate-300">{{ bar.value }}</span>
    </div>
    <p v-if="data.length === 0" class="text-xs text-slate-600">No data</p>
  </div>
</template>
