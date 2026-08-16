<script setup lang="ts">
// Standardizes the inline `<p class="text-red-400">{{ error }}</p>`
// pattern repeated in every self-contained fetch widget.
defineProps<{ message?: string }>();
</script>

<template>
  <p class="flex items-center gap-1.5 text-sm text-danger-400">
    <span aria-hidden="true">⚠</span>
    <slot>{{ message }}</slot>
  </p>
</template>
