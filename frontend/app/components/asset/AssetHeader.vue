<script setup lang="ts">
// Header/metadata section of the Asset detail page (18d.1). `asset` is the
// parent's single source of truth -- this component never mutates it
// itself, it only emits intent (update-authorization/update-criticality/
// remove-tag) and lets the parent perform the PATCH and reassign `asset`.
//
// `addTag` is passed as an async function prop (not just an event) because
// the original behavior only clears the input on a *successful* save (a
// failed PATCH keeps the typed text so the user can retry) -- that needs a
// result back from the parent's API call, which a fire-and-forget event
// can't give without duplicating `asset.tags` locally to detect success.
import { ref } from "vue";
import type { Asset } from "~/types/asset";
import type { Project } from "~/types/project";
import { formatDate } from "~/utils/datetime";

const props = defineProps<{
  asset: Asset;
  project: Project | null;
  assetId: string;
  savingAuth: boolean;
  savingCriticality: boolean;
  savingTags: boolean;
  addTag: (tag: string) => Promise<boolean>;
}>();

const emit = defineEmits<{
  "update-authorization": [status: string];
  "update-criticality": [criticality: string];
  "remove-tag": [tag: string];
}>();

const AUTH_STATUSES = ["LAB", "AUTHORIZED", "LOCAL", "UNKNOWN"] as const;
const CRITICALITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;

const newTag = ref("");

async function submitTag() {
  const tag = newTag.value.trim();
  if (!tag || props.asset.tags.includes(tag)) {
    newTag.value = "";
    return;
  }
  const ok = await props.addTag(tag);
  if (ok) newTag.value = "";
}
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center gap-3">
      <AuthorizationBadge :status="asset.authorization_status" />
      <CriticalityBadge :criticality="asset.criticality" />
      <span class="text-xs text-slate-500">{{ asset.type }}</span>
      <NuxtLink v-if="project" :to="`/projects/${project.id}`" class="text-xs text-emerald-400 hover:underline">
        {{ project.name }}
      </NuxtLink>
      <NuxtLink :to="`/ai?target_id=${assetId}`" class="ml-auto text-xs text-emerald-400 hover:underline">
        Ask AI about this asset
      </NuxtLink>
      <slot name="actions" />
    </div>

    <div
      v-if="asset.authorization_status === 'UNKNOWN'"
      class="mt-4 rounded-lg border border-amber-900 bg-amber-950/20 p-3 text-sm text-amber-400"
    >
      This asset's authorization status is UNKNOWN — jobs will be rejected until you mark it LAB, AUTHORIZED, or LOCAL.
    </div>

    <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <p class="mb-2 text-xs font-medium text-slate-500">Authorization status</p>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="status in AUTH_STATUSES"
            :key="status"
            class="rounded-md border px-3 py-1 text-xs disabled:opacity-50"
            :class="
              asset.authorization_status === status
                ? 'border-emerald-600 bg-emerald-500/10 text-emerald-400'
                : 'border-slate-700 text-slate-400 hover:bg-slate-800'
            "
            :disabled="savingAuth"
            @click="emit('update-authorization', status)"
          >
            {{ status }}
          </button>
        </div>
        <p v-if="asset.description" class="mt-3 text-sm text-slate-400">{{ asset.description }}</p>
      </div>

      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <p class="mb-2 text-xs font-medium text-slate-500">Criticality</p>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="c in CRITICALITIES"
            :key="c"
            class="rounded-md border px-3 py-1 text-xs disabled:opacity-50"
            :class="
              asset.criticality === c
                ? 'border-emerald-600 bg-emerald-500/10 text-emerald-400'
                : 'border-slate-700 text-slate-400 hover:bg-slate-800'
            "
            :disabled="savingCriticality"
            @click="emit('update-criticality', c)"
          >
            {{ c }}
          </button>
        </div>
        <p class="mt-3 text-xs text-slate-500">Manually assigned — used by future risk scoring, not auto-computed yet.</p>
      </div>
    </div>

    <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <p class="mb-2 text-xs font-medium text-slate-500">Tags</p>
        <div class="mb-2 flex flex-wrap gap-1.5">
          <span
            v-for="tag in asset.tags"
            :key="tag"
            class="flex items-center gap-1 rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300"
          >
            {{ tag }}
            <button
              class="text-slate-500 hover:text-red-400"
              :disabled="savingTags"
              :aria-label="`Remove tag ${tag}`"
              @click="emit('remove-tag', tag)"
            >
              ×
            </button>
          </span>
          <span v-if="asset.tags.length === 0" class="text-xs text-slate-600">No tags yet</span>
        </div>
        <div class="flex gap-1.5">
          <label for="asset-new-tag" class="sr-only">Add a tag</label>
          <input
            id="asset-new-tag"
            v-model="newTag"
            type="text"
            placeholder="add tag…"
            class="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200"
            @keyup.enter="submitTag"
          />
          <button class="rounded-md bg-slate-800 px-2 py-1 text-xs text-slate-300 hover:bg-slate-700" :disabled="savingTags" @click="submitTag">
            Add
          </button>
        </div>
      </div>

      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <p class="mb-2 text-xs font-medium text-slate-500">Technologies</p>
        <div class="flex flex-wrap gap-1.5">
          <span v-for="tech in asset.technologies" :key="tech" class="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
            {{ tech }}
          </span>
          <span v-if="asset.technologies.length === 0" class="text-xs text-slate-600">
            None detected yet — populated automatically from whatweb scans.
          </span>
        </div>
      </div>

      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <p class="mb-2 text-xs font-medium text-slate-500">Activity</p>
        <p class="text-xs text-slate-400">First seen: <span class="text-slate-300">{{ formatDate(asset.first_seen) }}</span></p>
        <p class="mt-1 text-xs text-slate-400">Last seen: <span class="text-slate-300">{{ formatDate(asset.last_seen) }}</span></p>
        <p class="mt-2 text-xs text-slate-600">Derived from real job activity, not editable.</p>
      </div>
    </div>
  </div>
</template>
