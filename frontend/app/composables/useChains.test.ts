import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.fn();
vi.mock("./useApi", () => ({
  useApi: () => ({ apiFetch: apiFetchMock }),
}));

const { useChains } = await import("./useChains");

describe("useChains", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue([]);
  });

  it("listTemplates() calls GET /api/chains/templates", async () => {
    await useChains().listTemplates();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/chains/templates");
  });

  it("getTemplate(id) calls GET /api/chains/templates/{id}", async () => {
    await useChains().getTemplate("t1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/chains/templates/t1");
  });

  it("createTemplate() POSTs name/description/steps", async () => {
    const steps = [{ tool: "nmap", profile: "quick_scan" }];
    await useChains().createTemplate("My Chain", "desc", steps);
    expect(apiFetchMock).toHaveBeenCalledWith("/api/chains/templates", {
      method: "POST",
      body: { name: "My Chain", description: "desc", steps },
    });
  });

  it("createTemplate() sends null description when empty", async () => {
    await useChains().createTemplate("My Chain", "", []);
    expect(apiFetchMock).toHaveBeenCalledWith("/api/chains/templates", {
      method: "POST",
      body: { name: "My Chain", description: null, steps: [] },
    });
  });

  it("deleteTemplate(id) calls DELETE /api/chains/templates/{id}", async () => {
    await useChains().deleteTemplate("t1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/chains/templates/t1", { method: "DELETE" });
  });

  it("createRun() POSTs template_id/target_id", async () => {
    await useChains().createRun("t1", "a1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/chains/runs", {
      method: "POST",
      body: { template_id: "t1", target_id: "a1" },
    });
  });

  it("listRuns() with no params calls GET /api/chains/runs", async () => {
    await useChains().listRuns();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/chains/runs");
  });

  it("listRuns(params) appends them as a query string", async () => {
    await useChains().listRuns({ target_id: "a1" });
    expect(apiFetchMock).toHaveBeenCalledWith("/api/chains/runs?target_id=a1");
  });

  it("getRun(id) calls GET /api/chains/runs/{id}", async () => {
    await useChains().getRun("r1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/chains/runs/r1");
  });

  it("cancelRun(id) POSTs to the cancel endpoint", async () => {
    await useChains().cancelRun("r1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/chains/runs/r1/cancel", { method: "POST" });
  });
});
