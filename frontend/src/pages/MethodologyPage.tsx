import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  GitCompareArrows,
  Layers3,
  Repeat2,
  Target,
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
          <p className="eyebrow">How Coach Effect works</p>
          <h1>Does performance follow the coach?</h1>
          <p>
            Coach Effect asks whether a coaching signal travels across seasons,
            quarterbacks, teams, and changing football situations—not simply
            whether one offense had a good year.
          </p>
        </div>
      </div>
      <div className="method-grid">
        <article>
          <Target aria-hidden="true" />
          <span>01</span>
          <h2>Measure performance against expectation</h2>
          <p>
            Quarterback performance is compared with what could reasonably have
            been expected entering the season. This separates raw production
            from performance beyond the preseason expectation.
          </p>
          <strong>
            A talented quarterback can play well without exceeding an already
            high expectation.
          </strong>
        </article>
        <article>
          <GitCompareArrows aria-hidden="true" />
          <span>02</span>
          <h2>Evaluate play-calling decisions</h2>
          <p>
            Play calling is evaluated from the game situation and the expected
            value of the available choices. One fortunate bounce or missed
            tackle does not by itself make a decision good or bad.
          </p>
          <strong>
            Decision quality is separated from the actual outcome of one play.
          </strong>
        </article>
        <article>
          <Layers3 aria-hidden="true" />
          <span>03</span>
          <h2>Account for the environment</h2>
          <p>
            QB expectations, prior team performance, offensive supporting
            talent, opponent difficulty, and other context are considered so a
            coach is not simply credited for what he inherited.
          </p>
          <strong>
            Context helps distinguish a coaching pattern from roster and
            schedule advantages.
          </strong>
        </article>
        <article className="method-card-featured">
          <Repeat2 aria-hidden="true" />
          <span>04</span>
          <h2>Look for what follows the coach</h2>
          <p>
            The strongest evidence repeats across seasons, quarterbacks, teams,
            and changing situations. Broader, repeated evidence increases
            confidence; small or inconsistent samples are treated cautiously.
          </p>
          <strong>
            The central question remains: Does performance follow the coach?
          </strong>
        </article>
      </div>
      <section className="section-block">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Interpretation guide</p>
            <h2>How to read Coach Effect</h2>
          </div>
        </div>
        <dl className="coach-effect-guide">
          <div>
            <dt>Positive Coach Effect</dt>
            <dd>
              The observed coaching signal is associated with performance above
              expectation across the available evidence.
            </dd>
          </div>
          <div>
            <dt>Near Average</dt>
            <dd>
              The evidence sits near the league baseline. That does not prove
              the coach had no impact.
            </dd>
          </div>
          <div>
            <dt>Negative Coach Effect</dt>
            <dd>
              The observed signal is associated with performance below
              expectation and must still be read alongside team circumstances.
            </dd>
          </div>
          <div>
            <dt>Confidence</dt>
            <dd>
              Confidence grows when the pattern repeats across more seasons,
              quarterbacks, teams, and situations. Small or inconsistent samples
              receive more caution.
            </dd>
          </div>
        </dl>
        <p className="long-copy coach-effect-caution">
          Coach Effect is an evidence-based observational coaching signal. It
          should not be interpreted as proof that a coach caused a particular
          result. Current coach estimates remain exploratory and retain their
          evidence and suppression labels.
        </p>
      </section>
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
