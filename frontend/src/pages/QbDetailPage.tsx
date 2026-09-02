import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CalendarDays, ShieldCheck } from "lucide-react";
import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { apiGet, apiGetAll } from "../api/client";
import type {
  ApiPage,
  CoachAssignment,
  QbPae,
  QbProfile,
  Team,
} from "../api/contracts";
import { EmptyState, ErrorState, LoadingState } from "../components/DataState";
import { MetricCard } from "../components/MetricCard";
import { PerformanceChart } from "../components/PerformanceChart";
import { StatusBadge } from "../components/StatusBadge";
import { integer, percent, roleLabel, signed } from "../lib/format";

export function QbDetailPage() {
  const { playerId = "" } = useParams();
  const profile = useQuery({
    queryKey: ["qb-profile", playerId],
    queryFn: ({ signal }) => apiGet<QbProfile>(`/qbs/${playerId}`, {}, signal),
    enabled: Boolean(playerId),
  });
  const pae = useQuery({
    queryKey: ["qb-pae", playerId],
    queryFn: ({ signal }) =>
      apiGet<ApiPage<QbPae>>(`/qbs/${playerId}/pae`, { limit: 50 }, signal),
    enabled: Boolean(playerId),
  });
  const assignments = useQuery({
    queryKey: ["assignments", "all"],
    queryFn: ({ signal }) =>
      apiGetAll<CoachAssignment>("/assignments", {}, signal),
    staleTime: Infinity,
  });
  const teams = useQuery({
    queryKey: ["teams"],
    queryFn: ({ signal }) => apiGetAll<Team>("/teams", {}, signal),
    staleTime: Infinity,
  });

  const teamMap = useMemo(
    () => new Map(teams.data?.map((team) => [team.team_id, team]) ?? []),
    [teams.data],
  );
  const staffMap = useMemo(() => {
    const result = new Map<string, CoachAssignment[]>();
    assignments.data?.forEach((row) => {
      const key = `${row.team_id}-${row.season}`;
      result.set(key, [...(result.get(key) ?? []), row]);
    });
    return result;
  }, [assignments.data]);
  const latest = [...(pae.data?.items ?? [])].sort(
    (a, b) => b.season - a.season,
  )[0];
  const latestSeason = profile.data?.seasons.find(
    (row) => row.season === latest?.season && row.team_id === latest.team_id,
  );
  const error = profile.error || pae.error || assignments.error || teams.error;

  if (
    profile.isLoading ||
    pae.isLoading ||
    assignments.isLoading ||
    teams.isLoading
  ) {
    return (
      <section className="page">
        <LoadingState label="Loading quarterback profile" />
      </section>
    );
  }
  if (error) {
    return (
      <section className="page">
        <ErrorState error={error} retry={() => void profile.refetch()} />
      </section>
    );
  }
  if (!profile.data || !pae.data) {
    return (
      <section className="page">
        <EmptyState title="Quarterback not found">
          This player is not present in the current analysis publication.
        </EmptyState>
      </section>
    );
  }

  const seasons = [...profile.data.seasons].sort(
    (a, b) => b.season - a.season || a.team_id.localeCompare(b.team_id),
  );
  return (
    <section className="page detail-page">
      <Link className="back-link" to="/statistics">
        <ArrowLeft aria-hidden="true" /> Back to statistics
      </Link>
      <header className="profile-header">
        <div>
          <p className="eyebrow">
            Quarterback profile · GSIS {profile.data.player.player_id}
          </p>
          <h1>{profile.data.player.display_name}</h1>
          <p>
            {seasons.length} published QB-team seasons ·{" "}
            {seasons[seasons.length - 1]?.season}–{seasons[0]?.season}
          </p>
        </div>
        {latest && latestSeason && (
          <div className="profile-summary">
            <MetricCard
              label="Latest PAE"
              value={signed(latest.performance_above_expectation)}
              tone={
                latest.performance_above_expectation >= 0
                  ? "positive"
                  : "negative"
              }
              note={`${latest.season} · ${teamMap.get(latest.team_id)?.team_abbr ?? latest.team_id}`}
            />
            <MetricCard
              label="Dropbacks"
              value={integer(latestSeason.dropbacks)}
              note={<StatusBadge value={latest.eligibility_status} />}
            />
            <MetricCard
              label="Reliability"
              value={latest.reliability}
              note="Expected-performance label"
            />
          </div>
        )}
      </header>

      <div className="notice-strip">
        <ShieldCheck aria-hidden="true" />
        <p>
          <strong>Out-of-sample expectations only.</strong> Each prediction was
          built without the target season or any future season. PAE is
          descriptive, not a player grade.
        </p>
      </div>

      <section className="section-block">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Season trajectory</p>
            <h2>Actual vs expected EPA/dropback</h2>
          </div>
          <p>PAE is the vertical difference between the two lines.</p>
        </div>
        <PerformanceChart rows={pae.data.items} />
      </section>

      <section className="section-block">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Published history</p>
            <h2>Quarterback-team seasons</h2>
          </div>
          <p>Missing rates remain unavailable, never zero-filled.</p>
        </div>
        <div className="table-frame">
          <table className="detail-table">
            <thead>
              <tr>
                <th>Season / team</th>
                <th>Actual</th>
                <th>Expected</th>
                <th>PAE</th>
                <th>CPOE</th>
                <th>Success</th>
                <th>Sack rate</th>
                <th>Dropbacks</th>
                <th>Eligibility</th>
                <th>Season totals</th>
              </tr>
            </thead>
            <tbody>
              {seasons.map((season) => {
                const prediction = pae.data.items.find(
                  (row) =>
                    row.season === season.season &&
                    row.team_id === season.team_id,
                );
                const team = teamMap.get(season.team_id);
                return (
                  <tr key={`${season.season}-${season.team_id}`}>
                    <td data-label="Season / team">
                      <strong>{season.season}</strong>
                      <small>
                        {team
                          ? `${team.team_abbr} · ${team.team_name}`
                          : season.team_id}
                      </small>
                    </td>
                    <td data-label="Actual">
                      {signed(season.epa_per_dropback)}
                    </td>
                    <td data-label="Expected">
                      {signed(prediction?.expected_epa_per_dropback)}
                    </td>
                    <td data-label="PAE">
                      <strong
                        className={
                          (prediction?.performance_above_expectation ?? 0) >= 0
                            ? "metric-up"
                            : "metric-down"
                        }
                      >
                        {signed(prediction?.performance_above_expectation)}
                      </strong>
                    </td>
                    <td data-label="CPOE">
                      {season.cpoe === null ? "—" : season.cpoe.toFixed(1)}
                    </td>
                    <td data-label="Success">{percent(season.success_rate)}</td>
                    <td data-label="Sack rate">{percent(season.sack_rate)}</td>
                    <td data-label="Dropbacks">{integer(season.dropbacks)}</td>
                    <td data-label="Eligibility">
                      {prediction ? (
                        <>
                          <StatusBadge value={prediction.eligibility_status} />
                          <small>{prediction.reliability} reliability</small>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td data-label="Season totals">
                      <details className="season-totals">
                        <summary>
                          {integer(season.total_yards)} yards ·{" "}
                          {integer(season.total_touchdowns)} TD
                        </summary>
                        <span>
                          Starter record: {starterRecord(season)} · Team points:{" "}
                          {integer(season.team_points_scored)}
                        </span>
                        <span>
                          Passing: {integer(season.passing_yards)} yards /{" "}
                          {integer(season.passing_touchdowns)} TD
                        </span>
                        <span>
                          Rushing: {integer(season.rushing_yards)} yards /{" "}
                          {integer(season.rushing_touchdowns)} TD
                        </span>
                        <span>
                          Completion: {percent(season.completion_percentage)} ·
                          Fumbles: {integer(season.fumbles)}
                        </span>
                      </details>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section-block">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Source-backed context</p>
            <h2>Coaching environments</h2>
          </div>
          <p>Intervals and evidence status are shown exactly as published.</p>
        </div>
        <div className="environment-grid">
          {seasons.map((season) => {
            const staff =
              staffMap.get(`${season.team_id}-${season.season}`) ?? [];
            return (
              <article
                className="environment-card"
                key={`${season.team_id}-${season.season}`}
              >
                <div>
                  <CalendarDays aria-hidden="true" />
                  <strong>
                    {season.season} ·{" "}
                    {teamMap.get(season.team_id)?.team_abbr ?? season.team_id}
                  </strong>
                </div>
                {staff.length ? (
                  <ul>
                    {staff.map((assignment) => (
                      <li key={assignment.assignment_key}>
                        <Link to={`/coaches/${assignment.coach_id}`}>
                          {assignment.canonical_name}
                        </Link>
                        <span>
                          {roleLabel(assignment.role)} · Weeks{" "}
                          {assignment.start_week}–{assignment.end_week}
                        </span>
                        <StatusBadge value={assignment.verification_status} />
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>No published staff assignment for this team-season.</p>
                )}
              </article>
            );
          })}
        </div>
      </section>

      <section className="provenance-panel">
        <div>
          <span>Expected-performance version</span>
          <strong>{latest?.data_version ?? "—"}</strong>
        </div>
        <div>
          <span>Model version</span>
          <strong>{latest?.model_version ?? "—"}</strong>
        </div>
        <div>
          <span>Metric version</span>
          <strong>{latestSeason?.metric_version ?? "—"}</strong>
        </div>
        <div>
          <span>Training cutoff</span>
          <strong>
            {latest?.payload.training_end_season
              ? String(latest.payload.training_end_season)
              : "See model metadata"}
          </strong>
        </div>
      </section>
    </section>
  );
}

function starterRecord(season: QbProfile["seasons"][number]): string {
  if (
    typeof season.starter_wins !== "number" ||
    typeof season.starter_losses !== "number" ||
    typeof season.starter_ties !== "number"
  )
    return "—";
  return `${season.starter_wins}-${season.starter_losses}-${season.starter_ties}`;
}
