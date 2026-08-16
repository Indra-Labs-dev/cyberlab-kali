<script setup lang="ts">
// SOC-lite (docs/roadmap.md §8) -- half of the Dashboard's "Findings
// actifs + changements récents" view. Fully self-contained (own fetch,
// own loading/error state), same pattern as AssetChangeTimeline.vue --
// nothing else on the Dashboard reads this data.
import { onMounted, ref } from "vue";
import { useApi } from "~/composables/useApi";
import { RISK_PRIORITY_COLORS } from "~/constants/colors";
import type { Finding } from "~/types/finding";

const { apiFetch } = useApi();

const findings = ref<Finding[]>([]);
const loading = ref(true);
const error = ref("");

async function load() {
  loading.value = true;
  error.value = "";
  try {
    findings.value = await apiFetch<Finding[]>("/api/findings?active_only=true&sort=risk_score_desc&limit=8");
  } catch (err: any) {
    error.value = err?.data?.detail || "Failed to load active findings";
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
    <div class="mb-3 flex items-center justify-between">
      <h2 class="text-sm font-semibold text-slate-300">Active findings</h2>
      <NuxtLink to="/findings" class="text-xs text-emerald-400 hover:underline">View all</NuxtLink>
    </div>
    <LoadingState v-if="loading" />
    <p v-else-if="error" class="text-sm text-red-400">{{ error }}</p>
    <p v-else-if="findings.length === 0" class="text-sm text-slate-600">No active findings right now.</p>
    <ul v-else class="space-y-2">
      <li v-for="f in findings" :key="f.id">
        <NuxtLink
          :to="`/findings/${f.id}`"
          class="flex items-center gap-3 rounded-md border border-slate-800 bg-slate-950/50 px-3 py-2 hover:bg-slate-900"
        >
          <span
            class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold"
            :class="RISK_PRIORITY_COLORS[f.risk_priority || 'INFORMATIONAL']"
          >
            {{ f.risk_score ?? "—" }}
          </span>
          <div class="min-w-0 flex-1 text-sm">
            <span class="font-medium text-slate-200">{{ f.title }}</span>
            <span class="ml-2 text-slate-500">{{ f.target }}</span>
          </div>
        </NuxtLink>
      </li>
    </ul>
  </div>
</template>
