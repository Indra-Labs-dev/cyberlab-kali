<script setup lang="ts">
interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

interface MissionStep {
  label: string;
  tool: string | null;
  target: string | null;
  options: Record<string, unknown>;
  rationale: string;
}

interface MissionPlan {
  goal: string;
  target: string;
  steps: MissionStep[];
  raw_response: string | null;
}

const { apiUrl } = useApi();

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
    const res = await $fetch<{ reply: string }>(apiUrl("/api/ai/chat"), {
      method: "POST",
      body: { message },
    });
    chatHistory.value.push({ role: "assistant", content: res.reply });
  } catch (err: any) {
    chatHistory.value.push({ role: "assistant", content: `Error: ${err?.data?.detail || "request failed"}` });
  } finally {
    chatBusy.value = false;
  }
}

// --- Mission Planner ---
const planTarget = ref("");
const planGoal = ref("");
const planning = ref(false);
const planError = ref("");
const plan = ref<MissionPlan | null>(null);
const runningStep = ref<number | null>(null);
const stepResult = ref<Record<number, { ok: boolean; message: string }>>({});

async function requestPlan() {
  if (!planTarget.value || !planGoal.value) return;
  planning.value = true;
  planError.value = "";
  plan.value = null;
  stepResult.value = {};
  try {
    plan.value = await $fetch<MissionPlan>(apiUrl("/api/ai/plan"), {
      method: "POST",
      body: { target: planTarget.value, goal: planGoal.value },
    });
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
    const job = await $fetch<{ id: string }>(apiUrl("/api/jobs"), {
      method: "POST",
      body: { tool: step.tool, target: step.target || plan.value?.target, options: step.options },
    });
    stepResult.value[index] = { ok: true, message: `Started — job ${job.id}` };
  } catch (err: any) {
    stepResult.value[index] = { ok: false, message: err?.data?.detail || "Failed to start" };
  } finally {
    runningStep.value = null;
  }
}
</script>

<template>
  <div>
    <PageHeader title="AI Assistant" subtitle="Local analysis via Ollama — nothing here executes automatically" />

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
            v-model="planTarget"
            type="text"
            placeholder="Target, e.g. cyberlab-lab-dvwa-xxxx"
            class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600"
          />
          <input
            v-model="planGoal"
            type="text"
            placeholder="Goal, e.g. find open web services and check for common vulnerabilities"
            class="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600"
          />
          <button
            type="submit"
            class="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
            :disabled="planning || !planTarget || !planGoal"
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
