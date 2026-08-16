<script setup lang="ts">
// Thin composition of the extracted Topbar + Sidebar (previously all
// inline here). Mobile drawer open/close state and its Escape-to-close /
// aria-controls behavior are preserved as-is, just relocated from the
// <aside> markup to the Sidebar prop/emit boundary.
const route = useRoute();
const sidebarOpen = ref(false);

function closeSidebar() {
  sidebarOpen.value = false;
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape" && sidebarOpen.value) closeSidebar();
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));
watch(() => route.path, closeSidebar);
</script>

<template>
  <div class="min-h-screen bg-bg text-slate-100 md:flex">
    <LayoutAnimatedBackground />
    <LayoutSidebar :open="sidebarOpen" :current-path="route.path" @close="closeSidebar" />

    <div class="flex min-w-0 flex-1 flex-col">
      <LayoutTopbar :sidebar-open="sidebarOpen" @toggle-sidebar="sidebarOpen = !sidebarOpen" />
      <main class="min-w-0 flex-1 overflow-y-auto">
        <slot />
      </main>
    </div>
  </div>
</template>
