// Shared by AssetHeader, AssetContinuousRecon, and AssetChangeTimeline (18d)
// -- moved here instead of duplicated three times. Pure, no API calls.
export function formatDate(iso: string | null): string {
  if (!iso) return "never";
  return new Date(iso).toLocaleString();
}

export function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
