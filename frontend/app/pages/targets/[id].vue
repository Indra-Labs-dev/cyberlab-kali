<script setup lang="ts">
// Legacy route kept only as a redirect (18b) -- the real page moved to
// pages/assets/[id].vue. The function form of `redirect` receives the
// resolved route so the :id param carries over -- vue-router's native
// mechanism (Nuxt's `redirect` page-meta option forwards to it directly),
// not a client-side navigateTo() call.
definePageMeta({
  redirect: (to) => `/assets/${to.params.id}`,
});
</script>

<template>
  <div />
</template>
