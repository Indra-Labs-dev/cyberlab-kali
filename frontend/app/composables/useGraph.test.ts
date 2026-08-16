import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.fn();
vi.mock("./useApi", () => ({
  useApi: () => ({ apiFetch: apiFetchMock }),
}));

const { useGraph } = await import("./useGraph");

describe("useGraph", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it("searchNodes('ASSET', q) calls GET /api/assets?search= and maps to {id, type, label}", async () => {
    apiFetchMock.mockResolvedValue([{ id: "a1", name: "DVWA E2E" }]);
    const results = await useGraph().searchNodes("ASSET", "dvwa");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/assets?search=dvwa");
    expect(results).toEqual([{ id: "a1", type: "ASSET", label: "DVWA E2E" }]);
  });

  it("searchNodes('FINDING', q) filters client-side by title (GET /api/findings has no search param)", async () => {
    apiFetchMock.mockResolvedValue([
      { id: "f1", title: "Technology detected: Apache" },
      { id: "f2", title: "SQL injection" },
    ]);
    const results = await useGraph().searchNodes("FINDING", "apache");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/findings?limit=500");
    expect(results).toEqual([{ id: "f1", type: "FINDING", label: "Technology detected: Apache" }]);
  });

  it("searchNodes('CVE', q) returns the typed identifier itself (no list endpoint exists for virtual node types)", async () => {
    const results = await useGraph().searchNodes("CVE", "CVE-2021-44228");
    expect(apiFetchMock).not.toHaveBeenCalled();
    expect(results).toEqual([{ id: "CVE-2021-44228", type: "CVE", label: "CVE-2021-44228" }]);
  });

  it("searchNodes returns [] for an empty query without calling the API", async () => {
    const results = await useGraph().searchNodes("ASSET", "   ");
    expect(apiFetchMock).not.toHaveBeenCalled();
    expect(results).toEqual([]);
  });

  it("loadNode(type, id, depth) calls GET /api/graph/nodes/{type}/{id}?depth=", async () => {
    apiFetchMock.mockResolvedValue({ nodes: [], edges: [] });
    await useGraph().loadNode("ASSET", "a1", 2);
    expect(apiFetchMock).toHaveBeenCalledWith("/api/graph/nodes/ASSET/a1?depth=2");
  });

  it("loadAttackPathsToCriticalAssets(type, id, maxHops) calls GET /api/graph/attack-paths/critical/{type}/{id}?max_hops=", async () => {
    apiFetchMock.mockResolvedValue({ disclaimer: "x", seed: {}, truncated: false, paths: [] });
    await useGraph().loadAttackPathsToCriticalAssets("ASSET", "a1", 3);
    expect(apiFetchMock).toHaveBeenCalledWith("/api/graph/attack-paths/critical/ASSET/a1?max_hops=3");
  });

  it("loadAttackPathsToCriticalAssets defaults max_hops to 4", async () => {
    apiFetchMock.mockResolvedValue({ disclaimer: "x", seed: {}, truncated: false, paths: [] });
    await useGraph().loadAttackPathsToCriticalAssets("ASSET", "a1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/graph/attack-paths/critical/ASSET/a1?max_hops=4");
  });

  it("loadAttackPathsBetween(fromType, fromId, toType, toId, maxHops) calls GET /api/graph/attack-paths/between/{...}", async () => {
    apiFetchMock.mockResolvedValue({ disclaimer: "x", seed: {}, truncated: false, paths: [] });
    await useGraph().loadAttackPathsBetween("ASSET", "a1", "FINDING", "f1", 2);
    expect(apiFetchMock).toHaveBeenCalledWith("/api/graph/attack-paths/between/ASSET/a1/FINDING/f1?max_hops=2");
  });

  it("loadAttackPathsBetween URL-encodes node ids that contain special characters", async () => {
    apiFetchMock.mockResolvedValue({ disclaimer: "x", seed: {}, truncated: false, paths: [] });
    await useGraph().loadAttackPathsBetween("SERVICE", "80/tcp", "TECHNOLOGY", "Apache", 4);
    expect(apiFetchMock).toHaveBeenCalledWith("/api/graph/attack-paths/between/SERVICE/80%2Ftcp/TECHNOLOGY/Apache?max_hops=4");
  });
});
