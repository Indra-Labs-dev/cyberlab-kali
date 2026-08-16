<script setup lang="ts">
// Dashboard centerpiece -- stands in for the reference image's world-map +
// globe hero (no geo/traffic data exists anywhere in this backend, so a
// literal map would be fabricated). Same visual grammar instead: a
// glowing center hub, concentric "radar" rings, and real entities
// radiating outward with connecting lines -- built entirely from
// `items` the caller passes in (this Dashboard passes its real
// top-risk findings). The rings rotate slowly and decoratively; the data
// nodes themselves stay fixed, since their position encodes nothing
// time-based and spinning real labels would just be noise.
import { computed } from "vue";

export interface RadarItem {
  id: string;
  label: string;
  tone: "danger" | "warning" | "accent" | "ai" | "success" | "default";
  value?: string | number;
}

const props = withDefaults(
  defineProps<{ items: RadarItem[]; centerValue: string | number; centerLabel: string; size?: number }>(),
  { size: 280 },
);

const toneColor: Record<string, string> = {
  danger: "#f87171",
  warning: "#fbbf24",
  accent: "#22d3ee",
  ai: "#a78bfa",
  success: "#34d399",
  default: "#64748b",
};

const cx = computed(() => props.size / 2);
const cy = computed(() => props.size / 2);
const ringR = computed(() => props.size * 0.46);
const hubR = computed(() => props.size * 0.135);

const nodes = computed(() => {
  const n = props.items.length;
  if (n === 0) return [];
  return props.items.map((item, i) => {
    const angle = (-90 + (360 / n) * i) * (Math.PI / 180);
    const x = cx.value + ringR.value * Math.cos(angle);
    const y = cy.value + ringR.value * Math.sin(angle);
    const lineX = cx.value + (hubR.value + 4) * Math.cos(angle);
    const lineY = cy.value + (hubR.value + 4) * Math.sin(angle);
    return { ...item, x, y, lineX, lineY, color: toneColor[item.tone] };
  });
});

const ticks = computed(() => {
  const count = 16;
  const inner = ringR.value + 6;
  const outer = ringR.value + 12;
  return Array.from({ length: count }, (_, i) => {
    const angle = ((360 / count) * i) * (Math.PI / 180);
    return {
      x1: cx.value + inner * Math.cos(angle),
      y1: cy.value + inner * Math.sin(angle),
      x2: cx.value + outer * Math.cos(angle),
      y2: cy.value + outer * Math.sin(angle),
    };
  });
});
</script>

<template>
  <svg
    :width="size"
    :height="size"
    :viewBox="`0 0 ${size} ${size}`"
    role="img"
    :aria-label="`${centerLabel}: ${centerValue}, with ${items.length} highlighted signals`"
  >
    <!-- Decorative rings + ticks: purely ornamental, slow rotation only. -->
    <g class="motion-safe:animate-spin-slow" :style="{ transformOrigin: `${cx}px ${cy}px` }">
      <circle :cx="cx" :cy="cy" :r="ringR" fill="none" stroke="currentColor" class="text-slate-700/40" stroke-width="1" />
      <circle :cx="cx" :cy="cy" :r="ringR * 0.68" fill="none" stroke="currentColor" class="text-slate-700/25" stroke-width="1" />
      <line
        v-for="(t, i) in ticks"
        :key="i"
        :x1="t.x1"
        :y1="t.y1"
        :x2="t.x2"
        :y2="t.y2"
        stroke="currentColor"
        class="text-slate-600/40"
        stroke-width="1"
      />
    </g>

    <!-- Connecting lines + nodes: real data, stays fixed. -->
    <line
      v-for="node in nodes"
      :key="`line-${node.id}`"
      :x1="node.lineX"
      :y1="node.lineY"
      :x2="node.x"
      :y2="node.y"
      :stroke="node.color"
      stroke-width="1"
      stroke-opacity="0.35"
    />
    <g v-for="node in nodes" :key="node.id">
      <circle :cx="node.x" :cy="node.y" r="9" :fill="node.color" fill-opacity="0.18" />
      <circle :cx="node.x" :cy="node.y" r="4" :fill="node.color" />
      <title>{{ node.label }}</title>
    </g>

    <!-- Center hub: soft halo + crisp core showing the real aggregate. -->
    <circle :cx="cx" :cy="cy" :r="hubR * 1.8" fill="url(#heroRadarGlow)" />
    <circle :cx="cx" :cy="cy" :r="hubR" fill="#0f172a" stroke="#22d3ee" stroke-opacity="0.4" stroke-width="1" />
    <text :x="cx" :y="cy - 4" text-anchor="middle" class="fill-slate-100 text-lg font-semibold">{{ centerValue }}</text>
    <text :x="cx" :y="cy + 14" text-anchor="middle" class="fill-slate-500 text-[9px] uppercase tracking-wider">
      {{ centerLabel }}
    </text>

    <defs>
      <radialGradient id="heroRadarGlow">
        <stop offset="0%" stop-color="#22d3ee" stop-opacity="0.35" />
        <stop offset="100%" stop-color="#22d3ee" stop-opacity="0" />
      </radialGradient>
    </defs>
  </svg>
</template>
