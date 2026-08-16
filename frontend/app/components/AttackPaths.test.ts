import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

const loadAttackPathsToCriticalAssetsMock = vi.fn();
const loadAttackPathsBetweenMock = vi.fn();
const searchNodesMock = vi.fn();

vi.mock("~/composables/useGraph", () => ({
  useGraph: () => ({
    searchNodes: searchNodesMock,
    loadAttackPathsToCriticalAssets: loadAttackPathsToCriticalAssetsMock,
    loadAttackPathsBetween: loadAttackPathsBetweenMock,
  }),
}));

const { default: AttackPaths } = await import("./AttackPaths.vue");

const SAMPLE_RESULT = {
  disclaimer: "These are structural paths derived from the graph data collected so far -- not proof of real exploitability.",
  seed: { id: "entry", type: "ASSET", label: "entry", metadata: {} },
  truncated: false,
  paths: [
    {
      hops: 2,
      nodes: [
        { id: "entry", type: "ASSET", label: "entry", metadata: {} },
        { id: "apache", type: "TECHNOLOGY", label: "apache", metadata: {} },
        { id: "critical", type: "ASSET", label: "critical", metadata: {} },
      ],
      edges: [
        { id: "e1", from_type: "ASSET", from_id: "entry", to_type: "TECHNOLOGY", to_id: "apache", relation: "USES_TECHNOLOGY", source: "test", reason: "r1", metadata: {} },
        { id: "e2", from_type: "TECHNOLOGY", from_id: "apache", to_type: "ASSET", to_id: "critical", relation: "RELATED_TO", source: "test", reason: "r2", metadata: {} },
      ],
    },
  ],
};

async function selectViaSearchBar(wrapper: ReturnType<typeof mount>) {
  searchNodesMock.mockResolvedValue([{ id: "entry", type: "ASSET", label: "entry" }]);
  await wrapper.find("#graph-search-input").setValue("entry");
  await wrapper.find("#graph-search-input").trigger("keydown.enter");
  await flushPromises();
  await wrapper.find('[role="option"]').trigger("click");
}

describe("AttackPaths", () => {
  it("always renders the hypothesis disclaimer banner, before any search", () => {
    const wrapper = mount(AttackPaths);
    expect(wrapper.text().toLowerCase()).toContain("potential paths only");
    expect(wrapper.text().toLowerCase()).toContain("verify");
  });

  it("defaults to 'To critical assets' mode with a single node picker (no 'To' picker)", () => {
    const wrapper = mount(AttackPaths);
    expect(wrapper.text()).toContain("Starting point");
    expect(wrapper.text()).not.toContain("To\n");
  });

  it("switching to 'Between two nodes' mode shows a second picker", async () => {
    const wrapper = mount(AttackPaths);
    await wrapper.findAll("button").find((b) => b.text() === "Between two nodes")!.trigger("click");
    expect(wrapper.text()).toContain("From");
  });

  it("searches via loadAttackPathsToCriticalAssets in the default mode and renders paths + the API disclaimer", async () => {
    loadAttackPathsToCriticalAssetsMock.mockResolvedValue(SAMPLE_RESULT);
    const wrapper = mount(AttackPaths);

    await selectViaSearchBar(wrapper);
    await wrapper.find("button:not([disabled])").trigger("click"); // fallback if Search isn't uniquely findable below
    const searchButton = wrapper.findAll("button").find((b) => b.text() === "Search")!;
    await searchButton.trigger("click");
    await flushPromises();

    expect(loadAttackPathsToCriticalAssetsMock).toHaveBeenCalledWith("ASSET", "entry", 4);
    expect(wrapper.text()).toContain("Potential path 1");
    expect(wrapper.text()).toContain("2 hop(s)");
    expect(wrapper.text()).toContain("USES_TECHNOLOGY");
    expect(wrapper.text().toLowerCase()).toContain("structural paths derived");
  });

  it("shows 'No potential path found' when the API returns zero paths", async () => {
    loadAttackPathsToCriticalAssetsMock.mockResolvedValue({ ...SAMPLE_RESULT, paths: [] });
    const wrapper = mount(AttackPaths);

    await selectViaSearchBar(wrapper);
    const searchButton = wrapper.findAll("button").find((b) => b.text() === "Search")!;
    await searchButton.trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("No potential path found");
  });

  it("shows a truncation notice when the API reports truncated=true", async () => {
    loadAttackPathsToCriticalAssetsMock.mockResolvedValue({ ...SAMPLE_RESULT, truncated: true });
    const wrapper = mount(AttackPaths);

    await selectViaSearchBar(wrapper);
    const searchButton = wrapper.findAll("button").find((b) => b.text() === "Search")!;
    await searchButton.trigger("click");
    await flushPromises();

    expect(wrapper.text().toLowerCase()).toContain("more potential paths exist");
  });

  it("never renders an exploitability/probability score anywhere", async () => {
    loadAttackPathsToCriticalAssetsMock.mockResolvedValue(SAMPLE_RESULT);
    const wrapper = mount(AttackPaths);

    await selectViaSearchBar(wrapper);
    const searchButton = wrapper.findAll("button").find((b) => b.text() === "Search")!;
    await searchButton.trigger("click");
    await flushPromises();

    const text = wrapper.text().toLowerCase();
    for (const forbidden of ["score", "probability", "likelihood", "confidence: "]) {
      expect(text).not.toContain(forbidden);
    }
  });

  it("Search is disabled in 'Between two nodes' mode until both nodes are selected", async () => {
    const wrapper = mount(AttackPaths);
    await wrapper.findAll("button").find((b) => b.text() === "Between two nodes")!.trigger("click");

    const searchButton = wrapper.findAll("button").find((b) => b.text() === "Search")!;
    expect(searchButton.attributes("disabled")).toBeDefined();
  });
});
