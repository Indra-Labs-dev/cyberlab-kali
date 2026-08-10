<script setup lang="ts">
interface ArgumentDef {
  name: string;
  type: "target" | "url" | "string" | "boolean" | "choice" | "integer";
  required: boolean;
  positional: boolean;
  flag: string | null;
  default: boolean | string | number | null;
  choices: string[] | null;
  description: string;
}

interface ToolDef {
  name: string;
  category: string;
  description: string;
  risk_level: "SAFE" | "CAUTION" | "RESTRICTED";
  arguments: ArgumentDef[];
}

const riskColor: Record<string, string> = {
  SAFE: "bg-emerald-500/15 text-emerald-400",
  CAUTION: "bg-amber-500/15 text-amber-400",
  RESTRICTED: "bg-red-500/15 text-red-400",
};

const { apiFetch } = useApi();
const router = useRouter();

const tools = ref<ToolDef[]>([]);
const loading = ref(true);
const openTool = ref<string | null>(null);
const formValues = reactive<Record<string, Record<string, string | boolean>>>({});
const submitting = ref<string | null>(null);
const submitError = ref<Record<string, string>>({});

async function loadTools() {
  loading.value = true;
  try {
    tools.value = await apiFetch<ToolDef[]>("/api/tools");
  } finally {
    loading.value = false;
  }
}

function toggleTool(name: string) {
  if (openTool.value === name) {
    openTool.value = null;
    return;
  }
  openTool.value = name;
  if (!formValues[name]) {
    const tool = tools.value.find((t) => t.name === name);
    const defaults: Record<string, string | boolean> = {};
    tool?.arguments.forEach((arg) => {
      defaults[arg.name] = arg.type === "boolean" ? Boolean(arg.default) : "";
    });
    formValues[name] = defaults;
  }
}

async function runTool(tool: ToolDef) {
  submitting.value = tool.name;
  submitError.value[tool.name] = "";
  const values = formValues[tool.name];
  const targetArg = tool.arguments.find((a) => a.type === "target" || a.type === "url");
  const target = targetArg ? (values[targetArg.name] as string) : "";
  const options: Record<string, string | boolean> = {};
  tool.arguments.forEach((arg) => {
    if (arg === targetArg) return;
    const value = values[arg.name];
    if (arg.type === "boolean") {
      if (value) options[arg.name] = true;
    } else if (value) {
      options[arg.name] = value;
    }
  });

  try {
    const job = await apiFetch<{ id: string }>("/api/jobs", {
      method: "POST",
      body: { tool: tool.name, target, options },
    });
    router.push(`/scans/${job.id}`);
  } catch (err: any) {
    submitError.value[tool.name] = err?.data?.detail || "Failed to start job";
  } finally {
    submitting.value = null;
  }
}

onMounted(loadTools);
</script>

<template>
  <div>
    <PageHeader title="Tools" subtitle="Tool Registry — allowlisted security tools available in the Kali container" />

    <div class="space-y-3 px-8 py-6">
      <p v-if="loading" class="text-sm text-slate-600">Loading tools…</p>
      <p v-else-if="tools.length === 0" class="text-sm text-slate-600">No tools registered.</p>

      <div v-for="tool in tools" :key="tool.name" class="rounded-lg border border-slate-800 bg-slate-900/40">
        <button
          class="flex w-full items-center justify-between px-4 py-3 text-left"
          @click="toggleTool(tool.name)"
        >
          <div>
            <div class="flex items-center gap-2">
              <span class="font-medium text-slate-200">{{ tool.name }}</span>
              <span class="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-500">{{ tool.category }}</span>
              <span class="rounded px-1.5 py-0.5 text-xs" :class="riskColor[tool.risk_level]">{{ tool.risk_level }}</span>
            </div>
            <p class="mt-0.5 text-sm text-slate-500">{{ tool.description }}</p>
          </div>
          <span class="text-slate-500">{{ openTool === tool.name ? "−" : "+" }}</span>
        </button>

        <div v-if="openTool === tool.name" class="border-t border-slate-800 px-4 py-4">
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div v-for="arg in tool.arguments" :key="arg.name">
              <label class="mb-1 block text-xs font-medium text-slate-400">
                {{ arg.name }}<span v-if="arg.required" class="text-red-400">*</span>
              </label>

              <select
                v-if="arg.type === 'choice'"
                v-model="formValues[tool.name][arg.name]"
                class="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200"
              >
                <option value="">—</option>
                <option v-for="choice in arg.choices" :key="choice" :value="choice">{{ choice }}</option>
              </select>

              <label v-else-if="arg.type === 'boolean'" class="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" v-model="formValues[tool.name][arg.name]" class="accent-emerald-500" />
                enabled
              </label>

              <input
                v-else
                type="text"
                v-model="formValues[tool.name][arg.name]"
                :placeholder="arg.type === 'target' || arg.type === 'url' ? 'e.g. 10.0.0.5' : ''"
                class="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200 placeholder:text-slate-600"
              />
              <p class="mt-0.5 text-xs text-slate-600">{{ arg.description }}</p>
            </div>
          </div>

          <p v-if="submitError[tool.name]" class="mt-3 text-sm text-red-400">{{ submitError[tool.name] }}</p>

          <button
            class="mt-4 rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-emerald-500 disabled:opacity-50"
            :disabled="submitting === tool.name"
            @click="runTool(tool)"
          >
            {{ submitting === tool.name ? "Starting…" : "Run" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
