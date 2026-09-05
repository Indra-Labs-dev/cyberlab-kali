<script setup lang="ts">
// 270° circular progress gauge (SVG) -- same geometry idea as the
// reference's "Uptime" ring, but the value is whatever real ratio the
// caller passes in. The Dashboard's System Status card feeds it
// (healthy checks / total checks) from useSystemStatus's real results --
// never a fabricated "99.9% uptime" figure with nothing behind it.
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    value: number; // 0-100
    label?: string;
    size?: number;
    thickness?: number;
    tone?: "accent" | "ai" | "success" | "warning" | "danger";
  }>(),
  { size: 128, thickness: 9, tone: "success" },
);

// Both `stroke-*` (the actual arc color) and `text-*` (so `currentColor`
// resolves correctly for the drop-shadow filter below -- SVG `stroke` and
// CSS `color` are different properties, `currentColor` only follows the
// latter).
const strokeColor: Record<string, string> = {
  accent: "stroke-accent-400 text-accent-400",
  ai: "stroke-ai-400 text-ai-400",
  success: "stroke-success-400 text-success-400",
  warning: "stroke-warning-400 text-warning-400",
  danger: "stroke-danger-400 text-danger-400",
};
const textColor: Record<string, string> = {
  accent: "fill-accent-400",
  ai: "fill-ai-400",
  success: "fill-success-400",
  warning: "fill-warning-400",
  danger: "fill-danger-400",
};

const radius = computed(() => (props.size - props.thickness) / 2);
// A 270° gauge (3/4 of the full circle) reads as a dial, not just a
// truncated donut -- rotated so the open gap sits at the bottom.
const arcFraction = 0.75;
const circumference = computed(() => 2 * Math.PI * radius.value);
const arcLength = computed(() => circumference.value * arcFraction);
const clampedValue = computed(() => Math.max(0, Math.min(100, props.value)));
const progressLength = computed(() => arcLength.value * (clampedValue.value / 100));
</script>

<template>
  <div class="relative inline-grid place-items-center" :style="{ width: `${size}px`, height: `${size}px` }">
    <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`" class="-rotate-[135deg]" role="img" :aria-label="`${label ?? 'Gauge'}: ${clampedValue}%`">
      <circle
        :cx="size / 2"
        :cy="size / 2"
        :r="radius"
        fill="none"
        class="stroke-slate-800"
        :stroke-width="thickness"
        stroke-linecap="round"
        :stroke-dasharray="`${arcLength} ${circumference}`"
      />
      <circle
        :cx="size / 2"
        :cy="size / 2"
        :r="radius"
        fill="none"
        :class="strokeColor[tone]"
        :stroke-width="thickness"
        stroke-linecap="round"
        :stroke-dasharray="`${progressLength} ${circumference}`"
        class="transition-[stroke-dasharray] duration-700 ease-out"
        :style="{ filter: `drop-shadow(0 0 6px currentColor)` }"
      />
    </svg>
    <div class="pointer-events-none absolute inset-0 grid place-items-center text-center">
      <div>
        <p class="font-display text-xl font-black tabular-nums" :class="textColor[tone]">{{ Math.round(clampedValue) }}%</p>
        <p v-if="label" class="text-[10px] text-slate-500">{{ label }}</p>
      </div>
    </div>
  </div>
</template>
