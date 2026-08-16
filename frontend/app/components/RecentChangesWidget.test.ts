import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EmptyState from "./EmptyState.vue";
import LoadingState from "./LoadingState.vue";

const apiFetchMock = vi.fn();
vi.mock("~/composables/useApi", () => ({
  useApi: () => ({ apiFetch: apiFetchMock }),
}));

const { default: RecentChangesWidget } = await import("./RecentChangesWidget.vue");

const globalComponents = { global: { components: { LoadingState, EmptyState }, stubs: { NuxtLink: { template: "<a><slot /></a>" } } } };

describe("RecentChangesWidget", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it("requests the global changes endpoint on mount, not a single asset's", async () => {
    apiFetchMock.mockResolvedValue([]);
    mount(RecentChangesWidget, globalComponents);
    await flushPromises();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/asset-changes?limit=8");
  });

  it("shows the empty state when there are no changes", async () => {
    apiFetchMock.mockResolvedValue([]);
    const wrapper = mount(RecentChangesWidget, globalComponents);
    await flushPromises();
    expect(wrapper.text()).toContain("No changes detected yet across any asset.");
  });

  it("shows an error message on failure", async () => {
    apiFetchMock.mockRejectedValue({ data: { detail: "boom" } });
    const wrapper = mount(RecentChangesWidget, globalComponents);
    await flushPromises();
    expect(wrapper.text()).toContain("boom");
  });

  it("renders a change's computed summary regardless of which asset it came from", async () => {
    apiFetchMock.mockResolvedValue([
      {
        id: "c1",
        asset_id: "a1",
        job_id: "j1",
        previous_job_id: null,
        change_type: "PORT_OPENED",
        severity: "HIGH",
        field: "port:443/tcp",
        old_value: null,
        new_value: "open",
        change_metadata: {},
        detected_at: "2026-01-01T00:00:00Z",
      },
    ]);
    const wrapper = mount(RecentChangesWidget, globalComponents);
    await flushPromises();
    expect(wrapper.text()).toContain("Port 443/tcp opened");
  });
});
