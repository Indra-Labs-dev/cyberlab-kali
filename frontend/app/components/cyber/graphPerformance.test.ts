import { describe, expect, it } from "vitest";
import { getQualityConfig, resolveQualityTier, supportsWebGL } from "./graphPerformance";

describe("resolveQualityTier", () => {
  it("falls back when WebGL isn't supported, regardless of viewport", () => {
    expect(resolveQualityTier({ viewportWidth: 1920, webglSupported: false, reducedMotion: false })).toBe("fallback");
  });

  it("falls back on small screens even when WebGL is supported", () => {
    expect(resolveQualityTier({ viewportWidth: 375, webglSupported: true, reducedMotion: false })).toBe("fallback");
  });

  it("uses medium tier on mid-sized screens", () => {
    expect(resolveQualityTier({ viewportWidth: 1024, webglSupported: true, reducedMotion: false })).toBe("medium");
  });

  it("uses high tier on large screens with no reduced-motion preference", () => {
    expect(resolveQualityTier({ viewportWidth: 1920, webglSupported: true, reducedMotion: false })).toBe("high");
  });

  it("steps down to low tier on large screens when reduced-motion is requested, without abandoning 3D", () => {
    expect(resolveQualityTier({ viewportWidth: 1920, webglSupported: true, reducedMotion: true })).toBe("low");
  });
});

describe("getQualityConfig", () => {
  it("gives high tier more nodes and bloom+particles than low tier", () => {
    const high = getQualityConfig("high");
    const low = getQualityConfig("low");
    expect(high.maxNodes).toBeGreaterThan(low.maxNodes);
    expect(high.bloom).toBe(true);
    expect(low.bloom).toBe(false);
    expect(low.autoRotate).toBe(false);
  });
});

describe("supportsWebGL", () => {
  it("returns a boolean without throwing in a non-WebGL test environment", () => {
    expect(typeof supportsWebGL()).toBe("boolean");
  });
});
