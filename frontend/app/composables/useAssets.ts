import type { Asset } from "~/types/asset";
import { useApi } from "./useApi";

// Thin wrapper around apiFetch -- encapsulates the endpoint path and the
// shared Asset type so callers don't redeclare either. No cache: nothing
// in 18a's scope needs one, and adding one speculatively would be exactly
// the kind of complexity this step is meant to avoid.
//
// useApi is imported explicitly here (Nuxt also auto-imports it, both work
// together) so this composable stays a plain, mockable ES module for
// tests/composables/useAssets.test.ts -- without it, Nuxt's auto-import
// macro would be the only thing resolving `useApi`, which only exists
// inside a running Nuxt build, not in a plain Vitest run.
export function useAssets() {
  const { apiFetch } = useApi();

  function listAssets(params?: Record<string, string>) {
    const query = params && Object.keys(params).length ? `?${new URLSearchParams(params).toString()}` : "";
    return apiFetch<Asset[]>(`/api/assets${query}`);
  }

  function getAsset(id: string) {
    return apiFetch<Asset>(`/api/assets/${id}`);
  }

  return { listAssets, getAsset };
}
