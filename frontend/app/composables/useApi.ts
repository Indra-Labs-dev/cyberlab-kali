export function useApi() {
  const config = useRuntimeConfig();
  const apiBase = config.public.apiBase as string;
  const wsBase = config.public.wsBase as string;

  function apiUrl(path: string): string {
    return `${apiBase}${path}`;
  }

  function wsUrl(path: string): string {
    return `${wsBase}${path}`;
  }

  return { apiBase, wsBase, apiUrl, wsUrl };
}
