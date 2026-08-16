import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import DonutChart from "./DonutChart.vue";

describe("DonutChart", () => {
  it("renders one arc circle per data entry (plus the background track), even zero-value ones", () => {
    // Every entry stays mounted (rather than being filtered out) so that
    // when real data replaces a 0 count later, Vue patches the existing
    // circle's stroke-dasharray -- which is what makes the CSS transition
    // animate instead of popping a brand-new element straight to size.
    const wrapper = mount(DonutChart, {
      props: {
        data: [
          { label: "CRITICAL", value: 3, color: "stroke-red-400" },
          { label: "HIGH", value: 1, color: "stroke-orange-400" },
          { label: "LOW", value: 0, color: "stroke-emerald-400" },
        ],
      },
    });
    expect(wrapper.findAll("circle")).toHaveLength(4); // background + 3 segments
  });

  it("gives a zero-value entry a zero-length arc", () => {
    const wrapper = mount(DonutChart, {
      props: {
        data: [
          { label: "CRITICAL", value: 3, color: "stroke-red-400" },
          { label: "LOW", value: 0, color: "stroke-emerald-400" },
        ],
      },
    });
    const circles = wrapper.findAll("circle");
    const zeroSegment = circles[circles.length - 1]!; // last data circle = LOW
    expect(zeroSegment.attributes("stroke-dasharray")).toMatch(/^0 /);
  });

  it("shows the total count in the center", () => {
    const wrapper = mount(DonutChart, {
      props: {
        data: [
          { label: "CRITICAL", value: 3, color: "stroke-red-400" },
          { label: "HIGH", value: 1, color: "stroke-orange-400" },
        ],
      },
    });
    expect(wrapper.text()).toContain("4");
  });

  it("shows a 'No data' label when every value is zero", () => {
    const wrapper = mount(DonutChart, { props: { data: [{ label: "CRITICAL", value: 0, color: "stroke-red-400" }] } });
    expect(wrapper.text()).toContain("No data");
  });
});
