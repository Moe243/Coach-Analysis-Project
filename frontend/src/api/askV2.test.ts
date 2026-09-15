import { askV2Response } from "../test/askV2Fixtures";
import { API_BASE_URL, ApiError } from "./client";
import { askQuestionV2, type AskV2Request } from "./askV2";

const request: AskV2Request = {
  question: "How did Josh Allen perform in 2022?",
  context: {
    turns: [{ role: "user", content: "How did he perform in 2021?" }],
    entities: [{ kind: "qb", id: "00-0034857" }],
  },
};

describe("Ask v2 API", () => {
  it("posts the exact typed contract to the additive endpoint", async () => {
    const payload = askV2Response();
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const controller = new AbortController();
    await expect(askQuestionV2(request, controller.signal)).resolves.toEqual(
      payload,
    );
    expect(fetch).toHaveBeenCalledWith(`${API_BASE_URL}/ask/v2`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
      signal: controller.signal,
    });
  });

  it("preserves explicit backend validation errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail: "Question is outside the supported contract.",
        }),
        {
          status: 422,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    await expect(askQuestionV2(request)).rejects.toEqual(
      new ApiError("Question is outside the supported contract.", 422),
    );
  });
});
