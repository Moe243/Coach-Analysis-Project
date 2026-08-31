import { useQueries, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, Link2, ShieldAlert } from "lucide-react";
import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { apiGet, apiGetAll } from "../api/client";
import type {
  ApiPage,
  Citation,
  CoachImpact,
  CoachProfile,
  QbProfile,
  QbSeason,
  Team,
} from "../api/contracts";
import { EmptyState, ErrorState, LoadingState } from "../components/DataState";
import { MetricCard } from "../components/MetricCard";
import { StatusBadge } from "../components/StatusBadge";
import { integer, roleLabel, signed } from "../lib/format";

export function CoachDetailPage() {
  const { coachId = "" } = useParams();
  const profile = useQuery({
    queryKey: ["coach-profile", coachId],
    queryFn: ({ signal }) =>
      apiGet<CoachProfile>(`/coaches/${coachId}`, {}, signal),
    enabled: Boolean(coachId),
  });
  const impact = useQuery({
    queryKey: ["coach-impact", "all"],
    queryFn: ({ signal }) =>
      apiGetAll<CoachImpact>("/coach-impact", {}, signal),
    staleTime: Infinity,
  });
  const citations = useQuery({
    queryKey: ["citations", coachId],
    queryFn: ({ signal }) =>
      apiGetAll<Citation>("/citations", { coach_id: coachId }, signal),
    enabled: Boolean(coachId),
  });
  const teams = useQuery({
    queryKey: ["teams"],
    queryFn: ({ signal }) => apiGetAll<Team>("/teams", {}, signal),
    staleTime: Infinity,
  });
  const teamSeasons = useMemo(
    () =>
      Array.from(
        new Set(
          profile.data?.role_history.map(
            (row) => `${row.team_id}:${row.season}`,
          ) ?? [],
        ),
      ),
    [profile.data?.role_history],
  );
  const qbs = useQueries({
    queries: teamSeasons.map((value) => {
      const [teamId, season] = value.split(":");
      return {
        queryKey: ["qbs", teamId, season],
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          apiGet<ApiPage<QbSeason>>(
            "/qbs",
            { team_id: teamId, season: Number(season), limit: 200 },
            signal,
          ),
        staleTime: Infinity,
      };
    }),
  });
  const teamMap = new Map(
    teams.data?.map((team) => [team.team_id, team]) ?? [],
  );
  const coachImpact =
    impact.data?.filter((row) => row.coach_id === coachId) ?? [];
  const participantRows = qbs.flatMap((query) => query.data?.items ?? []);
  const participantIds = Array.from(
    new Set(participantRows.map((row) => row.player_id)),
  );
  const participants = useQueries({
    queries: participantIds.map((playerId) => ({
      queryKey: ["qb-profile", playerId],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        apiGet<QbProfile>(`/qbs/${playerId}`, {}, signal),
      staleTime: Infinity,
    })),
  });
  const quarterbackIds = new Set(
    participants
      .filter((query) => query.data?.player.position === "QB")
      .map((query) => query.data!.player.player_id),
  );
  const qbRows = participantRows
    .filter((row) => quarterbackIds.has(row.player_id))
    .sort((a, b) => b.season - a.season || b.dropbacks - a.dropbacks);
  const isLoading =
    profile.isLoading ||
    impact.isLoading ||
    citations.isLoading ||
    teams.isLoading ||
    qbs.some((query) => query.isLoading) ||
    participants.some((query) => query.isLoading);
  const error =
    profile.error ||
    impact.error ||
    citations.error ||
    teams.error ||
    qbs.find((query) => query.error)?.error ||
    participants.find((query) => query.error)?.error;

  if (isLoading)
    return (
      <section className="page">
        <LoadingState label="Loading coach profile" />
      </section>
    );
  if (error)
    return (
      <section className="page">
        <ErrorState error={error} retry={() => void profile.refetch()} />
      </section>
    );
  if (!profile.data)
    return (
      <section className="page">
        <EmptyState title="Coach not found">
          This coach is not present in the current publication.
        </EmptyState>
      </section>
    );

  const history = [...profile.data.role_history].sort(
    (a, b) => b.season - a.season || a.start_week - b.start_week,
  );
  return (
    <section className="page detail-page">
      <Link className="back-link" to="/statistics">
        <ArrowLeft aria-hidden="true" /> Back to statistics
      </Link>
      <header className="profile-header">
        <div>
          <p className="eyebrow">
            Coach profile · {profile.data.coach.coach_id}
          </p>
          <h1>{profile.data.coach.canonical_name}</h1>
          <p>
            {history.length} published role intervals ·{" "}
            {new Set(history.map((row) => row.team_id)).size} teams
          </p>
        </div>
        <div className="profile-summary">
          <MetricCard
            label="Verified intervals"
            value={integer(
              history.filter((row) => row.verification_status === "verified")
                .length,
            )}
          />
          <MetricCard
            label="Provisional intervals"
            value={integer(
              history.filter((row) => row.verification_status === "provisional")
                .length,
            )}
          />
          <MetricCard
            label="Citations"
            value={integer(citations.data?.length)}
          />
        </div>
      </header>

      <div className="notice-strip notice-warning">
        <ShieldAlert aria-hidden="true" />
        <p>
          <strong>Coach effects are exploratory and suppressed.</strong> Team
          environment and coach assignment are not independently identified. No
          row on this page is a publishable ranking.
        </p>
      </div>

      <section className="section-block">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Exploratory associations</p>
            <h2>Impact model by role</h2>
          </div>
          <p>
            Uncertainty appears only when at least 160 of 200 coach-specific
            bootstrap draws succeeded.
          </p>
        </div>
        {coachImpact.length ? (
          <div className="impact-grid">
            {coachImpact.map((row) => (
              <article className="impact-card" key={row.role}>
                <div>
                  <StatusBadge value={row.ranking_status} />
                  <StatusBadge value={row.identification_status} />
                </div>
                <h3>{roleLabel(row.role)}</h3>
                <strong
                  className={
                    (row.estimated_effect ?? 0) >= 0
                      ? "metric-up"
                      : "metric-down"
                  }
                >
                  {signed(row.estimated_effect)}
                </strong>
                <p>
                  {row.bootstrap_interval_available
                    ? `${signed(row.confidence_low)} to ${signed(row.confidence_high)} conditional interval`
                    : "Conditional interval suppressed"}
                </p>
                <dl>
                  <div>
                    <dt>Verified exposure</dt>
                    <dd>{integer(row.verified_dropbacks)} DB</dd>
                  </div>
                  <div>
                    <dt>QB seasons</dt>
                    <dd>{row.qualifying_qb_seasons}</dd>
                  </div>
                  <div>
                    <dt>Quarterbacks</dt>
                    <dd>{row.distinct_quarterbacks}</dd>
                  </div>
                  <div>
                    <dt>Bootstrap support</dt>
                    <dd>
                      {row.bootstrap_replicates}/
                      {row.bootstrap_attempted_replicates}
                    </dd>
                  </div>
                </dl>
                <small>
                  {row.rank_exclusion_reason ??
                    "Ranking eligibility is not supported."}
                </small>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="No model row">
            This coach has assignment history but no checkpoint-six effect row.
          </EmptyState>
        )}
      </section>

      <section className="section-block split-section">
        <div>
          <div className="section-heading">
            <div>
              <p className="eyebrow">Role history</p>
              <h2>Assignments & intervals</h2>
            </div>
          </div>
          <div className="timeline">
            {history.map((row) => (
              <article key={row.assignment_key}>
                <div className="timeline-date">
                  {row.season}
                  <small>
                    {teamMap.get(row.team_id)?.team_abbr ?? row.team_id}
                  </small>
                </div>
                <div>
                  <h3>{roleLabel(row.role)}</h3>
                  <p>
                    Weeks {row.start_week}–{row.end_week} ·{" "}
                    {row.interval_basis.replaceAll("_", " ")}
                  </p>
                  <div className="badge-row">
                    <StatusBadge value={row.verification_status} />
                    <StatusBadge value={`${row.confidence_level} confidence`} />
                    {row.is_shared && <StatusBadge value="shared duty" />}
                    {row.is_interim && <StatusBadge value="interim" />}
                  </div>
                  {row.notes && <small>{row.notes}</small>}
                </div>
              </article>
            ))}
          </div>
        </div>
        <aside>
          <div className="section-heading">
            <div>
              <p className="eyebrow">Connected quarterbacks</p>
              <h2>Team-season overlap</h2>
            </div>
          </div>
          <p className="context-note">
            Only players whose published profile position is QB are shown.
            Connections reflect a shared team-season, not a causal exposure
            claim.
          </p>
          <ul className="connection-list">
            {qbRows.map((row) => (
              <li key={`${row.player_id}-${row.team_id}-${row.season}`}>
                <Link to={`/qbs/${row.player_id}`}>{row.display_name}</Link>
                <span>
                  {row.season} ·{" "}
                  {teamMap.get(row.team_id)?.team_abbr ?? row.team_id} ·{" "}
                  {integer(row.dropbacks)} DB
                </span>
              </li>
            ))}
          </ul>
        </aside>
      </section>

      <section className="section-block">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Evidence trail</p>
            <h2>Assignment citations</h2>
          </div>
          <p>Links open the original source in a new tab.</p>
        </div>
        {citations.data?.length ? (
          <div className="citation-list">
            {citations.data.map((citation) => (
              <article
                key={`${citation.assignment_key}-${citation.source_url}`}
              >
                <Link2 aria-hidden="true" />
                <div>
                  <h3>{citation.source_title || "Assignment source"}</h3>
                  <p>
                    {citation.season} ·{" "}
                    {teamMap.get(citation.team_id)?.team_abbr ??
                      citation.team_id}{" "}
                    · {roleLabel(citation.role)}
                  </p>
                  {citation.evidence_note && (
                    <small>{citation.evidence_note}</small>
                  )}
                  <a
                    href={citation.source_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View source <ExternalLink aria-hidden="true" />
                  </a>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="No citation rows">
            Only source-backed citations present in checkpoint seven are shown.
          </EmptyState>
        )}
      </section>
    </section>
  );
}
