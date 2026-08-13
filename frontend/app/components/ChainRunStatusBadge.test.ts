import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import Badge from "./Badge.vue";
import ChainRunStatusBadge from "./ChainRunStatusBadge.vue";
import ChainRunStepStatusBadge from "./ChainRunStepStatusBadge.vue";

const globalComponents = { global: { components: { Badge } } };

describe("ChainRunStatusBadge", () => {
  it("renders the status label by default", () => {
    const wrapper = mount(ChainRunStatusBadge, { props: { status: "RUNNING" }, ...globalComponents });
    expect(wrapper.text()).toBe("RUNNING");
  });

  it.each(["RUNNING", "COMPLETED", "FAILED", "CANCELLED"] as const)("renders a color class for %s", (status) => {
    const wrapper = mount(ChainRunStatusBadge, { props: { status }, ...globalComponents });
    expect(wrapper.attributes("class")).toBeTruthy();
  });
});

describe("ChainRunStepStatusBadge", () => {
  it("renders the status label by default", () => {
    const wrapper = mount(ChainRunStepStatusBadge, { props: { status: "SKIPPED" }, ...globalComponents });
    expect(wrapper.text()).toBe("SKIPPED");
  });

  it.each(["PENDING", "SKIPPED", "QUEUED", "SUCCESS", "FAILED", "CANCELLED"] as const)(
    "renders a color class for %s",
    (status) => {
      const wrapper = mount(ChainRunStepStatusBadge, { props: { status }, ...globalComponents });
      expect(wrapper.attributes("class")).toBeTruthy();
    },
  );
});
