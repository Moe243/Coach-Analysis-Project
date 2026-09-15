import { useEffect, useRef } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  ChevronRight,
  Database,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { Link } from "react-router-dom";
import type { AskV2ResolvedEntity, AskV2Response } from "../../api/askV2";
import type { AskV2ConversationTurn } from "../../hooks/useAskV2Conversation";
import {
  entityHref,
  formatAskV2Value,
  humanize,
  isAlignmentResponse,
  isComparisonResponse,
  isCounterfactualResponse,
  propositionUncertainty,
} from "../../lib/askV2";

interface AssistantTurnProps {
  turn: AskV2ConversationTurn;
  latest: boolean;
  onClarify: (entity: AskV2ResolvedEntity) => void;
  onFollowUp: (question: string) => void;
  onRetry: () => void;
}

const answerabilityLabels: Record<AskV2Response["answerability"], string> = {
  SUPPORTED: "Supported",
  PARTIALLY_SUPPORTED: "Partially supported",
  NOT_SUPPORTED: "Not supported",
  CLARIFICATION_REQUIRED: "Clarification needed",
  DATA_UNAVAILABLE: "Data unavailable",
};

function ModeBadge({ response }: { response: AskV2Response }) {
  const grounded = response.answer_mode === "grounded_ai";
  return (
    <span
      className="ask-v2-mode"
      title={
        grounded
          ? "Grounded AI organizes approved project evidence. Every analytical claim is validated by the backend."
          : "Generated directly from approved project evidence."
      }
    >
      {grounded ? "Grounded AI" : "Deterministic"}
    </span>
  );
}

function EntityLinks({ response }: { response: AskV2Response }) {
  if (response.entities.length === 0) return null;
  return (
    <nav className="ask-v2-entity-links" aria-label="Related profiles">
      {response.entities.map((entity) => (
        <Link key={`${entity.kind}:${entity.id}`} to={entityHref(entity)}>
          {entity.kind === "team" ? "Explore" : "View"} {entity.display_name}
          <ArrowUpRight aria-hidden="true" />
        </Link>
      ))}
    </nav>
  );
}

function ComparisonFrame({
  response,
  turnId,
}: {
  response: AskV2Response;
  turnId: number;
}) {
  if (!isComparisonResponse(response)) return null;
  return (
    <section
      className="ask-v2-comparison"
      aria-labelledby={`comparison-${turnId}`}
    >
      <h3 id={`comparison-${turnId}`}>Comparison frame</h3>
      <div>
        {response.entities.map((entity) => (
          <article key={`${entity.kind}:${entity.id}`}>
            <span>{humanize(entity.kind)}</span>
            <strong>{entity.display_name}</strong>
            <small>Evaluated from the same approved evidence contract</small>
          </article>
        ))}
      </div>
      <p>
        No overall winner is implied unless the backend explicitly permits that
        conclusion.
      </p>
    </section>
  );
}

function AlignmentFrame({ response }: { response: AskV2Response }) {
  if (!isAlignmentResponse(response)) return null;
  const player = response.entities.find((entity) => entity.kind === "qb");
  const team = response.entities.find((entity) => entity.kind === "team");
  const alignments = response.propositions.filter(
    (item) => item.kind === "PLAYER_SCHEME_DESCRIPTIVE_ALIGNMENT",
  );
  return (
    <section
      className="ask-v2-alignment"
      aria-label="Player and team descriptive alignment"
    >
      <div className="ask-v2-alignment-parties">
        <article>
          <span>Player profile</span>
          <strong>{player?.display_name ?? "Quarterback"}</strong>
        </article>
        <ChevronRight aria-hidden="true" />
        <article>
          <span>Historical scheme</span>
          <strong>{team?.display_name ?? "Team"}</strong>
        </article>
      </div>
      <h3>Comparable dimensions</h3>
      <ul>
        {alignments.map((proposition) => (
          <li key={proposition.proposition_id}>{proposition.statement}</li>
        ))}
      </ul>
      <p>Descriptive alignment only—not a destination forecast or fit grade.</p>
    </section>
  );
}

function EvidenceCards({
  response,
  turnId,
}: {
  response: AskV2Response;
  turnId: number;
}) {
  if (response.evidence.length === 0) return null;
  return (
    <section
      className="ask-v2-evidence-summary"
      aria-labelledby={`strongest-evidence-${turnId}`}
    >
      <h3 id={`strongest-evidence-${turnId}`}>Strongest evidence</h3>
      <div className="ask-v2-evidence-grid">
        {response.evidence.map((point) => {
          const proposition = response.propositions.find((item) =>
            item.evidence_ids.includes(point.evidence_id),
          );
          const uncertainty = proposition
            ? propositionUncertainty(proposition, response.uncertainty)
            : undefined;
          return (
            <article key={point.evidence_id}>
              <span>Evidence {point.rank}</span>
              <p>{point.summary}</p>
              {uncertainty && (
                <small>
                  {humanize(uncertainty.reliability)} reliability ·{" "}
                  {uncertainty.explanation}
                </small>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function EvidenceDetails({ response }: { response: AskV2Response }) {
  return (
    <details className="ask-v2-details">
      <summary>Evidence &amp; methodology</summary>
      <div className="ask-v2-detail-body">
        {response.propositions.length > 0 ? (
          <ol className="ask-v2-propositions">
            {response.propositions.map((proposition) => {
              const uncertainty = propositionUncertainty(
                proposition,
                response.uncertainty,
              );
              return (
                <li key={proposition.proposition_id}>
                  <p>{proposition.statement}</p>
                  <dl>
                    <div>
                      <dt>Claim type</dt>
                      <dd>{humanize(proposition.kind)}</dd>
                    </div>
                    <div>
                      <dt>Evidence</dt>
                      <dd>
                        {proposition.evidence_ids.join(", ") ||
                          "No analytical record"}
                      </dd>
                    </div>
                    {proposition.metric && (
                      <div>
                        <dt>{humanize(proposition.metric)}</dt>
                        <dd>
                          {formatAskV2Value(
                            proposition.value,
                            proposition.unit,
                          )}
                        </dd>
                      </div>
                    )}
                    {proposition.season && (
                      <div>
                        <dt>Season</dt>
                        <dd>{proposition.season}</dd>
                      </div>
                    )}
                    {uncertainty && (
                      <div>
                        <dt>Reliability</dt>
                        <dd>{humanize(uncertainty.reliability)}</dd>
                      </div>
                    )}
                  </dl>
                  {proposition.qualifier && (
                    <small>{proposition.qualifier}</small>
                  )}
                </li>
              );
            })}
          </ol>
        ) : (
          <p>No analytical evidence was approved for this response.</p>
        )}
        {response.uncertainty.length > 0 && (
          <section>
            <h3>Uncertainty</h3>
            <ul>
              {response.uncertainty.map((item) => {
                const proposition = response.propositions.find(
                  (candidate) =>
                    candidate.uncertainty_id === item.uncertainty_id,
                );
                return (
                  <li key={item.uncertainty_id}>
                    <strong>{humanize(item.reliability)} reliability.</strong>{" "}
                    {item.explanation}
                    {item.lower !== null && item.upper !== null
                      ? ` Interval: ${formatAskV2Value(item.lower, proposition?.unit ?? null)} to ${formatAskV2Value(item.upper, proposition?.unit ?? null)}.`
                      : ""}
                  </li>
                );
              })}
            </ul>
          </section>
        )}
        {response.limitations.length > 0 && (
          <section>
            <h3>Methodological limits</h3>
            <ul>
              {response.limitations.map((limitation) => (
                <li key={limitation}>{limitation}</li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </details>
  );
}

function Provenance({ response }: { response: AskV2Response }) {
  const versions = response.versions;
  return (
    <details className="ask-v2-details ask-v2-provenance">
      <summary>Versions &amp; provenance</summary>
      <dl className="ask-v2-version-grid">
        <div>
          <dt>Ask contract</dt>
          <dd>{versions.ask_contract_version}</dd>
        </div>
        <div>
          <dt>Evidence reducer</dt>
          <dd>{versions.evidence_reducer_version ?? "Not applicable"}</dd>
        </div>
        <div>
          <dt>Analytical data</dt>
          <dd>{versions.analytical_data_version ?? "Unavailable"}</dd>
        </div>
        <div>
          <dt>Analytical models</dt>
          <dd>
            {versions.analytical_model_versions.join(", ") || "Not applicable"}
          </dd>
        </div>
        <div>
          <dt>Answer mode</dt>
          <dd>
            {response.answer_mode === "grounded_ai"
              ? "Grounded AI"
              : "Deterministic"}
          </dd>
        </div>
        {versions.planner_model_version && (
          <div>
            <dt>Planner model</dt>
            <dd>{versions.planner_model_version}</dd>
          </div>
        )}
        {versions.synthesizer_model_version && (
          <div>
            <dt>Synthesizer model</dt>
            <dd>{versions.synthesizer_model_version}</dd>
          </div>
        )}
      </dl>
    </details>
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
            : "Reviewing approved project evidence…"}
        </p>
      </div>
    );
  }
  if (turn.status === "error") {
    return (
      <div className="ask-v2-assistant ask-v2-error" role="alert">
        <AlertTriangle aria-hidden="true" />
        <div>
          <strong>Published evidence could not be loaded.</strong>
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
  const counterfactual = isCounterfactualResponse(response);
  return (
    <article className="ask-v2-assistant">
      <header className="ask-v2-answer-header">
        <div>
          <ShieldCheck aria-hidden="true" />
          <span
            className={`ask-v2-status status-${response.answerability.toLowerCase()}`}
          >
            {answerabilityLabels[response.answerability]}
          </span>
        </div>
        <ModeBadge response={response} />
      </header>
      <section
        className="ask-v2-direct-answer"
        aria-labelledby={`answer-${turn.id}`}
      >
        <p className="eyebrow">
          {counterfactual ? "What we can compare" : "Answer"}
        </p>
        <h2
          ref={heading}
          tabIndex={-1}
          id={`answer-${turn.id}`}
          className="sr-only"
        >
          Answer to {turn.question}
        </h2>
        <p>{response.answer}</p>
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
      <EntityLinks response={response} />
      <ComparisonFrame response={response} turnId={turn.id} />
      <AlignmentFrame response={response} />
      <EvidenceCards response={response} turnId={turn.id} />
      {response.unsupported_portions.length > 0 && (
        <section
          className="ask-v2-unsupported"
          aria-labelledby={`unsupported-${turn.id}`}
        >
          <AlertTriangle aria-hidden="true" />
          <div>
            <h3 id={`unsupported-${turn.id}`}>
              {counterfactual
                ? "What we cannot estimate"
                : "What the model can't estimate"}
            </h3>
            {response.unsupported_portions.map((portion) => (
              <div key={`${portion.reason_code}:${portion.description}`}>
                <strong>{portion.description}</strong>
                <p>{portion.explanation}</p>
              </div>
            ))}
          </div>
        </section>
      )}
      {response.follow_ups.length > 0 && (
        <section
          className="ask-v2-followups"
          aria-labelledby={`followups-${turn.id}`}
        >
          <h3 id={`followups-${turn.id}`}>Keep exploring</h3>
          <div>
            {response.follow_ups.map((followUp) => (
              <button
                type="button"
                key={`${followUp.label}:${followUp.question}`}
                onClick={() => onFollowUp(followUp.question)}
              >
                <CheckCircle2 aria-hidden="true" /> {followUp.label}
              </button>
            ))}
          </div>
        </section>
      )}
      <EvidenceDetails response={response} />
      <Provenance response={response} />
      {turn.contextTrimmed && (
        <p className="ask-v2-context-note">
          Earlier turns remain visible but are no longer being used as context.
        </p>
      )}
      <footer className="ask-v2-authority-note">
        <Database aria-hidden="true" /> Analytics first. Language assistance
        cannot expand what the evidence supports.
      </footer>
    </article>
  );
}
