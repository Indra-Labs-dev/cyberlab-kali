<script setup lang="ts">
// Deliberately does not impose a retry behavior -- the `action` slot is
// only rendered when a caller provides one (e.g. a "Retry" button or a
// NuxtLink to where the data comes from), pages without a meaningful
// retry action just use the default slot/`message` prop, same as the
// plain <p> they replace.
defineProps<{ message?: string }>();
</script>

<template>
  <div>
    <p class="text-sm text-slate-600"><slot>{{ message }}</slot></p>
    <div v-if="$slots.action" class="mt-2">
      <slot name="action" />
    </div>
  </div>
</template>
