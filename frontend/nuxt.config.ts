export default defineNuxtConfig({
  compatibilityDate: "2025-01-01",
  devtools: { enabled: true },
  modules: ["@nuxtjs/tailwindcss"],
  css: ["~/assets/css/main.css"],
  app: {
    head: {
      title: "CyberLab",
      link: [{ rel: "icon", type: "image/png", href: "/logo.png" }],
    },
  },
  runtimeConfig: {
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || "http://localhost:8300",
      wsBase: process.env.NUXT_PUBLIC_WS_BASE || "ws://localhost:8300",
      // Only needed if the backend is started with AUTH_ENABLED=true (see
      // docs/security.md) -- empty by default, matching the API's own default.
      apiToken: process.env.NUXT_PUBLIC_API_TOKEN || "",
    },
  },
  nitro: {
    devProxy: {
      "/api": {
        target: process.env.NUXT_API_PROXY_TARGET || "http://cyberlab-api:8000/api",
        changeOrigin: true,
      },
    },
  },
});
