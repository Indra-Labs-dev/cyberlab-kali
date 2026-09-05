<script setup lang="ts">
// Holographic 3D preview of the real Security Graph -- self-contained data
// widget (same "own fetch, own loading/error state" convention as
// ActiveFindingsWidget.vue), rendering engine fully isolated from the rest
// of the app. Nothing here is fabricated: it seeds from the real top-risk
// findings (GET /api/findings?sort=risk_score_desc) and pulls each one's
// real 1-hop neighborhood (GET /api/graph/nodes/FINDING/{id}, the same
// endpoint the 2D Security Graph page uses via useGraph().loadNode),
// merges and caps the result client-side (graphAdapter.ts).
//
// The `.client.vue` filename is a Nuxt convention: this component is
// entirely excluded from SSR and lazy/code-split automatically -- no
// manual <ClientOnly> or process.client guards needed for that part.
//
// Quality tiers (graphPerformance.ts) decide whether this even mounts:
// the caller should check resolveQualityTier() itself and render
// <UiHeroRadar> instead for the "fallback" tier (small screens, no WebGL).
// This component assumes it's only being mounted for a real tier.
import * as THREE from "three";
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from "vue";
import { capNodes, mergeGraphResponses, toForceGraphData } from "./graphAdapter";
import { getQualityConfig, prefersReducedMotion, resolveQualityTier, supportsWebGL } from "./graphPerformance";
import { BACKGROUND_COLOR, BLOOM, LINK_COLOR, LINK_PARTICLE_COLOR, nodeColor, nodePriority, nodeRadius } from "./graphTheme";
import { useApi } from "~/composables/useApi";
import { useGraph } from "~/composables/useGraph";
import type { Finding } from "~/types/finding";
import type { GraphNodeType } from "~/types/graph";

const props = withDefaults(defineProps<{ seedLimit?: number; height?: string }>(), { seedLimit: 6, height: "320px" });
const emit = defineEmits<{ "select-node": [{ id: string; type: GraphNodeType }]; unavailable: [] }>();

const { apiFetch } = useApi();
const { loadNode } = useGraph();

const container = ref<HTMLDivElement>();
const loading = ref(true);
const error = ref("");
const isEmpty = ref(false);
const hoveredLabel = ref("");
const selectedNode = ref<{ id: string; type: GraphNodeType; label: string; metadata: Record<string, unknown> } | null>(null);

const selectedDetailLink = computed(() => {
  if (!selectedNode.value) return null;
  if (selectedNode.value.type === "ASSET") return `/assets/${selectedNode.value.id}`;
  if (selectedNode.value.type === "FINDING") return `/findings/${selectedNode.value.id}`;
  return null; // CVE/SERVICE/TECHNOLOGY are virtual nodes -- no dedicated detail page exists
});

// shallowRef -- this holds a 3d-force-graph instance + THREE internals,
// none of which should ever go through Vue's deep reactivity proxying.
const graphInstance = shallowRef<any>();
let resizeObserver: ResizeObserver | undefined;
let rotationFrame: number | undefined;
let rotationPaused = false;
let resumeTimeout: ReturnType<typeof setTimeout> | undefined;
let glowTexture: THREE.CanvasTexture | undefined;
let hoveredNodeObj: THREE.Object3D | undefined;
let selectedNodeObj: THREE.Object3D | undefined;

function makeGlowTexture(): THREE.CanvasTexture {
  if (glowTexture) return glowTexture;
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.35, "rgba(255,255,255,0.5)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  glowTexture = new THREE.CanvasTexture(canvas);
  return glowTexture;
}

// Scale a node's THREE object based on its current hover/selection state --
// both can apply at once (hovering the selected node), hover always wins
// visually since it's the more immediate signal.
function applyNodeScale(obj: THREE.Object3D) {
  if (obj === hoveredNodeObj) obj.scale.setScalar(1.6);
  else if (obj === selectedNodeObj) obj.scale.setScalar(1.35);
  else obj.scale.setScalar(1);
}

async function fetchGraphData() {
  const findings = await apiFetch<Finding[]>(`/api/findings?sort=risk_score_desc&limit=${props.seedLimit}`);
  if (findings.length === 0) return { nodes: [], edges: [] };
  const neighborhoods = await Promise.all(findings.map((f) => loadNode("FINDING", f.id, 1).catch(() => ({ nodes: [], edges: [] }))));
  return mergeGraphResponses(neighborhoods);
}

async function render() {
  if (!container.value) return;

  const tier = resolveQualityTier({
    viewportWidth: window.innerWidth,
    webglSupported: supportsWebGL(),
    reducedMotion: prefersReducedMotion(),
  });
  if (tier === "fallback") {
    emit("unavailable");
    loading.value = false;
    return;
  }
  const config = getQualityConfig(tier);

  const merged = await fetchGraphData();
  if (merged.nodes.length === 0) {
    isEmpty.value = true;
    loading.value = false;
    return;
  }
  const capped = capNodes(merged, config.maxNodes, nodePriority);
  const data = toForceGraphData(capped);

  const [{ default: ForceGraph3D }, { UnrealBloomPass }] = await Promise.all([
    import("3d-force-graph"),
    import("three/examples/jsm/postprocessing/UnrealBloomPass.js"),
  ]);

  // Explicit initial sizing -- the container is still `invisible` (visibility,
  // not display) at this point so clientWidth/Height should already reflect
  // its final layout box, but setting it explicitly rather than trusting the
  // library's own auto-detection avoids any risk of it falling back to
  // window dimensions.
  const instance = new ForceGraph3D(container.value)
    .width(container.value.clientWidth)
    .height(container.value.clientHeight)
    .backgroundColor(BACKGROUND_COLOR)
    .graphData(data as any)
    .nodeLabel((n: any) => `${n.label} (${n.type})`)
    .nodeThreeObjectExtend(false)
    .nodeThreeObject((n: any) => {
      const color = new THREE.Color(nodeColor(n));
      const radius = Math.max(1.8, nodeRadius(n) * 1.4);

      const group = new THREE.Group();
      const core = new THREE.Mesh(new THREE.SphereGeometry(radius, 16, 16), new THREE.MeshBasicMaterial({ color }));
      group.add(core);

      const halo = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: makeGlowTexture(),
          color,
          transparent: true,
          opacity: 0.55,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        }),
      );
      halo.scale.set(radius * 6, radius * 6, 1);
      group.add(halo);
      return group;
    })
    .linkColor(() => LINK_COLOR)
    .linkWidth(0.6)
    .linkOpacity(0.6)
    .onNodeHover((n: any) => {
      hoveredLabel.value = n ? `${n.label}` : "";
      if (container.value) container.value.style.cursor = n ? "pointer" : "default";
      const previous = hoveredNodeObj;
      hoveredNodeObj = n?.__threeObj ?? undefined;
      if (previous && previous !== hoveredNodeObj) applyNodeScale(previous);
      if (hoveredNodeObj) applyNodeScale(hoveredNodeObj);
    })
    .onNodeClick((n: any) => {
      const previous = selectedNodeObj;
      selectedNodeObj = n.__threeObj ?? undefined;
      if (previous && previous !== selectedNodeObj) applyNodeScale(previous);
      if (selectedNodeObj) applyNodeScale(selectedNodeObj);
      selectedNode.value = { id: n.id, type: n.type, label: n.label, metadata: n.metadata ?? {} };
      emit("select-node", { id: n.id, type: n.type });
      if (typeof n.x === "number") {
        const dist = 90;
        const ratio = 1 + dist / Math.hypot(n.x, n.y, n.z || 0.01);
        instance.cameraPosition({ x: n.x * ratio, y: n.y * ratio, z: (n.z || 0) * ratio }, { x: n.x, y: n.y, z: n.z || 0 }, 800);
      }
    })
    .onBackgroundClick(() => {
      const previous = selectedNodeObj;
      selectedNodeObj = undefined;
      if (previous) applyNodeScale(previous);
      selectedNode.value = null;
    })
    .cooldownTicks(config.cooldownTicks)
    .enableNodeDrag(false);

  if (config.linkParticles) {
    instance
      .linkDirectionalParticles(1)
      .linkDirectionalParticleWidth(1.4)
      .linkDirectionalParticleColor(() => LINK_PARTICLE_COLOR)
      .linkDirectionalParticleSpeed(0.006);
  }

  instance.renderer().setPixelRatio(Math.min(window.devicePixelRatio || 1, config.pixelRatioCap));

  if (config.bloom) {
    try {
      const composer = instance.postProcessingComposer();
      const size = new THREE.Vector2(container.value.clientWidth, container.value.clientHeight);
      composer.addPass(new UnrealBloomPass(size, BLOOM.strength, BLOOM.radius, BLOOM.threshold));
    } catch {
      // Bloom is an enhancement, not a requirement -- the sprite-based glow
      // on every node already gives a real (if softer) glow if this fails.
    }
  }

  if (config.autoRotate) {
    let angle = 0;
    const distance = 240;
    const tick = () => {
      if (!rotationPaused) {
        angle += 0.0007;
        instance.cameraPosition({ x: distance * Math.sin(angle), y: 30, z: distance * Math.cos(angle) });
      }
      rotationFrame = requestAnimationFrame(tick);
    };
    rotationFrame = requestAnimationFrame(tick);

    const pause = () => {
      rotationPaused = true;
      clearTimeout(resumeTimeout);
      resumeTimeout = setTimeout(() => (rotationPaused = false), 4000);
    };
    container.value.addEventListener("pointerdown", pause);
  } else {
    instance.cameraPosition({ x: 0, y: 30, z: 240 });
  }

  resizeObserver = new ResizeObserver(() => {
    if (!container.value) return;
    instance.width(container.value.clientWidth).height(container.value.clientHeight);
  });
  resizeObserver.observe(container.value);

  graphInstance.value = instance;
  loading.value = false;
}

onMounted(async () => {
  try {
    await render();
  } catch (err: any) {
    error.value = err?.data?.detail || err?.message || "Failed to load the security graph";
    loading.value = false;
  }
});

onBeforeUnmount(() => {
  if (rotationFrame !== undefined) cancelAnimationFrame(rotationFrame);
  clearTimeout(resumeTimeout);
  resizeObserver?.disconnect();
  graphInstance.value?._destructor?.();
  glowTexture?.dispose();
});
</script>

<template>
  <div class="relative" :style="{ height }">
    <UiSkeleton v-if="loading" :lines="4" />
    <UiErrorState v-else-if="error" :message="error" />
    <p v-else-if="isEmpty" class="text-sm text-slate-600">No risk-scored findings yet to visualize.</p>
    <div ref="container" class="h-full w-full" :class="{ invisible: loading || error || isEmpty }" />
    <div
      v-if="hoveredLabel && !selectedNode"
      class="pointer-events-none absolute left-2 top-2 rounded-md border border-slate-700 bg-slate-900/90 px-2 py-1 text-xs text-slate-200 backdrop-blur"
    >
      {{ hoveredLabel }}
    </div>

    <!-- Selection detail panel -- real node data only, no dedicated page
         link for CVE/SERVICE/TECHNOLOGY (virtual node types, nothing to
         open per the routing audit). -->
    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 translate-y-1"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 translate-y-1"
    >
      <div
        v-if="selectedNode"
        class="absolute bottom-2 left-2 right-2 max-w-xs rounded-md border border-slate-700 bg-slate-900/95 p-3 text-xs shadow-xl backdrop-blur-xl sm:right-auto"
      >
        <div class="mb-1.5 flex items-center justify-between gap-2">
          <span class="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide" :style="{ color: nodeColor(selectedNode), backgroundColor: nodeColor(selectedNode) + '22' }">
            {{ selectedNode.type }}
          </span>
          <button type="button" class="text-slate-500 hover:text-slate-300" aria-label="Close node details" @click="selectedNode = null">
            ✕
          </button>
        </div>
        <p class="mb-2 truncate font-medium text-slate-200">{{ selectedNode.label }}</p>

        <div v-if="selectedNode.type === 'FINDING'" class="mb-2 flex flex-wrap gap-1.5">
          <SeverityBadge v-if="selectedNode.metadata.severity" :severity="selectedNode.metadata.severity as any" size="sm" />
          <RiskBadge v-if="selectedNode.metadata.risk_priority" :priority="selectedNode.metadata.risk_priority as any" size="sm">
            {{ selectedNode.metadata.risk_score ?? "—" }}
          </RiskBadge>
        </div>
        <div v-else-if="selectedNode.type === 'ASSET'" class="mb-2 flex flex-wrap items-center gap-1.5">
          <CriticalityBadge v-if="selectedNode.metadata.criticality" :criticality="selectedNode.metadata.criticality as any" size="sm" />
          <span v-if="selectedNode.metadata.hostname" class="text-slate-500">{{ selectedNode.metadata.hostname }}</span>
        </div>

        <NuxtLink v-if="selectedDetailLink" :to="selectedDetailLink" class="text-accent-400 hover:underline">Open →</NuxtLink>
      </div>
    </Transition>
  </div>
</template>
