<script setup lang="ts">
interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

interface MissionStep {
  label: string;
  tool: string | null;
  target: string | null;
  target_id: string | null;
  options: Record<string, unknown>;
  rationale: string;
}

interface MissionPlan {
  goal: string;
  target: string;
  target_id: string | null;
  steps: MissionStep[];
  raw_response: string | null;
}

interface Target {
  id: string;
  name: string;
  hostname: string | null;
  ip_address: string | null;
  url: string | null;
  authorization_status: string;
}

const { apiFetch } = useApi();

// --- Shared target context ---
const targets = ref<Target[]>([]);
const activeTargetId = ref("");
const activeTarget = computed(() => targets.value.find((t) => t.id === activeTargetId.value) || null);

async function loadTargets() {
  targets.value = await apiFetch<Target[]>("/api/targets");
}

// --- Chat ---
const chatHistory = ref<ChatTurn[]>([]);
const chatInput = ref("");
const chatBusy = ref(false);

async function sendChat() {
  const message = chatInput.value.trim();
  if (!message || chatBusy.value) return;
  chatHistory.value.push({ role: "user", content: message });
  chatInput.value = "";
  chatBusy.value = true;
  try {
    const res = await apiFetch<{ reply: string }>("/api/ai/chat", {
      method: "POST",
      body: { message, target_id: activeTargetId.value || undefined },
    });
    chatHistory.value.push({ role: "assistant", content: res.reply });
  } catch (err: any) {
    chatHistory.value.push({ role: "assistant", content: `Error: ${err?.data?.detail || "request failed"}` });
  } finally {
    chatBusy.value = false;
  }
}

// --- Mission Planner ---
const planTargetFreeText = ref("");
const planGoal = ref("");
const planning = ref(false);
const planError = ref("");
const plan = ref<MissionPlan | null>(null);
const runningStep = ref<number | null>(null);
const stepResult = ref<Record<number, { ok: boolean; message: string }>>({});

async function requestPlan() {
  if ((!activeTargetId.value && !planTargetFreeText.value) || !planGoal.value) return;
  planning.value = true;
  planError.value = "";
  plan.value = null;
  stepResult.value = {};
  try {
    const body = activeTargetId.value
      ? { target_id: activeTargetId.value, goal: planGoal.value }
      : { target: planTargetFreeText.value, goal: planGoal.value };
    plan.value = await apiFetch<MissionPlan>("/api/ai/plan", { method: "POST", body });
  } catch (err: any) {
    planError.value = err?.data?.detail || "Planning failed";
  } finally {
    planning.value = false;
  }
}

async function runStep(step: MissionStep, index: number) {
  if (!step.tool) return;
  runningStep.value = index;
  try {
    // A step carries target_id whenever the plan itself was requested
    // against a registered Target (set server-side, never by the model) —
    // running it then goes through the same authorization enforcement as
    // every other job. Falls back to the free-text target otherwise.
    const body = step.target_id
      ? { tool: step.tool, target_id: step.target_id, options: step.options }
      : { tool: step.tool, target: step.target || plan.value?.target, options: step.options };
    const job = await apiFetch<{ id: string }>("/api/jobs", { method: "POST", body });
    stepResult.value[index] = { ok: true, message: `Started — job ${job.id}` };
  } catch (err: any) {
    stepResult.value[index] = { ok: false, message: err?.data?.detail || "Failed to start" };
  } finally {
    runningStep.value = null;
  }
}

function targetLabel(t: Target) {
  const address = t.url || t.hostname || t.ip_address || "—";
  return `${t.name} (${address}) — ${t.authorization_status}`;
}

onMounted(async () => {
  await loadTargets();
  const preselect = useRoute().query.target_id;
  if (typeof preselect === "string" && targets.value.some((t) => t.id === preselect)) {
    activeTargetId.value = preselect;
  }
});
</script>

<template>
  <div>
    <PageHeader title="AI Assistant" subtitle="Local analysis via Ollama — nothing here executes automatically" />

    <div class="px-8 pt-6">
      <label class="mb-1 block text-xs text-slate-500">Active target context (optional)</label>
      <select
        v-model="activeTargetId"
        class="w-full max-w-md rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200"
      >
        <option value="">No active target — chat generally, plan against free text</option>
        <option v-for="t in targets" :key="t.id" :value="t.id">{{ targetLabel(t) }}</option>
      </select>
      <p v-if="activeTarget" class="mt-1 text-xs text-slate-600">
        The AI is told about this target's name, address, and authorization status — it can't invent or change it.
      </p>
    </div>

    <div class="grid grid-cols-1 gap-6 px-8 py-6 lg:grid-cols-2">
      <!-- Chat -->
      <section class="flex flex-col rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-3 text-sm font-semibold text-slate-300">Chat</h2>
        <div class="mb-3 flex-1 space-y-3 overflow-y-auto" style="max-height: 420px">
          <p v-if="chatHistory.length === 0" class="text-sm text-slate-600">
            Ask about security concepts, scan results, or how to use CyberLab.
          </p>
          <div
            v-for="(turn, i) in chatHistory"
            :key="i"
            class="rounded-md px-3 py-2 text-sm"
            :class="turn.role === 'user' ? 'bg-slate-800/60 text-slate-200' : 'bg-emerald-500/10 text-slate-300'"
          >
            <p class="mb-1 text-xs font-medium text-slate-500">{{ turn.role === "user" ? "You" : "Assistant" }}</p>
            <p class="whitespace-pre-wrap">{{ turn.content }}</p>
          </div>
          <p v-if="chatBusy" class="text-sm text-slate-600">Thinking…</p>
        </div>
        <form class="flex gap-2" @submit.prevent="sendChat">
          <input
            v-model="chatInput"
            type="text"
            placeholder="Ask a question…"
            class="flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600"
          />
          <button
            type="submit"
            class="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
            :disabled="chatBusy || !chatInput.trim()"
          >
            Send
          </button>
        </form>
      </section>

      <!-- Mission Planner -->
      <section class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-3 text-sm font-semibold text-slate-300">Mission Planner</h2>
        <p class="mb-3 text-xs text-slate-500">
          Describe a goal — the AI proposes a plan using only registered tools. Nothing runs until you click
          "Run" on a step.
        </p>
        <form class="mb-4 space-y-2" @submit.prevent="requestPlan">
          <input
            v-if="!activeTargetId"
            v-model="planTargetFreeText"
            type="text"
            placeholder="Target, e.g. cyberlab-lab-dvwa-xxxx (or select an active target above)"
            class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600"
          />
          <p v-else class="rounded-md border border-slate-800 bg-slate-950/50 px-3 py-2 text-sm text-slate-400">
            Using active target: {{ activeTarget ? targetLabel(activeTarget) : "" }}
          </p>
          <input
            v-model="planGoal"
            type="text"
            placeholder="Goal, e.g. find open web services and check for common vulnerabilities"
            class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600"
          />
          <button
            type="submit"
            class="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
            :disabled="planning || (!activeTargetId && !planTargetFreeText) || !planGoal"
          >
            {{ planning ? "Planning…" : "Propose a plan" }}
          </button>
        </form>

        <p v-if="planError" class="text-sm text-red-400">{{ planError }}</p>

        <div v-if="plan && plan.steps.length" class="space-y-2">
          <div
            v-for="(step, i) in plan.steps"
            :key="i"
            class="rounded-md border border-slate-800 bg-slate-950/50 p-3"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-sm font-medium text-slate-200">{{ i + 1 }}. {{ step.label }}</p>
                <p class="mt-0.5 text-xs text-slate-500">{{ step.rationale }}</p>
                <p class="mt-1 text-xs text-slate-600">
                  <span v-if="step.tool">tool: {{ step.tool }} · target: {{ step.target }}</span>
                  <span v-else class="italic">no registered tool for this step — manual action</span>
                </p>
              </div>
              <button
                v-if="step.tool"
                class="shrink-0 rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                :disabled="runningStep === i"
                @click="runStep(step, i)"
              >
                {{ runningStep === i ? "Starting…" : "Run" }}
              </button>
            </div>
            <p
              v-if="stepResult[i]"
              class="mt-2 text-xs"
              :class="stepResult[i].ok ? 'text-emerald-400' : 'text-red-400'"
            >
              {{ stepResult[i].message }}
            </p>
          </div>
        </div>
        <p v-else-if="plan" class="text-sm text-slate-600">
          The model didn't return a usable plan. Raw response: {{ plan.raw_response }}
        </p>
      </section>
    </div>
  </div>
</template>
