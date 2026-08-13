import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.fn();
vi.mock("./useApi", () => ({
  useApi: () => ({ apiFetch: apiFetchMock }),
}));

const { useProjectMemory } = await import("./useProjectMemory");

describe("useProjectMemory", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue({});
  });

  it("getProjectSummary(id) calls GET /api/ai/projects/{id}/summary", async () => {
    await useProjectMemory().getProjectSummary("p1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/ai/projects/p1/summary");
  });

  it("regenerateProjectSummary(id) POSTs to the regenerate endpoint", async () => {
    await useProjectMemory().regenerateProjectSummary("p1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/ai/projects/p1/summary/regenerate", { method: "POST" });
  });
});
