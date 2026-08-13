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
});
