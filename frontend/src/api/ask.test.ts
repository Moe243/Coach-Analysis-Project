import { askQuestion } from "./ask";
import { API_BASE_URL } from "./client";

describe("Ask API", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("posts the question to the configured API base", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "NOT_SUPPORTED" }),
    });
    vi.stubGlobal("fetch", fetch);
    expect(await askQuestion("What would a transfer change?")).toEqual({
      status: "NOT_SUPPORTED",
    });
    expect(fetch).toHaveBeenCalledWith(`${API_BASE_URL}/ask`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question: "What would a transfer change?" }),
    });
  });
  it("does not invent a result when unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({ detail: "Snapshot unavailable" }),
      }),
    );
    await expect(askQuestion("Josh Allen projection")).rejects.toThrow(
      "Snapshot unavailable",
    );
  });
});
