<script setup lang="ts">
const props = defineProps<{ status: string }>();

const classes = computed(() => {
  return (
    {
      QUEUED: "bg-slate-700/50 text-slate-300",
      RUNNING: "bg-amber-500/15 text-amber-400",
      SUCCESS: "bg-emerald-500/15 text-emerald-400",
      FAILED: "bg-red-500/15 text-red-400",
      CANCELLED: "bg-slate-700/50 text-slate-500",
    }[props.status] || "bg-slate-700/50 text-slate-300"
  );
});
</script>

<template>
  <span class="rounded px-2 py-0.5 text-xs font-medium" :class="classes">{{ status }}</span>
</template>
