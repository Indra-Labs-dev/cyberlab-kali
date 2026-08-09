<script setup lang="ts">
const { apiBase, wsBase } = useApi();
</script>

<template>
  <div>
    <PageHeader title="Settings" subtitle="Runtime configuration" />

    <div class="max-w-xl space-y-4 px-8 py-6">
      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <p class="text-xs text-slate-500">API base URL</p>
        <p class="mt-1 font-mono text-sm text-slate-300">{{ apiBase }}</p>
      </div>
      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <p class="text-xs text-slate-500">WebSocket base URL</p>
        <p class="mt-1 font-mono text-sm text-slate-300">{{ wsBase }}</p>
      </div>
      <p class="text-xs text-slate-600">
        Set via <code class="rounded bg-slate-800 px-1 py-0.5">NUXT_PUBLIC_API_BASE</code> /
        <code class="rounded bg-slate-800 px-1 py-0.5">NUXT_PUBLIC_WS_BASE</code> in
        <code class="rounded bg-slate-800 px-1 py-0.5">docker-compose.yml</code>.
      </p>
    </div>
  </div>
</template>
