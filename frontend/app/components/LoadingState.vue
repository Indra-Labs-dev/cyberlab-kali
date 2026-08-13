<script setup lang="ts">
withDefaults(defineProps<{ label?: string }>(), { label: "Loading…" });
</script>

<template>
  <p class="text-sm text-slate-600"><slot>{{ label }}</slot></p>
</template>
