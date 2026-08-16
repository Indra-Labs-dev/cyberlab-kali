import type { Config } from "tailwindcss";

// Semantic aliases layered on top of Tailwind's own slate/cyan/violet/
// emerald/amber/red scales (same hex values as those scales -- not new
// hues) so components can express intent (`bg-surface`, `text-accent-400`,
// `shadow-glow-ai`) instead of repeating raw `slate-900/40` everywhere.
// `constants/colors.ts` (severity/risk/status badge maps) is untouched --
// it already encodes a deliberate, well-reasoned per-domain convention;
// these tokens are for shell/layout surfaces and the AI/tech accent hues,
// not a replacement for it.
export default {
  content: ["./app/components/**/*.{vue,js,ts}", "./app/layouts/**/*.vue", "./app/pages/**/*.vue", "./app/app.vue"],
  theme: {
    extend: {
      colors: {
        bg: "#020617", // slate-950
        surface: "#0f172a", // slate-900
        "surface-2": "#1e293b", // slate-800
        border: "#1e293b", // slate-800
        accent: { 400: "#22d3ee", 500: "#06b6d4", 600: "#0891b2" }, // cyan -- tech/info
        ai: { 400: "#a78bfa", 500: "#8b5cf6", 600: "#7c3aed" }, // violet -- AI
        success: { 400: "#34d399", 500: "#10b981" }, // emerald
        warning: { 400: "#fbbf24", 500: "#f59e0b" }, // amber
        danger: { 400: "#f87171", 500: "#ef4444" }, // red
      },
      boxShadow: {
        "glow-accent": "0 0 0 1px rgba(34,211,238,0.15), 0 0 24px -6px rgba(34,211,238,0.45)",
        "glow-ai": "0 0 0 1px rgba(167,139,250,0.15), 0 0 24px -6px rgba(167,139,250,0.45)",
        "glow-success": "0 0 0 1px rgba(52,211,153,0.15), 0 0 24px -6px rgba(52,211,153,0.45)",
        "glow-warning": "0 0 0 1px rgba(251,191,36,0.15), 0 0 24px -6px rgba(251,191,36,0.45)",
        "glow-danger": "0 0 0 1px rgba(248,113,113,0.15), 0 0 24px -6px rgba(248,113,113,0.45)",
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      // Motion design tokens (§11-12 of the visual pass): slow, elegant,
      // transform/opacity-only -- no layout-affecting properties, so these
      // stay cheap even running continuously (ambient background blobs).
      // Compliance with prefers-reduced-motion is handled two ways: pure
      // CSS animations use the `motion-safe:` variant at the call site,
      // and main.css carries a global `prefers-reduced-motion: reduce`
      // override as a safety net for anything that doesn't.
      keyframes: {
        fadeSlideUp: { "0%": { opacity: "0", transform: "translateY(8px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        drift: {
          "0%, 100%": { transform: "translate(0, 0) scale(1)" },
          "50%": { transform: "translate(24px, -18px) scale(1.06)" },
        },
        shimmerSweep: { "0%": { transform: "translateX(-100%)" }, "100%": { transform: "translateX(100%)" } },
        spinSlow: { from: { transform: "rotate(0deg)" }, to: { transform: "rotate(360deg)" } },
        lightSweep: { "0%, 100%": { backgroundPosition: "-200% 0" }, "50%": { backgroundPosition: "200% 0" } },
      },
      animation: {
        "fade-slide-up": "fadeSlideUp 0.5s ease-out both",
        drift: "drift 24s ease-in-out infinite",
        "drift-slow": "drift 32s ease-in-out infinite reverse",
        "shimmer-sweep": "shimmerSweep 1.6s ease-in-out infinite",
        "spin-slow": "spinSlow 120s linear infinite",
        "light-sweep": "lightSweep 8s ease-in-out infinite",
      },
    },
  },
} satisfies Config;
