import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import Badge from "./Badge.vue";
import EmptyState from "./EmptyState.vue";
import EvidenceTimeline from "./EvidenceTimeline.vue";
import JobStatusBadge from "./JobStatusBadge.vue";
import SeverityBadge from "./SeverityBadge.vue";

const globalComponents = {
  global: {
    components: { Badge, EmptyState, JobStatusBadge, SeverityBadge },
    stubs: { NuxtLink: { template: '<a :href="to"><slot /></a>', props: ["to"] } },
  },
};

function job(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "job-1",
    tool: "nmap",
    target: "10.0.0.1",
    status: "SUCCESS",
    created_at: "2026-08-01T10:00:00Z",
    finished_at: "2026-08-01T10:05:00Z",
    evidence_sha256: "a".repeat(64),
    ...overrides,
  };
}

function finding(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "finding-1",
    job_id: "job-1",
    target: "10.0.0.1",
    source_tool: "nmap",
    title: "Open port 80",
    severity: "MEDIUM",
    first_seen: "2026-08-01T10:06:00Z",
    ...overrides,
  };
}

describe("EvidenceTimeline", () => {
  it("shows an empty state with no jobs or findings", () => {
    const wrapper = mount(EvidenceTimeline, { props: { jobs: [], findings: [] }, ...globalComponents });
    expect(wrapper.text()).toContain("No scans or findings yet.");
  });

  it("renders a job entry with its tool, target, status, and truncated hash", () => {
    const wrapper = mount(EvidenceTimeline, { props: { jobs: [job()], findings: [] }, ...globalComponents });
    expect(wrapper.text()).toContain("nmap");
    expect(wrapper.text()).toContain("10.0.0.1");
    expect(wrapper.text()).toContain("sha256:");
    expect(wrapper.text()).toContain("a".repeat(12));
    expect(wrapper.text()).not.toContain("a".repeat(64)); // truncated, not the full 64-char hash
  });

  it("omits the hash line when evidence_sha256 is null", () => {
    const wrapper = mount(EvidenceTimeline, {
      props: { jobs: [job({ evidence_sha256: null })], findings: [] },
      ...globalComponents,
    });
    expect(wrapper.text()).not.toContain("sha256:");
  });

  it("renders a finding entry with its severity and title", () => {
    const wrapper = mount(EvidenceTimeline, { props: { jobs: [], findings: [finding()] }, ...globalComponents });
    expect(wrapper.text()).toContain("Open port 80");
    expect(wrapper.text()).toContain("MEDIUM");
  });

  it("sorts jobs and findings chronologically, most recent first", () => {
    const oldJob = job({ id: "old", finished_at: "2026-08-01T08:00:00Z" });
    const newFinding = finding({ id: "new", first_seen: "2026-08-01T12:00:00Z" });
    const wrapper = mount(EvidenceTimeline, {
      props: { jobs: [oldJob], findings: [newFinding] },
      ...globalComponents,
    });
    const text = wrapper.text();
    expect(text.indexOf("Open port 80")).toBeLessThan(text.indexOf("nmap"));
  });

  it("falls back to created_at for a job with no finished_at yet", () => {
    const runningJob = job({ status: "RUNNING", finished_at: null, created_at: "2026-08-01T09:00:00Z" });
    const wrapper = mount(EvidenceTimeline, { props: { jobs: [runningJob], findings: [] }, ...globalComponents });
    expect(wrapper.text()).toContain("RUNNING");
  });
});
