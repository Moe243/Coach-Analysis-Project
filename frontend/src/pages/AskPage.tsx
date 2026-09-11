import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { askQuestion } from "../api/ask";
import { isRetryableApiError } from "../api/client";
import "./AskPage.css";

const examples = [
  "How did Josh Allen perform in 2022?",
  "Is Lamar Jackson mobile?",
  "Which QBs played under Andy Reid in 2022?",
  "What type of offense did Miami run in 2024?",
  "What does the model project for Josh Allen in 2026?",
  "What does PCAE say about Andy Reid in 2024?",
];

function label(key: string) {
  return key.replaceAll("_", " ");
}

function valueText(value: unknown): string {
  if (value === null || value === undefined) return "Unavailable";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

const prominent = new Set([
  "quarterback_name",
  "coach_name",
  "team_name",
  "season",
  "target_season",
  "feature_name",
  "dropbacks",
  "epa_per_dropback",
  "expected_epa_per_dropback",
  "performance_above_expectation",
  "feature_value",
  "raw_value",
  "prediction",
  "pcae",
  "role",
  "start_week",
  "end_week",
  "interval_basis",
  "reliability",
  "qualified",
  "feature_status",
  "sample_size",
  "feature_sample_size",
  "denominator",
  "verification_status",
  "confidence_level",
  "is_shared",
  "missingness_reason",
  "interval_low",
  "interval_high",
  "lower_80",
  "upper_80",
  "attributed_play_count",
]);

function RecordCard({ row }: { row: Record<string, unknown> }) {
  const entries = Object.entries(row);
  return (
    <article className="ask-record">
      <dl>
        {entries
          .filter(([key]) => prominent.has(key))
          .map(([key, value]) => (
            <div key={key}>
              <dt>{label(key)}</dt>
              <dd>{valueText(value)}</dd>
            </div>
          ))}
      </dl>
      <details>
        <summary>All source fields and evidence</summary>
        <dl>
          {entries.map(([key, value]) => (
            <div key={key}>
              <dt>{label(key)}</dt>
              <dd>
                <pre>{valueText(value)}</pre>
              </dd>
            </div>
          ))}
        </dl>
      </details>
    </article>
  );
}

export function AskPage() {
  const [question, setQuestion] = useState("");
  const answer = useMutation({
    mutationFn: askQuestion,
    retry: (count, error) => count < 2 && isRetryableApiError(error),
    retryDelay: 3000,
  });
  const data = answer.data;
  function submit(text: string) {
    setQuestion(text);
    answer.reset();
    answer.mutate(text);
  }
  return (
    <section className="page ask-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Evidence, then explanation</p>
          <h1>Ask Anything</h1>
          <p>
            Explore approved QB history, style, scheme and research results.
            Unsupported questions receive an explanation—not an invented
            estimate.
          </p>
        </div>
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          submit(question.trim());
        }}
      >
        <label htmlFor="analytical-question">Your football question</label>
        <textarea
          id="analytical-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          minLength={3}
          maxLength={1000}
          required
          rows={3}
        />
        <button
          className="button button-primary"
          type="submit"
          disabled={answer.isPending || question.trim().length < 3}
        >
          Ask the data
        </button>
      </form>
      <details className="ask-examples">
        <summary>Try a supported question</summary>
        <ul>
          {examples.map((example) => (
            <li key={example}>
              <button
                type="button"
                disabled={answer.isPending}
                onClick={() => submit(example)}
              >
                {example}
              </button>
            </li>
          ))}
        </ul>
      </details>
      {answer.isPending && (
        <p role="status">
          {answer.failureCount > 0
            ? "API is waking up. Retrying automatically…"
            : "Looking up approved evidence…"}
        </p>
      )}
      {answer.isError && (
        <div role="alert">
          <p>{answer.error.message}</p>
          <button
            className="button button-secondary"
            onClick={() => submit(answer.variables ?? question)}
          >
            Retry question
          </button>
        </div>
      )}
      {data && !answer.isPending && (
        <section className="ask-answer" aria-labelledby="answer-heading">
          <h2 id="answer-heading">{data.status.replaceAll("_", " ")}</h2>
          <p className="eyebrow">
            {data.intent.replaceAll("_", " ")}
            {data.season ? ` · ${data.season}` : ""}
          </p>
          <p>Question: {answer.variables}</p>
          <p role="status">{data.explanation}</p>
          {data.candidates.length > 0 && (
            <div>
              <h3>Confirm the canonical entity</h3>
              {data.candidates.map((candidate) => (
                <button
                  className="button button-secondary"
                  key={`${candidate.kind}:${candidate.id}`}
                  onClick={() =>
                    submit(`${answer.variables} [${candidate.id}]`)
                  }
                >
                  {candidate.name} ({candidate.id})
                </button>
              ))}
            </div>
          )}
          <div className="ask-links">
            {data.entities.map((entity) =>
              entity.kind === "qb" || entity.kind === "coach" ? (
                <Link
                  key={entity.id}
                  to={`/${entity.kind === "qb" ? "qbs" : "coaches"}/${encodeURIComponent(entity.id)}`}
                >
                  {entity.name} profile
                </Link>
              ) : (
                <Link
                  key={entity.id}
                  to={`/network?team_id=${encodeURIComponent(entity.id)}`}
                >
                  {entity.name} relationships
                </Link>
              ),
            )}
          </div>
          {data.metrics.length > 0 && (
            <div className="ask-records">
              {data.metrics.map((row, index) => (
                <RecordCard key={index} row={row} />
              ))}
            </div>
          )}
          {data.uncertainty.length > 0 && (
            <details>
              <summary>Uncertainty and Player State context</summary>
              <pre>{JSON.stringify(data.uncertainty, null, 2)}</pre>
            </details>
          )}
          {data.limitations.length > 0 && (
            <div>
              <h3>How to interpret this</h3>
              <ul>
                {data.limitations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          <details>
            <summary>Versions and analytical sources</summary>
            <p>Contract: {data.contract_version}</p>
            <p>Snapshot: {data.data_version}</p>
            <p>Model: {data.model_version ?? "Not applicable / unavailable"}</p>
            {data.source_artifacts.map((source) => (
              <p key={source.artifact}>
                {source.artifact}
                <br />
                SHA-256: {source.sha256}
              </p>
            ))}
          </details>
        </section>
      )}
      <p className="ask-caution">
        Observational evidence, not proof of causation. No team-switch forecast,
        career counterfactual, rookie projection or universal Coach Effect score
        is currently supported. No external AI credentials are required.
      </p>
    </section>
  );
}
