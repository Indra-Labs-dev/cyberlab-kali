import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import HeroRadar from "./HeroRadar.vue";

describe("HeroRadar", () => {
  it("renders one node per item, plus a connecting line each", () => {
    const wrapper = mount(HeroRadar, {
      props: {
        items: [
          { id: "a", label: "Finding A", tone: "danger" },
          { id: "b", label: "Finding B", tone: "warning" },
        ],
        centerValue: 42,
        centerLabel: "Assets",
      },
    });
    // 2 decorative ring circles + hub glow + hub core + 2 node halo/core pairs = 8
    expect(wrapper.findAll("circle")).toHaveLength(8);
    expect(wrapper.findAll("line").length).toBeGreaterThanOrEqual(2); // ticks + connecting lines
  });

  it("shows the real center value and label", () => {
    const wrapper = mount(HeroRadar, { props: { items: [], centerValue: 63, centerLabel: "Assets Monitored" } });
    expect(wrapper.text()).toContain("63");
    expect(wrapper.text()).toContain("Assets Monitored");
  });

  it("places items evenly around the ring starting from the top", () => {
    const wrapper = mount(HeroRadar, {
      props: {
        items: [
          { id: "a", label: "A", tone: "danger" },
          { id: "b", label: "B", tone: "warning" },
          { id: "c", label: "C", tone: "accent" },
          { id: "d", label: "D", tone: "success" },
        ],
        centerValue: 1,
        centerLabel: "x",
        size: 200,
      },
    });
    // circle order: 2 decorative rings, then 2 circles (halo+core) per node, then 2 hub circles.
    const nodeCircles = wrapper.findAll("circle").slice(2, 2 + 2 * 4);
    const first = nodeCircles[0]!; // item "a" halo, angle = -90deg => x = cx, y = cy - r
    expect(Number(first.attributes("cx"))).toBeCloseTo(100, 0); // cx = size/2
  });

  it("handles zero items without throwing", () => {
    const wrapper = mount(HeroRadar, { props: { items: [], centerValue: 0, centerLabel: "Assets" } });
    expect(wrapper.find("svg").exists()).toBe(true);
  });
});
