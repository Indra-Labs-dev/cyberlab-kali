import vue from "@vitejs/plugin-vue";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Minimal, plain Vitest setup -- deliberately not @nuxt/test-utils' full
// Nuxt environment (which boots an actual Nuxt app context per test file):
// none of the 18a foundation tests need real Nuxt runtime behavior
// (useRuntimeConfig, SSR, ...), just Vue SFC compilation and the same `~`
// alias Nuxt itself resolves to app/. Composables that call other
// composables (useAssets -> useApi) import them explicitly rather than
// relying on Nuxt's auto-import macro, specifically so they stay testable
// here without a full Nuxt boot -- see app/composables/useAssets.ts.
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "~": fileURLToPath(new URL("./app", import.meta.url)),
      "@": fileURLToPath(new URL("./app", import.meta.url)),
    },
  },
  test: {
    environment: "happy-dom",
    include: ["app/**/*.{test,spec}.ts"],
  },
});
