<script setup lang="ts">
const nav = [
  { to: "/", label: "Dashboard", icon: "▣" },
  { to: "/projects", label: "Projects", icon: "◈" },
  { to: "/targets", label: "Targets", icon: "◎" },
  { to: "/tools", label: "Tools", icon: "⚒" },
  { to: "/scans", label: "Scans", icon: "⌘" },
  { to: "/labs", label: "Labs", icon: "⬢" },
  { to: "/terminal", label: "Terminal", icon: "⌥" },
  { to: "/ai", label: "AI Assistant", icon: "✦" },
  { to: "/findings", label: "Findings", icon: "⚠" },
  { to: "/reports", label: "Reports", icon: "≡" },
  { to: "/settings", label: "Settings", icon: "⚙" },
];
const route = useRoute();
</script>

<template>
  <div class="flex min-h-screen bg-slate-950 text-slate-100">
    <aside class="flex w-56 shrink-0 flex-col border-r border-slate-800 bg-slate-900/40">
      <div class="flex items-center gap-2 border-b border-slate-800 px-5 py-4">
        <span class="h-2 w-2 rounded-full bg-emerald-500"></span>
        <span class="font-semibold tracking-tight text-emerald-400">CyberLab</span>
      </div>
      <nav class="flex-1 space-y-0.5 px-2 py-3">
        <NuxtLink
          v-for="item in nav"
          :key="item.to"
          :to="item.to"
          class="flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors"
          :class="
            route.path === item.to
              ? 'bg-emerald-500/10 text-emerald-400'
              : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
          "
        >
          <span class="w-4 text-center">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </NuxtLink>
      </nav>
      <div class="border-t border-slate-800 px-5 py-3 text-xs text-slate-600">
        Lab / authorized use only
      </div>
    </aside>
    <main class="flex-1 overflow-y-auto">
      <slot />
    </main>
  </div>
</template>
