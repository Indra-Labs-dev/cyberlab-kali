import { describe, expect, it } from "vitest";
import { nodeColor, nodePriority, nodeRadius } from "./graphTheme";

describe("nodeColor", () => {
  it("colors a FINDING by its real risk_priority when known", () => {
    expect(nodeColor({ type: "FINDING", metadata: { risk_priority: "CRITICAL" } })).toBe("#f87171");
    expect(nodeColor({ type: "FINDING", metadata: { risk_priority: "LOW" } })).toBe("#34d399");
  });

  it("falls back to the type color for an unscored FINDING", () => {
    expect(nodeColor({ type: "FINDING", metadata: {} })).toBe("#f59e0b");
  });

  it("colors non-FINDING types by their fixed type color", () => {
    expect(nodeColor({ type: "ASSET", metadata: {} })).toBe("#38bdf8");
    expect(nodeColor({ type: "CVE", metadata: {} })).toBe("#f87171");
  });
});

describe("nodeRadius", () => {
  it("scales an ASSET by its real criticality", () => {
    const critical = nodeRadius({ type: "ASSET", metadata: { criticality: "CRITICAL" } });
    const low = nodeRadius({ type: "ASSET", metadata: { criticality: "LOW" } });
    expect(critical).toBeGreaterThan(low);
  });

  it("scales a FINDING by its real risk_score", () => {
    const high = nodeRadius({ type: "FINDING", metadata: { risk_score: 95 } });
    const low = nodeRadius({ type: "FINDING", metadata: { risk_score: 5 } });
    expect(high).toBeGreaterThan(low);
  });

  it("renders context node types (CVE/SERVICE/TECHNOLOGY) smaller than the default", () => {
    const cve = nodeRadius({ type: "CVE", metadata: {} });
    const unscored = nodeRadius({ type: "FINDING", metadata: {} });
    expect(cve).toBeLessThan(unscored);
  });
});

describe("nodePriority", () => {
  it("ranks a higher-risk finding above a lower-risk one", () => {
    const high = nodePriority({ type: "FINDING", metadata: { risk_score: 90 } });
    const low = nodePriority({ type: "FINDING", metadata: { risk_score: 10 } });
    expect(high).toBeGreaterThan(low);
  });

  it("ranks findings above assets above context nodes by default", () => {
    const finding = nodePriority({ type: "FINDING", metadata: {} });
    const asset = nodePriority({ type: "ASSET", metadata: { criticality: "CRITICAL" } });
    const cve = nodePriority({ type: "CVE", metadata: {} });
    expect(finding).toBeGreaterThan(asset);
    expect(asset).toBeGreaterThan(cve);
  });
});
