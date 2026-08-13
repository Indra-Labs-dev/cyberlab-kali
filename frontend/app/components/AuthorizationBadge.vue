<script setup lang="ts">
// Asset authorization_status (LAB/AUTHORIZED/LOCAL/UNKNOWN) -- the security
// boundary established in Phase 11, unchanged since. Not named in the
// original 18a component list but follows the same pattern, needed to
// migrate pages/targets/index.vue's authColor usage.
import { AUTHORIZATION_COLORS } from "~/constants/colors";
import type { AuthorizationStatus } from "~/types/asset";

withDefaults(defineProps<{ status: AuthorizationStatus; size?: "sm" | "md"; bold?: boolean }>(), {
  size: "md",
  bold: false,
});
</script>

<template>
  <Badge :color-class="AUTHORIZATION_COLORS[status]" :size="size" :bold="bold">
    <slot>{{ status }}</slot>
  </Badge>
</template>
