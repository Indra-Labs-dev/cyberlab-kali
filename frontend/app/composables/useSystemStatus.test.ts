import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.fn();
vi.mock("./useApi", () => ({
  useApi: () => ({ apiFetch: apiFetchMock }),
}));

const { useSystemStatus } = await import("./useSystemStatus");

describe("useSystemStatus", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it("marks every check ok when all four endpoints succeed", async () => {
    apiFetchMock.mockResolvedValue({ status: "ok" });
    const { status, refresh } = useSystemStatus();
    await refresh();
    expect(status.api).toBe("ok");
    expect(status.db).toBe("ok");
    expect(status.kali).toBe("ok");
    expect(status.ai).toBe("ok");
  });

  it("marks api/db as error and kali/ai as unreachable independently on failure", async () => {
    apiFetchMock.mockRejectedValue(new Error("network error"));
    const { status, refresh } = useSystemStatus();
    await refresh();
    expect(status.api).toBe("error");
    expect(status.db).toBe("error");
    expect(status.kali).toBe("unreachable");
    expect(status.ai).toBe("unreachable");
  });

  it("captures the kali tools_available and ollama models detail strings", async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === "/api/health/kali") return Promise.resolve({ status: "ok", tools_available: ["nmap", "gobuster"] });
      if (path === "/api/health/ollama") return Promise.resolve({ status: "ok", models: ["llama3"] });
      return Promise.resolve({ status: "ok" });
    });
    const { status, refresh } = useSystemStatus();
    await refresh();
    expect(status.kaliDetail).toBe("nmap, gobuster");
    expect(status.aiDetail).toBe("llama3");
  });

  it("calls all four health endpoints", async () => {
    apiFetchMock.mockResolvedValue({ status: "ok" });
    const { refresh } = useSystemStatus();
    await refresh();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/health");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/health/db");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/health/kali");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/health/ollama");
  });
});
