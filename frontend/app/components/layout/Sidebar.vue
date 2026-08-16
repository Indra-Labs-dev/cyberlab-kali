<script setup lang="ts">
// Extracted from the old layouts/default.vue inline <aside> (18b/19-era
// nav), regrouped around the product's actual surface (Workspace /
// Security Operations / AI / Intelligence / System) instead of the old
// flat "Attack Surface" + "Execution & Support" split. Every entry below
// is a route that exists under app/pages/ -- verified against the routing
// audit, nothing fictional. The old disabled "Recon (Soon)" stub is
// dropped: there's no backend Recon feature actually planned as its own
// page (recon happens via Tools/Chains/Missions), so a permanently
// disabled nav item was just confusing.
import {
  FileText,
  FlaskConical,
  FolderKanban,
  LayoutDashboard,
  Link2,
  Radar,
  Rocket,
  Server,
  Settings,
  Share2,
  ShieldAlert,
  Sparkles,
  Terminal,
  Wrench,
} from "@lucide/vue";
import type { Component } from "vue";
import { isNavItemActive } from "~/utils/navigation";

interface NavItem {
  to: string;
  label: string;
  icon: Component;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const navGroups: NavGroup[] = [
  {
    label: "Workspace",
    items: [
      { to: "/", label: "Overview", icon: LayoutDashboard },
      { to: "/projects", label: "Projects", icon: FolderKanban },
      { to: "/assets", label: "Assets", icon: Server },
    ],
  },
  {
    label: "Security Operations",
    items: [
      { to: "/findings", label: "Findings", icon: ShieldAlert },
      { to: "/graph", label: "Security Graph", icon: Share2 },
      { to: "/scans", label: "Scans", icon: Radar },
      { to: "/chains", label: "Chain Templates", icon: Link2 },
      { to: "/tools", label: "Tools", icon: Wrench },
    ],
  },
  {
    label: "AI",
    items: [
      { to: "/ai", label: "AI Assistant", icon: Sparkles },
      { to: "/ai/missions", label: "AI Missions", icon: Rocket },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { to: "/intelligence", label: "Intelligence", icon: FileText },
      { to: "/reports", label: "Reports", icon: FileText },
    ],
  },
  {
    label: "System",
    items: [
      { to: "/labs", label: "Labs", icon: FlaskConical },
      { to: "/terminal", label: "Terminal", icon: Terminal },
      { to: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

// `currentPath` is passed in (rather than calling useRoute() here) so this
// component stays a pure function of its props -- directly mountable in
// plain Vitest, same reasoning as isNavItemActive's own extraction below.
const props = defineProps<{ open: boolean; currentPath: string }>();
const emit = defineEmits<{ close: [] }>();

function isActive(path: string): boolean {
  return isNavItemActive(props.currentPath, path);
}
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm md:hidden"
    aria-hidden="true"
    @click="emit('close')"
  ></div>

  <aside
    id="main-nav"
    class="fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 -translate-x-full flex-col border-r border-white/5 bg-surface/80 backdrop-blur-xl transition-transform duration-200 after:pointer-events-none after:absolute after:inset-y-0 after:right-0 after:w-px after:bg-gradient-to-b after:from-transparent after:via-accent-500/30 after:to-transparent md:static md:z-auto md:translate-x-0 md:bg-surface/40"
    :class="open && 'translate-x-0'"
  >
    <div class="hidden border-b border-white/5 px-4 py-3 md:block">
      <NuxtLink to="/">
        <img src="/logo.png" alt="CyberLab" class="mx-auto h-auto w-full max-w-[180px]" />
      </NuxtLink>
    </div>

    <nav aria-label="Main" class="scrollbar-thin flex-1 space-y-5 overflow-y-auto px-2 py-3">
      <div v-for="group in navGroups" :key="group.label">
        <p class="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-600">{{ group.label }}</p>
        <NuxtLink
          v-for="item in group.items"
          :key="item.to"
          :to="item.to"
          :aria-current="isActive(item.to) ? 'page' : undefined"
          class="relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
          :class="
            isActive(item.to)
              ? 'bg-gradient-to-r from-accent-500/20 to-accent-500/[0.03] text-accent-400 before:absolute before:left-0 before:top-1/2 before:h-5 before:w-0.5 before:-translate-y-1/2 before:rounded-full before:bg-accent-400 before:shadow-glow-accent'
              : 'text-slate-400 hover:translate-x-0.5 hover:bg-slate-800/60 hover:text-slate-200'
          "
        >
          <component
            :is="item.icon"
            class="h-4 w-4 shrink-0"
            :class="isActive(item.to) && 'drop-shadow-[0_0_4px_rgba(34,211,238,0.7)]'"
            aria-hidden="true"
          />
          <span class="truncate">{{ item.label }}</span>
        </NuxtLink>
      </div>
    </nav>

    <div class="border-t border-white/5 px-5 py-3 text-xs text-slate-600">Lab / authorized use only</div>
  </aside>
</template>
