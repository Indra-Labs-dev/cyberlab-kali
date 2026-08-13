import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import Badge from "./Badge.vue";
import StatusBadge from "./StatusBadge.vue";

// Real Nuxt auto-registers Badge project-wide; this plain Vitest setup
// doesn't (see vitest.config.ts), so it's provided explicitly here.
const globalComponents = { global: { components: { Badge } } };

describe("StatusBadge", () => {
  it("renders the status label by default", () => {
    const wrapper = mount(StatusBadge, { props: { status: "CONFIRMED" }, ...globalComponents });
    expect(wrapper.text()).toBe("CONFIRMED");
  });

  it("does not strike through FALSE_POSITIVE by default", () => {
    const wrapper = mount(StatusBadge, { props: { status: "FALSE_POSITIVE" }, ...globalComponents });
    expect(wrapper.classes()).not.toContain("line-through");
  });

  it("strikes through FALSE_POSITIVE only when strikeFalsePositive is set", () => {
    const wrapper = mount(StatusBadge, {
      props: { status: "FALSE_POSITIVE", strikeFalsePositive: true },
      ...globalComponents,
    });
    expect(wrapper.classes()).toContain("line-through");
  });

  it("does not strike through a non-FALSE_POSITIVE status even with strikeFalsePositive set", () => {
    const wrapper = mount(StatusBadge, {
      props: { status: "REMEDIATED", strikeFalsePositive: true },
      ...globalComponents,
    });
    expect(wrapper.classes()).not.toContain("line-through");
  });
});
