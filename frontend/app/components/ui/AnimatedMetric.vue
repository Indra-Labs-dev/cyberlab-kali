<script setup lang="ts">
// Tweens the displayed number toward `value` whenever it changes --
// StatCard values start at 0 (empty arrays before the first fetch
// resolves) and this makes the real data's arrival read as a "count up"
// rather than a jump cut. Skips the tween entirely under
// prefers-reduced-motion, and there's nothing to fake here: it only ever
// animates toward a value the caller actually passed.
import { onBeforeUnmount, ref, watch } from "vue";

const props = defineProps<{ value: number }>();
const display = ref(props.value);
let frame: number | undefined;

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

function animateTo(target: number) {
  if (frame !== undefined) cancelAnimationFrame(frame);
  if (prefersReducedMotion() || typeof requestAnimationFrame !== "function") {
    display.value = target;
    return;
  }
  const start = display.value;
  const delta = target - start;
  if (delta === 0) return;
  const duration = 600;
  const startTime = performance.now();

  function step(now: number) {
    const progress = Math.min(1, (now - startTime) / duration);
    const eased = 1 - Math.pow(1 - progress, 3);
    display.value = Math.round(start + delta * eased);
    if (progress < 1) frame = requestAnimationFrame(step);
  }
  frame = requestAnimationFrame(step);
}

watch(() => props.value, animateTo);
onBeforeUnmount(() => {
  if (frame !== undefined) cancelAnimationFrame(frame);
});
</script>

<template>
  <span>{{ display }}</span>
</template>
