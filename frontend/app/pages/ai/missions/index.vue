<script setup lang="ts">
// Phase 18 -- Missions (Level 2 autonomy: approve a fixed plan, then it
// executes one re-validated step at a time), Correlation Agent suggestions,
// and the Report Agent proposal flow. Distinct from the existing Mission
// Planner on /ai (which only proposes a plan and runs steps one at a time
// manually via POST /api/jobs) -- a Mission here is a persisted, stateful
// entity with its own lifecycle (DRAFT/APPROVED/RUNNING/COMPLETED/FAILED/
// CANCELLED), approved once and then progresses on its own.
import { onBeforeUnmount, onMounted, ref } from "vue";
import { useApi } from "~/composables/useApi";
import { useAssets } from "~/composables/useAssets";
import { useMissions } from "~/composables/useMissions";
import { useProjects } from "~/composables/useProjects";
import type { Asset } from "~/types/asset";
import type { Finding } from "~/types/finding";
import type { AICorrelationSuggestion, Mission, ReportProposal } from "~/types/mission";
import type { Project } from "~/types/project";

const { apiFetch } = useApi();
const { listAssets } = useAssets();
const { listProjects } = useProjects();
const {
  listMissions,
  getMission,
  createMission,
  approveMission,
  cancelMission,
  generateCorrelationSuggestions,
  listCorrelationSuggestions,
  acceptCorrelationSuggestion,
  dismissCorrelationSuggestion,
  proposeReport,
} = useMissions();

// --- Target context (shared by Missions and Correlation Suggestions) ---
const assets = ref<Asset[]>([]);
const activeTargetId = ref("");

function targetLabel(a: Asset) {
  const address = a.url || a.hostname || a.ip_address || "—";
  return `${a.name} (${address}) — ${a.authorization_status}`;
}

// --- Missions ---
const missions = ref<Mission[]>([]);
const missionsLoading = ref(false);
const missionsError = ref("");
const goal = ref("");
const maxSteps = ref(10);
const creating = ref(false);
const busyMissionId = ref<string | null>(null);

// Bounded polling for RUNNING missions -- same idiom as
// IntelligenceSyncStatus.vue: a mission can plausibly stay RUNNING for a
// while (each step is a real tool run), there is no push channel for
// Mission progress, so this polls GET /api/ai/missions/{id} a bounded
// number of times rather than indefinitely.
const MAX_POLLS = 30;
const POLL_INTERVAL_MS = 4000;
const pollTimers = new Map<string, ReturnType<typeof setTimeout>>();
const pollCounts = new Map<string, number>();

function stopPolling(missionId: string) {
  const timer = pollTimers.get(missionId);
  if (timer) clearTimeout(timer);
  pollTimers.delete(missionId);
  pollCounts.delete(missionId);
}

function pollMission(missionId: string) {
  stopPolling(missionId);
  const tick = async () => {
    const count = (pollCounts.get(missionId) || 0) + 1;
    pollCounts.set(missionId, count);
    try {
      const updated = await getMission(missionId);
      const index = missions.value.findIndex((m) => m.id === missionId);
      if (index !== -1) missions.value[index] = updated;
      if (updated.status !== "RUNNING" || count >= MAX_POLLS) {
        stopPolling(missionId);
        return;
      }
    } catch {
      stopPolling(missionId);
      return;
    }
    pollTimers.set(missionId, setTimeout(tick, POLL_INTERVAL_MS));
  };
  pollTimers.set(missionId, setTimeout(tick, POLL_INTERVAL_MS));
}

async function loadMissions() {
  if (!activeTargetId.value) {
    missions.value = [];
    return;
  }
  missionsLoading.value = true;
  missionsError.value = "";
  try {
    missions.value = await listMissions(activeTargetId.value);
    for (const mission of missions.value) {
      if (mission.status === "RUNNING") pollMission(mission.id);
    }
  } catch (err: any) {
    missionsError.value = err?.data?.detail || "Failed to load missions";
  } finally {
    missionsLoading.value = false;
  }
}

async function submitCreateMission() {
  if (!activeTargetId.value || !goal.value.trim()) return;
  creating.value = true;
  missionsError.value = "";
  try {
    const mission = await createMission(activeTargetId.value, goal.value.trim(), maxSteps.value);
    missions.value.unshift(mission);
    goal.value = "";
  } catch (err: any) {
    missionsError.value = err?.data?.detail || "Failed to create mission";
  } finally {
    creating.value = false;
  }
}

async function onApprove(mission: Mission) {
  busyMissionId.value = mission.id;
  try {
    const updated = await approveMission(mission.id);
    const index = missions.value.findIndex((m) => m.id === mission.id);
    if (index !== -1) missions.value[index] = updated;
    if (updated.status === "RUNNING") pollMission(mission.id);
  } catch (err: any) {
    missionsError.value = err?.data?.detail || "Failed to approve mission";
  } finally {
    busyMissionId.value = null;
  }
}

async function onCancel(mission: Mission) {
  busyMissionId.value = mission.id;
  try {
    const updated = await cancelMission(mission.id);
    const index = missions.value.findIndex((m) => m.id === mission.id);
    if (index !== -1) missions.value[index] = updated;
    stopPolling(mission.id);
  } catch (err: any) {
    missionsError.value = err?.data?.detail || "Failed to cancel mission";
  } finally {
    busyMissionId.value = null;
  }
}

// --- Correlation Suggestions ---
const findings = ref<Finding[]>([]);
const findingTitle = (id: string) => findings.value.find((f) => f.id === id)?.title || id;
const suggestions = ref<AICorrelationSuggestion[]>([]);
const suggestionsLoading = ref(false);
const suggestionsGenerating = ref(false);
const suggestionsError = ref("");
const busySuggestionId = ref<string | null>(null);

async function loadSuggestions() {
  if (!activeTargetId.value) {
    suggestions.value = [];
    findings.value = [];
    return;
  }
  suggestionsLoading.value = true;
  suggestionsError.value = "";
  try {
    [findings.value, suggestions.value] = await Promise.all([
      apiFetch<Finding[]>(`/api/findings?target_id=${encodeURIComponent(activeTargetId.value)}`),
      listCorrelationSuggestions(activeTargetId.value),
    ]);
  } catch (err: any) {
    suggestionsError.value = err?.data?.detail || "Failed to load correlation suggestions";
  } finally {
    suggestionsLoading.value = false;
  }
}

async function onGenerateSuggestions() {
  if (!activeTargetId.value) return;
  suggestionsGenerating.value = true;
  suggestionsError.value = "";
  try {
    suggestions.value = await generateCorrelationSuggestions(activeTargetId.value);
  } catch (err: any) {
    suggestionsError.value = err?.data?.detail || "Failed to generate correlation suggestions";
  } finally {
    suggestionsGenerating.value = false;
  }
}

async function onAcceptSuggestion(suggestion: AICorrelationSuggestion) {
  busySuggestionId.value = suggestion.id;
  try {
    const updated = await acceptCorrelationSuggestion(suggestion.id);
    const index = suggestions.value.findIndex((s) => s.id === suggestion.id);
    if (index !== -1) suggestions.value[index] = updated;
  } catch (err: any) {
    suggestionsError.value = err?.data?.detail || "Failed to accept suggestion";
  } finally {
    busySuggestionId.value = null;
  }
}

async function onDismissSuggestion(suggestion: AICorrelationSuggestion) {
  busySuggestionId.value = suggestion.id;
  try {
    const updated = await dismissCorrelationSuggestion(suggestion.id);
    const index = suggestions.value.findIndex((s) => s.id === suggestion.id);
    if (index !== -1) suggestions.value[index] = updated;
  } catch (err: any) {
    suggestionsError.value = err?.data?.detail || "Failed to dismiss suggestion";
  } finally {
    busySuggestionId.value = null;
  }
}

// --- Report proposal ---
const projects = ref<Project[]>([]);
const activeProjectId = ref("");
const proposing = ref(false);
const proposeError = ref("");
const proposal = ref<ReportProposal | null>(null);
const generatingReport = ref(false);
const generateError = ref("");
const generatedReportId = ref("");

async function onProposeReport() {
  if (!activeProjectId.value) return;
  proposing.value = true;
  proposeError.value = "";
  proposal.value = null;
  try {
    proposal.value = await proposeReport(activeProjectId.value);
  } catch (err: any) {
    proposeError.value = err?.data?.detail || "Failed to propose a report";
  } finally {
    proposing.value = false;
  }
}

function toggleProposedJob(jobId: string) {
  if (!proposal.value) return;
  const jobIds = proposal.value.job_ids;
  const index = jobIds.indexOf(jobId);
  if (index === -1) jobIds.push(jobId);
  else jobIds.splice(index, 1);
}

async function onGenerateFromProposal() {
  if (!proposal.value || proposal.value.job_ids.length === 0) return;
  generatingReport.value = true;
  generateError.value = "";
  generatedReportId.value = "";
  try {
    // Human-approved proposal -> the exact same, untouched POST /api/reports
    // real reports have always used -- the agent never generates anything
    // itself.
    const report = await apiFetch<{ id: string }>("/api/reports", {
      method: "POST",
      body: { title: proposal.value.title, job_ids: proposal.value.job_ids, format: "html" },
    });
    generatedReportId.value = report.id;
  } catch (err: any) {
    generateError.value = err?.data?.detail || "Failed to generate report";
  } finally {
    generatingReport.value = false;
  }
}

watch(activeTargetId, () => {
  loadMissions();
  loadSuggestions();
});

onMounted(async () => {
  const [loadedAssets, loadedProjects] = await Promise.all([listAssets(), listProjects()]);
  assets.value = loadedAssets;
  projects.value = loadedProjects;
  const preselect = useRoute().query.target_id;
  if (typeof preselect === "string" && assets.value.some((a) => a.id === preselect)) {
    activeTargetId.value = preselect;
  }
});

onBeforeUnmount(() => {
  for (const missionId of Array.from(pollTimers.keys())) stopPolling(missionId);
});
</script>

<template>
  <div>
    <PageHeader
      title="AI Missions"
      subtitle="Approve a plan once — it then executes one re-validated step at a time"
    />

    <div class="px-8 pt-6">
      <label class="mb-1 block text-xs text-slate-500">Target</label>
      <select
        v-model="activeTargetId"
        class="w-full max-w-md rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200"
      >
        <option value="">Select a target to view/create missions and correlation suggestions</option>
        <option v-for="a in assets" :key="a.id" :value="a.id">{{ targetLabel(a) }}</option>
      </select>
    </div>

    <div class="grid grid-cols-1 gap-6 px-8 py-6 xl:grid-cols-2">
      <!-- Missions -->
      <section class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-3 text-sm font-semibold text-slate-300">Missions</h2>

        <form v-if="activeTargetId" class="mb-4 space-y-2" @submit.prevent="submitCreateMission">
          <input
            v-model="goal"
            type="text"
            placeholder="Goal, e.g. find open web services and check for common vulnerabilities"
            class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600"
          />
          <div class="flex items-center gap-2">
            <label class="text-xs text-slate-500">Max steps</label>
            <input
              v-model.number="maxSteps"
              type="number"
              min="1"
              max="50"
              class="w-20 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200"
            />
            <button
              type="submit"
              class="ml-auto rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
              :disabled="creating || !goal.trim()"
            >
              {{ creating ? "Proposing…" : "Propose mission" }}
            </button>
          </div>
        </form>
        <EmptyState v-else message="Select a target to create a mission." />

        <p v-if="missionsError" class="mb-2 text-sm text-red-400">{{ missionsError }}</p>
        <LoadingState v-if="missionsLoading" />
        <EmptyState v-else-if="activeTargetId && missions.length === 0" message="No missions for this target yet." />

        <div v-if="missions.length" class="space-y-3">
          <div v-for="mission in missions" :key="mission.id" class="rounded-md border border-slate-800 bg-slate-950/50 p-3">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="truncate text-sm font-medium text-slate-200">{{ mission.goal }}</p>
                <p class="mt-0.5 text-xs text-slate-600">
                  {{ mission.steps.length }} step(s) · max {{ mission.max_steps }}
                </p>
              </div>
              <div class="flex shrink-0 items-center gap-2">
                <MissionStatusBadge :status="mission.status" />
                <button
                  v-if="mission.status === 'DRAFT'"
                  class="rounded-md border border-emerald-700 px-2.5 py-1 text-xs text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-50"
                  :disabled="busyMissionId === mission.id"
                  @click="onApprove(mission)"
                >
                  Approve
                </button>
                <button
                  v-if="!['COMPLETED', 'FAILED', 'CANCELLED'].includes(mission.status)"
                  class="rounded-md border border-red-800 px-2.5 py-1 text-xs text-red-400 hover:bg-red-500/10 disabled:opacity-50"
                  :disabled="busyMissionId === mission.id"
                  @click="onCancel(mission)"
                >
                  Cancel
                </button>
              </div>
            </div>

            <ol class="mt-3 space-y-1.5">
              <li
                v-for="step in mission.steps"
                :key="step.id"
                class="flex items-start justify-between gap-2 rounded border border-slate-800/70 bg-slate-900/40 px-2 py-1.5"
              >
                <div class="min-w-0">
                  <p class="truncate text-xs text-slate-300">{{ step.step_order + 1 }}. {{ step.label }}</p>
                  <p v-if="step.skip_reason" class="mt-0.5 text-xs text-slate-600">{{ step.skip_reason }}</p>
                </div>
                <MissionStepStatusBadge :status="step.status" />
              </li>
            </ol>
          </div>
        </div>
      </section>

      <!-- Correlation Suggestions -->
      <section class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-3 text-sm font-semibold text-slate-300">Correlation Suggestions</h2>
        <p class="mb-3 text-xs text-slate-500">
          AI-proposed links between Findings on this target that the deterministic correlation engine didn't catch.
          Never applied automatically — accept or dismiss each one.
        </p>

        <button
          v-if="activeTargetId"
          class="mb-4 rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
          :disabled="suggestionsGenerating"
          @click="onGenerateSuggestions"
        >
          {{ suggestionsGenerating ? "Generating…" : "Generate suggestions" }}
        </button>
        <EmptyState v-else message="Select a target to view correlation suggestions." />

        <p v-if="suggestionsError" class="mb-2 text-sm text-red-400">{{ suggestionsError }}</p>
        <LoadingState v-if="suggestionsLoading" />
        <EmptyState
          v-else-if="activeTargetId && suggestions.length === 0"
          message="No correlation suggestions yet."
        />

        <div v-if="suggestions.length" class="space-y-2">
          <div
            v-for="suggestion in suggestions"
            :key="suggestion.id"
            class="rounded-md border border-slate-800 bg-slate-950/50 p-3"
          >
            <div class="mb-1 flex items-center gap-2">
              <Badge color-class="bg-violet-500/15 text-violet-400" size="sm" bold>Suggestion IA</Badge>
              <Badge
                :color-class="
                  suggestion.status === 'ACCEPTED'
                    ? 'bg-emerald-500/15 text-emerald-400'
                    : suggestion.status === 'DISMISSED'
                      ? 'bg-slate-700/50 text-slate-500'
                      : 'bg-amber-500/15 text-amber-400'
                "
                size="sm"
              >
                {{ suggestion.status }}
              </Badge>
            </div>
            <p class="text-sm text-slate-300">
              {{ findingTitle(suggestion.finding_id) }} <span class="text-slate-600">↔</span>
              {{ findingTitle(suggestion.related_finding_id) }}
            </p>
            <p class="mt-0.5 text-xs text-slate-500">{{ suggestion.rationale }}</p>
            <div v-if="suggestion.status === 'PENDING'" class="mt-2 flex gap-2">
              <button
                class="rounded-md border border-emerald-700 px-2.5 py-1 text-xs text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-50"
                :disabled="busySuggestionId === suggestion.id"
                @click="onAcceptSuggestion(suggestion)"
              >
                Accept
              </button>
              <button
                class="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-400 hover:bg-slate-800 disabled:opacity-50"
                :disabled="busySuggestionId === suggestion.id"
                @click="onDismissSuggestion(suggestion)"
              >
                Reject
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- Report proposal -->
      <section class="rounded-lg border border-slate-800 bg-slate-900/40 p-4 xl:col-span-2">
        <h2 class="mb-3 text-sm font-semibold text-slate-300">Report Proposal</h2>
        <p class="mb-3 text-xs text-slate-500">
          The Report Agent proposes a title and which completed scans to include — nothing is generated until you
          review/edit the proposal and click Generate.
        </p>

        <div class="mb-3 flex items-end gap-2">
          <div>
            <label class="mb-1 block text-xs text-slate-500">Project</label>
            <select
              v-model="activeProjectId"
              class="w-72 rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200"
            >
              <option value="">Select a project</option>
              <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </div>
          <button
            class="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
            :disabled="!activeProjectId || proposing"
            @click="onProposeReport"
          >
            {{ proposing ? "Proposing…" : "Propose report" }}
          </button>
        </div>

        <p v-if="proposeError" class="mb-2 text-sm text-red-400">{{ proposeError }}</p>

        <div v-if="proposal" class="space-y-3 rounded-md border border-slate-800 bg-slate-950/50 p-3">
          <div>
            <label class="mb-1 block text-xs text-slate-500">Title (editable)</label>
            <input
              v-model="proposal.title"
              type="text"
              class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200"
            />
          </div>
          <p class="text-xs text-slate-500">{{ proposal.rationale }}</p>
          <div>
            <label class="mb-1 block text-xs text-slate-500">Scans to include (editable)</label>
            <div class="max-h-48 space-y-1 overflow-y-auto rounded-md border border-slate-800 p-2">
              <label
                v-for="jobId in proposal.job_ids"
                :key="jobId"
                class="flex items-center gap-2 rounded px-1.5 py-1 text-sm text-slate-300 hover:bg-slate-800/50"
              >
                <input
                  type="checkbox"
                  :checked="true"
                  class="accent-emerald-500"
                  @change="toggleProposedJob(jobId)"
                />
                <span class="font-mono text-xs">{{ jobId }}</span>
              </label>
              <p v-if="proposal.job_ids.length === 0" class="text-xs text-slate-600">
                No scans selected — the proposal removed all suggested jobs, or none were available.
              </p>
            </div>
          </div>
          <p v-if="generateError" class="text-sm text-red-400">{{ generateError }}</p>
          <p v-if="generatedReportId" class="text-sm text-emerald-400">
            Report generated —
            <NuxtLink to="/reports" class="underline">view in Reports</NuxtLink>
          </p>
          <button
            class="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
            :disabled="generatingReport || proposal.job_ids.length === 0"
            @click="onGenerateFromProposal"
          >
            {{ generatingReport ? "Generating…" : "Generate" }}
          </button>
        </div>
      </section>
    </div>
  </div>
</template>
