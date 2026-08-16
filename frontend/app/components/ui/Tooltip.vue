<script setup lang="ts">
// Minimal hover/focus tooltip for icon-only controls (topbar buttons).
// CSS-only (group-hover), no positioning library.
defineProps<{ label: string }>();
</script>

<template>
  <span class="group relative inline-flex">
    <slot />
    <span
      role="tooltip"
      class="pointer-events-none absolute left-1/2 top-full z-50 mt-2 -translate-x-1/2 whitespace-nowrap rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200 opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
    >
      {{ label }}
    </span>
  </span>
</template>
