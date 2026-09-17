import { act, renderHook, waitFor } from "@testing-library/react";
import type { AskV2Request, AskV2Response } from "../api/askV2";
import { ApiError } from "../api/client";
import { askV2Response } from "../test/askV2Fixtures";
import { useAskV2Conversation } from "./useAskV2Conversation";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((complete) => {
    resolve = complete;
  });
  return { promise, resolve };
}

it("prevents a late superseded response from replacing a newer turn", async () => {
  const first = deferred<AskV2Response>();
  const second = deferred<AskV2Response>();
  const client = vi
    .fn<
      (request: AskV2Request, signal?: AbortSignal) => Promise<AskV2Response>
    >()
    .mockReturnValueOnce(first.promise)
    .mockReturnValueOnce(second.promise);
  const { result } = renderHook(() =>
    useAskV2Conversation({
      client,
      automaticRetryLimit: 0,
      retryDelayMilliseconds: 0,
    }),
  );
  act(() => result.current.submit("Question A about Josh Allen"));
  act(() => result.current.submit("Question B about Josh Allen"));
  await act(async () => second.resolve(askV2Response({ answer: "Answer B" })));
  await waitFor(() =>
    expect(result.current.turns.at(-1)?.response?.answer).toBe("Answer B"),
  );
  await act(async () =>
    first.resolve(askV2Response({ answer: "Late answer A" })),
  );
  expect(result.current.turns[0].status).toBe("cancelled");
  expect(result.current.turns.at(-1)?.response?.answer).toBe("Answer B");
  expect(
    result.current.turns.some(
      (turn) => turn.response?.answer === "Late answer A",
    ),
  ).toBe(false);
});

it("retries transient 503 and network failures within the configured bound", async () => {
  const client = vi
    .fn<
      (request: AskV2Request, signal?: AbortSignal) => Promise<AskV2Response>
    >()
    .mockRejectedValueOnce(new ApiError("API waking", 503))
    .mockRejectedValueOnce(new TypeError("network unavailable"))
    .mockResolvedValueOnce(askV2Response({ answer: "Recovered answer" }));
  const { result } = renderHook(() =>
    useAskV2Conversation({
      client,
      automaticRetryLimit: 2,
      retryDelayMilliseconds: 0,
    }),
  );
  act(() => result.current.submit("How did Josh Allen perform?"));
  await waitFor(() =>
    expect(result.current.turns[0]?.response?.answer).toBe("Recovered answer"),
  );
  expect(client).toHaveBeenCalledTimes(3);
  expect(result.current.turns[0]?.retryAttempt).toBe(2);
});

it("does not expose raw API diagnostics in public errors", async () => {
  const client = vi
    .fn()
    .mockRejectedValue(
      new ApiError(
        "publication_id=private /private/snapshot provider_internal_error",
        500,
      ),
    );
  const { result } = renderHook(() =>
    useAskV2Conversation({ client, automaticRetryLimit: 0 }),
  );
  act(() => result.current.submit("How did Josh Allen perform?"));
  await waitFor(() => expect(result.current.turns[0]?.status).toBe("error"));
  expect(result.current.turns[0].error).toBe(
    "The answer could not be loaded. Please retry this question.",
  );
});

it("aborts and ignores a delayed request when the conversation is reset", async () => {
  const pending = deferred<AskV2Response>();
  const client = vi
    .fn<
      (request: AskV2Request, signal?: AbortSignal) => Promise<AskV2Response>
    >()
    .mockReturnValue(pending.promise);
  const { result } = renderHook(() =>
    useAskV2Conversation({
      client,
      automaticRetryLimit: 0,
      retryDelayMilliseconds: 0,
    }),
  );
  act(() => result.current.submit("How did Josh Allen perform?"));
  const signal = client.mock.calls[0][1];
  act(() => result.current.reset());
  expect(signal?.aborted).toBe(true);
  await act(async () => pending.resolve(askV2Response()));
  expect(result.current.turns).toEqual([]);
});

it("ignores a duplicate submit while the same turn is pending", () => {
  const pending = deferred<AskV2Response>();
  const client = vi
    .fn<
      (request: AskV2Request, signal?: AbortSignal) => Promise<AskV2Response>
    >()
    .mockReturnValue(pending.promise);
  const { result } = renderHook(() =>
    useAskV2Conversation({
      client,
      automaticRetryLimit: 0,
      retryDelayMilliseconds: 0,
    }),
  );
  act(() => {
    result.current.submit("How did Josh Allen perform?");
    result.current.submit("How did Josh Allen perform?");
  });
  expect(client).toHaveBeenCalledTimes(1);
  expect(result.current.turns).toHaveLength(1);
  expect(result.current.turns[0].status).toBe("pending");
});

it("does not let an old retry abort a newer pending turn", async () => {
  const firstFailure = new Error("failed request");
  const newer = deferred<AskV2Response>();
  const client = vi
    .fn<
      (request: AskV2Request, signal?: AbortSignal) => Promise<AskV2Response>
    >()
    .mockRejectedValueOnce(firstFailure)
    .mockReturnValueOnce(newer.promise);
  const { result } = renderHook(() =>
    useAskV2Conversation({
      client,
      automaticRetryLimit: 0,
      retryDelayMilliseconds: 0,
    }),
  );
  act(() => result.current.submit("First Josh Allen question"));
  await waitFor(() => expect(result.current.turns[0].status).toBe("error"));
  act(() => result.current.submit("Second Josh Allen question"));
  const newerSignal = client.mock.calls[1][1];
  act(() => result.current.retry(1));
  expect(client).toHaveBeenCalledTimes(2);
  expect(newerSignal?.aborted).toBe(false);
  await act(async () =>
    newer.resolve(askV2Response({ answer: "Second answer" })),
  );
  await waitFor(() =>
    expect(result.current.turns[1]?.response?.answer).toBe("Second answer"),
  );
});
