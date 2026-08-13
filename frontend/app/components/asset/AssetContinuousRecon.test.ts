import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EmptyState from "../EmptyState.vue";
import LoadingState from "../LoadingState.vue";

const apiFetchMock = vi.fn();
vi.mock("~/composables/useApi", () => ({
  useApi: () => ({ apiFetch: apiFetchMock }),
}));

const { default: AssetContinuousRecon } = await import("./AssetContinuousRecon.vue");

// Real Nuxt auto-registers NuxtLink/LoadingState/EmptyState project-wide;
// this plain Vitest setup doesn't (see vitest.config.ts), so they're
// provided explicitly here.
const stubs = {
  global: {
    components: { LoadingState, EmptyState },
    stubs: { NuxtLink: { template: "<a><slot /></a>" } },
  },
};

function schedule(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "s1",
    asset_id: "a1",
    tool: "nmap",
    profile: null,
    params: {},
    interval_seconds: 3600,
    status: "ACTIVE",
    next_run_at: "2026-01-01T01:00:00Z",
    last_run_at: null,
    last_job_id: null,
    consecutive_failures: 0,
    last_error: null,
    ...overrides,
  };
}

describe("AssetContinuousRecon", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it("fetches schedules for the given assetId on mount, using the tools prop (no /api/tools call)", async () => {
    apiFetchMock.mockResolvedValue([]);
    mount(AssetContinuousRecon, {
      props: { assetId: "a1", tools: [], refreshAssetData: vi.fn() },
      ...stubs,
    });
    await flushPromises();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/assets/a1/schedules");
    expect(apiFetchMock).not.toHaveBeenCalledWith("/api/tools");
  });

  it("shows the empty state when there are no schedules", async () => {
    apiFetchMock.mockResolvedValue([]);
    const wrapper = mount(AssetContinuousRecon, {
      props: { assetId: "a1", tools: [], refreshAssetData: vi.fn() },
      ...stubs,
    });
    await flushPromises();
    expect(wrapper.text()).toContain("No scheduled scans yet");
  });

  it("renders a schedule row with its tool and status", async () => {
    apiFetchMock.mockResolvedValue([schedule()]);
    const wrapper = mount(AssetContinuousRecon, {
      props: { assetId: "a1", tools: [], refreshAssetData: vi.fn() },
      ...stubs,
    });
    await flushPromises();
    expect(wrapper.text()).toContain("nmap");
    expect(wrapper.text()).toContain("ACTIVE");
  });

  it("'Run now' calls POST /run, then reloads schedules AND calls refreshAssetData (parent's loadAll)", async () => {
    apiFetchMock.mockResolvedValueOnce([schedule()]); // initial load
    const refreshAssetData = vi.fn().mockResolvedValue(undefined);
    const wrapper = mount(AssetContinuousRecon, {
      props: { assetId: "a1", tools: [], refreshAssetData },
      ...stubs,
    });
    await flushPromises();

    apiFetchMock.mockResolvedValueOnce(undefined); // POST /run
    apiFetchMock.mockResolvedValueOnce([schedule({ last_run_at: "2026-01-01T02:00:00Z" })]); // reload
    const runNowButton = wrapper.findAll("button").find((b) => b.text() === "Run now");
    await runNowButton!.trigger("click");
    await flushPromises();

    expect(apiFetchMock).toHaveBeenCalledWith("/api/schedules/s1/run", { method: "POST" });
    expect(refreshAssetData).toHaveBeenCalledTimes(1);
  });

  it("shows a create-schedule error and keeps the form open on failure", async () => {
    apiFetchMock.mockResolvedValueOnce([]); // initial load
    const wrapper = mount(AssetContinuousRecon, {
      props: { assetId: "a1", tools: [{ name: "nmap", category: "recon", description: "", arguments: [], profiles: [] }], refreshAssetData: vi.fn() },
      ...stubs,
    });
    await flushPromises();

    await wrapper.find("button").trigger("click"); // "+ Schedule scan"
    await wrapper.find("select").setValue("nmap");

    apiFetchMock.mockRejectedValueOnce({ data: { detail: "worker unavailable" } });
    const createButton = wrapper.findAll("button").find((b) => b.text().includes("Create schedule"));
    await createButton!.trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("worker unavailable");
    expect(wrapper.find("select").exists()).toBe(true); // form still open
  });
});
