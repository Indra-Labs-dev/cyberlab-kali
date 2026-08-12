<script setup lang="ts">
import type { Core, ElementDefinition } from "cytoscape";

type NodeType = "ASSET" | "FINDING" | "CVE" | "SERVICE" | "TECHNOLOGY";

interface GraphNode {
  id: string;
  type: NodeType;
  label: string;
  metadata: Record<string, unknown>;
}

interface GraphEdge {
  id: string;
  from_type: string;
  from_id: string;
  to_type: string;
  to_id: string;
  relation: string;
  source: string;
  reason: string;
  metadata: Record<string, unknown>;
}

interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

const props = defineProps<{
  // e.g. "/api/graph/assets/{id}" or "/api/graph/findings/{id}" -- the
  // component only needs the fully-resolved URL, it fetches depth itself.
  baseUrl: string;
}>();

const { apiFetch } = useApi();

const container = ref<HTMLDivElement | null>(null);
let cy: Core | null = null;

const loading = ref(true);
const error = ref("");
const depth = ref(1);
const search = ref("");
const typeFilters = ref<Set<NodeType>>(new Set(["ASSET", "FINDING", "CVE", "SERVICE", "TECHNOLOGY"]));
const ALL_TYPES: NodeType[] = ["ASSET", "FINDING", "CVE", "SERVICE", "TECHNOLOGY"];

const graph = ref<GraphResponse>({ nodes: [], edges: [] });
const selected = ref<GraphNode | null>(null);
const selectedConnections = ref<{ edge: GraphEdge; otherEnd: GraphNode | null }[]>([]);

const typeColor: Record<NodeType, string> = {
  ASSET: "#38bdf8", // sky-400
  FINDING: "#f59e0b", // amber-500
  CVE: "#f87171", // red-400
  SERVICE: "#34d399", // emerald-400
  TECHNOLOGY: "#a78bfa", // violet-400
};
const typeShape: Record<NodeType, string> = {
  ASSET: "ellipse",
  FINDING: "diamond",
  SERVICE: "round-rectangle",
  TECHNOLOGY: "hexagon",
  CVE: "triangle",
};

function nodeById(id: string): GraphNode | null {
  return graph.value.nodes.find((n) => n.id === id) ?? null;
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    graph.value = await apiFetch<GraphResponse>(`${props.baseUrl}?depth=${depth.value}`);
    await nextTick();
    render();
  } catch (err: any) {
    error.value = err?.data?.detail || "Failed to load the security graph";
  } finally {
    loading.value = false;
  }
}

function visibleNodeIds(): Set<string> {
  const q = search.value.trim().toLowerCase();
  const ids = new Set<string>();
  for (const n of graph.value.nodes) {
    if (!typeFilters.value.has(n.type)) continue;
    if (q && !n.label.toLowerCase().includes(q) && !n.id.toLowerCase().includes(q)) continue;
    ids.add(n.id);
  }
  return ids;
}

function render() {
  if (!container.value) return;
  const visible = visibleNodeIds();

  const elements: ElementDefinition[] = [];
  for (const n of graph.value.nodes) {
    if (!visible.has(n.id)) continue;
    elements.push({ data: { id: n.id, label: n.label, type: n.type } });
  }
  for (const e of graph.value.edges) {
    if (!visible.has(e.from_id) || !visible.has(e.to_id)) continue;
    elements.push({ data: { id: e.id, source: e.from_id, target: e.to_id, relation: e.relation } });
  }

  if (cy) {
    cy.destroy();
    cy = null;
  }

  // cytoscape.js chosen over a heavier force-directed/WebGL library
  // (sigma.js, d3-force from scratch) -- no dependency already existed in
  // package.json for this, and cytoscape is purpose-built for exactly this
  // kind of typed node/edge security graph at a few hundred elements,
  // with zoom/pan/select built in and no framework coupling.
  import("cytoscape").then(({ default: cytoscape }) => {
    if (!container.value) return;
    cy = cytoscape({
      container: container.value,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (ele: any) => typeColor[ele.data("type") as NodeType] || "#64748b",
            shape: (ele: any) => (typeShape[ele.data("type") as NodeType] || "ellipse") as any,
            label: "data(label)",
            "font-size": "9px",
            color: "#e2e8f0",
            "text-valign": "bottom",
            "text-margin-y": 4,
            "text-wrap": "ellipsis",
            "text-max-width": "80px",
            width: 28,
            height: 28,
            "border-width": 2,
            "border-color": "#0f172a",
          },
        },
        {
          selector: "node:selected",
          style: { "border-color": "#facc15", "border-width": 3 },
        },
        {
          selector: "edge",
          style: {
            width: 1.5,
            "line-color": "#475569",
            "target-arrow-color": "#475569",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(relation)",
            "font-size": "7px",
            color: "#94a3b8",
            "text-rotation": "autorotate",
          },
        },
      ],
      layout: { name: "cose", animate: false, padding: 30 },
    });

    cy.on("tap", "node", (evt) => {
      const id = evt.target.id();
      selectNode(id);
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        selected.value = null;
        selectedConnections.value = [];
      }
    });
  });
}

function selectNode(id: string) {
  const node = nodeById(id);
  selected.value = node;
  if (!node) {
    selectedConnections.value = [];
    return;
  }
  selectedConnections.value = graph.value.edges
    .filter((e) => e.from_id === id || e.to_id === id)
    .map((e) => {
      const otherId = e.from_id === id ? e.to_id : e.from_id;
      return { edge: e, otherEnd: nodeById(otherId) };
    });
  cy?.$id(id).select();
  cy?.animate({ center: { eles: cy.$id(id) }, zoom: 1.5 }, { duration: 300 });
}

function resetView() {
  cy?.zoom(1);
  cy?.center();
}
function fitGraph() {
  cy?.fit(undefined, 30);
}

function toggleType(t: NodeType) {
  if (typeFilters.value.has(t)) typeFilters.value.delete(t);
  else typeFilters.value.add(t);
  typeFilters.value = new Set(typeFilters.value);
  render();
}

watch(depth, load);
watch([search, typeFilters], render, { deep: true });
onMounted(load);
onBeforeUnmount(() => cy?.destroy());
</script>

<template>
  <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <h2 class="text-sm font-semibold text-slate-300">Security Graph</h2>
      <div class="flex flex-wrap items-center gap-2">
        <input
          v-model="search"
          type="text"
          placeholder="Search nodes…"
          class="w-36 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200"
        />
        <div class="flex gap-1">
          <button
            v-for="t in ALL_TYPES"
            :key="t"
            class="rounded px-1.5 py-0.5 text-[10px] font-medium"
            :class="typeFilters.has(t) ? 'bg-slate-700 text-slate-200' : 'bg-slate-900 text-slate-600'"
            @click="toggleType(t)"
          >
            {{ t }}
          </button>
        </div>
        <select v-model.number="depth" class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-300">
          <option :value="1">Depth 1</option>
          <option :value="2">Depth 2</option>
          <option :value="3">Depth 3</option>
        </select>
        <button class="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800" @click="fitGraph">
          Fit
        </button>
        <button class="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800" @click="resetView">
          Reset view
        </button>
      </div>
    </div>

    <p v-if="loading" class="text-sm text-slate-600">Loading graph…</p>
    <p v-else-if="error" class="text-sm text-red-400">{{ error }}</p>
    <p v-else-if="graph.nodes.length === 0" class="text-sm text-slate-600">No graph data yet for this node.</p>

    <div v-show="!loading && !error && graph.nodes.length > 0" class="flex gap-4">
      <div ref="container" class="h-96 flex-1 rounded-md border border-slate-800 bg-slate-950/50"></div>

      <div v-if="selected" class="w-64 shrink-0 rounded-md border border-slate-800 bg-slate-950/50 p-3 text-xs">
        <div class="mb-2 flex items-center justify-between">
          <span class="rounded px-1.5 py-0.5 font-medium" :style="{ background: typeColor[selected.type] + '25', color: typeColor[selected.type] }">
            {{ selected.type }}
          </span>
          <button class="text-slate-500 hover:text-slate-300" @click="selected = null">✕</button>
        </div>
        <p class="mb-2 font-medium text-slate-200">{{ selected.label }}</p>

        <div v-if="Object.keys(selected.metadata).length" class="mb-3 space-y-0.5 text-slate-400">
          <p v-for="(v, k) in selected.metadata" :key="k">
            <span class="text-slate-600">{{ k }}:</span> {{ v }}
          </p>
        </div>

        <NuxtLink
          v-if="selected.type === 'ASSET'"
          :to="`/targets/${selected.id}`"
          class="mb-3 block text-emerald-400 hover:underline"
        >
          Open Asset →
        </NuxtLink>
        <NuxtLink
          v-else-if="selected.type === 'FINDING'"
          :to="`/findings/${selected.id}`"
          class="mb-3 block text-emerald-400 hover:underline"
        >
          Open Finding →
        </NuxtLink>

        <p class="mb-1 font-medium text-slate-500">Connections ({{ selectedConnections.length }})</p>
        <div class="max-h-64 space-y-2 overflow-y-auto">
          <div v-for="c in selectedConnections" :key="c.edge.id" class="border-t border-slate-800 pt-2">
            <p class="text-slate-400">
              <span class="text-slate-600">{{ c.edge.relation }}</span> · {{ c.otherEnd?.label || "?" }}
            </p>
            <p class="text-slate-600">{{ c.edge.reason }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
