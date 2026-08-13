// Mirrors backend/app/schemas/intelligence.py::IntelSyncStateResponse.
// `details` is a free-form per-source counter bag (e.g. {"catalog_size":
// 1665}) -- informational only, never a fixed shape across sources.
export interface IntelSyncState {
  source: string;
  last_attempt_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  details: Record<string, unknown>;
}
