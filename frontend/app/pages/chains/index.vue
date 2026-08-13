<script setup lang="ts">
// Phase 21 -- Tool Orchestrator: MissionTemplate management. A template
// is entirely deterministic (no AI) -- distinct from /ai/missions
// (Phase 18), which is AI-planned. See backend/app/chains/service.py's
// module docstring for why the two are deliberately separate systems.
import { onMounted, reactive, ref } from "vue";
import { useApi } from "~/composables/useApi";
import { useChains, type MissionTemplateStepInput } from "~/composables/useChains";
import type { ChainConditionType, MissionTemplate } from "~/types/chain";

interface ProfileDef {
  name: string;
  description: string;
}

interface ToolDef {
  name: string;
  category: string;
  description: string;
  profiles: ProfileDef[];
}

const { apiFetch } = useApi();
const { listTemplates, createTemplate, deleteTemplate } = useChains();

const templates = ref<MissionTemplate[]>([]);
const tools = ref<ToolDef[]>([]);
const loading = ref(true);
const loadError = ref("");

const name = ref("");
const description = ref("");
const steps = reactive<MissionTemplateStepInput[]>([
  { tool: "", profile: null, condition_type: "ALWAYS", condition_params: {} },
]);
const creating = ref(false);
const createError = ref("");

const CONDITION_TYPES: ChainConditionType[] = ["ALWAYS", "PORT_OPEN", "TECHNOLOGY_DETECTED", "MIN_SEVERITY"];

function profilesFor(toolName: string): ProfileDef[] {
  return tools.value.find((t) => t.name === toolName)?.profiles || [];
}

function addStep() {
  steps.push({ tool: "", profile: null, condition_type: "PORT_OPEN", condition_params: {} });
}

function removeStep(index: number) {
  if (steps.length <= 1) return;
  steps.splice(index, 1);
}

// condition_params is edited as a raw comma-separated ports list or a
// min_severity select, then folded into the real shape on submit --
// keeps the form simple rather than a generic JSON editor.
const portsInput = reactive<Record<number, string>>({});
const minSeverityInput = reactive<Record<number, string>>({});

async function loadAll() {
  loading.value = true;
  loadError.value = "";
  try {
    [templates.value, tools.value] = await Promise.all([listTemplates(), apiFetch<ToolDef[]>("/api/tools")]);
  } catch (err: any) {
    loadError.value = err?.data?.detail || "Failed to load templates";
  } finally {
    loading.value = false;
  }
}

async function submitCreate() {
  if (!name.value.trim() || steps.some((s) => !s.tool)) return;
  creating.value = true;
  createError.value = "";
  try {
    const payload: MissionTemplateStepInput[] = steps.map((s, i) => {
      const condition_params: Record<string, unknown> = {};
      if (s.condition_type === "PORT_OPEN") {
        condition_params.ports = (portsInput[i] || "")
          .split(",")
          .map((p) => parseInt(p.trim(), 10))
          .filter((p) => !Number.isNaN(p));
      } else if (s.condition_type === "MIN_SEVERITY") {
        condition_params.min_severity = minSeverityInput[i] || "MEDIUM";
      }
      return { tool: s.tool, profile: s.profile || null, options: {}, condition_type: s.condition_type, condition_params };
    });
    await createTemplate(name.value.trim(), description.value.trim(), payload);
    name.value = "";
    description.value = "";
    steps.splice(0, steps.length, { tool: "", profile: null, condition_type: "ALWAYS", condition_params: {} });
    Object.keys(portsInput).forEach((k) => delete portsInput[Number(k)]);
    Object.keys(minSeverityInput).forEach((k) => delete minSeverityInput[Number(k)]);
    await loadAll();
  } catch (err: any) {
    createError.value = err?.data?.detail || "Failed to create template";
  } finally {
    creating.value = false;
  }
}

async function onDelete(id: string) {
  await deleteTemplate(id);
  await loadAll();
}

onMounted(loadAll);
</script>

<template>
  <div>
    <PageHeader
      title="Chain Templates"
      subtitle="Reusable, deterministic tool chains — no AI involved, each step re-validated by the Policy Engine"
    />

    <div class="grid grid-cols-1 gap-6 px-8 py-6 lg:grid-cols-2">
      <section class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-3 text-sm font-semibold text-slate-300">New template</h2>

        <label class="mb-1 block text-xs text-slate-500">Name</label>
        <input
          v-model="name"
          type="text"
          placeholder="e.g. Web recon chain"
          class="mb-3 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200"
        />
        <label class="mb-1 block text-xs text-slate-500">Description (optional)</label>
        <input
          v-model="description"
          type="text"
          class="mb-4 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200"
        />

        <div class="space-y-3">
          <div v-for="(step, i) in steps" :key="i" class="rounded-md border border-slate-800 bg-slate-950/50 p-3">
            <div class="mb-2 flex items-center justify-between">
              <p class="text-xs font-medium text-slate-400">Step {{ i + 1 }}</p>
              <button v-if="steps.length > 1" class="text-xs text-red-400 hover:underline" @click="removeStep(i)">
                Remove
              </button>
            </div>
            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="mb-1 block text-xs text-slate-500">Tool</label>
                <select
                  v-model="step.tool"
                  class="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200"
                >
                  <option value="">Select…</option>
                  <option v-for="t in tools" :key="t.name" :value="t.name">{{ t.name }}</option>
                </select>
              </div>
              <div>
                <label class="mb-1 block text-xs text-slate-500">Profile</label>
                <select
                  v-model="step.profile"
                  class="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200"
                >
                  <option :value="null">None (raw options)</option>
                  <option v-for="p in profilesFor(step.tool)" :key="p.name" :value="p.name">{{ p.name }}</option>
                </select>
              </div>
            </div>

            <div class="mt-2">
              <label class="mb-1 block text-xs text-slate-500">
                {{ i === 0 ? "Condition (step 1 always runs)" : "Runs only if previous step's result…" }}
              </label>
              <select
                v-model="step.condition_type"
                :disabled="i === 0"
                class="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200 disabled:opacity-50"
              >
                <option v-for="c in i === 0 ? ['ALWAYS'] : CONDITION_TYPES.filter((c) => c !== 'ALWAYS')" :key="c" :value="c">
                  {{ c }}
                </option>
              </select>

              <input
                v-if="step.condition_type === 'PORT_OPEN'"
                v-model="portsInput[i]"
                type="text"
                placeholder="ports, e.g. 80,443"
                class="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200 placeholder:text-slate-600"
              />
              <select
                v-if="step.condition_type === 'MIN_SEVERITY'"
                v-model="minSeverityInput[i]"
                class="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200"
              >
                <option value="LOW">LOW</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="HIGH">HIGH</option>
                <option value="CRITICAL">CRITICAL</option>
              </select>
            </div>
          </div>
        </div>

        <button class="mt-3 text-xs text-emerald-400 hover:underline" @click="addStep">+ Add step</button>

        <p v-if="createError" class="mt-3 text-sm text-red-400">{{ createError }}</p>
        <button
          class="mt-4 rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          :disabled="creating || !name.trim() || steps.some((s) => !s.tool)"
          @click="submitCreate"
        >
          {{ creating ? "Creating…" : "Create template" }}
        </button>
      </section>

      <section class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h2 class="mb-3 text-sm font-semibold text-slate-300">Templates</h2>
        <p v-if="loadError" class="mb-2 text-sm text-red-400">{{ loadError }}</p>
        <LoadingState v-if="loading" />
        <EmptyState v-else-if="templates.length === 0" message="No templates yet — create one to the left." />
        <div v-else class="space-y-2">
          <div v-for="t in templates" :key="t.id" class="rounded-md border border-slate-800 bg-slate-950/50 p-3">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="truncate text-sm font-medium text-slate-200">{{ t.name }}</p>
                <p v-if="t.description" class="text-xs text-slate-500">{{ t.description }}</p>
                <p class="mt-1 text-xs text-slate-600">
                  {{ t.steps.map((s) => s.tool).join(" → ") }}
                </p>
              </div>
              <button class="shrink-0 text-xs text-red-400 hover:underline" @click="onDelete(t.id)">Delete</button>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
