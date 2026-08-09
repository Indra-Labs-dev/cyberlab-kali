export default defineNuxtConfig({
  compatibilityDate: "2025-01-01",
  devtools: { enabled: true },
  modules: ["@nuxtjs/tailwindcss"],
  css: ["~/assets/css/main.css"],
  runtimeConfig: {
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || "http://localhost:8300",
      wsBase: process.env.NUXT_PUBLIC_WS_BASE || "ws://localhost:8300",
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
