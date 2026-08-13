<script setup lang="ts">
// Explicit imports (not just Nuxt auto-import) so this component stays
// mountable in plain Vitest -- see IntelligenceSyncStatus.test.ts and the
// same pattern in app/composables/useAssets.ts.
import { onBeforeUnmount, onMounted, ref } from "vue";
import { useApi } from "~/composables/useApi";
import type { IntelSyncState } from "~/types/intelligence";

const { apiFetch } = useApi();

const sources = ref<IntelSyncState[]>([]);
const loading = ref(true);
const error = ref("");
const syncing = ref(false);
const syncError = ref("");

// POST /api/intelligence/sync is fire-and-forget through the RQ queue
// (backend/app/api/routes/intelligence.py returns 202 immediately, no
// job-status endpoint to subscribe to -- unlike a scan Job's WebSocket
// channel). The only observable signal that a sync actually ran is
// GET /api/intelligence/status advancing last_attempt_at past the moment
// sync was triggered, so this polls that existing endpoint a bounded
// number of times rather than indefinitely -- a source can keep
// erroring/retrying forever in an offline sandbox (as it does in this
// project's own dev stack today), so there is no universal "done" signal
// to wait for.
const MAX_POLLS = 12;
const POLL_INTERVAL_MS = 5000;
let pollTimer: ReturnType<typeof setTimeout> | undefined;
let pollCount = 0;
let triggeredAt = 0;

async function loadStatus() {
  loading.value = true;
  error.value = "";
  try {
    sources.value = await apiFetch<IntelSyncState[]>("/api/intelligence/status");
  } catch (err: any) {
    error.value = err?.data?.detail || "Failed to load intelligence status";
  } finally {
    loading.value = false;
  }
}

function stopPolling() {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = undefined;
  syncing.value = false;
}

// A source counts as resolved only once its attempt has actually finished
// (success or error recorded at/after the attempt), not merely started --
// last_attempt_at is written before the sync call runs (see
// backend/app/intel/sync.py), so checking last_attempt_at alone can catch a
// source mid-flight and stop polling while it's still showing the
// *previous* run's last_error.
function sourceResolved(s: IntelSyncState): boolean {
  if (s.last_attempt_at === null) return false;
  const attemptTime = new Date(s.last_attempt_at).getTime();
  if (attemptTime < triggeredAt) return false;
  if (s.last_error) return true;
  return s.last_success_at !== null && new Date(s.last_success_at).getTime() >= attemptTime;
}

async function pollOnce() {
  pollCount += 1;
  await loadStatus();
  const allResolved = sources.value.length > 0 && sources.value.every(sourceResolved);
  if (allResolved || pollCount >= MAX_POLLS) {
    stopPolling();
    return;
  }
  pollTimer = setTimeout(pollOnce, POLL_INTERVAL_MS);
}

async function triggerSync() {
  syncing.value = true;
  syncError.value = "";
  pollCount = 0;
  triggeredAt = Date.now();
  try {
    await apiFetch("/api/intelligence/sync", { method: "POST" });
  } catch (err: any) {
    syncError.value = err?.data?.detail || "Failed to trigger sync";
    syncing.value = false;
    return;
  }
  pollTimer = setTimeout(pollOnce, POLL_INTERVAL_MS);
}

function sourceState(s: IntelSyncState): "never" | "error" | "ok" {
  if (!s.last_success_at && !s.last_error) return "never";
  if (s.last_error) return "error";
  return "ok";
}

onMounted(loadStatus);
onBeforeUnmount(stopPolling);

defineExpose({ triggerSync, loadStatus });
</script>

<template>
  <div>
    <div class="mb-3 flex items-center justify-between">
      <h2 class="text-sm font-semibold text-slate-300">Sync status</h2>
      <button
        type="button"
        class="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
        :disabled="syncing"
        @click="triggerSync"
      >
        {{ syncing ? "Syncing…" : "Sync now" }}
      </button>
    </div>

    <p v-if="syncError" class="mb-2 text-xs text-red-400" role="alert">{{ syncError }}</p>

    <LoadingState v-if="loading" />
    <p v-else-if="error" class="text-sm text-red-400" role="alert">{{ error }}</p>
    <EmptyState v-else-if="sources.length === 0" message="No intelligence sources reported yet." />

    <div v-else class="space-y-2">
      <div v-for="s in sources" :key="s.source" class="rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-xs">
        <div class="flex items-center justify-between">
          <span class="font-medium text-slate-200">{{ s.source }}</span>
          <Badge
            :color-class="
              sourceState(s) === 'ok'
                ? 'bg-emerald-500/15 text-emerald-400'
                : sourceState(s) === 'error'
                  ? 'bg-red-500/15 text-red-400'
                  : 'bg-slate-700/50 text-slate-300'
            "
            size="sm"
          >
            {{ sourceState(s) === "ok" ? "OK" : sourceState(s) === "error" ? "Error" : "Never synced" }}
          </Badge>
        </div>
        <p class="mt-1 text-slate-500">
          Last attempt: {{ s.last_attempt_at ? new Date(s.last_attempt_at).toLocaleString() : "—" }} · Last success:
          {{ s.last_success_at ? new Date(s.last_success_at).toLocaleString() : "—" }}
        </p>
        <p v-if="s.last_error" class="mt-1 text-red-400">{{ s.last_error }}</p>
        <p v-if="Object.keys(s.details).length" class="mt-1 text-slate-600">
          <span v-for="(v, k) in s.details" :key="k" class="mr-2">{{ k }}: {{ v }}</span>
        </p>
      </div>
    </div>
  </div>
</template>
