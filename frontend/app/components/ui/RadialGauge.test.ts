import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import RadialGauge from "./RadialGauge.vue";

describe("RadialGauge", () => {
  it("shows the rounded percentage in the center", () => {
    const wrapper = mount(RadialGauge, { props: { value: 74.6 } });
    expect(wrapper.text()).toContain("75%");
  });

  it("clamps values outside 0-100", () => {
    const over = mount(RadialGauge, { props: { value: 150 } });
    expect(over.text()).toContain("100%");
    const under = mount(RadialGauge, { props: { value: -20 } });
    expect(under.text()).toContain("0%");
  });

  it("sizes the progress arc proportionally to the value", () => {
    const half = mount(RadialGauge, { props: { value: 50, size: 100 } });
    const full = mount(RadialGauge, { props: { value: 100, size: 100 } });
    const halfArc = Number(half.findAll("circle")[1]!.attributes("stroke-dasharray")!.split(" ")[0]);
    const fullArc = Number(full.findAll("circle")[1]!.attributes("stroke-dasharray")!.split(" ")[0]);
    expect(halfArc).toBeCloseTo(fullArc / 2, 0);
  });

  it("shows an optional label", () => {
    const wrapper = mount(RadialGauge, { props: { value: 90, label: "Uptime" } });
    expect(wrapper.text()).toContain("Uptime");
  });
});
