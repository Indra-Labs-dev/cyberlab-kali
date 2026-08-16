import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import BarChart from "./BarChart.vue";

describe("BarChart", () => {
  it("sizes each bar relative to the largest value", () => {
    const wrapper = mount(BarChart, {
      props: {
        data: [
          { label: "CRITICAL", value: 10, color: "bg-red-400" },
          { label: "LOW", value: 5, color: "bg-emerald-400" },
        ],
      },
    });
    const bars = wrapper.findAll("[style]");
    expect((bars[0]!.attributes("style") || "").replace(/\s/g, "")).toContain("width:100%");
    expect((bars[1]!.attributes("style") || "").replace(/\s/g, "")).toContain("width:50%");
  });

  it("shows a 'No data' message when there are no bars", () => {
    const wrapper = mount(BarChart, { props: { data: [] } });
    expect(wrapper.text()).toContain("No data");
  });
});
