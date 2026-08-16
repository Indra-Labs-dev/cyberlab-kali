<script setup lang="ts">
// The genuinely missing piece per the audit (layouts/default.vue had no
// topbar at all). Search results and the activity popover are both real
// data (useGlobalSearch / useRecentActivity, both backed by existing
// endpoints) -- no fabricated notification count, no fake user identity:
// there's no auth/account model in this backend, so the session indicator
// is a static label, not a fabricated "Admin" persona.
import { Bell, Menu, Search, Settings, X } from "@lucide/vue";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useGlobalSearch } from "~/composables/useGlobalSearch";
import { useRecentActivity } from "~/composables/useRecentActivity";
import { useSystemStatus } from "~/composables/useSystemStatus";

defineProps<{ sidebarOpen: boolean }>();
const emit = defineEmits<{ "toggle-sidebar": [] }>();

const { status, refresh: refreshStatus } = useSystemStatus();
const { items: activityItems, loading: activityLoading, error: activityError, load: loadActivity } = useRecentActivity();
const { results: searchResults, loading: searchLoading, search, clear: clearSearch } = useGlobalSearch();

const query = ref("");
const searchOpen = ref(false);
const activityOpen = ref(false);
const searchInput = ref<HTMLInputElement>();
let debounceHandle: ReturnType<typeof setTimeout> | undefined;

watch(query, (value) => {
  clearTimeout(debounceHandle);
  if (!value) {
    clearSearch();
    return;
  }
  debounceHandle = setTimeout(() => search(value), 250);
});

function toggleActivity() {
  activityOpen.value = !activityOpen.value;
  searchOpen.value = false;
  if (activityOpen.value) loadActivity();
}

function closeSearch() {
  searchOpen.value = false;
}

function onSearchBlur() {
  // Deferred so a result link's click (mousedown.prevent keeps focus off
  // the input, but blur can still fire on some browsers) has a chance to
  // register its navigation before the dropdown unmounts.
  setTimeout(closeSearch, 150);
}

function closeAll() {
  searchOpen.value = false;
  activityOpen.value = false;
}

async function onGlobalKeydown(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    searchOpen.value = true;
    await nextTick();
    searchInput.value?.focus();
  } else if (e.key === "Escape") {
    closeAll();
  }
}

const overallStatus = computed<"checking" | "ok" | "degraded">(() => {
  const values = [status.api, status.db, status.kali, status.ai];
  if (values.includes("checking")) return "checking";
  if (values.every((v) => v === "ok")) return "ok";
  return "degraded";
});
const statusLabel = computed(() => ({ checking: "Checking…", ok: "Systems nominal", degraded: "Degraded" })[overallStatus.value]);
const statusTone = computed<"warning" | "success" | "danger">(
  () => ({ checking: "warning", ok: "success", degraded: "danger" })[overallStatus.value] as "warning" | "success" | "danger",
);

onMounted(() => {
  refreshStatus();
  window.addEventListener("keydown", onGlobalKeydown);
});
onBeforeUnmount(() => {
  clearTimeout(debounceHandle);
  window.removeEventListener("keydown", onGlobalKeydown);
});
</script>

<template>
  <header
    class="sticky top-0 z-20 flex items-center gap-3 border-b border-white/5 bg-surface/50 px-4 py-2.5 backdrop-blur-xl relative after:pointer-events-none after:absolute after:inset-x-0 after:bottom-0 after:h-px after:bg-gradient-to-r after:from-transparent after:via-accent-500/40 after:to-transparent"
  >
    <button
      type="button"
      class="rounded-md border border-slate-700 p-2 text-slate-300 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 md:hidden"
      aria-controls="main-nav"
      :aria-expanded="sidebarOpen"
      aria-label="Toggle navigation menu"
      @click="emit('toggle-sidebar')"
    >
      <component :is="sidebarOpen ? X : Menu" class="h-5 w-5" aria-hidden="true" />
    </button>

    <div class="relative min-w-0 flex-1 sm:max-w-md">
      <Search class="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" aria-hidden="true" />
      <input
        ref="searchInput"
        v-model="query"
        type="search"
        placeholder="Search assets, findings, projects, tools… (⌘K)"
        class="w-full rounded-md border border-slate-700 bg-slate-900/50 py-1.5 pl-8 pr-3 text-sm text-slate-200 outline-none transition-all duration-200 placeholder:text-slate-500 focus:border-accent-500/60 focus:bg-slate-900/80 focus:shadow-glow-accent"
        @focus="searchOpen = true"
        @blur="onSearchBlur"
      />
      <Transition
        enter-active-class="transition duration-150 ease-out"
        enter-from-class="opacity-0 -translate-y-1"
        enter-to-class="opacity-100 translate-y-0"
        leave-active-class="transition duration-100 ease-in"
        leave-from-class="opacity-100 translate-y-0"
        leave-to-class="opacity-0 -translate-y-1"
      >
        <div
          v-if="searchOpen && query.trim().length >= 2"
          class="scrollbar-thin absolute left-0 right-0 top-full z-30 mt-1 max-h-80 overflow-y-auto rounded-md border border-slate-700 bg-slate-900/95 p-1.5 shadow-xl backdrop-blur-xl"
        >
          <p v-if="searchLoading" class="px-2 py-1.5 text-xs text-slate-500">Searching…</p>
          <p v-else-if="searchResults.length === 0" class="px-2 py-1.5 text-xs text-slate-500">No matches for "{{ query }}".</p>
          <NuxtLink
            v-for="result in searchResults"
            :key="`${result.type}-${result.id}`"
            :to="result.to"
            class="flex items-center justify-between gap-2 rounded px-2 py-1.5 text-sm text-slate-200 transition-colors hover:bg-slate-800"
            @mousedown.prevent
          >
            <span class="min-w-0 truncate">{{ result.label }}</span>
            <span class="shrink-0 text-[10px] uppercase tracking-wide text-slate-500">{{ result.type }}</span>
          </NuxtLink>
        </div>
      </Transition>
    </div>

    <div class="ml-auto flex items-center gap-1.5">
      <div class="hidden items-center gap-2 rounded-md border border-slate-800 bg-slate-900/40 px-2.5 py-1 text-xs text-slate-400 sm:flex">
        <UiPulseIndicator :tone="statusTone" size="sm" />
        {{ statusLabel }}
      </div>

      <div class="hidden h-5 w-px bg-white/10 sm:block" aria-hidden="true" />

      <div class="relative">
        <UiTooltip label="Recent activity">
          <button
            type="button"
            class="rounded-md p-2 text-slate-400 transition-colors hover:bg-slate-800/60 hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
            aria-label="Recent activity"
            :aria-expanded="activityOpen"
            @click="toggleActivity"
          >
            <Bell class="h-4 w-4" aria-hidden="true" />
          </button>
        </UiTooltip>
        <Transition
          enter-active-class="transition duration-150 ease-out"
          enter-from-class="opacity-0 -translate-y-1"
          enter-to-class="opacity-100 translate-y-0"
          leave-active-class="transition duration-100 ease-in"
          leave-from-class="opacity-100 translate-y-0"
          leave-to-class="opacity-0 -translate-y-1"
        >
          <div
            v-if="activityOpen"
            class="absolute right-0 top-full z-30 mt-2 w-80 rounded-md border border-slate-700 bg-slate-900/95 p-3 shadow-xl backdrop-blur-xl"
          >
            <p class="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Recent activity</p>
            <UiSkeleton v-if="activityLoading" :lines="4" />
            <UiErrorState v-else-if="activityError" :message="activityError" />
            <UiActivityFeed v-else :items="activityItems" />
          </div>
        </Transition>
      </div>

      <div class="hidden h-5 w-px bg-white/10 sm:block" aria-hidden="true" />

      <NuxtLink
        to="/settings"
        class="hidden items-center gap-2 rounded-md border border-slate-800 bg-slate-900/40 px-2.5 py-1.5 text-xs text-slate-400 transition-colors hover:border-slate-700 hover:bg-slate-800/60 hover:text-slate-200 sm:flex"
      >
        <Settings class="h-3.5 w-3.5" aria-hidden="true" />
        Lab Operator
      </NuxtLink>
    </div>
  </header>
</template>
