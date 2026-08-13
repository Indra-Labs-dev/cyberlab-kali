import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.fn();
vi.mock("./useApi", () => ({
  useApi: () => ({ apiFetch: apiFetchMock }),
}));

const { useProjects } = await import("./useProjects");

describe("useProjects", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue([]);
  });

  it("listProjects() calls GET /api/projects", async () => {
    await useProjects().listProjects();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/projects");
  });

  it("listProjects() returns the fetched list", async () => {
    apiFetchMock.mockResolvedValue([{ id: "p1", name: "Phase 16 E2E" }]);
    const result = await useProjects().listProjects();
    expect(result).toEqual([{ id: "p1", name: "Phase 16 E2E" }]);
  });
});
