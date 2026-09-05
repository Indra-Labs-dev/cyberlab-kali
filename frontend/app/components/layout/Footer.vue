<script setup lang="ts">
// Fixed branding bar (reference image + the community clone both anchor
// one at the bottom) -- pure tagline copy, no operational data, so nothing
// here needs to be real/fake-checked the way a metric would.
import { ShieldHalf } from "@lucide/vue";
</script>

<template>
  <footer
    class="fixed inset-x-0 bottom-0 z-20 hidden border-t border-white/5 bg-surface/80 py-2 text-center backdrop-blur-xl md:block"
    style="box-shadow: 0 -12px 40px -24px rgba(34, 211, 238, 0.5)"
  >
    <p class="flex flex-wrap items-center justify-center gap-2 font-display text-sm font-bold text-slate-200">
      <ShieldHalf class="h-4 w-4 text-accent-400" aria-hidden="true" />
      CyberLab — <span class="text-accent-400">Staying ahead of the threats</span>
    </p>
    <p class="text-xs text-slate-500">AI · Automation · Collective Intelligence · Proactive Security</p>
  </footer>
</template>
