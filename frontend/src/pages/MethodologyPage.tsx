import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Database,
  Sigma,
} from "lucide-react";
import { Link } from "react-router-dom";
import { apiGet } from "../api/client";
import type { Versions } from "../api/contracts";

export function MethodologyPage() {
  const versions = useQuery({
    queryKey: ["versions"],
    queryFn: ({ signal }) => apiGet<Versions>("/versions", {}, signal),
    staleTime: Infinity,
  });
  return (
    <section className="page methodology-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Interpretation guide</p>
          <h1>Read the signal, keep the uncertainty</h1>
          <p>
            This interface makes the project’s timing, evidence, and suppression
            rules visible. It does not turn observational football data into
            causal proof.
          </p>
        </div>
      </div>
      <div className="method-grid">
        <article>
          <Sigma aria-hidden="true" />
          <span>01</span>
          <h2>Start with PAE</h2>
          <p>
            Performance Above Expectation is actual EPA per eligible quarterback
            dropback minus a prediction built strictly before that season.
          </p>
          <strong>
            Positive means above the model expectation—not automatically “good
            coaching.”
          </strong>
        </article>
        <article>
          <Database aria-hidden="true" />
          <span>02</span>
          <h2>Check the sample</h2>
          <p>
            Quarterbacks qualify at 200 dropbacks. Smaller samples remain
            visible with an ineligible label and lower reliability.
          </p>
          <strong>
            Eligibility changes interpretation, never the underlying arithmetic.
          </strong>
        </article>
        <article>
          <CheckCircle2 aria-hidden="true" />
          <span>03</span>
          <h2>Read evidence status</h2>
          <p>
            Verified assignments have citations. Provisional rows preserve
            season designations or unresolved boundaries without pretending they
            are settled facts.
          </p>
          <strong>
            Shared, interim, confidence, and interval fields remain visible.
          </strong>
        </article>
        <article>
          <AlertCircle aria-hidden="true" />
          <span>04</span>
          <h2>Do not rank coaches</h2>
          <p>
            Checkpoint six could not independently separate coach assignments
            from team environment. All coach effects remain exploratory and
            suppressed.
          </p>
          <strong>
            Conditional bootstrap intervals are not unconditional confidence
            intervals.
          </strong>
        </article>
      </div>
      <section className="section-block">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Metric contract</p>
            <h2>Eligible quarterback dropback</h2>
          </div>
        </div>
        <p className="long-copy">
          A regular-season play with <code>qb_dropback = 1</code>, excluding
          kneels and spikes, and including attempts, sacks, and quarterback
          scrambles. EPA/dropback is the sum of quarterback EPA divided by those
          plays. CPOE, success, explosive-pass, interception, touchdown, sack,
          air-yards, first-down, and WPA rates retain their documented
          denominators and missingness.
        </p>
      </section>
      <section className="version-panel">
        <div>
          <p className="eyebrow">Current publication</p>
          <h2>Versioned from source to screen</h2>
        </div>
        {versions.data ? (
          <dl>
            <div>
              <dt>API</dt>
              <dd>{versions.data.api_contract_version}</dd>
            </div>
            <div>
              <dt>Historical</dt>
              <dd>{versions.data.historical_data_version}</dd>
            </div>
            <div>
              <dt>Expected performance</dt>
              <dd>{versions.data.expected_data_version}</dd>
            </div>
            <div>
              <dt>Coach impact</dt>
              <dd>{versions.data.coach_model_version}</dd>
            </div>
          </dl>
        ) : (
          <p>Version service unavailable.</p>
        )}
      </section>
      <div className="method-actions">
        <Link className="button button-secondary" to="/statistics">
          Explore statistics <ArrowRight aria-hidden="true" />
        </Link>
        <Link className="button button-ghost" to="/network">
          Open coaching network
        </Link>
      </div>
    </section>
  );
}
