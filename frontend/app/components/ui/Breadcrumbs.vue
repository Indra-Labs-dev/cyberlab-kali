<script setup lang="ts">
export interface Crumb {
  label: string;
  to?: string;
}

defineProps<{ items: Crumb[] }>();
</script>

<template>
  <nav aria-label="Breadcrumb" class="flex items-center gap-1.5 text-xs text-slate-500">
    <template v-for="(crumb, i) in items" :key="`${crumb.label}-${i}`">
      <NuxtLink v-if="crumb.to" :to="crumb.to" class="hover:text-slate-300 hover:underline">{{ crumb.label }}</NuxtLink>
      <span v-else class="text-slate-400">{{ crumb.label }}</span>
      <span v-if="i < items.length - 1" aria-hidden="true">/</span>
    </template>
  </nav>
</template>
