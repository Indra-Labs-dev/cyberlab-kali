import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.fn();
vi.mock("./useApi", () => ({
  useApi: () => ({ apiFetch: apiFetchMock }),
}));

const { useGlobalSearch } = await import("./useGlobalSearch");

describe("useGlobalSearch", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it("does not search for a query shorter than 2 characters", async () => {
    const { results, search } = useGlobalSearch();
    await search("a");
    expect(results.value).toEqual([]);
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("searches assets server-side via the real search param", async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path.startsWith("/api/assets?search=")) return Promise.resolve([{ id: "a1", name: "web-01", hostname: "web-01.local", type: "HOST" }]);
      return Promise.resolve([]);
    });
    const { results, search } = useGlobalSearch();
    await search("web");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/assets?search=web&limit=5");
    expect(results.value).toContainEqual(expect.objectContaining({ type: "asset", label: "web-01" }));
  });

  it("filters cached findings/projects/tools client-side by title/name", async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === "/api/projects") return Promise.resolve([{ id: "p1", name: "Acme Pentest" }, { id: "p2", name: "Other" }]);
      if (path === "/api/tools") return Promise.resolve([{ name: "acme-scanner", category: "recon" }]);
      if (path.startsWith("/api/findings")) return Promise.resolve([{ id: "f1", title: "Acme SQLi", severity: "HIGH" }]);
      return Promise.resolve([]);
    });
    const { results, search } = useGlobalSearch();
    await search("acme");
    const types = results.value.map((r) => r.type);
    expect(types).toEqual(expect.arrayContaining(["finding", "project", "tool"]));
    expect(results.value.find((r) => r.type === "project")?.label).toBe("Acme Pentest");
  });

  it("clear() empties the results", async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path.startsWith("/api/assets?search=")) return Promise.resolve([{ id: "a1", name: "web-01", type: "HOST" }]);
      return Promise.resolve([]);
    });
    const { results, search, clear } = useGlobalSearch();
    await search("web");
    clear();
    expect(results.value).toEqual([]);
  });
});
