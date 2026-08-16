<script setup lang="ts">
// Generic timeline list -- generalizes the row markup already duplicated
// across RecentChangesWidget.vue / ActiveFindingsWidget.vue / dashboard job
// lists, for the new Topbar activity popover and Dashboard activity
// section. Each item is real data assembled by the caller (jobs, findings,
// asset-changes) -- this component has no fetch logic of its own.
export interface ActivityItem {
  id: string;
  label: string;
  detail?: string;
  timestamp: string;
  to?: string;
  tone?: "default" | "success" | "warning" | "danger" | "ai";
}

defineProps<{ items: ActivityItem[]; emptyMessage?: string }>();

const toneDot: Record<string, string> = {
  default: "bg-slate-500",
  success: "bg-success-400",
  warning: "bg-warning-400",
  danger: "bg-danger-400",
  ai: "bg-ai-400",
};

function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
</script>

<template>
  <p v-if="items.length === 0" class="text-sm text-slate-600">{{ emptyMessage ?? "No recent activity." }}</p>
  <ul v-else class="scrollbar-thin space-y-1.5">
    <!-- NuxtLink is a Nuxt compiler-injected component: resolving it
         dynamically via `:is="'NuxtLink'"` (a string) silently renders an
         inert <nuxtlink> custom element instead of an <a>, no console
         warning -- see Button.vue's docstring. Two branches, same as there. -->
    <li v-for="item in items" :key="item.id">
      <NuxtLink v-if="item.to" :to="item.to" class="flex items-start gap-2.5 rounded-md px-2 py-1.5 text-sm hover:bg-slate-800/60">
        <span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" :class="toneDot[item.tone ?? 'default']" aria-hidden="true" />
        <span class="min-w-0 flex-1">
          <span class="block truncate text-slate-200">{{ item.label }}</span>
          <span v-if="item.detail" class="block truncate text-xs text-slate-500">{{ item.detail }}</span>
        </span>
        <span class="shrink-0 text-xs text-slate-600">{{ formatTime(item.timestamp) }}</span>
      </NuxtLink>
      <div v-else class="flex items-start gap-2.5 rounded-md px-2 py-1.5 text-sm">
        <span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" :class="toneDot[item.tone ?? 'default']" aria-hidden="true" />
        <span class="min-w-0 flex-1">
          <span class="block truncate text-slate-200">{{ item.label }}</span>
          <span v-if="item.detail" class="block truncate text-xs text-slate-500">{{ item.detail }}</span>
        </span>
        <span class="shrink-0 text-xs text-slate-600">{{ formatTime(item.timestamp) }}</span>
      </div>
    </li>
  </ul>
</template>
