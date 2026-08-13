import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

const searchNodesMock = vi.fn();
vi.mock("~/composables/useGraph", () => ({
  useGraph: () => ({ searchNodes: searchNodesMock }),
}));

const { default: GraphSearchBar } = await import("./GraphSearchBar.vue");

describe("GraphSearchBar", () => {
  it("runs a search on Enter and renders the results", async () => {
    searchNodesMock.mockResolvedValue([{ id: "a1", type: "ASSET", label: "DVWA E2E" }]);
    const wrapper = mount(GraphSearchBar);

    await wrapper.find("#graph-search-input").setValue("dvwa");
    await wrapper.find("#graph-search-input").trigger("keydown.enter");
    await flushPromises();

    expect(searchNodesMock).toHaveBeenCalledWith("ASSET", "dvwa");
    expect(wrapper.text()).toContain("DVWA E2E");
  });

  it("shows 'No results.' when a search returns nothing", async () => {
    searchNodesMock.mockResolvedValue([]);
    const wrapper = mount(GraphSearchBar);

    await wrapper.find("#graph-search-input").setValue("nonexistent");
    await wrapper.find("#graph-search-input").trigger("keydown.enter");
    await flushPromises();

    expect(wrapper.text()).toContain("No results.");
  });

  it("emits 'select' with the chosen result and clears the search", async () => {
    searchNodesMock.mockResolvedValue([{ id: "a1", type: "ASSET", label: "DVWA E2E" }]);
    const wrapper = mount(GraphSearchBar);

    await wrapper.find("#graph-search-input").setValue("dvwa");
    await wrapper.find("#graph-search-input").trigger("keydown.enter");
    await flushPromises();

    await wrapper.find('button[role="option"]').trigger("click");

    expect(wrapper.emitted("select")).toEqual([[{ id: "a1", type: "ASSET", label: "DVWA E2E" }]]);
    expect((wrapper.find("#graph-search-input").element as HTMLInputElement).value).toBe("");
  });

  it("shows an error message when the search fails", async () => {
    searchNodesMock.mockRejectedValue({ data: { detail: "boom" } });
    const wrapper = mount(GraphSearchBar);

    await wrapper.find("#graph-search-input").setValue("dvwa");
    await wrapper.find("#graph-search-input").trigger("keydown.enter");
    await flushPromises();

    expect(wrapper.text()).toContain("boom");
  });
});
