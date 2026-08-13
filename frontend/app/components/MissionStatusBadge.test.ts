import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import Badge from "./Badge.vue";
import MissionStatusBadge from "./MissionStatusBadge.vue";
import MissionStepStatusBadge from "./MissionStepStatusBadge.vue";

const globalComponents = { global: { components: { Badge } } };

describe("MissionStatusBadge", () => {
  it("renders the status label by default", () => {
    const wrapper = mount(MissionStatusBadge, { props: { status: "RUNNING" }, ...globalComponents });
    expect(wrapper.text()).toBe("RUNNING");
  });

  it.each(["DRAFT", "APPROVED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"] as const)(
    "renders a color class for %s",
    (status) => {
      const wrapper = mount(MissionStatusBadge, { props: { status }, ...globalComponents });
      expect(wrapper.attributes("class")).toBeTruthy();
    },
  );
});

describe("MissionStepStatusBadge", () => {
  it("renders the status label by default", () => {
    const wrapper = mount(MissionStepStatusBadge, { props: { status: "SKIPPED" }, ...globalComponents });
    expect(wrapper.text()).toBe("SKIPPED");
  });

  it.each(["PENDING", "SKIPPED", "QUEUED", "SUCCESS", "FAILED", "CANCELLED"] as const)(
    "renders a color class for %s",
    (status) => {
      const wrapper = mount(MissionStepStatusBadge, { props: { status }, ...globalComponents });
      expect(wrapper.attributes("class")).toBeTruthy();
    },
  );
});
