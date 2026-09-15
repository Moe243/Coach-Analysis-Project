import { useCallback, useEffect, useRef, useState } from "react";
import {
  askQuestionV2,
  type AskV2CanonicalEntity,
  type AskV2Request,
  type AskV2ResolvedEntity,
  type AskV2Response,
} from "../api/askV2";
import { ApiError, isRetryableApiError } from "../api/client";
import {
  buildBoundedAskV2Context,
  clarificationQuestion,
  type ContextSourceTurn,
} from "../lib/askV2";

export type AskV2TurnStatus = "pending" | "success" | "error" | "cancelled";

export interface AskV2ConversationTurn {
  id: number;
  question: string;
  request: AskV2Request;
  status: AskV2TurnStatus;
  response?: AskV2Response;
  error?: string;
  contextTrimmed: boolean;
  retryAttempt: number;
}

type AskV2Client = (
  request: AskV2Request,
  signal?: AbortSignal,
) => Promise<AskV2Response>;

interface SubmitOptions {
  visibleQuestion?: string;
  canonicalEntity?: AskV2CanonicalEntity;
}

interface UseAskV2ConversationOptions {
  client?: AskV2Client;
  retryDelayMilliseconds?: number;
  automaticRetryLimit?: number;
}

function publicError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof TypeError)
    return "The analytics API could not be reached.";
  return "The analytics request could not be completed.";
}

function pause(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, milliseconds);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(new DOMException("Request cancelled", "AbortError"));
      },
      { once: true },
    );
  });
}

export function useAskV2Conversation({
  client = askQuestionV2,
  retryDelayMilliseconds = 900,
  automaticRetryLimit = 2,
}: UseAskV2ConversationOptions = {}) {
  const [turns, setTurns] = useState<AskV2ConversationTurn[]>([]);
  const turnsRef = useRef(turns);
  const nextId = useRef(1);
  const active = useRef<{ id: number; controller: AbortController } | null>(
    null,
  );

  useEffect(() => {
    turnsRef.current = turns;
  }, [turns]);

  const updateTurn = useCallback(
    (
      id: number,
      update: (turn: AskV2ConversationTurn) => AskV2ConversationTurn,
    ) => {
      setTurns((current) => {
        const next = current.map((turn) =>
          turn.id === id ? update(turn) : turn,
        );
        turnsRef.current = next;
        return next;
      });
    },
    [],
  );

  const execute = useCallback(
    async (id: number, request: AskV2Request) => {
      active.current?.controller.abort();
      const controller = new AbortController();
      active.current = { id, controller };
      for (let attempt = 0; attempt <= automaticRetryLimit; attempt += 1) {
        updateTurn(id, (turn) => ({
          ...turn,
          status: "pending",
          error: undefined,
          retryAttempt: attempt,
        }));
        try {
          const response = await client(request, controller.signal);
          if (active.current?.id !== id || controller.signal.aborted) return;
          updateTurn(id, (turn) => ({ ...turn, status: "success", response }));
          active.current = null;
          return;
        } catch (error) {
          if (controller.signal.aborted || active.current?.id !== id) return;
          if (attempt < automaticRetryLimit && isRetryableApiError(error)) {
            try {
              await pause(
                retryDelayMilliseconds * (attempt + 1),
                controller.signal,
              );
              continue;
            } catch {
              return;
            }
          }
          updateTurn(id, (turn) => ({
            ...turn,
            status: "error",
            error: publicError(error),
          }));
          active.current = null;
          return;
        }
      }
    },
    [automaticRetryLimit, client, retryDelayMilliseconds, updateTurn],
  );

  const submit = useCallback(
    (question: string, options: SubmitOptions = {}) => {
      const normalized = question.trim();
      if (normalized.length < 3 || normalized.length > 1_000) return;
      if (active.current) {
        const superseded = active.current.id;
        const pending = turnsRef.current.find((turn) => turn.id === superseded);
        if (pending?.request.question === normalized) return;
        active.current.controller.abort();
        turnsRef.current = turnsRef.current.map((turn) =>
          turn.id === superseded ? { ...turn, status: "cancelled" } : turn,
        );
        setTurns(turnsRef.current);
      }
      const history: ContextSourceTurn[] = turnsRef.current
        .filter((turn) => turn.status === "success")
        .map((turn) => ({
          question: turn.request.question,
          response: turn.response,
        }));
      const bounded = buildBoundedAskV2Context(
        history,
        options.canonicalEntity,
      );
      const request: AskV2Request = {
        question: normalized,
        context: bounded.context,
      };
      const id = nextId.current;
      nextId.current += 1;
      const turn: AskV2ConversationTurn = {
        id,
        question: options.visibleQuestion ?? normalized,
        request,
        status: "pending",
        contextTrimmed: bounded.trimmed,
        retryAttempt: 0,
      };
      turnsRef.current = [...turnsRef.current, turn];
      setTurns(turnsRef.current);
      void execute(id, request);
    },
    [execute],
  );

  const retry = useCallback(
    (id: number) => {
      if (active.current) return;
      const turn = turnsRef.current.find((candidate) => candidate.id === id);
      if (!turn) return;
      void execute(id, turn.request);
    },
    [execute],
  );

  const clarify = useCallback(
    (turn: AskV2ConversationTurn, entity: AskV2ResolvedEntity) => {
      submit(clarificationQuestion(turn.request.question, entity), {
        visibleQuestion: entity.display_name,
        canonicalEntity: entity,
      });
    },
    [submit],
  );

  const reset = useCallback(() => {
    active.current?.controller.abort();
    active.current = null;
    turnsRef.current = [];
    setTurns([]);
  }, []);

  useEffect(() => () => active.current?.controller.abort(), []);

  return {
    turns,
    isPending: turns.some((turn) => turn.status === "pending"),
    submit,
    retry,
    clarify,
    reset,
  };
}
