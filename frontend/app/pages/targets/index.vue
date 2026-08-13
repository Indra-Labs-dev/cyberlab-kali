<script setup lang="ts">
// Legacy route kept only as a redirect (18b) -- the real page moved to
// pages/assets/index.vue. `redirect` in definePageMeta is forwarded
// directly to vue-router's route-record `redirect` option, resolved
// before this component ever renders (no flash of old content, no extra
// client-side navigateTo() call needed).
definePageMeta({
  redirect: "/assets",
});
</script>

<template>
  <div />
</template>
