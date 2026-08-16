import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import Sidebar from "./Sidebar.vue";

const stubs = { NuxtLink: { template: "<a :href=\"to\"><slot /></a>", props: ["to"] } };

describe("Sidebar", () => {
  it("renders every real route grouped, not the removed fictional Recon stub", () => {
    const wrapper = mount(Sidebar, { props: { open: false, currentPath: "/" }, global: { stubs } });
    const hrefs = wrapper.findAll("a").map((a) => a.attributes("href"));
    expect(hrefs).toEqual(
      expect.arrayContaining([
        "/",
        "/projects",
        "/assets",
        "/findings",
        "/graph",
        "/scans",
        "/chains",
        "/tools",
        "/ai",
        "/ai/missions",
        "/intelligence",
        "/reports",
        "/labs",
        "/terminal",
        "/settings",
      ]),
    );
    expect(wrapper.text()).not.toContain("Recon");
  });

  it("marks the item matching currentPath as the active page", () => {
    const wrapper = mount(Sidebar, { props: { open: false, currentPath: "/assets/123" }, global: { stubs } });
    const assetsLink = wrapper.findAll("a").find((a) => a.attributes("href") === "/assets");
    expect(assetsLink?.attributes("aria-current")).toBe("page");
    const findingsLink = wrapper.findAll("a").find((a) => a.attributes("href") === "/findings");
    expect(findingsLink?.attributes("aria-current")).toBeUndefined();
  });

  it("emits close when the mobile backdrop is clicked", async () => {
    const wrapper = mount(Sidebar, { props: { open: true, currentPath: "/" }, global: { stubs } });
    await wrapper.find('[aria-hidden="true"]').trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);
  });
});
