import { useEffect, useRef } from "react";
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  MessageCircleQuestion,
  RefreshCw,
} from "lucide-react";
import { Link } from "react-router-dom";
import type { AskV2ResolvedEntity, AskV2Response } from "../../api/askV2";
import type { AskV2ConversationTurn } from "../../hooks/useAskV2Conversation";
import { formatAskV2Value, metricLabel } from "../../lib/askV2";
import {
  buildKeepExploringActions,
  type AskV2ExploreAction,
} from "../../lib/askV2Exploration";

interface AssistantTurnProps {
  turn: AskV2ConversationTurn;
  latest: boolean;
  onClarify: (entity: AskV2ResolvedEntity) => void;
  onFollowUp: (action: AskV2ExploreAction) => void;
  onRetry: () => void;
}

function MetricExplainer({ response }: { response: AskV2Response }) {
  const hasEpa = response.answer.includes("EPA/dropback");
  const hasPae = response.answer.includes("PAE");
  if (!hasEpa && !hasPae) return null;
  return (
    <p className="ask-v2-metric-explainer">
      {hasEpa &&
        "EPA/dropback estimates expected scoring value added per passing dropback."}
      {hasEpa && hasPae && " "}
      {hasPae && "PAE is actual EPA/dropback minus the preseason expectation."}
    </p>
  );
}

function KeyNumbers({ response }: { response: AskV2Response }) {
  const permitted = new Set(
    response.conclusion_permissions
      .filter((permission) => permission.decision !== "DENIED")
      .map((permission) => permission.permission_id),
  );
  const numbers = response.propositions
    .filter(
      (proposition) =>
        proposition.metric &&
        proposition.metric !== "distinct_qb_team_seasons" &&
        proposition.kind !== "PLAYER_SCHEME_DESCRIPTIVE_ALIGNMENT" &&
        proposition.predicate !== "same_metric_descriptive_comparison" &&
        typeof proposition.value === "number" &&
        permitted.has(proposition.permission_id),
    )
    .sort(
      (left, right) =>
        right.importance - left.importance ||
        left.proposition_id.localeCompare(right.proposition_id),
    )
    .filter(
      (proposition, _index, values) =>
        // Public propositions do not carry a team label field. If a player-season
        // has multiple stints, do not present one as an unqualified season metric.
        values.filter(
          (candidate) =>
            candidate.metric === proposition.metric &&
            candidate.season === proposition.season &&
            candidate.subject === proposition.subject,
        ).length === 1,
    )
    .slice(0, 4);
  if (numbers.length === 0) return null;
  return (
    <section className="ask-v2-key-numbers" aria-label="Key numbers">
      <h3>Key numbers</h3>
      <div>
        {numbers.map((proposition) => (
          <article key={proposition.proposition_id}>
            <span>{metricLabel(proposition.metric ?? "metric")}</span>
            <strong>
              {formatAskV2Value(proposition.value, proposition.unit)}
            </strong>
            {(proposition.subject || proposition.season) && (
              <small>
                {[proposition.subject, proposition.season]
                  .filter(Boolean)
                  .join(" · ")}
              </small>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

function publicLimitationText(response: AskV2Response) {
  const unsupported = response.unsupported_portions[0];
  if (!unsupported) {
    const text = response.limitations[0];
    if (!text) return null;
    if (text.startsWith("BOUNDED_SCOPE:"))
      return "This is a focused sample of the published history, not a complete record-by-record career comparison.";
    if (text === "Expectation intervals are not newly fitted PAE intervals.")
      return "PAE compares performance with a preseason estimate; it does not establish what caused the difference.";
    return /\bC\d+\b|\b[A-Z][A-Z_]+:/.test(text)
      ? "The answer is limited to the available observed evidence; some requested detail is unavailable."
      : text;
  }
  switch (unsupported.reason_code) {
    case "DEVELOPMENT_CONCLUSION_NOT_PERMITTED":
      return "A documented coaching role is not proof that a coach caused a quarterback's improvement.";
    case "C17_SCENARIO_NOT_SUPPORTED":
      return "Historical tendencies can be compared, but the research cannot reliably estimate performance in a different team environment.";
    case "C18_COUNTERFACTUAL_NOT_IMPLEMENTED":
      return "Observed histories can be compared, but the research cannot reliably estimate an alternate career.";
    case "C20_ROOKIE_MODEL_NOT_ESTIMABLE":
      return "The available evidence cannot support a reliable college-to-NFL rookie forecast.";
    default:
      return /\bC\d+\b/.test(unsupported.explanation)
        ? "That requested analysis is not supported by the validated research, so this answer is limited to observed evidence."
        : unsupported.explanation;
  }
}

function PublicLimitation({ response }: { response: AskV2Response }) {
  const limitation = publicLimitationText(response);
  if (!limitation) return null;
  return (
    <p className="ask-v2-public-limitation">
      <strong>Keep in mind:</strong> {limitation}
    </p>
  );
}

function KeepExploring({
  response,
  turnId,
  question,
  onFollowUp,
}: {
  response: AskV2Response;
  turnId: number;
  question: string;
  onFollowUp: (action: AskV2ExploreAction) => void;
}) {
  const lastFollowUp = useRef<{ id: string; at: number } | null>(null);
  const actions = buildKeepExploringActions(response, question);
  if (actions.length === 0) return null;
  return (
    <section
      className="ask-v2-explore"
      aria-labelledby={`keep-exploring-${turnId}`}
    >
      <div className="ask-v2-explore-heading">
        <p className="eyebrow">Connected analysis</p>
        <h3 id={`keep-exploring-${turnId}`}>Keep exploring</h3>
      </div>
      <div className="ask-v2-explore-grid">
        {actions.map((action) => {
          const body = (
            <>
              <span className="ask-v2-explore-kind">
                {action.kind === "navigate" ? (
                  <ArrowUpRight aria-hidden="true" />
                ) : (
                  <MessageCircleQuestion aria-hidden="true" />
                )}
                {action.kind === "navigate"
                  ? "Open analytics"
                  : "Ask follow-up"}
              </span>
              <strong>{action.label}</strong>
              <small>{action.description}</small>
              <ArrowRight className="ask-v2-explore-arrow" aria-hidden="true" />
            </>
          );
          return action.kind === "navigate" && action.href ? (
            <Link key={action.id} to={action.href}>
              {body}
            </Link>
          ) : (
            <button
              type="button"
              key={action.id}
              onClick={() => {
                const at = Date.now();
                if (
                  lastFollowUp.current?.id === action.id &&
                  at - lastFollowUp.current.at < 500
                )
                  return;
                lastFollowUp.current = { id: action.id, at };
                onFollowUp(action);
              }}
            >
              {body}
            </button>
          );
        })}
      </div>
    </section>
  );
}

export function AskV2AssistantTurn({
  turn,
  latest,
  onClarify,
  onFollowUp,
  onRetry,
}: AssistantTurnProps) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (latest && turn.status === "success") heading.current?.focus();
  }, [latest, turn.status]);

  if (turn.status === "pending") {
    return (
      <div
        className="ask-v2-assistant ask-v2-pending"
        role="status"
        aria-live="polite"
      >
        <span className="ask-v2-pulse" aria-hidden="true" />
        <p>
          {turn.retryAttempt > 0
            ? "The analytics API is waking up. Retrying automatically…"
            : "Analyzing the question…"}
        </p>
      </div>
    );
  }
  if (turn.status === "error") {
    return (
      <div className="ask-v2-assistant ask-v2-error" role="alert">
        <AlertTriangle aria-hidden="true" />
        <div>
          <strong>Published data could not be loaded.</strong>
          <p>{turn.error}</p>
          <button
            className="button button-secondary"
            type="button"
            onClick={onRetry}
          >
            <RefreshCw aria-hidden="true" /> Retry this question
          </button>
        </div>
      </div>
    );
  }
  if (turn.status === "cancelled") {
    return <p className="ask-v2-cancelled">Superseded by a newer question.</p>;
  }
  const response = turn.response;
  if (!response) return null;

  return (
    <article className="ask-v2-assistant">
      <section
        className="ask-v2-direct-answer"
        aria-labelledby={`answer-${turn.id}`}
      >
        <p className="eyebrow">Answer</p>
        <h2
          ref={heading}
          tabIndex={-1}
          id={`answer-${turn.id}`}
          className="sr-only"
        >
          Answer to {turn.question}
        </h2>
        <p className="ask-v2-answer-copy">{response.answer}</p>
        <MetricExplainer response={response} />
      </section>
      {response.answerability === "CLARIFICATION_REQUIRED" &&
        response.clarification_candidates.length > 0 && (
          <section
            className="ask-v2-clarification"
            aria-labelledby={`clarify-${turn.id}`}
          >
            <h3 id={`clarify-${turn.id}`}>Which one did you mean?</h3>
            <div>
              {response.clarification_candidates.map((entity) => (
                <button
                  className="button button-secondary"
                  type="button"
                  key={`${entity.kind}:${entity.id}`}
                  onClick={() => onClarify(entity)}
                >
                  {entity.display_name}
                </button>
              ))}
            </div>
          </section>
        )}
      <KeyNumbers response={response} />
      <PublicLimitation response={response} />
      <KeepExploring
        response={response}
        turnId={turn.id}
        question={turn.question}
        onFollowUp={onFollowUp}
      />
      {turn.contextTrimmed && (
        <p className="ask-v2-context-note">
          Earlier turns remain visible but are no longer being used as context.
        </p>
      )}
    </article>
  );
}
