import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ActivityFeed from "../ui/ActivityFeed.vue";
import ErrorState from "../ui/ErrorState.vue";
import Skeleton from "../ui/Skeleton.vue";
import Tooltip from "../ui/Tooltip.vue";

const searchMock = vi.fn();
const clearSearchMock = vi.fn();
const loadActivityMock = vi.fn();
const refreshStatusMock = vi.fn();

vi.mock("~/composables/useGlobalSearch", () => ({
  useGlobalSearch: () => ({ results: { value: [] }, loading: { value: false }, search: searchMock, clear: clearSearchMock }),
}));
vi.mock("~/composables/useRecentActivity", () => ({
  useRecentActivity: () => ({ items: { value: [] }, loading: { value: false }, error: { value: "" }, load: loadActivityMock }),
}));
vi.mock("~/composables/useSystemStatus", () => ({
  useSystemStatus: () => ({ status: { api: "ok", db: "ok", kali: "ok", ai: "ok" }, refresh: refreshStatusMock }),
}));

const { default: Topbar } = await import("./Topbar.vue");

const globalComponents = {
  global: {
    components: { UiTooltip: Tooltip, UiSkeleton: Skeleton, UiErrorState: ErrorState, UiActivityFeed: ActivityFeed },
    stubs: { NuxtLink: { template: "<a><slot /></a>" } },
  },
};

describe("Topbar", () => {
  beforeEach(() => {
    searchMock.mockReset();
    clearSearchMock.mockReset();
    loadActivityMock.mockReset();
    refreshStatusMock.mockReset();
  });

  it("refreshes system status on mount", () => {
    mount(Topbar, { props: { sidebarOpen: false }, ...globalComponents });
    expect(refreshStatusMock).toHaveBeenCalledOnce();
  });

  it("emits toggle-sidebar when the mobile menu button is clicked", async () => {
    const wrapper = mount(Topbar, { props: { sidebarOpen: false }, ...globalComponents });
    await wrapper.find('button[aria-label="Toggle navigation menu"]').trigger("click");
    expect(wrapper.emitted("toggle-sidebar")).toHaveLength(1);
  });

  it("debounces search input before calling search()", async () => {
    vi.useFakeTimers();
    const wrapper = mount(Topbar, { props: { sidebarOpen: false }, ...globalComponents });
    await wrapper.find("input[type=search]").setValue("web-01");
    expect(searchMock).not.toHaveBeenCalled();
    vi.advanceTimersByTime(250);
    expect(searchMock).toHaveBeenCalledWith("web-01");
    vi.useRealTimers();
  });

  it("loads activity the first time the bell is opened", async () => {
    const wrapper = mount(Topbar, { props: { sidebarOpen: false }, ...globalComponents });
    await wrapper.find('button[aria-label="Recent activity"]').trigger("click");
    expect(loadActivityMock).toHaveBeenCalledOnce();
  });
});
