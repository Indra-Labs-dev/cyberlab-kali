import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.fn();
vi.mock("./useApi", () => ({
  useApi: () => ({ apiFetch: apiFetchMock }),
}));

const { useMissions } = await import("./useMissions");

describe("useMissions", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue([]);
  });

  it("listMissions() with no target calls GET /api/ai/missions", async () => {
    await useMissions().listMissions();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/ai/missions");
  });

  it("listMissions(targetId) appends the query string", async () => {
    await useMissions().listMissions("t1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/ai/missions?target_id=t1");
  });

  it("getMission(id) calls GET /api/ai/missions/{id}", async () => {
    await useMissions().getMission("m1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/ai/missions/m1");
  });

  it("createMission() POSTs target_id/goal/max_steps", async () => {
    await useMissions().createMission("t1", "recon the box", 5);
    expect(apiFetchMock).toHaveBeenCalledWith("/api/ai/missions", {
      method: "POST",
      body: { target_id: "t1", goal: "recon the box", max_steps: 5 },
    });
  });

  it("approveMission(id) POSTs to the approve endpoint", async () => {
    await useMissions().approveMission("m1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/ai/missions/m1/approve", { method: "POST" });
  });

  it("cancelMission(id) POSTs to the cancel endpoint", async () => {
    await useMissions().cancelMission("m1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/ai/missions/m1/cancel", { method: "POST" });
  });

  it("generateCorrelationSuggestions(targetId) POSTs target_id", async () => {
    await useMissions().generateCorrelationSuggestions("t1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/ai/correlation-suggestions", {
      method: "POST",
      body: { target_id: "t1" },
    });
  });

  it("listCorrelationSuggestions(targetId) calls GET with the query string", async () => {
    await useMissions().listCorrelationSuggestions("t1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/ai/correlation-suggestions?target_id=t1");
  });

  it("acceptCorrelationSuggestion(id) POSTs to the accept endpoint", async () => {
    await useMissions().acceptCorrelationSuggestion("s1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/ai/correlation-suggestions/s1/accept", { method: "POST" });
  });

  it("dismissCorrelationSuggestion(id) POSTs to the dismiss endpoint", async () => {
    await useMissions().dismissCorrelationSuggestion("s1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/ai/correlation-suggestions/s1/dismiss", { method: "POST" });
  });

  it("proposeReport(projectId) POSTs project_id", async () => {
    await useMissions().proposeReport("p1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/ai/reports/propose", {
      method: "POST",
      body: { project_id: "p1" },
    });
  });
});
