<script setup lang="ts">
import type { Crumb } from "~/components/ui/Breadcrumbs.vue";

defineProps<{ title: string; subtitle?: string; breadcrumbs?: Crumb[] }>();
</script>

<template>
  <div class="flex flex-col gap-3 border-b border-slate-800 px-8 py-5 sm:flex-row sm:items-center sm:justify-between">
    <div class="min-w-0">
      <UiBreadcrumbs v-if="breadcrumbs && breadcrumbs.length" :items="breadcrumbs" class="mb-1.5" />
      <h1 class="text-lg font-semibold text-slate-100">{{ title }}</h1>
      <p v-if="subtitle" class="mt-0.5 text-sm text-slate-500">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.actions" class="flex shrink-0 items-center gap-2">
      <slot name="actions" />
    </div>
  </div>
</template>
