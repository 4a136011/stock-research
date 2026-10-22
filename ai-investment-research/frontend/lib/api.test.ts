import { describe, expect, it, vi } from "vitest";
import { getHealth } from "./api";

const body = {
  status: "ok",
  version: "0.1.0",
  app_env: "test",
  llm_provider: "mock",
  database_configured: false,
  llm_key_configured: false,
};

function asFetch(mock: ReturnType<typeof vi.fn>): typeof fetch {
  return mock as unknown as typeof fetch;
}

describe("getHealth", () => {
  it("returns data when the backend responds 200", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body });
    const result = await getHealth(asFetch(fetchMock));
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.data.llm_provider).toBe("mock");
  });

  it("returns an error state (no data) on HTTP errors", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) });
    const result = await getHealth(asFetch(fetchMock));
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toContain("503");
      expect("data" in result).toBe(false);
    }
  });

  it("returns an error state (no data) when the network fails", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("ECONNREFUSED"));
    const result = await getHealth(asFetch(fetchMock));
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toContain("ECONNREFUSED");
      expect("data" in result).toBe(false);
    }
  });
});
