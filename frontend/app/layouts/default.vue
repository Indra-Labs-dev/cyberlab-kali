<script setup lang="ts">
interface NavItem {
  to: string;
  label: string;
  icon: string;
}

// Attack Surface Management first, execution/collection mechanisms second
// (18b) -- reflects the product model built up through Phases 13-17, not
// just a list of pages. Security Graph and Intelligence became real pages
// in 18c. Recon stays a disabled "Soon" entry (see soonSecondary below): it
// depends on a global GET /api/schedules-style listing endpoint that does
// not exist yet, unlike Graph/Intelligence which had real backend routes
// already (Phase 15/17).
const primaryNav: NavItem[] = [
  { to: "/", label: "Overview", icon: "▣" },
  { to: "/projects", label: "Projects", icon: "◈" },
  { to: "/assets", label: "Assets", icon: "◎" },
  { to: "/findings", label: "Findings", icon: "⚠" },
  { to: "/graph", label: "Security Graph", icon: "◇" },
  { to: "/intelligence", label: "Intelligence", icon: "◆" },
];
const soonPrimary: NavItem[] = [];

const soonSecondary: NavItem[] = [{ to: "/recon", label: "Recon", icon: "⟳" }];
const secondaryNav: NavItem[] = [
  { to: "/tools", label: "Tools", icon: "⚒" },
  { to: "/scans", label: "Scans", icon: "⌘" },
  { to: "/terminal", label: "Terminal", icon: "⌥" },
  { to: "/labs", label: "Labs", icon: "⬢" },
  { to: "/ai", label: "AI Assistant", icon: "✦" },
  { to: "/reports", label: "Reports", icon: "≡" },
  { to: "/settings", label: "Settings", icon: "⚙" },
];

const route = useRoute();
const sidebarOpen = ref(false);

function isActive(path: string): boolean {
  return isNavItemActive(route.path, path);
}

function closeSidebar() {
  sidebarOpen.value = false;
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape" && sidebarOpen.value) closeSidebar();
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));
watch(() => route.path, closeSidebar);
</script>

<template>
  <div class="min-h-screen bg-slate-950 text-slate-100 md:flex">
    <div class="flex items-center justify-between border-b border-slate-800 bg-slate-900/95 px-4 py-3 md:hidden">
      <NuxtLink to="/" class="shrink-0">
        <img src="/logo.png" alt="CyberLab" class="h-8 w-auto" />
      </NuxtLink>
      <button
        type="button"
        class="rounded-md border border-slate-700 p-2 text-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
        aria-controls="main-nav"
        :aria-expanded="sidebarOpen"
        aria-label="Toggle navigation menu"
        @click="sidebarOpen = !sidebarOpen"
      >
        <span aria-hidden="true">{{ sidebarOpen ? "✕" : "☰" }}</span>
      </button>
    </div>

    <div
      v-if="sidebarOpen"
      class="fixed inset-0 z-30 bg-black/50 md:hidden"
      aria-hidden="true"
      @click="closeSidebar"
    ></div>

    <aside
      id="main-nav"
      class="fixed inset-y-0 left-0 z-40 flex w-56 shrink-0 -translate-x-full flex-col border-r border-slate-800 bg-slate-900 transition-transform duration-200 md:static md:z-auto md:w-56 md:translate-x-0 md:bg-slate-900/40"
      :class="sidebarOpen && 'translate-x-0'"
    >
      <div class="hidden border-b border-slate-800 px-4 py-3 md:block">
        <NuxtLink to="/">
          <img src="/logo.png" alt="CyberLab" class="mx-auto h-auto w-full max-w-[180px]" />
        </NuxtLink>
      </div>

      <nav aria-label="Main" class="flex-1 space-y-4 overflow-y-auto px-2 py-3">
        <div>
          <p class="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-600">Attack Surface</p>
          <NuxtLink
            v-for="item in primaryNav"
            :key="item.to"
            :to="item.to"
            :aria-current="isActive(item.to) ? 'page' : undefined"
            class="flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
            :class="
              isActive(item.to)
                ? 'bg-emerald-500/10 text-emerald-400'
                : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
            "
          >
            <span class="w-4 text-center" aria-hidden="true">{{ item.icon }}</span>
            <span>{{ item.label }}</span>
          </NuxtLink>
          <button
            v-for="item in soonPrimary"
            :key="item.to"
            type="button"
            disabled
            :aria-label="`${item.label}, coming soon`"
            title="Coming soon"
            class="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-slate-600"
          >
            <span class="w-4 text-center" aria-hidden="true">{{ item.icon }}</span>
            <span>{{ item.label }}</span>
            <span class="ml-auto rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-500">Soon</span>
          </button>
        </div>

        <div>
          <p class="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-600">Execution &amp; Support</p>
          <button
            v-for="item in soonSecondary"
            :key="item.to"
            type="button"
            disabled
            :aria-label="`${item.label}, coming soon`"
            title="Coming soon"
            class="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-slate-600"
          >
            <span class="w-4 text-center" aria-hidden="true">{{ item.icon }}</span>
            <span>{{ item.label }}</span>
            <span class="ml-auto rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-500">Soon</span>
          </button>
          <NuxtLink
            v-for="item in secondaryNav"
            :key="item.to"
            :to="item.to"
            :aria-current="isActive(item.to) ? 'page' : undefined"
            class="flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
            :class="
              isActive(item.to)
                ? 'bg-emerald-500/10 text-emerald-400'
                : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
            "
          >
            <span class="w-4 text-center" aria-hidden="true">{{ item.icon }}</span>
            <span>{{ item.label }}</span>
          </NuxtLink>
        </div>
      </nav>

      <div class="border-t border-slate-800 px-5 py-3 text-xs text-slate-600">Lab / authorized use only</div>
    </aside>

    <main class="min-w-0 flex-1 overflow-y-auto">
      <slot />
    </main>
  </div>
</template>
