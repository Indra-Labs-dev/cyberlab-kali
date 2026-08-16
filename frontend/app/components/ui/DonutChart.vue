<script setup lang="ts">
// Pure inline-SVG donut -- no charting dependency added for what's really
// one shape. `color` is a Tailwind `stroke-*` class chosen by the caller
// (kept out of constants/colors.ts, which maps bg/text pill colors for
// badges, a different concern from chart stroke colors).
import { computed } from "vue";

export interface DonutSegment {
  label: string;
  value: number;
  color: string;
}

const props = withDefaults(defineProps<{ data: DonutSegment[]; size?: number; thickness?: number }>(), {
  size: 120,
  thickness: 14,
});

const radius = computed(() => (props.size - props.thickness) / 2);
const circumference = computed(() => 2 * Math.PI * radius.value);
const total = computed(() => props.data.reduce((sum, d) => sum + d.value, 0));

// Every entry gets a circle, even ones currently at 0 -- so when real data
// arrives async (severity counts start at 0 before the findings fetch
// resolves) Vue patches an *existing* element's stroke-dasharray instead
// of inserting a brand-new one, which is what lets the CSS transition
// below actually animate the arc growing in rather than snapping straight
// to its final size.
const segments = computed(() => {
  let offset = 0;
  return props.data.map((d) => {
    const fraction = total.value > 0 ? d.value / total.value : 0;
    const length = fraction * circumference.value;
    const segment = { ...d, length, offset };
    offset += length;
    return segment;
  });
});
</script>

<template>
  <svg
    :width="size"
    :height="size"
    :viewBox="`0 0 ${size} ${size}`"
    role="img"
    :aria-label="total > 0 ? `Distribution: ${data.map((d) => `${d.label} ${d.value}`).join(', ')}` : 'No data'"
  >
    <circle :cx="size / 2" :cy="size / 2" :r="radius" fill="none" class="stroke-slate-800" :stroke-width="thickness" />
    <circle
      v-for="segment in segments"
      :key="segment.label"
      :cx="size / 2"
      :cy="size / 2"
      :r="radius"
      fill="none"
      class="transition-[stroke-dasharray] duration-700 ease-out"
      :class="segment.color"
      :stroke-width="thickness"
      :stroke-dasharray="`${segment.length} ${circumference - segment.length}`"
      :stroke-dashoffset="-segment.offset"
      :transform="`rotate(-90 ${size / 2} ${size / 2})`"
    />
    <text
      v-if="total > 0"
      x="50%"
      y="50%"
      text-anchor="middle"
      dominant-baseline="middle"
      class="fill-slate-100 text-sm font-semibold"
    >
      {{ total }}
    </text>
    <text v-else x="50%" y="50%" text-anchor="middle" dominant-baseline="middle" class="fill-slate-600 text-xs">
      No data
    </text>
  </svg>
</template>
