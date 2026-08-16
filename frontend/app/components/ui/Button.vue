<script setup lang="ts">
// Renders as a NuxtLink when `to` is given, a <button> otherwise -- one
// component instead of choosing between a styled <button> and a
// styled <NuxtLink> at every call site.
//
// This is two branches, not `<component :is="to ? 'NuxtLink' : 'button'">`:
// NuxtLink is a Nuxt compiler-injected component, not something registered
// in Vue's runtime component registry, so resolving it dynamically *by
// string* silently fails -- it renders as an inert `<nuxtlink>` custom
// element instead of an `<a>`, with no console warning. Using the tag
// literally (as below) is what makes the compiler wire it up correctly.
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    variant?: "primary" | "secondary" | "ghost" | "danger";
    size?: "sm" | "md";
    to?: string;
    type?: "button" | "submit";
    disabled?: boolean;
  }>(),
  { variant: "secondary", size: "md", type: "button", disabled: false },
);

const classes = computed(() => [
  "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 disabled:cursor-not-allowed disabled:opacity-50",
  props.size === "sm" ? "px-2.5 py-1 text-xs" : "px-3.5 py-1.5 text-sm",
  props.variant === "primary" && "bg-accent-500 text-slate-950 hover:bg-accent-400",
  props.variant === "secondary" && "border border-slate-700 bg-slate-900/60 text-slate-200 hover:bg-slate-800",
  props.variant === "ghost" && "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200",
  props.variant === "danger" && "bg-danger-500/15 text-danger-400 hover:bg-danger-500/25",
]);
</script>

<template>
  <NuxtLink v-if="to" :to="to" :class="classes">
    <slot />
  </NuxtLink>
  <button v-else :type="type" :disabled="disabled" :class="classes">
    <slot />
  </button>
</template>
