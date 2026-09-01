import {
  apiGet,
  apiGetAll,
  ApiError,
  isRetryableApiError,
  queryString,
} from "./client";

describe("API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("serializes defined query values and omits empty values", () => {
    expect(
      queryString({
        season: 2025,
        eligible: false,
        search: "C.J. Stroud",
        empty: "",
        missing: undefined,
      }),
    ).toBe("?season=2025&eligible=false&search=C.J.+Stroud");
  });

  it("returns typed JSON and forwards the abort signal", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    await expect(
      apiGet<{ ok: boolean }>("/health", {}, controller.signal),
    ).resolves.toEqual({ ok: true });
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      signal: controller.signal,
    });
  });

  it("surfaces API detail messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Publication unavailable" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    await expect(apiGet("/versions")).rejects.toEqual(
      new ApiError("Publication unavailable", 503),
    );
  });

  it("loads stable API pages until total is reached", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const offset = Number(
        new URL(String(input), "http://test").searchParams.get("offset"),
      );
      return new Response(
        JSON.stringify({
          items: offset === 0 ? [1, 2] : [3],
          total: 3,
          limit: 2,
          offset,
        }),
        { status: 200 },
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(apiGetAll<number>("/rows", { limit: 2 })).resolves.toEqual([
      1, 2, 3,
    ]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("retries only network and transient cold-start failures", () => {
    expect(isRetryableApiError(new TypeError("fetch failed"))).toBe(true);
    expect(isRetryableApiError(new ApiError("waking", 503))).toBe(true);
    expect(isRetryableApiError(new ApiError("bad gateway", 502))).toBe(true);
    expect(isRetryableApiError(new ApiError("not found", 404))).toBe(false);
    expect(isRetryableApiError(new Error("application failure"))).toBe(false);
  });
});
