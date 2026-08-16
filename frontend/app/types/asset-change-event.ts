// Mirrors backend/app/schemas/asset_change_event.py::AssetChangeEventResponse
// field-for-field. Previously only declared inline inside
// AssetChangeTimeline.vue (single-asset view); factored out here so the
// SOC-lite global "Recent Changes" dashboard section can share the exact
// same shape without redeclaring it.
export type ChangeType =
  | "PORT_OPENED"
  | "PORT_CLOSED"
  | "SERVICE_CHANGED"
  | "TECHNOLOGY_ADDED"
  | "TECHNOLOGY_REMOVED"
  | "TECHNOLOGY_CHANGED"
  | "CERTIFICATE_CHANGED"
  | "HTTP_CHANGED"
  | "OTHER";

export interface AssetChangeEvent {
  id: string;
  asset_id: string;
  job_id: string;
  previous_job_id: string | null;
  change_type: ChangeType;
  severity: "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  field: string;
  old_value: string | null;
  new_value: string | null;
  change_metadata: Record<string, unknown>;
  detected_at: string;
}
