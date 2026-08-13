import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Badge from "./Badge.vue";
import EmptyState from "./EmptyState.vue";
import LoadingState from "./LoadingState.vue";

const apiFetchMock = vi.fn();
vi.mock("~/composables/useApi", () => ({
  useApi: () => ({ apiFetch: apiFetchMock }),
}));

const { default: IntelligenceSyncStatus } = await import("./IntelligenceSyncStatus.vue");

// Real Nuxt auto-registers Badge/LoadingState/EmptyState project-wide; this
// plain Vitest setup doesn't (see vitest.config.ts), so they're registered
// explicitly here -- same reasoning as useApi being imported explicitly in
// app/composables/useAssets.ts.
const globalComponents = { global: { components: { Badge, LoadingState, EmptyState } } };

describe("IntelligenceSyncStatus", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it("renders normal (OK) status for a successfully-synced source", async () => {
    apiFetchMock.mockResolvedValue([
      { source: "nvd", last_attempt_at: "2026-08-12T22:04:33Z", last_success_at: "2026-08-12T22:04:33Z", last_error: null, details: { cves_checked: 0 } },
    ]);
    const wrapper = mount(IntelligenceSyncStatus, globalComponents);
    await flushPromises();

    expect(wrapper.text()).toContain("nvd");
    expect(wrapper.text()).toContain("OK");
  });

  it("renders an error state for a source with last_error set", async () => {
    apiFetchMock.mockResolvedValue([
      {
        source: "cisa_kev",
        last_attempt_at: "2026-08-12T22:04:32Z",
        last_success_at: "2026-08-12T16:08:50Z",
        last_error: "CISA KEV request failed: name resolution",
        details: { catalog_size: 1665 },
      },
    ]);
    const wrapper = mount(IntelligenceSyncStatus, globalComponents);
    await flushPromises();

    expect(wrapper.text()).toContain("Error");
    expect(wrapper.text()).toContain("CISA KEV request failed");
  });

  it("renders 'Never synced' for a source with no success and no error yet", async () => {
    apiFetchMock.mockResolvedValue([
      { source: "epss", last_attempt_at: null, last_success_at: null, last_error: null, details: {} },
    ]);
    const wrapper = mount(IntelligenceSyncStatus, globalComponents);
    await flushPromises();

    expect(wrapper.text()).toContain("Never synced");
  });

  it("clicking 'Sync now' triggers POST /api/intelligence/sync and disables the button", async () => {
    apiFetchMock.mockResolvedValueOnce([]); // initial status load
    const wrapper = mount(IntelligenceSyncStatus, globalComponents);
    await flushPromises();

    apiFetchMock.mockResolvedValueOnce({ status: "queued" }); // sync trigger
    apiFetchMock.mockResolvedValueOnce([]); // status re-fetch inside pollOnce
    await wrapper.find("button").trigger("click");
    await flushPromises();

    expect(apiFetchMock).toHaveBeenCalledWith("/api/intelligence/sync", { method: "POST" });
    expect(wrapper.find("button").attributes("disabled")).toBeDefined();
    expect(wrapper.find("button").text()).toBe("Syncing…");
  });

  it("shows a sync error without leaving the button stuck in a syncing state", async () => {
    apiFetchMock.mockResolvedValueOnce([]); // initial status load
    const wrapper = mount(IntelligenceSyncStatus, globalComponents);
    await flushPromises();

    apiFetchMock.mockRejectedValueOnce({ data: { detail: "queue unavailable" } });
    await wrapper.find("button").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("queue unavailable");
    expect(wrapper.find("button").attributes("disabled")).toBeUndefined();
  });
});
