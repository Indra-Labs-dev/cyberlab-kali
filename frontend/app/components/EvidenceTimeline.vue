<script setup lang="ts">
// Phase 20 -- Evidence & Chain of Custody. A pure presentational merge of
// already-fetched Jobs + Findings, sorted chronologically -- never fetches
// anything itself (unlike AssetChangeTimeline.vue, which owns its own
// fetch/filters for a *different* data source, AssetChangeEvent, that this
// component deliberately does not touch: the roadmap scopes this timeline
// to Job/Finding only, "pas une nouvelle table Evidence dupliquant les
// données de Job"). Shared between the Asset page (asset-scoped jobs/
// findings) and the Project page (project-scoped) via props, so the merge/
// sort logic exists exactly once.
import { computed } from "vue";
import { formatDate } from "~/utils/datetime";
import type { Severity } from "~/types/finding";

interface Job {
  id: string;
  tool: string;
  target: string;
  status: string;
  created_at: string;
  finished_at: string | null;
  evidence_sha256: string | null;
}

// Deliberately local/minimal, not the full shared ~/types/finding.ts
// Finding -- every page that already fetches findings for its own list
// (Asset/Project) declares its own narrower local interface too (see
// ~/types/finding.ts's own comment on that convention); requiring the
// full shared type here would force every consumer to widen its local
// interface just to satisfy this component's props.
interface Finding {
  id: string;
  job_id: string;
  title: string;
  severity: string;
  source_tool: string;
  first_seen: string;
}

const props = defineProps<{ jobs: Job[]; findings: Finding[] }>();

type TimelineEntry =
  | { type: "job"; timestamp: string; job: Job }
  | { type: "finding"; timestamp: string; finding: Finding };

// Jobs are timestamped by when they actually completed (finished_at),
// falling back to created_at for a still-QUEUED/RUNNING job -- the
// completion moment is the meaningful "event" for a chain-of-custody
// timeline, not when it was merely requested. Findings are timestamped by
// first_seen -- when this evidence was first observed, not last re-confirmed.
const entries = computed<TimelineEntry[]>(() => {
  const jobEntries: TimelineEntry[] = props.jobs.map((job) => ({
    type: "job",
    timestamp: job.finished_at || job.created_at,
    job,
  }));
  const findingEntries: TimelineEntry[] = props.findings.map((finding) => ({
    type: "finding",
    timestamp: finding.first_seen,
    finding,
  }));
  return [...jobEntries, ...findingEntries].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
  );
});

function truncatedHash(hash: string): string {
  return `${hash.slice(0, 12)}…`;
}
</script>

<template>
  <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
    <h2 class="mb-3 text-sm font-semibold text-slate-300">Evidence Timeline</h2>
    <p class="mb-3 text-xs text-slate-500">
      Every scan and finding, in the order they actually happened — a chronological chain of custody, not a new
      data store.
    </p>

    <EmptyState v-if="entries.length === 0" message="No scans or findings yet." />
    <div v-else class="space-y-3">
      <div
        v-for="entry in entries"
        :key="`${entry.type}-${entry.type === 'job' ? entry.job.id : entry.finding.id}`"
        class="flex items-start gap-3 border-b border-slate-800 pb-3 last:border-0 last:pb-0"
      >
        <template v-if="entry.type === 'job'">
          <span class="mt-0.5 text-base leading-none">▶</span>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <p class="text-sm text-slate-200">
                <span class="font-medium">{{ entry.job.tool }}</span> → {{ entry.job.target }}
              </p>
              <JobStatusBadge :status="entry.job.status" />
            </div>
            <p class="text-xs text-slate-600">{{ formatDate(entry.timestamp) }}</p>
            <p v-if="entry.job.evidence_sha256" class="mt-0.5 font-mono text-xs text-slate-600" :title="entry.job.evidence_sha256">
              sha256:{{ truncatedHash(entry.job.evidence_sha256) }}
            </p>
          </div>
          <NuxtLink :to="`/scans/${entry.job.id}`" class="shrink-0 text-xs text-emerald-400 hover:underline">scan</NuxtLink>
        </template>
        <template v-else>
          <span class="mt-0.5 text-base leading-none">⚠</span>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <SeverityBadge :severity="(entry.finding.severity as Severity)" size="sm" />
              <p class="truncate text-sm text-slate-200">{{ entry.finding.title }}</p>
            </div>
            <p class="text-xs text-slate-600">{{ formatDate(entry.timestamp) }} · {{ entry.finding.source_tool }}</p>
          </div>
          <NuxtLink :to="`/scans/${entry.finding.job_id}`" class="shrink-0 text-xs text-emerald-400 hover:underline">scan</NuxtLink>
        </template>
      </div>
    </div>
  </div>
</template>
