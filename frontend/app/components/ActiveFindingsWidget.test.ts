import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EmptyState from "./EmptyState.vue";
import LoadingState from "./LoadingState.vue";

const apiFetchMock = vi.fn();
vi.mock("~/composables/useApi", () => ({
  useApi: () => ({ apiFetch: apiFetchMock }),
}));

const { default: ActiveFindingsWidget } = await import("./ActiveFindingsWidget.vue");

const globalComponents = { global: { components: { LoadingState, EmptyState }, stubs: { NuxtLink: { template: "<a><slot /></a>" } } } };

describe("ActiveFindingsWidget", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it("requests active findings sorted by risk on mount", async () => {
    apiFetchMock.mockResolvedValue([]);
    mount(ActiveFindingsWidget, globalComponents);
    await flushPromises();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/findings?active_only=true&sort=risk_score_desc&limit=8");
  });

  it("shows the empty state when there are no active findings", async () => {
    apiFetchMock.mockResolvedValue([]);
    const wrapper = mount(ActiveFindingsWidget, globalComponents);
    await flushPromises();
    expect(wrapper.text()).toContain("No active findings right now.");
  });

  it("shows an error message on failure", async () => {
    apiFetchMock.mockRejectedValue({ data: { detail: "boom" } });
    const wrapper = mount(ActiveFindingsWidget, globalComponents);
    await flushPromises();
    expect(wrapper.text()).toContain("boom");
  });

  it("renders a finding's title, target, and risk score", async () => {
    apiFetchMock.mockResolvedValue([
      { id: "f1", title: "Outdated Apache", target: "10.0.0.5", risk_score: 87, risk_priority: "CRITICAL" },
    ]);
    const wrapper = mount(ActiveFindingsWidget, globalComponents);
    await flushPromises();
    expect(wrapper.text()).toContain("Outdated Apache");
    expect(wrapper.text()).toContain("10.0.0.5");
    expect(wrapper.text()).toContain("87");
  });

  it("falls back to an em dash when risk_score is null", async () => {
    apiFetchMock.mockResolvedValue([{ id: "f1", title: "Unscored", target: "10.0.0.5", risk_score: null, risk_priority: null }]);
    const wrapper = mount(ActiveFindingsWidget, globalComponents);
    await flushPromises();
    expect(wrapper.text()).toContain("—");
  });
});
