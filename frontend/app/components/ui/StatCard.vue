<script setup lang="ts">
import { computed, type Component } from "vue";

// Overview-row metric tile (Assets, Active Jobs, Critical Findings, ...).
// Deliberately has no trend/delta prop -- there's no time-series endpoint
// backing a "+3% vs last hour" figure, so this only ever shows a value the
// backend actually returned, plus an optional real `hint` string. The
// count-up (AnimatedMetric) is the honest substitute for a fake trend
// arrow: it's driven by the real value going from 0 (before the first
// fetch resolves) to whatever the backend returned.
const props = withDefaults(
  defineProps<{
    label: string;
    value: number;
    icon?: Component;
    tone?: "default" | "accent" | "ai" | "success" | "warning" | "danger";
    hint?: string;
    to?: string;
    delay?: number;
    // Static (non-animated -- see the visual pass's explicit "no permanent
    // animation" rule) glow for a card that represents something actually
    // urgent right now (e.g. Critical Findings when the count is > 0).
    // Never set unconditionally -- always tied to the real value.
    alert?: boolean;
  }>(),
  { tone: "default", delay: 0, alert: false },
);

const toneIcon: Record<string, string> = {
  default: "text-slate-300 bg-slate-800/60",
  accent: "text-accent-400 bg-accent-500/10",
  ai: "text-ai-400 bg-ai-500/10",
  success: "text-success-400 bg-success-500/10",
  warning: "text-warning-400 bg-warning-500/10",
  danger: "text-danger-400 bg-danger-500/10",
};

// Literal strings so Tailwind's scanner sees them (see Card.vue's same
// note) -- a faint radial tint in the tone color, and a matching hover
// glow, kept subtle: opacity is low and only 2 of 5 stat cards on the
// Dashboard actually use a non-default tone, so it stays a rare accent
// rather than "an interface that looks like a rainbow".
const toneBg: Record<string, string> = {
  default: "",
  accent: "bg-[radial-gradient(circle_at_top_right,theme(colors.accent.500/12%),transparent_65%)]",
  ai: "bg-[radial-gradient(circle_at_top_right,theme(colors.ai.500/12%),transparent_65%)]",
  success: "bg-[radial-gradient(circle_at_top_right,theme(colors.success.500/12%),transparent_65%)]",
  warning: "bg-[radial-gradient(circle_at_top_right,theme(colors.warning.500/12%),transparent_65%)]",
  danger: "bg-[radial-gradient(circle_at_top_right,theme(colors.danger.500/12%),transparent_65%)]",
};

const toneHoverGlow: Record<string, string> = {
  default: "hover:border-slate-600",
  accent: "hover:border-accent-500/40 hover:shadow-glow-accent",
  ai: "hover:border-ai-500/40 hover:shadow-glow-ai",
  success: "hover:border-success-500/40 hover:shadow-glow-success",
  warning: "hover:border-warning-500/40 hover:shadow-glow-warning",
  danger: "hover:border-danger-500/40 hover:shadow-glow-danger",
};

const rootClasses = computed(() => [
  "motion-safe:animate-fade-slide-up block overflow-hidden rounded-lg border border-border bg-surface/40 p-4 transition-all duration-300",
  toneBg[props.tone],
  props.to && toneHoverGlow[props.tone],
  props.alert && "border-danger-500/30 shadow-glow-danger",
]);
</script>

<template>
  <!-- NuxtLink is a Nuxt compiler-injected component: resolving it
       dynamically via `:is="'NuxtLink'"` (a string) silently renders an
       inert <nuxtlink> custom element instead of an <a>, no console
       warning -- see Button.vue's docstring. Two branches, same as there. -->
  <NuxtLink v-if="to" :to="to" :class="rootClasses" :style="{ animationDelay: `${delay}ms` }">
    <div class="flex items-center justify-between">
      <p class="text-xs font-medium uppercase tracking-wide text-slate-500">{{ label }}</p>
      <span v-if="icon" class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md" :class="toneIcon[tone]">
        <component :is="icon" class="h-4 w-4" aria-hidden="true" />
      </span>
    </div>
    <p class="mt-2 text-2xl font-semibold tabular-nums text-slate-100">
      <UiAnimatedMetric :value="value" />
    </p>
    <p v-if="hint" class="mt-1 text-xs text-slate-500">{{ hint }}</p>
  </NuxtLink>
  <div v-else :class="rootClasses" :style="{ animationDelay: `${delay}ms` }">
    <div class="flex items-center justify-between">
      <p class="text-xs font-medium uppercase tracking-wide text-slate-500">{{ label }}</p>
      <span v-if="icon" class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md" :class="toneIcon[tone]">
        <component :is="icon" class="h-4 w-4" aria-hidden="true" />
      </span>
    </div>
    <p class="mt-2 text-2xl font-semibold tabular-nums text-slate-100">
      <UiAnimatedMetric :value="value" />
    </p>
    <p v-if="hint" class="mt-1 text-xs text-slate-500">{{ hint }}</p>
  </div>
</template>
