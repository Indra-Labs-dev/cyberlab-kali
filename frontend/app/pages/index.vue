<script setup lang="ts">
// Security Operations Center dashboard. Every metric/chart below is
// aggregated client-side from real endpoints already used elsewhere in the
// app (GET /api/assets, /api/findings, /api/jobs, /api/ai/missions,
// /api/tools) -- see the redesign plan's "Deliberate deviations" table for
// why this deliberately does NOT include a world map, a global AI-insights
// paragraph, or a fabricated "+3% vs last hour" trend: none of those are
// backed by anything the backend actually returns.
import { Activity, AlertTriangle, Rocket, Server, ShieldAlert } from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";
import type { RadarItem } from "~/components/ui/HeroRadar.vue";
import { useApi } from "~/composables/useApi";
import { useSystemStatus } from "~/composables/useSystemStatus";
import type { Asset, AssetCriticality } from "~/types/asset";
import type { Finding, RiskPriority, Severity } from "~/types/finding";
import type { Mission } from "~/types/mission";

interface Job {
  id: string;
  tool: string;
  target: string;
  status: string;
  created_at: string;
}

interface ToolDef {
  name: string;
  category: string;
  ai_allowed: boolean;
}

const { apiFetch } = useApi();
const { status, refresh: refreshStatus } = useSystemStatus();

const assets = ref<Asset[]>([]);
const findings = ref<Finding[]>([]);
const topFindings = ref<Finding[]>([]);
const recentJobs = ref<Job[]>([]);
const missions = ref<Mission[]>([]);

const assetsLoading = ref(true);
const findingsLoading = ref(true);
const missionsLoading = ref(true);

const toolStats = reactive({ total: 0, installed: 0, aiEnabled: 0, byCategory: {} as Record<string, number> });

const activeJobs = computed(() => recentJobs.value.filter((j) => j.status === "QUEUED" || j.status === "RUNNING"));
const criticalFindings = computed(() => findings.value.filter((f) => f.severity === "CRITICAL"));
const highRiskFindings = computed(() => findings.value.filter((f) => f.risk_priority === "HIGH" || f.risk_priority === "CRITICAL"));
const runningMissions = computed(() => missions.value.filter((m) => m.status === "RUNNING"));
const recentMissions = computed(() =>
  [...missions.value].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).slice(0, 5),
);

const SEVERITY_VISUAL: Record<Severity, { stroke: string; dot: string }> = {
  CRITICAL: { stroke: "stroke-red-400", dot: "bg-red-400" },
  HIGH: { stroke: "stroke-orange-400", dot: "bg-orange-400" },
  MEDIUM: { stroke: "stroke-amber-400", dot: "bg-amber-400" },
  LOW: { stroke: "stroke-emerald-400", dot: "bg-emerald-400" },
  INFO: { stroke: "stroke-slate-500", dot: "bg-slate-500" },
};
const SEVERITY_ORDER: Severity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];

const severityDonutData = computed(() =>
  SEVERITY_ORDER.map((sev) => ({
    label: sev,
    value: findings.value.filter((f) => f.severity === sev).length,
    color: SEVERITY_VISUAL[sev].stroke,
    dot: SEVERITY_VISUAL[sev].dot,
  })),
);

const CRITICALITY_BAR_COLOR: Record<AssetCriticality, string> = {
  CRITICAL: "bg-red-400",
  HIGH: "bg-orange-400",
  MEDIUM: "bg-cyan-400",
  LOW: "bg-slate-500",
};
const criticalityBarData = computed(() =>
  (["CRITICAL", "HIGH", "MEDIUM", "LOW"] as AssetCriticality[]).map((c) => ({
    label: c,
    value: assets.value.filter((a) => a.criticality === c).length,
    color: CRITICALITY_BAR_COLOR[c],
  })),
);

// Radar nodes for the Dashboard's hero visual -- the same real top-risk
// findings already fetched for the "Top findings by risk" list, just
// visualized differently. No separate fetch, no invented data.
const RISK_TONE: Record<RiskPriority, RadarItem["tone"]> = {
  CRITICAL: "danger",
  HIGH: "danger",
  MEDIUM: "warning",
  LOW: "success",
  INFORMATIONAL: "default",
};
const radarItems = computed<RadarItem[]>(() =>
  topFindings.value.map((f) => ({
    id: f.id,
    label: f.title,
    tone: RISK_TONE[f.risk_priority ?? "INFORMATIONAL"],
    value: f.risk_score ?? undefined,
  })),
);

async function loadAssets() {
  assetsLoading.value = true;
  try {
    assets.value = await apiFetch<Asset[]>("/api/assets");
  } catch {
    assets.value = [];
  } finally {
    assetsLoading.value = false;
  }
}

async function loadFindings() {
  findingsLoading.value = true;
  try {
    const [all, top] = await Promise.all([
      apiFetch<Finding[]>("/api/findings?limit=200"),
      apiFetch<Finding[]>("/api/findings?sort=risk_score_desc&limit=5"),
    ]);
    findings.value = all;
    topFindings.value = top;
  } catch {
    findings.value = [];
    topFindings.value = [];
  } finally {
    findingsLoading.value = false;
  }
}

async function loadMissions() {
  missionsLoading.value = true;
  try {
    missions.value = await apiFetch<Mission[]>("/api/ai/missions");
  } catch {
    missions.value = [];
  } finally {
    missionsLoading.value = false;
  }
}

async function loadToolStats() {
  try {
    const [tools, health] = await Promise.all([
      apiFetch<ToolDef[]>("/api/tools"),
      apiFetch<{ name: string; status: string }[]>("/api/tools/health"),
    ]);
    const readyNames = new Set(health.filter((h) => h.status === "ready").map((h) => h.name));
    toolStats.total = tools.length;
    toolStats.installed = tools.filter((t) => readyNames.has(t.name)).length;
    toolStats.aiEnabled = tools.filter((t) => t.ai_allowed).length;
    const byCategory: Record<string, number> = {};
    tools.forEach((t) => {
      byCategory[t.category] = (byCategory[t.category] || 0) + 1;
    });
    toolStats.byCategory = byCategory;
  } catch {
    // Leave defaults (0) -- the tile below only renders once total > 0.
  }
}

async function loadJobs() {
  try {
    recentJobs.value = await apiFetch<Job[]>("/api/jobs?limit=8");
  } catch {
    recentJobs.value = [];
  }
}

onMounted(() => {
  refreshStatus();
  loadJobs();
  loadToolStats();
  loadAssets();
  loadFindings();
  loadMissions();
});
</script>

<template>
  <div class="pb-8">
    <PageHeader title="Security Operations Center" subtitle="Live view of assets, findings, jobs, and AI-driven activity." />

    <!-- Overview -->
    <div class="grid grid-cols-2 gap-4 px-8 pt-6 sm:grid-cols-3 lg:grid-cols-5">
      <UiStatCard label="Assets" :value="assets.length" :icon="Server" tone="accent" to="/assets" :delay="0" />
      <UiStatCard label="Active Jobs" :value="activeJobs.length" :icon="Activity" tone="warning" to="/scans" :delay="60" />
      <UiStatCard
        label="Critical Findings"
        :value="criticalFindings.length"
        :icon="ShieldAlert"
        tone="danger"
        :hint="`of ${findings.length} total`"
        :alert="criticalFindings.length > 0"
        to="/findings"
        :delay="120"
      />
      <UiStatCard
        label="High-Risk Findings"
        :value="highRiskFindings.length"
        :icon="AlertTriangle"
        tone="danger"
        hint="by computed risk score"
        to="/findings"
        :delay="180"
      />
      <UiStatCard label="AI Missions Running" :value="runningMissions.length" :icon="Rocket" tone="ai" to="/ai/missions" :delay="240" />
    </div>

    <!-- Hero: Attack Surface Radar + Top Risk (stands in for the reference
         image's world-map/globe centerpiece -- see HeroRadar.vue's
         docstring for why a literal map isn't built). -->
    <div class="motion-safe:animate-fade-slide-up grid grid-cols-1 gap-6 px-8 pt-6 lg:grid-cols-3" style="animation-delay: 300ms">
      <UiCard title="Attack Surface Radar" subtitle="Top-risk findings across every project" glow="accent" interactive class="lg:col-span-2">
        <LoadingState v-if="findingsLoading" />
        <div v-else class="flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
          <UiHeroRadar :items="radarItems" :center-value="assets.length" center-label="Assets Monitored" :size="260" />
          <ul class="w-full max-w-xs space-y-1.5 text-sm sm:ml-4">
            <li v-for="item in radarItems" :key="item.id" class="flex items-center gap-2">
              <span
                class="h-1.5 w-1.5 shrink-0 rounded-full"
                :class="{
                  'bg-danger-400': item.tone === 'danger',
                  'bg-warning-400': item.tone === 'warning',
                  'bg-success-400': item.tone === 'success',
                  'bg-slate-500': item.tone === 'default',
                }"
                aria-hidden="true"
              />
              <span class="min-w-0 flex-1 truncate text-slate-300">{{ item.label }}</span>
              <span class="shrink-0 text-xs text-slate-500">{{ item.value ?? "—" }}</span>
            </li>
            <li v-if="radarItems.length === 0" class="text-slate-600">No findings yet.</li>
          </ul>
        </div>
      </UiCard>

      <UiCard title="Top findings by risk" subtitle="Highest computed risk score" glow="danger" interactive>
        <template #actions>
          <UiButton variant="ghost" size="sm" to="/findings">Open →</UiButton>
        </template>
        <LoadingState v-if="findingsLoading" />
        <EmptyState v-else-if="topFindings.length === 0" message="No findings yet." />
        <ul v-else class="space-y-2">
          <li v-for="f in topFindings" :key="f.id">
            <NuxtLink
              :to="`/findings/${f.id}`"
              class="flex items-center gap-3 rounded-md border border-slate-800 bg-slate-950/50 px-3 py-2 transition-colors hover:bg-slate-900"
            >
              <RiskBadge :priority="f.risk_priority || 'INFORMATIONAL'" size="sm">{{ f.risk_score ?? "—" }}</RiskBadge>
              <div class="min-w-0 flex-1 text-sm">
                <span class="font-medium text-slate-200">{{ f.title }}</span>
                <span class="ml-2 text-slate-500">{{ f.target }}</span>
              </div>
            </NuxtLink>
          </li>
        </ul>
      </UiCard>
    </div>

    <!-- Security overview -->
    <div class="motion-safe:animate-fade-slide-up grid grid-cols-1 gap-6 px-8 pt-6 lg:grid-cols-2" style="animation-delay: 360ms">
      <UiCard title="Findings by severity" subtitle="Across every project" interactive>
        <LoadingState v-if="findingsLoading" />
        <div v-else class="flex items-center gap-6">
          <UiDonutChart :data="severityDonutData" />
          <ul class="flex-1 space-y-1.5 text-sm">
            <li v-for="seg in severityDonutData" :key="seg.label" class="flex items-center justify-between gap-3">
              <span class="flex items-center gap-2 text-slate-300">
                <span
                  class="h-2 w-2 shrink-0 rounded-full"
                  :class="[seg.dot, seg.label === 'CRITICAL' && seg.value > 0 && 'shadow-glow-danger']"
                  aria-hidden="true"
                />
                {{ seg.label }}
              </span>
              <span class="text-slate-400">{{ seg.value }}</span>
            </li>
          </ul>
        </div>
      </UiCard>

      <UiCard title="Assets by criticality" subtitle="Inventory breakdown" interactive>
        <LoadingState v-if="assetsLoading" />
        <UiBarChart v-else :data="criticalityBarData" />
      </UiCard>
    </div>

    <!-- System / AI / Tools -->
    <div class="motion-safe:animate-fade-slide-up grid grid-cols-1 gap-6 px-8 pt-6 lg:grid-cols-3" style="animation-delay: 420ms">
      <UiCard title="System Status" subtitle="Live health checks" glow="success" interactive>
        <div class="grid grid-cols-2 gap-3">
          <StatusTile label="API" :status="status.api" />
          <StatusTile label="Database" :status="status.db" />
          <StatusTile label="Kali" :status="status.kali" :detail="status.kaliDetail" />
          <StatusTile label="AI (Ollama)" :status="status.ai" :detail="status.aiDetail" />
        </div>
      </UiCard>

      <UiCard title="AI Missions" subtitle="Recent mission activity" glass glow="ai" ambient>
        <template #actions>
          <UiAIStatus :state="runningMissions.length > 0 ? 'active' : 'idle'" />
        </template>
        <LoadingState v-if="missionsLoading" />
        <EmptyState v-else-if="recentMissions.length === 0" message="No AI missions yet.">
          <template #action>
            <UiButton variant="secondary" size="sm" to="/ai">Start one from AI Assistant</UiButton>
          </template>
        </EmptyState>
        <ul v-else class="space-y-2">
          <li v-for="m in recentMissions" :key="m.id">
            <NuxtLink
              to="/ai/missions"
              class="flex items-center justify-between gap-3 rounded-md border border-slate-800 bg-slate-950/50 px-3 py-2 transition-colors hover:bg-slate-900"
            >
              <span class="min-w-0 flex-1 truncate text-sm text-slate-200">{{ m.goal }}</span>
              <MissionStatusBadge :status="m.status" size="sm" />
            </NuxtLink>
          </li>
        </ul>
      </UiCard>

      <UiCard v-if="toolStats.total > 0" title="Tool Arsenal" glow="accent" interactive>
        <template #actions>
          <UiButton variant="ghost" size="sm" to="/tools">Open Tools</UiButton>
        </template>
        <div class="mb-3 grid grid-cols-2 gap-3">
          <div>
            <div class="text-lg font-semibold text-slate-100">{{ toolStats.total }}</div>
            <div class="text-xs text-slate-500">Tools</div>
          </div>
          <div>
            <div class="text-lg font-semibold text-emerald-400">{{ toolStats.installed }}</div>
            <div class="text-xs text-slate-500">Installed</div>
          </div>
          <div>
            <div class="text-lg font-semibold text-accent-400">{{ toolStats.aiEnabled }}</div>
            <div class="text-xs text-slate-500">AI-enabled</div>
          </div>
          <div>
            <div class="text-lg font-semibold text-slate-400">{{ toolStats.total - toolStats.aiEnabled }}</div>
            <div class="text-xs text-slate-500">Manual-only</div>
          </div>
        </div>
        <div class="flex flex-wrap gap-1.5 text-xs text-slate-500">
          <span v-for="(count, category) in toolStats.byCategory" :key="category" class="rounded bg-slate-800/60 px-1.5 py-0.5">
            {{ category }}: {{ count }}
          </span>
        </div>
      </UiCard>
    </div>

    <!-- Jobs -->
    <div class="motion-safe:animate-fade-slide-up grid grid-cols-1 gap-6 px-8 py-6 lg:grid-cols-2" style="animation-delay: 480ms">
      <UiCard title="Active jobs" interactive>
        <template #actions>
          <span class="text-xs text-slate-600">{{ activeJobs.length }}</span>
        </template>
        <p v-if="activeJobs.length === 0" class="text-sm text-slate-600">No job currently running.</p>
        <ul v-else class="space-y-2">
          <li
            v-for="job in activeJobs"
            :key="job.id"
            class="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/50 px-3 py-2"
          >
            <div class="text-sm">
              <span class="font-medium text-slate-200">{{ job.tool }}</span>
              <span class="ml-2 text-slate-500">{{ job.target }}</span>
            </div>
            <JobStatusBadge :status="job.status" />
          </li>
        </ul>
      </UiCard>

      <UiCard title="Recent scans" interactive>
        <template #actions>
          <UiButton variant="ghost" size="sm" to="/scans">View all</UiButton>
        </template>
        <p v-if="recentJobs.length === 0" class="text-sm text-slate-600">No scans yet — run one from the Tools page.</p>
        <ul v-else class="space-y-2">
          <li
            v-for="job in recentJobs.slice(0, 6)"
            :key="job.id"
            class="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/50 px-3 py-2"
          >
            <NuxtLink :to="`/scans/${job.id}`" class="text-sm hover:underline">
              <span class="font-medium text-slate-200">{{ job.tool }}</span>
              <span class="ml-2 text-slate-500">{{ job.target }}</span>
            </NuxtLink>
            <JobStatusBadge :status="job.status" />
          </li>
        </ul>
      </UiCard>
    </div>

    <!-- SOC-lite (docs/roadmap.md §8): "Findings actifs + changements
         récents" -- unchanged fetch/loading/error logic, own tests. -->
    <div class="motion-safe:animate-fade-slide-up grid grid-cols-1 gap-6 px-8 pb-2 lg:grid-cols-2" style="animation-delay: 540ms">
      <ActiveFindingsWidget />
      <RecentChangesWidget />
    </div>
  </div>
</template>
