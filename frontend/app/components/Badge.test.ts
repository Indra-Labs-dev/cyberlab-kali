import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import Badge from "./Badge.vue";

describe("Badge", () => {
  it("renders slot content", () => {
    const wrapper = mount(Badge, {
      props: { colorClass: "bg-red-500/15 text-red-400" },
      slots: { default: "CRITICAL" },
    });
    expect(wrapper.text()).toBe("CRITICAL");
  });

  it("applies the given color class", () => {
    const wrapper = mount(Badge, { props: { colorClass: "bg-red-500/15 text-red-400" } });
    expect(wrapper.classes()).toContain("bg-red-500/15");
    expect(wrapper.classes()).toContain("text-red-400");
  });

  it("defaults to the md size (px-2) without bold", () => {
    const wrapper = mount(Badge, { props: { colorClass: "bg-slate-700/50 text-slate-300" } });
    expect(wrapper.classes()).toContain("px-2");
    expect(wrapper.classes()).not.toContain("font-medium");
  });

  it("uses the sm size (px-1.5) when requested", () => {
    const wrapper = mount(Badge, { props: { colorClass: "bg-slate-700/50 text-slate-300", size: "sm" } });
    expect(wrapper.classes()).toContain("px-1.5");
  });

  it("adds font-medium when bold is true", () => {
    const wrapper = mount(Badge, { props: { colorClass: "bg-slate-700/50 text-slate-300", bold: true } });
    expect(wrapper.classes()).toContain("font-medium");
  });
});
