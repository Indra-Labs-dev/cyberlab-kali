// Mirrors backend/app/schemas/asset.py::AssetResponse and
// backend/app/models/asset.py's enums. `description` included even though
// not every consuming page reads it -- this is what the API actually
// returns for every Asset, not a per-page projection.
export type AssetType = "HOST" | "IP" | "DOMAIN" | "SUBDOMAIN" | "URL" | "SERVICE" | "CONTAINER" | "LAB" | "LAB_RESOURCE" | "OTHER";
export type AssetCriticality = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type AuthorizationStatus = "LAB" | "AUTHORIZED" | "LOCAL" | "UNKNOWN";

export interface Asset {
  id: string;
  project_id: string;
  name: string;
  hostname: string | null;
  ip_address: string | null;
  url: string | null;
  type: AssetType;
  criticality: AssetCriticality;
  authorization_status: AuthorizationStatus;
  tags: string[];
  technologies: string[];
  description: string | null;
  first_seen: string | null;
  last_seen: string | null;
  created_at: string;
}
