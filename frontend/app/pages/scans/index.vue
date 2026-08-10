<script setup lang="ts">
interface Job {
  id: string;
  tool: string;
  target: string;
  status: string;
  created_at: string;
}

const { apiFetch } = useApi();
const jobs = ref<Job[]>([]);
const loading = ref(true);

async function loadJobs() {
  loading.value = true;
  try {
    jobs.value = await apiFetch<Job[]>("/api/jobs?limit=100");
  } finally {
    loading.value = false;
  }
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString();
}

onMounted(loadJobs);
</script>

<template>
  <div>
    <PageHeader title="Scans" subtitle="All jobs, most recent first" />

    <div class="px-8 py-6">
      <p v-if="loading" class="text-sm text-slate-600">Loading…</p>
      <p v-else-if="jobs.length === 0" class="text-sm text-slate-600">
        No scans yet. Launch one from the <NuxtLink to="/tools" class="text-emerald-400 hover:underline">Tools</NuxtLink> page.
      </p>

      <div v-else class="overflow-hidden rounded-lg border border-slate-800">
        <table class="w-full text-sm">
          <thead class="bg-slate-900/60 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th class="px-4 py-2">Tool</th>
              <th class="px-4 py-2">Target</th>
              <th class="px-4 py-2">Status</th>
              <th class="px-4 py-2">Created</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-800">
            <tr
              v-for="job in jobs"
              :key="job.id"
              class="cursor-pointer hover:bg-slate-900/40"
              @click="$router.push(`/scans/${job.id}`)"
            >
              <td class="px-4 py-2 font-medium text-slate-200">{{ job.tool }}</td>
              <td class="px-4 py-2 text-slate-400">{{ job.target }}</td>
              <td class="px-4 py-2"><JobStatusBadge :status="job.status" /></td>
              <td class="px-4 py-2 text-slate-500">{{ formatDate(job.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
