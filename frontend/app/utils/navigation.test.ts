import { describe, expect, it } from "vitest";
import { isNavItemActive } from "./navigation";

describe("isNavItemActive", () => {
  it("matches the Overview item only on the exact root path", () => {
    expect(isNavItemActive("/", "/")).toBe(true);
    expect(isNavItemActive("/assets", "/")).toBe(false);
  });

  it("matches an item's own path exactly", () => {
    expect(isNavItemActive("/assets", "/assets")).toBe(true);
    expect(isNavItemActive("/findings", "/findings")).toBe(true);
  });

  it("matches a detail route under a list item's path", () => {
    expect(isNavItemActive("/assets/123", "/assets")).toBe(true);
    expect(isNavItemActive("/findings/abc-def", "/findings")).toBe(true);
    expect(isNavItemActive("/projects/123", "/projects")).toBe(true);
    expect(isNavItemActive("/scans/123", "/scans")).toBe(true);
  });

  it("does not match a different section, even with a shared prefix", () => {
    expect(isNavItemActive("/assets-other", "/assets")).toBe(false);
    expect(isNavItemActive("/scans/123", "/assets")).toBe(false);
  });
});
