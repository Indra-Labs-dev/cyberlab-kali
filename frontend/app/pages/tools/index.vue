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

interface ProfileDef {
  name: string;
  description: string;
  args: Record<string, boolean | string | number>;
  timeout: number | null;
  risk_level: "SAFE" | "CAUTION" | "RESTRICTED" | "MANUAL_ONLY" | null;
  target_type_hint: string | null;
}

interface ToolDef {
  name: string;
  category: string;
  description: string;
  risk_level: "SAFE" | "CAUTION" | "RESTRICTED" | "MANUAL_ONLY";
  ai_allowed: boolean;
  arguments: ArgumentDef[];
  profiles: ProfileDef[];
  output: { format: string; parser: string };
}

interface HealthEntry {
  name: string;
  status: "ready" | "broken" | "not_installed" | "unknown";
  detail: string | null;
}

interface Target {
  id: string;
  project_id: string;
  name: string;
  hostname: string | null;
  ip_address: string | null;
  url: string | null;
  authorization_status: "LAB" | "AUTHORIZED" | "LOCAL" | "UNKNOWN";
}

const riskColor: Record<string, string> = {
  SAFE: "bg-emerald-500/15 text-emerald-400",
  CAUTION: "bg-amber-500/15 text-amber-400",
  RESTRICTED: "bg-orange-500/15 text-orange-400",
  MANUAL_ONLY: "bg-red-500/15 text-red-400",
};

const healthIcon: Record<string, string> = {
  ready: "✓",
  broken: "✕",
  not_installed: "⚠",
  unknown: "?",
};
const healthColor: Record<string, string> = {
  ready: "text-emerald-400",
  broken: "text-red-400",
  not_installed: "text-amber-400",
  unknown: "text-slate-500",
};

const categoryLabels: Record<string, string> = {
  reconnaissance: "Reconnaissance",
  dns_network: "DNS/Network",
  web_recon: "Web Recon",
  web_security: "Web Security",
  ssl_tls: "SSL/TLS",
  enumeration: "Enumeration",
  vulnerability: "Vulnerability",
  osint: "OSINT",
  utilities: "Utilities",
};

const { apiFetch } = useApi();
const router = useRouter();

const tools = ref<ToolDef[]>([]);
const health = ref<Record<string, HealthEntry>>({});
const targets = ref<Target[]>([]);
const loading = ref(true);
const healthLoading = ref(false);

const search = ref("");
const categoryFilter = ref("");
const riskFilter = ref("");
const aiFilter = ref<"" | "ai" | "manual">("");

const openTool = ref<string | null>(null);
const runState = reactive<
  Record<string, { targetMode: "existing" | "free"; targetId: string; freeTarget: string; profile: string; custom: Record<string, string | boolean> }>
>({});
const submitting = ref<string | null>(null);
const submitError = ref<Record<string, string>>({});

const categories = computed(() => Array.from(new Set(tools.value.map((t) => t.category))).sort());

const filteredTools = computed(() =>
  tools.value.filter((t) => {
    if (search.value && !`${t.name} ${t.description}`.toLowerCase().includes(search.value.toLowerCase())) return false;
    if (categoryFilter.value && t.category !== categoryFilter.value) return false;
    if (riskFilter.value && t.risk_level !== riskFilter.value) return false;
    if (aiFilter.value === "ai" && !t.ai_allowed) return false;
    if (aiFilter.value === "manual" && t.ai_allowed) return false;
    return true;
  }),
);

const stats = computed(() => {
  const installed = tools.value.filter((t) => health.value[t.name]?.status === "ready").length;
  const aiEnabled = tools.value.filter((t) => t.ai_allowed).length;
  return {
    total: tools.value.length,
    installed,
    aiEnabled,
    manualOnly: tools.value.length - aiEnabled,
  };
});

async function loadTools() {
  loading.value = true;
  try {
    tools.value = await apiFetch<ToolDef[]>("/api/tools");
  } finally {
    loading.value = false;
  }
}

async function loadHealth() {
  healthLoading.value = true;
  try {
    const results = await apiFetch<HealthEntry[]>("/api/tools/health");
    health.value = Object.fromEntries(results.map((r) => [r.name, r]));
  } catch {
    health.value = {};
  } finally {
    healthLoading.value = false;
  }
}

async function loadTargets() {
  try {
    targets.value = await apiFetch<Target[]>("/api/targets");
  } catch {
    targets.value = [];
  }
}

function targetAddress(t: Target) {
  return t.url || t.hostname || t.ip_address || t.name;
}

function toggleTool(name: string) {
  if (openTool.value === name) {
    openTool.value = null;
    return;
  }
  openTool.value = name;
  if (!runState[name]) {
    const tool = tools.value.find((t) => t.name === name);
    const defaults: Record<string, string | boolean> = {};
    tool?.arguments.forEach((arg) => {
      if (arg.type === "target" || arg.type === "url") return;
      defaults[arg.name] = arg.type === "boolean" ? Boolean(arg.default) : "";
    });
    runState[name] = {
      targetMode: "existing",
      targetId: "",
      freeTarget: "",
      profile: tool?.profiles[0]?.name || "",
      custom: defaults,
    };
  }
}

async function runTool(tool: ToolDef) {
  const state = runState[tool.name];
  submitting.value = tool.name;
  submitError.value[tool.name] = "";

  const body: Record<string, unknown> = { tool: tool.name };
  if (state.targetMode === "existing") {
    if (!state.targetId) {
      submitError.value[tool.name] = "Select a target";
      submitting.value = null;
      return;
    }
    body.target_id = state.targetId;
  } else {
    if (!state.freeTarget) {
      submitError.value[tool.name] = "Enter a target";
      submitting.value = null;
      return;
    }
    body.target = state.freeTarget;
  }

  if (state.profile) {
    body.profile = state.profile;
  } else {
    const options: Record<string, string | boolean> = {};
    tool.arguments.forEach((arg) => {
      if (arg.type === "target" || arg.type === "url") return;
      const value = state.custom[arg.name];
      if (arg.type === "boolean") {
        if (value) options[arg.name] = true;
      } else if (value) {
        options[arg.name] = value;
      }
    });
    body.options = options;
  }

  try {
    const job = await apiFetch<{ id: string }>("/api/jobs", { method: "POST", body });
    router.push(`/scans/${job.id}`);
  } catch (err: any) {
    submitError.value[tool.name] = err?.data?.detail || "Failed to start job";
  } finally {
    submitting.value = null;
  }
}

onMounted(async () => {
  await Promise.all([loadTools(), loadTargets()]);
  loadHealth();
});
</script>

<template>
  <div>
    <PageHeader title="Tools" subtitle="CyberLab Tool Arsenal — curated, allowlisted security tools" />

    <div class="space-y-4 px-8 py-6">
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
          <div class="text-xl font-semibold text-slate-100">{{ stats.total }}</div>
          <div class="text-xs text-slate-500">Tools</div>
        </div>
        <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
          <div class="text-xl font-semibold text-emerald-400">{{ healthLoading ? "…" : stats.installed }}</div>
          <div class="text-xs text-slate-500">Installed &amp; ready</div>
        </div>
        <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
          <div class="text-xl font-semibold text-cyan-400">{{ stats.aiEnabled }}</div>
          <div class="text-xs text-slate-500">AI-enabled</div>
        </div>
        <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
          <div class="text-xl font-semibold text-slate-400">{{ stats.manualOnly }}</div>
          <div class="text-xs text-slate-500">Manual-only</div>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <input
          v-model="search"
          type="text"
          placeholder="Search tools…"
          class="w-56 rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-600"
        />
        <select v-model="categoryFilter" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200">
          <option value="">All categories</option>
          <option v-for="c in categories" :key="c" :value="c">{{ categoryLabels[c] || c }}</option>
        </select>
        <select v-model="riskFilter" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200">
          <option value="">All risk levels</option>
          <option v-for="r in ['SAFE', 'CAUTION', 'RESTRICTED', 'MANUAL_ONLY']" :key="r" :value="r">{{ r }}</option>
        </select>
        <select v-model="aiFilter" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200">
          <option value="">AI: any</option>
          <option value="ai">AI-enabled only</option>
          <option value="manual">Manual-only</option>
        </select>
        <button
          class="ml-auto rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-400 hover:border-slate-500 hover:text-slate-200 disabled:opacity-50"
          :disabled="healthLoading"
          @click="loadHealth"
        >
          {{ healthLoading ? "Checking…" : "Refresh Tool Health" }}
        </button>
      </div>

      <p v-if="loading" class="text-sm text-slate-600">Loading…</p>
      <p v-else-if="filteredTools.length === 0" class="text-sm text-slate-600">No tools match these filters.</p>

      <div v-else class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div
          v-for="tool in filteredTools"
          :key="tool.name"
          class="flex flex-col rounded-lg border border-slate-800 bg-slate-900/40 p-4"
        >
          <div class="mb-1 flex items-center justify-between">
            <span class="font-medium capitalize text-slate-200">{{ tool.name }}</span>
            <span class="rounded px-1.5 py-0.5 text-xs" :class="riskColor[tool.risk_level]">{{ tool.risk_level }}</span>
          </div>
          <div class="mb-2 text-xs text-slate-500">{{ categoryLabels[tool.category] || tool.category }}</div>
          <p class="mb-3 line-clamp-2 flex-1 text-sm text-slate-400">{{ tool.description }}</p>
          <div class="mb-3 flex items-center gap-3 text-xs text-slate-500">
            <span>Profiles: {{ tool.profiles.length }}</span>
            <span :class="tool.ai_allowed ? 'text-cyan-400' : 'text-slate-600'">AI: {{ tool.ai_allowed ? "ENABLED" : "DISABLED" }}</span>
            <span v-if="health[tool.name]" :class="healthColor[health[tool.name].status]" :title="health[tool.name].detail || ''">
              {{ healthIcon[health[tool.name].status] }} {{ health[tool.name].status.replace("_", " ") }}
            </span>
          </div>
          <button
            class="mt-auto rounded-md border border-slate-700 py-1.5 text-sm text-slate-200 hover:border-emerald-500 hover:text-emerald-400"
            @click="toggleTool(tool.name)"
          >
            {{ openTool === tool.name ? "Close" : "Open Tool" }}
          </button>

          <div v-if="openTool === tool.name" class="mt-4 space-y-3 border-t border-slate-800 pt-4">
            <div v-if="tool.profiles.length" class="space-y-1.5">
              <label class="block text-xs font-medium text-slate-400">Profile</label>
              <select
                v-model="runState[tool.name].profile"
                class="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200"
              >
                <option v-for="p in tool.profiles" :key="p.name" :value="p.name">{{ p.name }}</option>
                <option value="">Custom arguments…</option>
              </select>
              <p v-if="runState[tool.name].profile" class="text-xs text-slate-600">
                {{ tool.profiles.find((p) => p.name === runState[tool.name].profile)?.description }}
              </p>
            </div>

            <div v-if="!runState[tool.name].profile" class="space-y-2 rounded-md border border-slate-800 bg-slate-950/40 p-3">
              <div v-for="arg in tool.arguments.filter((a) => a.type !== 'target' && a.type !== 'url')" :key="arg.name">
                <label class="mb-1 block text-xs text-slate-500">{{ arg.name }}<span v-if="arg.required" class="text-red-400">*</span></label>
                <select
                  v-if="arg.type === 'choice'"
                  v-model="runState[tool.name].custom[arg.name]"
                  class="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200"
                >
                  <option value="">—</option>
                  <option v-for="c in arg.choices" :key="c" :value="c">{{ c }}</option>
                </select>
                <label v-else-if="arg.type === 'boolean'" class="flex items-center gap-2 text-sm text-slate-300">
                  <input type="checkbox" v-model="runState[tool.name].custom[arg.name]" class="accent-emerald-500" />
                  enabled
                </label>
                <input
                  v-else
                  type="text"
                  v-model="runState[tool.name].custom[arg.name]"
                  class="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200"
                />
              </div>
            </div>

            <div class="space-y-1.5">
              <label class="block text-xs font-medium text-slate-400">Target</label>
              <div class="flex gap-2 text-xs">
                <button
                  class="rounded px-2 py-1"
                  :class="runState[tool.name].targetMode === 'existing' ? 'bg-slate-800 text-slate-200' : 'text-slate-500'"
                  @click="runState[tool.name].targetMode = 'existing'"
                >
                  Existing target
                </button>
                <button
                  class="rounded px-2 py-1"
                  :class="runState[tool.name].targetMode === 'free' ? 'bg-slate-800 text-slate-200' : 'text-slate-500'"
                  @click="runState[tool.name].targetMode = 'free'"
                >
                  Free text
                </button>
              </div>
              <select
                v-if="runState[tool.name].targetMode === 'existing'"
                v-model="runState[tool.name].targetId"
                class="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200"
              >
                <option value="">Select a target…</option>
                <option v-for="t in targets" :key="t.id" :value="t.id">
                  {{ t.name }} ({{ targetAddress(t) }}) — {{ t.authorization_status }}
                </option>
              </select>
              <input
                v-else
                v-model="runState[tool.name].freeTarget"
                type="text"
                placeholder="e.g. 10.0.0.5 (no authorization check)"
                class="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200 placeholder:text-slate-600"
              />
            </div>

            <p v-if="submitError[tool.name]" class="text-sm text-red-400">{{ submitError[tool.name] }}</p>

            <button
              class="w-full rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-emerald-500 disabled:opacity-50"
              :disabled="submitting === tool.name"
              @click="runTool(tool)"
            >
              {{ submitting === tool.name ? "Starting…" : "Run" }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
