<script setup lang="ts">
withDefaults(defineProps<{ label?: string; lines?: number }>(), { label: "Loading…", lines: 3 });
</script>

<template>
  <div role="status" :aria-label="label">
    <slot>
      <UiSkeleton :lines="lines" />
    </slot>
  </div>
</template>
