import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import AssetHeader from "./AssetHeader.vue";

const asset = {
  id: "a1",
  project_id: "p1",
  name: "DVWA",
  hostname: "dvwa.local",
  ip_address: null,
  url: null,
  type: "HOST" as const,
  criticality: "MEDIUM" as const,
  authorization_status: "LAB" as const,
  tags: ["web"],
  technologies: ["Apache"],
  description: "Test asset",
  first_seen: "2026-01-01T00:00:00Z",
  last_seen: "2026-01-02T00:00:00Z",
  created_at: "2026-01-01T00:00:00Z",
};

function makeProps(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    asset,
    project: { id: "p1", name: "Phase 16 E2E" },
    assetId: "a1",
    savingAuth: false,
    savingCriticality: false,
    savingTags: false,
    addTag: vi.fn().mockResolvedValue(true),
    ...overrides,
  };
}

describe("AssetHeader", () => {
  it("renders the asset's authorization, criticality, type and project link", () => {
    const wrapper = mount(AssetHeader, { props: makeProps() });
    expect(wrapper.text()).toContain("LAB");
    expect(wrapper.text()).toContain("MEDIUM");
    expect(wrapper.text()).toContain("HOST");
    expect(wrapper.text()).toContain("Phase 16 E2E");
  });

  it("shows the UNKNOWN authorization warning only when relevant", () => {
    const wrapper = mount(AssetHeader, { props: makeProps() });
    expect(wrapper.text()).not.toContain("jobs will be rejected");

    const unknownWrapper = mount(AssetHeader, {
      props: makeProps({ asset: { ...asset, authorization_status: "UNKNOWN" as const } }),
    });
    expect(unknownWrapper.text()).toContain("jobs will be rejected");
  });

  it("emits update-authorization when a status button is clicked", async () => {
    const wrapper = mount(AssetHeader, { props: makeProps() });
    const buttons = wrapper.findAll("button").filter((b) => b.text() === "AUTHORIZED");
    await buttons[0]!.trigger("click");
    expect(wrapper.emitted("update-authorization")).toEqual([["AUTHORIZED"]]);
  });

  it("emits remove-tag when a tag's remove button is clicked", async () => {
    const wrapper = mount(AssetHeader, { props: makeProps() });
    await wrapper.find("button.text-slate-500.hover\\:text-red-400").trigger("click");
    expect(wrapper.emitted("remove-tag")).toEqual([["web"]]);
  });

  it("calls addTag and clears the input only on success", async () => {
    const addTag = vi.fn().mockResolvedValue(true);
    const wrapper = mount(AssetHeader, { props: makeProps({ addTag }) });
    const input = wrapper.find('input[placeholder="add tag…"]');
    await input.setValue("newtag");
    await input.trigger("keyup.enter");
    await wrapper.vm.$nextTick();
    expect(addTag).toHaveBeenCalledWith("newtag");
    expect((input.element as HTMLInputElement).value).toBe("");
  });

  it("keeps the typed tag when addTag fails", async () => {
    const addTag = vi.fn().mockResolvedValue(false);
    const wrapper = mount(AssetHeader, { props: makeProps({ addTag }) });
    const input = wrapper.find('input[placeholder="add tag…"]');
    await input.setValue("newtag");
    await input.trigger("keyup.enter");
    await wrapper.vm.$nextTick();
    expect((input.element as HTMLInputElement).value).toBe("newtag");
  });

  it("does not call addTag for a tag that already exists", async () => {
    const addTag = vi.fn();
    const wrapper = mount(AssetHeader, { props: makeProps({ addTag }) });
    const input = wrapper.find('input[placeholder="add tag…"]');
    await input.setValue("web");
    await input.trigger("keyup.enter");
    expect(addTag).not.toHaveBeenCalled();
  });
});
