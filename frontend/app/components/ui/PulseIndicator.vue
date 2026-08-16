<script setup lang="ts">
// Small pulsing status dot (system-status pill, AI active state). Built on
// Tailwind's own `animate-ping` utility -- transform/opacity only, no
// custom keyframes needed, and it's already covered by main.css's global
// prefers-reduced-motion override.
withDefaults(
  defineProps<{
    tone?: "default" | "accent" | "ai" | "success" | "warning" | "danger";
    active?: boolean;
    size?: "sm" | "md";
  }>(),
  { tone: "default", active: true, size: "md" },
);

const toneDot: Record<string, string> = {
  default: "bg-slate-500",
  accent: "bg-accent-400",
  ai: "bg-ai-400",
  success: "bg-success-400",
  warning: "bg-warning-400",
  danger: "bg-danger-400",
};
</script>

<template>
  <span class="relative inline-flex" :class="size === 'sm' ? 'h-1.5 w-1.5' : 'h-2 w-2'">
    <span
      v-if="active"
      class="absolute inset-0 motion-safe:animate-ping rounded-full opacity-60"
      :class="toneDot[tone]"
      aria-hidden="true"
    />
    <span class="relative inline-block h-full w-full rounded-full" :class="toneDot[tone]" aria-hidden="true" />
  </span>
</template>
