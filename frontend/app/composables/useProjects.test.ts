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

  it("updateProject() PATCHes the given fields", async () => {
    await useProjects().updateProject("p1", { notes: "Kickoff notes" });
    expect(apiFetchMock).toHaveBeenCalledWith("/api/projects/p1", {
      method: "PATCH",
      body: { notes: "Kickoff notes" },
    });
  });

  it("updateProject() returns the updated project", async () => {
    apiFetchMock.mockResolvedValue({ id: "p1", name: "Phase 22", notes: "updated" });
    const result = await useProjects().updateProject("p1", { notes: "updated" });
    expect(result).toEqual({ id: "p1", name: "Phase 22", notes: "updated" });
  });
});
