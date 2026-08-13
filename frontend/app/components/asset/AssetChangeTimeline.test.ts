import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EmptyState from "../EmptyState.vue";
import LoadingState from "../LoadingState.vue";

const apiFetchMock = vi.fn();
vi.mock("~/composables/useApi", () => ({
  useApi: () => ({ apiFetch: apiFetchMock }),
}));

const { default: AssetChangeTimeline } = await import("./AssetChangeTimeline.vue");

// Real Nuxt auto-registers LoadingState/EmptyState project-wide; this plain
// Vitest setup doesn't (see vitest.config.ts), so they're provided
// explicitly here.
const globalComponents = { global: { components: { LoadingState, EmptyState } } };

describe("AssetChangeTimeline", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it("loads changes for the given assetId on mount", async () => {
    apiFetchMock.mockResolvedValue([]);
    mount(AssetChangeTimeline, { props: { assetId: "a1" }, ...globalComponents });
    await flushPromises();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/assets/a1/changes");
  });

  it("shows the empty state when there are no changes", async () => {
    apiFetchMock.mockResolvedValue([]);
    const wrapper = mount(AssetChangeTimeline, { props: { assetId: "a1" }, ...globalComponents });
    await flushPromises();
    expect(wrapper.text()).toContain("No changes detected yet");
  });

  it("shows an error message on failure", async () => {
    apiFetchMock.mockRejectedValue({ data: { detail: "boom" } });
    const wrapper = mount(AssetChangeTimeline, { props: { assetId: "a1" }, ...globalComponents });
    await flushPromises();
    expect(wrapper.text()).toContain("boom");
  });

  it("renders a change with its computed summary", async () => {
    apiFetchMock.mockResolvedValue([
      {
        id: "c1",
        job_id: "j1",
        previous_job_id: null,
        change_type: "PORT_OPENED",
        severity: "MEDIUM",
        field: "port:80/tcp",
        old_value: null,
        new_value: "open",
        detected_at: "2026-01-01T00:00:00Z",
      },
    ]);
    const wrapper = mount(AssetChangeTimeline, { props: { assetId: "a1" }, ...globalComponents });
    await flushPromises();
    expect(wrapper.text()).toContain("Port 80/tcp opened");
  });

  it("re-fetches with query params when a filter changes", async () => {
    apiFetchMock.mockResolvedValue([]);
    const wrapper = mount(AssetChangeTimeline, { props: { assetId: "a1" }, ...globalComponents });
    await flushPromises();
    apiFetchMock.mockClear();

    await wrapper.find("select").setValue("PORT_OPENED");
    await flushPromises();

    expect(apiFetchMock).toHaveBeenCalledWith("/api/assets/a1/changes?change_type=PORT_OPENED");
  });
});
