import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.fn();
vi.mock("./useApi", () => ({
  useApi: () => ({ apiFetch: apiFetchMock }),
}));

// Imported after the mock so useAssets picks up the mocked useApi.
const { useAssets } = await import("./useAssets");

describe("useAssets", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue([]);
  });

  it("listAssets() with no params calls GET /api/assets", async () => {
    await useAssets().listAssets();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/assets");
  });

  it("listAssets(params) appends them as a query string", async () => {
    await useAssets().listAssets({ project_id: "p1", criticality: "HIGH" });
    expect(apiFetchMock).toHaveBeenCalledWith("/api/assets?project_id=p1&criticality=HIGH");
  });

  it("getAsset(id) calls GET /api/assets/{id}", async () => {
    await useAssets().getAsset("a1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/assets/a1");
  });
});
