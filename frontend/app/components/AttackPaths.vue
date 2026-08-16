<script setup lang="ts">
// Phase 24 -- Attack Path Analysis. Deliberately list-based, not another
// Cytoscape render like SecurityGraph.vue -- a handful of ordered node
// chips per path reads more clearly as "here is one specific hypothesis
// to verify" than a dense graph would, and keeps this component genuinely
// "léger" per the roadmap's own framing.
import { ref } from "vue";
import type { GraphSearchResult } from "~/composables/useGraph";
import { useGraph } from "~/composables/useGraph";
import type { AttackPathsResponse } from "~/types/graph";
// Explicit import (not just Nuxt auto-import) so this component stays
// mountable in plain Vitest, same reasoning as GraphSearchBar.vue's own
// explicit ref/watch imports -- a plain mount() has no Nuxt auto-import
// resolution for child components either.
import GraphSearchBar from "./GraphSearchBar.vue";

type Mode = "critical" | "between";

const { loadAttackPathsToCriticalAssets, loadAttackPathsBetween } = useGraph();

const mode = ref<Mode>("critical");
const maxHops = ref(4);
const from = ref<GraphSearchResult | null>(null);
const to = ref<GraphSearchResult | null>(null);
const loading = ref(false);
const error = ref("");
const result = ref<AttackPathsResponse | null>(null);

function setMode(m: Mode) {
  mode.value = m;
  result.value = null;
  error.value = "";
}

function onSelectFrom(r: GraphSearchResult) {
  from.value = r;
  result.value = null;
}

function onSelectTo(r: GraphSearchResult) {
  to.value = r;
  result.value = null;
}

async function search() {
  if (!from.value) return;
  if (mode.value === "between" && !to.value) return;

  loading.value = true;
  error.value = "";
  result.value = null;
  try {
    result.value =
      mode.value === "critical"
        ? await loadAttackPathsToCriticalAssets(from.value.type, from.value.id, maxHops.value)
        : await loadAttackPathsBetween(from.value.type, from.value.id, to.value!.type, to.value!.id, maxHops.value);
  } catch (err: any) {
    error.value = err?.data?.detail || "Failed to search for attack paths";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <h2 class="text-sm font-semibold text-slate-300">Attack Path Analysis</h2>
      <div class="flex gap-1">
        <button
          type="button"
          class="rounded px-2 py-1 text-xs font-medium"
          :class="mode === 'critical' ? 'bg-slate-700 text-slate-200' : 'bg-slate-900 text-slate-500'"
          @click="setMode('critical')"
        >
          To critical assets
        </button>
        <button
          type="button"
          class="rounded px-2 py-1 text-xs font-medium"
          :class="mode === 'between' ? 'bg-slate-700 text-slate-200' : 'bg-slate-900 text-slate-500'"
          @click="setMode('between')"
        >
          Between two nodes
        </button>
      </div>
    </div>

    <p class="mb-3 rounded-md border border-amber-800/50 bg-amber-950/30 px-3 py-2 text-xs text-amber-300">
      Potential paths only, derived from the graph data collected so far -- never proof of real exploitability,
      and the graph is not guaranteed to represent the complete attack surface. Verify every path manually.
    </p>

    <div class="space-y-3">
      <div>
        <p class="mb-1 text-xs text-slate-500">{{ mode === "critical" ? "Starting point" : "From" }}</p>
        <GraphSearchBar @select="onSelectFrom" />
        <p v-if="from" class="mt-1 text-xs text-slate-400">
          Selected: <span class="text-slate-200">{{ from.label }}</span>
          <span class="ml-1 rounded bg-slate-800 px-1.5 py-0.5 text-[10px]">{{ from.type }}</span>
        </p>
      </div>

      <div v-if="mode === 'between'">
        <p class="mb-1 text-xs text-slate-500">To</p>
        <GraphSearchBar @select="onSelectTo" />
        <p v-if="to" class="mt-1 text-xs text-slate-400">
          Selected: <span class="text-slate-200">{{ to.label }}</span>
          <span class="ml-1 rounded bg-slate-800 px-1.5 py-0.5 text-[10px]">{{ to.type }}</span>
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <label for="attack-path-max-hops" class="text-xs text-slate-500">Max hops</label>
        <select
          id="attack-path-max-hops"
          v-model.number="maxHops"
          class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-300"
        >
          <option v-for="h in [1, 2, 3, 4]" :key="h" :value="h">{{ h }}</option>
        </select>
        <button
          type="button"
          class="rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!from || (mode === 'between' && !to)"
          @click="search"
        >
          Search
        </button>
      </div>
    </div>

    <p v-if="loading" class="mt-3 text-sm text-slate-600">Searching for potential paths…</p>
    <p v-else-if="error" class="mt-3 text-sm text-red-400">{{ error }}</p>

    <div v-else-if="result" class="mt-3 space-y-3">
      <!-- The API's own disclaimer, not just the static banner above --
           it is the backend's authoritative wording and must never be
           silently dropped even though the two convey the same idea. -->
      <p class="text-[11px] italic text-slate-500">{{ result.disclaimer }}</p>
      <p v-if="result.paths.length === 0" class="text-sm text-slate-600">
        No potential path found within {{ maxHops }} hop(s) of the current graph data.
      </p>
      <p v-if="result.truncated" class="text-xs text-amber-400">
        More potential paths exist than shown below -- results capped, shortest paths kept.
      </p>
      <div
        v-for="(path, i) in result.paths"
        :key="i"
        class="rounded-md border border-slate-800 bg-slate-950/50 p-3"
      >
        <p class="mb-2 text-xs text-slate-500">Potential path {{ i + 1 }} · {{ path.hops }} hop(s)</p>
        <div class="flex flex-wrap items-center gap-1 text-xs">
          <template v-for="(node, ni) in path.nodes" :key="`${node.type}:${node.id}`">
            <span class="rounded bg-slate-800 px-2 py-1 text-slate-200">{{ node.label }}</span>
            <span v-if="ni < path.edges.length" class="text-slate-600">→ {{ path.edges[ni].relation }} →</span>
          </template>
        </div>
        <div class="mt-2 space-y-0.5 text-[11px] text-slate-600">
          <p v-for="edge in path.edges" :key="edge.id">{{ edge.relation }}: {{ edge.reason }}</p>
        </div>
      </div>
    </div>
  </div>
</template>
