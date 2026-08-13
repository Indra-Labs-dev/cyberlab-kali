// Pure, testable extraction of the sidebar's active-route logic (18b) --
// section-aware rather than a bare string match: /assets/123 belongs to
// the Assets item, /findings/123 to Findings, etc. "/" is a special case
// (every path starts with "/", so it needs exact match only, or every nav
// item would render as active).
export function isNavItemActive(currentPath: string, itemPath: string): boolean {
  if (itemPath === "/") return currentPath === "/";
  return currentPath === itemPath || currentPath.startsWith(`${itemPath}/`);
}
