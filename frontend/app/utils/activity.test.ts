import { describe, expect, it } from "vitest";
import { mergeActivity } from "./activity";

describe("mergeActivity", () => {
  it("interleaves jobs, findings, and changes sorted by time descending", () => {
    const result = mergeActivity(
      [{ id: "j1", tool: "nmap", target: "10.0.0.1", status: "SUCCESS", created_at: "2026-01-01T10:00:00Z" }],
      [{ id: "f1", title: "Outdated Apache", target: "10.0.0.2", severity: "HIGH", first_seen: "2026-01-01T12:00:00Z" }],
      [{ id: "c1", job_id: "j2", change_type: "PORT_OPENED", field: "port:443/tcp", severity: "HIGH", detected_at: "2026-01-01T08:00:00Z" }],
    );
    expect(result.map((i) => i.id)).toEqual(["finding-f1", "job-j1", "change-c1"]);
  });

  it("maps job status and finding/change severity to a tone", () => {
    const result = mergeActivity(
      [{ id: "j1", tool: "nmap", target: "t", status: "FAILED", created_at: "2026-01-01T00:00:00Z" }],
      [{ id: "f1", title: "x", target: "t", severity: "CRITICAL", first_seen: "2026-01-01T00:00:00Z" }],
      [],
    );
    expect(result.find((i) => i.id === "job-j1")?.tone).toBe("danger");
    expect(result.find((i) => i.id === "finding-f1")?.tone).toBe("danger");
  });

  it("formats a change's summary the same way as RecentChangesWidget", () => {
    const result = mergeActivity(
      [],
      [],
      [{ id: "c1", job_id: "j1", change_type: "PORT_OPENED", field: "port:443/tcp", severity: "HIGH", detected_at: "2026-01-01T00:00:00Z" }],
    );
    expect(result[0]!.label).toBe("Port 443/tcp opened");
  });

  it("caps the merged list at the given limit", () => {
    const jobs = Array.from({ length: 20 }, (_, i) => ({
      id: `j${i}`,
      tool: "nmap",
      target: "t",
      status: "SUCCESS",
      created_at: `2026-01-01T${String(i).padStart(2, "0")}:00:00Z`,
    }));
    expect(mergeActivity(jobs, [], [], 5)).toHaveLength(5);
  });
});
