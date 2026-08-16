<script setup lang="ts">
withDefaults(defineProps<{ lines?: number; height?: string }>(), { lines: 3, height: "0.875rem" });
</script>

<template>
  <div class="space-y-2" role="status" aria-label="Loading">
    <div
      v-for="i in lines"
      :key="i"
      class="relative overflow-hidden rounded bg-slate-800/60"
      :style="{ height }"
      :class="lines > 1 && i === lines ? 'w-2/3' : 'w-full'"
    >
      <div class="absolute inset-0 motion-safe:animate-shimmer-sweep bg-gradient-to-r from-transparent via-slate-600/40 to-transparent" />
    </div>
  </div>
</template>
