<script setup lang="ts">
defineProps<{ phase: string; description: string }>();
</script>

<template>
  <div class="mx-8 mt-6 rounded-lg border border-dashed border-slate-800 bg-slate-900/30 p-8 text-center">
    <p class="text-sm font-medium text-slate-400">{{ phase }}</p>
    <p class="mx-auto mt-2 max-w-md text-sm text-slate-600">{{ description }}</p>
  </div>
</template>
