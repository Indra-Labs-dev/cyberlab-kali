import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { GraphEdge, GraphNode } from "~/types/graph";
import Badge from "./Badge.vue";
import CveDetailPanel from "./CveDetailPanel.vue";
import EmptyState from "./EmptyState.vue";
import LoadingState from "./LoadingState.vue";
import RiskBadge from "./RiskBadge.vue";
import SeverityBadge from "./SeverityBadge.vue";

type Connection = { edge: GraphEdge; otherEnd: GraphNode | null };

const apiFetchMock = vi.fn();
vi.mock("~/composables/useApi", () => ({
  useApi: () => ({ apiFetch: apiFetchMock }),
}));

const globalStubs = {
  global: {
    components: { Badge, LoadingState, EmptyState, SeverityBadge, RiskBadge },
    stubs: { NuxtLink: { template: "<a :href=\"to\"><slot /></a>", props: ["to"] } },
  },
};

function connection(overrides: Partial<Connection> = {}): Connection {
  return {
    edge: {
      id: "e1",
      from_type: "FINDING",
      from_id: "f1",
      to_type: "CVE",
      to_id: "CVE-2021-44228",
      relation: "REFERENCES_CVE",
      source: "nuclei",
      reason: "",
      metadata: {},
    },
    otherEnd: { id: "f1", type: "FINDING", label: "Log4Shell", metadata: {} },
    ...overrides,
  };
}

describe("CveDetailPanel", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it("shows the empty state and skips fetching when there are no REFERENCES_CVE connections", async () => {
    const wrapper = mount(CveDetailPanel, {
      props: { cveId: "CVE-2021-44228", connections: [] },
      ...globalStubs,
    });
    await flushPromises();
    expect(apiFetchMock).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("No findings in the current graph reference this CVE.");
  });

  it("ignores connections that aren't REFERENCES_CVE edges to a FINDING", async () => {
    const wrapper = mount(CveDetailPanel, {
      props: {
        cveId: "CVE-2021-44228",
        connections: [connection({ edge: { id: "e2", from_type: "ASSET", from_id: "a1", to_type: "CVE", to_id: "x", relation: "HAS_FINDING", source: "system", reason: "", metadata: {} } })],
      },
      ...globalStubs,
    });
    await flushPromises();
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("fetches and renders findings referenced via REFERENCES_CVE edges", async () => {
    apiFetchMock.mockResolvedValue({
      id: "f1",
      job_id: "j1",
      target: "http://example.com",
      source_tool: "nuclei",
      title: "Log4Shell RCE",
      description: "",
      severity: "CRITICAL",
      confidence: "HIGH",
      evidence: {},
      recommendation: null,
      created_at: "2026-01-01T00:00:00Z",
      cve_ids: ["CVE-2021-44228"],
      cvss_score: 10,
      epss_score: 0.97,
      kev: true,
      risk_score: 95,
      risk_priority: "CRITICAL",
      risk_calculated_at: null,
      status: "NEW",
      first_seen: "2026-01-01T00:00:00Z",
      last_seen: "2026-01-01T00:00:00Z",
      observation_count: 1,
      source_tools: ["nuclei"],
    });
    const wrapper = mount(CveDetailPanel, {
      props: { cveId: "CVE-2021-44228", connections: [connection()] },
      ...globalStubs,
    });
    await flushPromises();

    expect(apiFetchMock).toHaveBeenCalledWith("/api/findings/f1");
    expect(wrapper.text()).toContain("Log4Shell RCE");
    expect(wrapper.text()).toContain("CVSS 10");
    expect(wrapper.text()).toContain("KEV");
    expect(wrapper.text()).toContain("YES");
  });

  it("shows an error message when a finding fetch fails", async () => {
    apiFetchMock.mockRejectedValue({ data: { detail: "boom" } });
    const wrapper = mount(CveDetailPanel, {
      props: { cveId: "CVE-2021-44228", connections: [connection()] },
      ...globalStubs,
    });
    await flushPromises();
    expect(wrapper.text()).toContain("boom");
  });

  it("re-fetches when cveId changes", async () => {
    apiFetchMock.mockResolvedValue({
      id: "f1",
      job_id: "j1",
      target: "x",
      source_tool: "nuclei",
      title: "T",
      description: "",
      severity: "LOW",
      confidence: "LOW",
      evidence: {},
      recommendation: null,
      created_at: "2026-01-01T00:00:00Z",
      cve_ids: [],
      cvss_score: null,
      epss_score: null,
      kev: null,
      risk_score: null,
      risk_priority: null,
      risk_calculated_at: null,
      status: "NEW",
      first_seen: "2026-01-01T00:00:00Z",
      last_seen: "2026-01-01T00:00:00Z",
      observation_count: 1,
      source_tools: ["nuclei"],
    });
    const wrapper = mount(CveDetailPanel, {
      props: { cveId: "CVE-2021-44228", connections: [connection()] },
      ...globalStubs,
    });
    await flushPromises();
    apiFetchMock.mockClear();

    await wrapper.setProps({ cveId: "CVE-2022-0001", connections: [] });
    await flushPromises();
    expect(apiFetchMock).not.toHaveBeenCalled(); // no connections for the new CVE -> no fetch
    expect(wrapper.text()).toContain("No findings in the current graph reference this CVE.");
  });
});
