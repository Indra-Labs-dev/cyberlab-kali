// Pure merge/format logic for the cross-entity activity feed (Topbar
// popover + Dashboard activity section) -- fed by three already-existing
// endpoints (jobs, findings, asset-changes), same data SOC-lite's widgets
// use, just interleaved and sorted by time. `changeSummary` is
// deliberately duplicated from RecentChangesWidget.vue rather than
// imported from it, same precedent as that component's own docstring
// (small pure helpers are kept local, not shared, in this codebase).
import type { ActivityItem } from "~/components/ui/ActivityFeed.vue";

export interface JobActivitySource {
  id: string;
  tool: string;
  target: string;
  status: string;
  created_at: string;
}

export interface FindingActivitySource {
  id: string;
  title: string;
  target: string;
  severity: string;
  first_seen: string;
}

export interface ChangeActivitySource {
  id: string;
  job_id: string;
  change_type: string;
  field: string;
  severity: string;
  detected_at: string;
}

const JOB_TONE: Record<string, ActivityItem["tone"]> = {
  SUCCESS: "success",
  FAILED: "danger",
  RUNNING: "warning",
  QUEUED: "default",
  CANCELLED: "default",
};

const SEVERITY_TONE: Record<string, ActivityItem["tone"]> = {
  CRITICAL: "danger",
  HIGH: "danger",
  MEDIUM: "warning",
  LOW: "success",
  INFO: "default",
};

function changeSummary(change: ChangeActivitySource): string {
  const label = change.field;
  if (change.change_type === "PORT_OPENED") return `Port ${label.replace("port:", "")} opened`;
  if (change.change_type === "PORT_CLOSED") return `Port ${label.replace("port:", "")} closed`;
  if (change.change_type.startsWith("TECHNOLOGY")) {
    const tech = label.replace("technology:", "");
    if (change.change_type === "TECHNOLOGY_ADDED") return `${tech} detected`;
    if (change.change_type === "TECHNOLOGY_REMOVED") return `${tech} no longer detected`;
    return `${tech} changed`;
  }
  if (change.change_type === "CERTIFICATE_CHANGED") return `Certificate changed (${label})`;
  if (change.change_type === "HTTP_CHANGED") return "HTTP status changed";
  if (change.change_type === "SERVICE_CHANGED") return `Service changed on ${label.replace("port:", "")}`;
  return label;
}

export function mergeActivity(
  jobs: JobActivitySource[],
  findings: FindingActivitySource[],
  changes: ChangeActivitySource[],
  limit = 10,
): ActivityItem[] {
  const items: ActivityItem[] = [
    ...jobs.map((j) => ({
      id: `job-${j.id}`,
      label: `${j.tool} on ${j.target}`,
      detail: j.status,
      timestamp: j.created_at,
      to: `/scans/${j.id}`,
      tone: JOB_TONE[j.status] ?? "default",
    })),
    ...findings.map((f) => ({
      id: `finding-${f.id}`,
      label: f.title,
      detail: f.target,
      timestamp: f.first_seen,
      to: `/findings/${f.id}`,
      tone: SEVERITY_TONE[f.severity] ?? "default",
    })),
    ...changes.map((c) => ({
      id: `change-${c.id}`,
      label: changeSummary(c),
      timestamp: c.detected_at,
      to: `/scans/${c.job_id}`,
      tone: SEVERITY_TONE[c.severity] ?? "default",
    })),
  ];

  return items.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()).slice(0, limit);
}
