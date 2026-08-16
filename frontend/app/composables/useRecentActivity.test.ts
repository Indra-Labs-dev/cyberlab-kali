import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.fn();
vi.mock("./useApi", () => ({
  useApi: () => ({ apiFetch: apiFetchMock }),
}));

const { useRecentActivity } = await import("./useRecentActivity");

describe("useRecentActivity", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it("fetches jobs, findings, and asset-changes and merges them", async () => {
    apiFetchMock.mockResolvedValue([]);
    const { items, load } = useRecentActivity();
    await load();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/jobs?limit=6");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/findings?limit=6");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/asset-changes?limit=6");
    expect(items.value).toEqual([]);
  });

  it("does not refetch on a second load() unless forced", async () => {
    apiFetchMock.mockResolvedValue([]);
    const { load } = useRecentActivity();
    await load();
    await load();
    expect(apiFetchMock).toHaveBeenCalledTimes(3);
    await load(true);
    expect(apiFetchMock).toHaveBeenCalledTimes(6);
  });

  it("sets an error message on failure", async () => {
    apiFetchMock.mockRejectedValue({ data: { detail: "boom" } });
    const { error, load } = useRecentActivity();
    await load();
    expect(error.value).toBe("boom");
  });
});
