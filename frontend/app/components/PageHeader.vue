<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>();
</script>

<template>
  <div class="border-b border-slate-800 px-8 py-5">
    <h1 class="text-lg font-semibold text-slate-100">{{ title }}</h1>
    <p v-if="subtitle" class="mt-0.5 text-sm text-slate-500">{{ subtitle }}</p>
  </div>
</template>
