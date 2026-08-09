<script setup lang="ts">
const config = useRuntimeConfig();
const status = ref<"checking" | "ok" | "error">("checking");
const dbStatus = ref<"checking" | "ok" | "error">("checking");

async function checkHealth() {
  try {
    await $fetch(`${config.public.apiBase}/api/health`);
    status.value = "ok";
  } catch {
    status.value = "error";
  }
  try {
    await $fetch(`${config.public.apiBase}/api/health/db`);
    dbStatus.value = "ok";
  } catch {
    dbStatus.value = "error";
  }
}

onMounted(checkHealth);
</script>

<template>
  <main class="mx-auto flex min-h-screen max-w-3xl flex-col items-start justify-center gap-6 px-6">
    <div class="flex items-center gap-3">
      <span class="h-2 w-2 rounded-full bg-emerald-500"></span>
      <h1 class="text-2xl font-semibold tracking-tight text-emerald-400">CyberLab</h1>
    </div>
    <p class="text-slate-400">Cybersecurity Workbench — Phase 1 Foundation</p>

    <div class="grid w-full grid-cols-1 gap-4 sm:grid-cols-2">
      <div class="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
        <p class="text-sm text-slate-500">API</p>
        <p
          class="text-lg font-medium"
          :class="{
            'text-amber-400': status === 'checking',
            'text-emerald-400': status === 'ok',
            'text-red-400': status === 'error',
          }"
        >
          {{ status }}
        </p>
      </div>
      <div class="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
        <p class="text-sm text-slate-500">Database</p>
        <p
          class="text-lg font-medium"
          :class="{
            'text-amber-400': dbStatus === 'checking',
            'text-emerald-400': dbStatus === 'ok',
            'text-red-400': dbStatus === 'error',
          }"
        >
          {{ dbStatus }}
        </p>
      </div>
    </div>
  </main>
</template>
