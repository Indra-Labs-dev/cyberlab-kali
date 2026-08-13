import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EmptyState from "../EmptyState.vue";
import LoadingState from "../LoadingState.vue";

const apiFetchMock = vi.fn();
vi.mock("~/composables/useApi", () => ({
  useApi: () => ({ apiFetch: apiFetchMock }),
}));

const { default: AssetRiskOverview } = await import("./AssetRiskOverview.vue");

// Real Nuxt auto-registers LoadingState/EmptyState project-wide; this plain
// Vitest setup doesn't (see vitest.config.ts), so they're provided
// explicitly here.
const globalComponents = { global: { components: { LoadingState, EmptyState } } };

describe("AssetRiskOverview", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it("fetches the risk summary for the given assetId on mount", async () => {
    apiFetchMock.mockResolvedValue({
      total_findings: 0,
      critical_findings: 0,
      high_findings: 0,
      medium_findings: 0,
      low_findings: 0,
      informational_findings: 0,
      kev_findings: 0,
      highest_risk_score: null,
      unscored_findings: 0,
    });
    mount(AssetRiskOverview, { props: { assetId: "a1" }, ...globalComponents });
    await flushPromises();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/assets/a1/risk-summary");
  });

  it("shows the empty state when there are no findings", async () => {
    apiFetchMock.mockResolvedValue({
      total_findings: 0,
      critical_findings: 0,
      high_findings: 0,
      medium_findings: 0,
      low_findings: 0,
      informational_findings: 0,
      kev_findings: 0,
      highest_risk_score: null,
      unscored_findings: 0,
    });
    const wrapper = mount(AssetRiskOverview, { props: { assetId: "a1" }, ...globalComponents });
    await flushPromises();
    expect(wrapper.text()).toContain("No findings yet");
  });

  it("renders KPI tiles when findings exist", async () => {
    apiFetchMock.mockResolvedValue({
      total_findings: 5,
      critical_findings: 1,
      high_findings: 2,
      medium_findings: 1,
      low_findings: 1,
      informational_findings: 0,
      kev_findings: 1,
      highest_risk_score: 85,
      unscored_findings: 2,
    });
    const wrapper = mount(AssetRiskOverview, { props: { assetId: "a1" }, ...globalComponents });
    await flushPromises();
    expect(wrapper.text()).toContain("85");
    expect(wrapper.text()).toContain("2 finding(s) not yet scored");
  });

  it("shows an error message on failure", async () => {
    apiFetchMock.mockRejectedValue({ data: { detail: "boom" } });
    const wrapper = mount(AssetRiskOverview, { props: { assetId: "a1" }, ...globalComponents });
    await flushPromises();
    expect(wrapper.text()).toContain("boom");
  });
});
