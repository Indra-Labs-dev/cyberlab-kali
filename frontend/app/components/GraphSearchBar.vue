<script setup lang="ts">
// ref/computed imported explicitly (not just Nuxt auto-import) so this
// component stays mountable in plain Vitest -- see GraphSearchBar.test.ts
// and the same pattern in app/composables/useAssets.ts.
import { ref, watch } from "vue";
import { type GraphSearchResult, useGraph } from "~/composables/useGraph";
import type { GraphNodeType } from "~/types/graph";

const emit = defineEmits<{ select: [result: GraphSearchResult] }>();

const TYPES: GraphNodeType[] = ["ASSET", "FINDING", "CVE", "SERVICE", "TECHNOLOGY"];

const { searchNodes } = useGraph();

const query = ref("");
const type = ref<GraphNodeType>("ASSET");
const loading = ref(false);
const error = ref("");
const results = ref<GraphSearchResult[]>([]);
const searched = ref(false);

// Guards against an earlier, slower request overwriting a later one's
// results (e.g. switching ASSET -> FINDING mid-search).
let requestId = 0;

async function runSearch() {
  const q = query.value.trim();
  if (!q) {
    results.value = [];
    searched.value = false;
    error.value = "";
    return;
  }
  const id = ++requestId;
  loading.value = true;
  error.value = "";
  try {
    const r = await searchNodes(type.value, q);
    if (id !== requestId) return;
    results.value = r;
    searched.value = true;
  } catch (err: any) {
    if (id !== requestId) return;
    error.value = err?.data?.detail || "Search failed";
    results.value = [];
  } finally {
    if (id === requestId) loading.value = false;
  }
}

function selectResult(r: GraphSearchResult) {
  emit("select", r);
  reset();
}

function reset() {
  query.value = "";
  results.value = [];
  searched.value = false;
  error.value = "";
}

let debounceTimer: ReturnType<typeof setTimeout> | undefined;
watch([query, type], () => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(runSearch, 250);
});
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center gap-2">
      <label for="graph-search-type" class="sr-only">Node type</label>
      <select
        id="graph-search-type"
        v-model="type"
        class="rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200"
      >
        <option v-for="t in TYPES" :key="t" :value="t">{{ t }}</option>
      </select>

      <label for="graph-search-input" class="sr-only">Search the security graph</label>
      <input
        id="graph-search-input"
        v-model="query"
        type="text"
        :placeholder="
          type === 'ASSET' || type === 'FINDING' ? `Search ${type.toLowerCase()}s…` : `Enter exact ${type.toLowerCase()} id…`
        "
        class="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200"
        @keydown.enter="runSearch"
      />

      <button
        v-if="query"
        type="button"
        aria-label="Clear search"
        class="rounded-md border border-slate-700 px-2 py-1.5 text-xs text-slate-400 hover:bg-slate-800"
        @click="reset"
      >
        ✕
      </button>
    </div>

    <p v-if="loading" class="mt-2 text-xs text-slate-600">Searching…</p>
    <p v-else-if="error" class="mt-2 text-xs text-red-400">{{ error }}</p>
    <ul
      v-else-if="results.length"
      role="listbox"
      aria-label="Search results"
      class="mt-2 max-h-64 space-y-1 overflow-y-auto"
    >
      <li v-for="r in results" :key="`${r.type}:${r.id}`">
        <button
          type="button"
          role="option"
          class="flex w-full items-center justify-between gap-2 rounded-md border border-slate-800 bg-slate-900/40 px-3 py-1.5 text-left text-sm text-slate-200 hover:bg-slate-800/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
          @click="selectResult(r)"
        >
          <span class="truncate">{{ r.label }}</span>
          <span class="shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-500">{{ r.type }}</span>
        </button>
      </li>
    </ul>
    <p v-else-if="searched" class="mt-2 text-xs text-slate-600">No results.</p>
  </div>
</template>
