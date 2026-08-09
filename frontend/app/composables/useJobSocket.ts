export interface JobUpdate {
  id: string;
  status: string;
  exit_code?: number | null;
  result?: unknown;
  error?: string | null;
}

export function useJobSocket(jobId: string, onUpdate: (update: JobUpdate) => void) {
  const { wsUrl } = useApi();
  let socket: WebSocket | null = null;

  function connect() {
    socket = new WebSocket(wsUrl(`/api/ws/jobs/${jobId}`));
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as JobUpdate;
        onUpdate(data);
      } catch {
        // ignore malformed frames
      }
    };
  }

  function disconnect() {
    socket?.close();
    socket = null;
  }

  onMounted(connect);
  onUnmounted(disconnect);

  return { disconnect };
}
