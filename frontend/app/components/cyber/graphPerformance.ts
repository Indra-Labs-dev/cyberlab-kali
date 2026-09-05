// Quality-tier resolution for the 3D Security Graph -- decides whether to
// mount it at all, and how much to ask of it when mounted. Kept separate
// from SecurityGraph3D.client.vue so the decision logic is testable without
// touching Three.js, and reusable by whatever component decides between
// <CyberSecurityGraph3D> and <UiHeroRadar> on the Dashboard.
//
// Philosophy (per the Adaptive Experience direction, not "shrink
// everything"): viewport alone decides 3D vs. 2D fallback -- small screens
// get the 2D radar outright, not a crippled 3D scene. WebGL support is a
// hard gate regardless of viewport. Within "desktop-class", reduced-motion
// steps down a tier (less continuous motion) without abandoning 3D
// entirely, since a static/low-motion 3D graph is still more information-
// dense than falling back to 2D.
export type QualityTier = "high" | "medium" | "low" | "fallback";

export interface GraphQualityConfig {
  tier: Exclude<QualityTier, "fallback">;
  maxNodes: number;
  bloom: boolean;
  linkParticles: boolean;
  autoRotate: boolean;
  /** How many simulation ticks before the force layout freezes -- lower is cheaper. */
  cooldownTicks: number;
  /** Caps devicePixelRatio-driven render resolution -- a 3x DPR phone shouldn't render at 3x cost. */
  pixelRatioCap: number;
}

const QUALITY_CONFIG: Record<Exclude<QualityTier, "fallback">, GraphQualityConfig> = {
  high: { tier: "high", maxNodes: 60, bloom: true, linkParticles: true, autoRotate: true, cooldownTicks: 200, pixelRatioCap: 2 },
  medium: { tier: "medium", maxNodes: 35, bloom: true, linkParticles: false, autoRotate: true, cooldownTicks: 120, pixelRatioCap: 1.5 },
  low: { tier: "low", maxNodes: 25, bloom: false, linkParticles: false, autoRotate: false, cooldownTicks: 80, pixelRatioCap: 1 },
};

export function getQualityConfig(tier: Exclude<QualityTier, "fallback">): GraphQualityConfig {
  return QUALITY_CONFIG[tier];
}

export function supportsWebGL(): boolean {
  if (typeof document === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// Pure decision function -- WebGL/matchMedia checks are injected as params
// (rather than called internally) so this is directly testable without a
// real browser; the .client.vue component supplies the live values.
export function resolveQualityTier(params: { viewportWidth: number; webglSupported: boolean; reducedMotion: boolean }): QualityTier {
  const { viewportWidth, webglSupported, reducedMotion } = params;
  if (!webglSupported) return "fallback";
  if (viewportWidth < 768) return "fallback"; // small screens: 2D HeroRadar, not a cut-down 3D scene
  if (viewportWidth < 1280) return "medium";
  if (reducedMotion) return "low"; // desktop-class, WebGL fine, just minimize continuous motion
  return "high";
}
