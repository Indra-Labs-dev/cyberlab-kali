import { describe, expect, it } from "vitest";
import { AI_RISK_COLORS, FINDING_STATUS_COLORS, RISK_PRIORITY_COLORS, SEVERITY_COLORS } from "./colors";

// Byte-for-byte the values every page declared locally before the 18a
// centralization (see the module docstring in colors.ts) -- these tests
// exist to catch an accidental value change during a future edit, not to
// re-litigate the values themselves.
describe("SEVERITY_COLORS", () => {
  it("covers all five severities", () => {
    expect(Object.keys(SEVERITY_COLORS).sort()).toEqual(["CRITICAL", "HIGH", "INFO", "LOW", "MEDIUM"]);
  });

  it("matches the pre-centralization values", () => {
    expect(SEVERITY_COLORS.CRITICAL).toBe("bg-red-500/15 text-red-400");
    expect(SEVERITY_COLORS.INFO).toBe("bg-slate-700/50 text-slate-300");
  });

  it("is reused verbatim for AI_RISK_COLORS (same scale, different domain)", () => {
    expect(AI_RISK_COLORS).toBe(SEVERITY_COLORS);
  });
});

describe("RISK_PRIORITY_COLORS", () => {
  it("covers INFORMATIONAL in addition to the severity scale", () => {
    expect(Object.keys(RISK_PRIORITY_COLORS).sort()).toEqual(["CRITICAL", "HIGH", "INFORMATIONAL", "LOW", "MEDIUM"]);
  });
});

describe("FINDING_STATUS_COLORS", () => {
  it("covers all seven Finding lifecycle statuses", () => {
    expect(Object.keys(FINDING_STATUS_COLORS).sort()).toEqual(
      ["ACCEPTED_RISK", "CONFIRMED", "FALSE_POSITIVE", "IN_REVIEW", "NEW", "REMEDIATED", "REOPENED"].sort(),
    );
  });

  it("does NOT include line-through in the base FALSE_POSITIVE color (see StatusBadge's strikeFalsePositive prop)", () => {
    expect(FINDING_STATUS_COLORS.FALSE_POSITIVE).not.toContain("line-through");
  });
});
