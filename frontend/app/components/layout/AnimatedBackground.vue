<script setup lang="ts">
// Ambient command-center backdrop mounted once behind the app shell:
// three very slow soft glow blobs (transform/opacity only, `motion-safe:`
// gated), a static technical grid, a faint particle field, and a vignette
// for depth toward the edges. Fixed + pointer-events-none so it never
// intercepts clicks or affects layout; -z-10 keeps it strictly behind the
// Sidebar/Topbar/page surfaces, which are all opaque or semi-transparent
// enough to let it show through the gaps between cards.
</script>

<template>
  <div class="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-bg" aria-hidden="true">
    <div
      class="absolute -left-40 -top-40 h-[28rem] w-[28rem] rounded-full bg-accent-500/[0.12] blur-[110px] motion-safe:animate-drift"
    />
    <div
      class="absolute -bottom-48 -right-32 h-[32rem] w-[32rem] rounded-full bg-ai-500/[0.12] blur-[120px] motion-safe:animate-drift-slow"
    />
    <div
      class="absolute left-1/2 top-0 h-80 w-80 -translate-x-1/2 rounded-full bg-danger-500/[0.05] blur-[100px] motion-safe:animate-drift"
      style="animation-duration: 28s"
    />

    <!-- Technical grid: two scales layered for a subtle parallax-like depth cue, static (no motion cost). -->
    <div
      class="absolute inset-0 opacity-[0.035]"
      style="
        background-image:
          linear-gradient(to right, white 1px, transparent 1px),
          linear-gradient(to bottom, white 1px, transparent 1px);
        background-size: 48px 48px;
      "
    />
    <div
      class="absolute inset-0 opacity-[0.02]"
      style="
        background-image:
          linear-gradient(to right, white 1px, transparent 1px),
          linear-gradient(to bottom, white 1px, transparent 1px);
        background-size: 160px 160px;
      "
    />

    <!-- Faint particle field -- a single gradient layer, not individual DOM nodes. -->
    <div
      class="absolute inset-0 opacity-[0.15]"
      style="background-image: radial-gradient(circle, rgba(255, 255, 255, 0.5) 1px, transparent 1px); background-size: 140px 140px"
    />

    <!-- Vignette: darkens toward the edges so the center (main content) reads as the focal plane. -->
    <div class="absolute inset-0" style="background: radial-gradient(ellipse at center, transparent 40%, rgba(2, 6, 23, 0.55) 100%)" />
  </div>
</template>
