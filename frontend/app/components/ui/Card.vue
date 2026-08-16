<script setup lang="ts">
// The `rounded-lg border border-slate-800 bg-slate-900/40 p-4` shell
// repeated verbatim across ~10 existing widgets, formalized with the new
// surface/border tokens plus the header row (title/subtitle + actions
// slot, e.g. a "View all" link) that pattern always paired it with.
//
// `glow`/`glass`/`interactive` cover what the visual pass asked for as
// separate GlowCard/GlassCard primitives -- kept as props on one component
// instead, since a GlowCard and a GlassCard would otherwise be two copies
// of the exact same header/slot markup with a different class list.
withDefaults(
  defineProps<{
    title?: string;
    subtitle?: string;
    padded?: boolean;
    glow?: "none" | "accent" | "ai" | "success" | "warning" | "danger";
    glass?: boolean;
    interactive?: boolean;
    // Ambient light sweep (§6/§12 of the visual pass: "la section IA peut
    // avoir une animation ambiante ... gradient vivant"). Opt-in and
    // reserved for the one section that's actually meant to feel like a
    // living intelligence layer -- not a generic decoration for every
    // card, which is exactly the "tout qui bouge" the same brief warns
    // against.
    ambient?: boolean;
  }>(),
  { padded: true, glow: "none", glass: false, interactive: false, ambient: false },
);

// Literal class strings (not template-built) so Tailwind's content scanner
// picks them up -- `shadow-glow-${tone}` interpolation wouldn't be seen at
// build time. Each tone also gets a faint interior wash so a card reads as
// having a color *identity* (Security=cyan, Risk=danger, AI=violet,
// System=success), not just a border tint on hover.
const glowClass: Record<string, string> = {
  none: "",
  accent: "shadow-glow-accent border-accent-500/20 bg-[radial-gradient(circle_at_top_left,theme(colors.accent.500/8%),transparent_60%)]",
  ai: "shadow-glow-ai border-ai-500/20 bg-[radial-gradient(circle_at_top_left,theme(colors.ai.500/10%),transparent_60%)]",
  success: "shadow-glow-success border-success-500/20 bg-[radial-gradient(circle_at_top_left,theme(colors.success.500/8%),transparent_60%)]",
  warning: "shadow-glow-warning border-warning-500/20 bg-[radial-gradient(circle_at_top_left,theme(colors.warning.500/8%),transparent_60%)]",
  danger: "shadow-glow-danger border-danger-500/20 bg-[radial-gradient(circle_at_top_left,theme(colors.danger.500/8%),transparent_60%)]",
};
</script>

<template>
  <div
    class="relative overflow-hidden rounded-lg border shadow-lg shadow-black/20 transition-all duration-300 before:pointer-events-none before:absolute before:inset-x-0 before:top-0 before:h-px before:bg-gradient-to-r before:from-transparent before:via-white/10 before:to-transparent"
    :class="[
      glass ? 'border-slate-700/50 bg-slate-900/30 backdrop-blur-md' : 'border-border bg-surface/40',
      padded && 'p-4',
      glow !== 'none' && glowClass[glow],
      interactive && 'hover:-translate-y-0.5 hover:border-slate-600',
    ]"
  >
    <div
      v-if="ambient"
      class="pointer-events-none absolute inset-0 motion-safe:animate-light-sweep bg-[length:200%_100%] opacity-40"
      style="background-image: linear-gradient(75deg, transparent 40%, rgba(167, 139, 250, 0.08) 50%, transparent 60%)"
      aria-hidden="true"
    />
    <div v-if="title || subtitle || $slots.actions" class="relative mb-3 flex items-center justify-between gap-3">
      <div class="min-w-0">
        <h2 v-if="title" class="truncate text-sm font-semibold text-slate-300">{{ title }}</h2>
        <p v-if="subtitle" class="mt-0.5 text-xs text-slate-500">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="flex shrink-0 items-center gap-2">
        <slot name="actions" />
      </div>
    </div>
    <div class="relative"><slot /></div>
  </div>
</template>
