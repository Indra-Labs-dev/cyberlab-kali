<script setup lang="ts">
import "@xterm/xterm/css/xterm.css";
import type { Terminal as XTerm } from "@xterm/xterm";
import type { FitAddon as XFitAddon } from "@xterm/addon-fit";

definePageMeta({ ssr: false });

const { wsUrl } = useApi();
const container = ref<HTMLDivElement | null>(null);
const connected = ref(false);

let term: XTerm | null = null;
let fitAddon: XFitAddon | null = null;
let socket: WebSocket | null = null;
let resizeObserver: ResizeObserver | null = null;

function sendResize() {
  if (!term || !socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "resize", rows: term.rows, cols: term.cols }));
}

onMounted(async () => {
  if (!container.value) return;

  const { Terminal } = await import("@xterm/xterm");
  const { FitAddon } = await import("@xterm/addon-fit");

  term = new Terminal({
    theme: { background: "#020617", foreground: "#e2e8f0", cursor: "#34d399" },
    fontSize: 13,
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
    cursorBlink: true,
  });
  fitAddon = new FitAddon();
  term.loadAddon(fitAddon);
  term.open(container.value);
  fitAddon.fit();

  term.onData((data) => {
    socket?.send(JSON.stringify({ type: "stdin", data }));
  });

  socket = new WebSocket(wsUrl("/api/ws/terminal"));
  socket.onopen = () => {
    connected.value = true;
    sendResize();
  };
  socket.onclose = () => {
    connected.value = false;
    term?.writeln("\r\n\x1b[31m[connection closed]\x1b[0m");
  };
  socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "stdout") term?.write(msg.data);
    } catch {
      // ignore malformed frames
    }
  };

  resizeObserver = new ResizeObserver(() => {
    fitAddon?.fit();
    sendResize();
  });
  resizeObserver.observe(container.value);
});

onUnmounted(() => {
  resizeObserver?.disconnect();
  socket?.close();
  term?.dispose();
});
</script>

<template>
  <div class="flex h-screen flex-col">
    <PageHeader title="Terminal" subtitle="Interactive shell inside the isolated cyberlab-kali container" />
    <div class="flex items-center gap-2 px-8 pt-3 text-xs">
      <span class="h-1.5 w-1.5 rounded-full" :class="connected ? 'bg-emerald-500' : 'bg-red-500'"></span>
      <span class="text-slate-500">{{ connected ? "connected" : "disconnected" }}</span>
    </div>
    <div class="min-h-0 flex-1 px-8 py-4">
      <div ref="container" class="h-full rounded-lg border border-slate-800 bg-[#020617] p-2"></div>
    </div>
  </div>
</template>
