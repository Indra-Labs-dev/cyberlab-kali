<script setup lang="ts">
const props = defineProps<{
  label: string;
  status: "checking" | "ok" | "unreachable" | "error";
  detail?: string;
}>();

const statusColor = computed(() => {
  return {
    checking: "text-amber-400",
    ok: "text-emerald-400",
    unreachable: "text-red-400",
    error: "text-red-400",
  }[props.status];
});
</script>

<template>
  <div class="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
    <p class="text-sm text-slate-500">{{ label }}</p>
    <p class="mt-1 text-lg font-medium" :class="statusColor">{{ status }}</p>
    <p v-if="detail" class="mt-1 truncate text-xs text-slate-600">{{ detail }}</p>
  </div>
</template>
