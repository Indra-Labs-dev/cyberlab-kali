export function useApi() {
  const config = useRuntimeConfig();
  const apiBase = config.public.apiBase as string;
  const wsBase = config.public.wsBase as string;
  const apiToken = config.public.apiToken as string;

  function apiUrl(path: string): string {
    return `${apiBase}${path}`;
  }

  // Browsers can't set custom headers on a WebSocket handshake or a plain
  // <a href> download, so those two paths authenticate via a ?token= query
  // param instead of the Authorization header apiFetch uses.
  function withToken(url: string): string {
    if (!apiToken) return url;
    const separator = url.includes("?") ? "&" : "?";
    return `${url}${separator}token=${encodeURIComponent(apiToken)}`;
  }

  function wsUrl(path: string): string {
    return withToken(`${wsBase}${path}`);
  }

  function downloadUrl(path: string): string {
    return withToken(apiUrl(path));
  }

  function apiFetch<T = unknown>(path: string, options: Record<string, unknown> = {}) {
    const headers: Record<string, string> = { ...(options.headers as Record<string, string> | undefined) };
    if (apiToken) headers.Authorization = `Bearer ${apiToken}`;
    return $fetch<T>(apiUrl(path), { ...options, headers });
  }

  return { apiBase, wsBase, apiUrl, wsUrl, downloadUrl, apiFetch };
}
