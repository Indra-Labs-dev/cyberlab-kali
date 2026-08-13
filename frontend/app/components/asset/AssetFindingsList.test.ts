import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { Finding } from "~/types/finding";
import EmptyState from "../EmptyState.vue";
import RiskBadge from "../RiskBadge.vue";
import SeverityBadge from "../SeverityBadge.vue";
import AssetFindingsList from "./AssetFindingsList.vue";

// Real Nuxt auto-registers NuxtLink/SeverityBadge/RiskBadge/EmptyState
// project-wide; this plain Vitest setup doesn't (see vitest.config.ts), so
// they're provided explicitly here -- same reasoning as useApi being
// imported explicitly in app/composables/useAssets.ts. NuxtLink is stubbed
// as a plain <a> since only its `to` -> `href` mapping matters for this
// test.
const globalStubs = {
  global: {
    components: { SeverityBadge, RiskBadge, EmptyState },
    stubs: { NuxtLink: { template: "<a :href=\"to\"><slot /></a>", props: ["to"] } },
  },
};

function makeFinding(overrides: Partial<Finding> = {}): Finding {
  return {
    id: "f1",
    job_id: "j1",
    target: "http://example.com",
    source_tool: "nuclei",
    title: "Technology detected: Apache",
    description: "",
    severity: "INFO" as const,
    confidence: "MEDIUM" as const,
    evidence: {},
    recommendation: null,
    created_at: "2026-01-01T00:00:00Z",
    cve_ids: [],
    cvss_score: null,
    epss_score: null,
    kev: null,
    risk_score: 0,
    risk_priority: "INFORMATIONAL" as const,
    risk_calculated_at: null,
    status: "NEW" as const,
    first_seen: "2026-01-01T00:00:00Z",
    last_seen: "2026-01-01T00:00:00Z",
    observation_count: 1,
    source_tools: ["nuclei"],
    ...overrides,
  };
}

describe("AssetFindingsList", () => {
  it("shows the empty state when there are no findings", () => {
    const wrapper = mount(AssetFindingsList, { props: { findings: [] }, ...globalStubs });
    expect(wrapper.text()).toContain("No findings for this asset yet.");
  });

  it("renders a finding with its severity badge, risk badge, and title", () => {
    const wrapper = mount(AssetFindingsList, {
      props: { findings: [makeFinding({ risk_priority: "CRITICAL", risk_score: 85 })] },
      ...globalStubs,
    });
    expect(wrapper.text()).toContain("INFO");
    expect(wrapper.text()).toContain("Risk 85");
    expect(wrapper.text()).toContain("Technology detected: Apache");
  });

  it("omits the risk badge when risk_priority is null", () => {
    const wrapper = mount(AssetFindingsList, {
      props: { findings: [makeFinding({ risk_priority: null })] },
      ...globalStubs,
    });
    expect(wrapper.text()).not.toContain("Risk");
  });

  it("links each finding to its detail page", () => {
    const wrapper = mount(AssetFindingsList, { props: { findings: [makeFinding({ id: "f42" })] }, ...globalStubs });
    expect(wrapper.find("a").attributes("href")).toBe("/findings/f42");
  });
});
