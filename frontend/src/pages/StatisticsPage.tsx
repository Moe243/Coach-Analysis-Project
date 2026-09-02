import { useQuery } from "@tanstack/react-query";
import { ChevronDown, FilterX, Search, SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiGet, apiGetAll } from "../api/client";
import type {
  ApiPage,
  CoachAssignment,
  CoachRole,
  QbSeason,
  Team,
} from "../api/contracts";
import { DataErrorBoundary } from "../components/DataErrorBoundary";
import { EmptyState, ErrorState, LoadingState } from "../components/DataState";
import { Pagination } from "../components/Pagination";
import { integer, percent, roleLabel, signed } from "../lib/format";
import { useDebouncedValue } from "../hooks/useDebouncedValue";

const PAGE_SIZE = 25;
const roles: CoachRole[] = [
  "head_coach",
  "offensive_coordinator",
  "play_caller",
  "quarterbacks_coach",
];

interface Filters {
  player: string;
  coach: string;
  team: string;
  season: string;
  role: string;
  verification: string;
  eligibility: string;
  sort:
    | "name"
    | "season"
    | "dropbacks"
    | "epa"
    | "pae"
    | "passing_yards"
    | "passing_touchdowns"
    | "interceptions"
    | "total_touchdowns";
  minDropbacks: string;
  expanded: boolean;
  offset: number;
}

function getFilters(params: URLSearchParams): Filters {
  const sort = params.get("sort");
  return {
    player: params.get("player") ?? "",
    coach: params.get("coach") ?? "",
    team: params.get("team") ?? "",
    season: params.get("season") ?? "",
    role: params.get("role") ?? "",
    verification: params.get("verification") ?? "",
    eligibility: params.get("eligibility") ?? "",
    sort: [
      "name",
      "season",
      "dropbacks",
      "epa",
      "pae",
      "passing_yards",
      "passing_touchdowns",
      "interceptions",
      "total_touchdowns",
    ].includes(sort ?? "")
      ? (sort as Filters["sort"])
      : "dropbacks",
    minDropbacks: params.get("minDropbacks") ?? "",
    expanded: params.get("expanded") === "true",
    offset: Math.max(0, Number(params.get("offset") ?? 0) || 0),
  };
}

function PAECell({ value }: { value?: number | null }) {
  if (value === null || value === undefined)
    return <span title="No published value">—</span>;
  return (
    <strong className={value >= 0 ? "metric-up" : "metric-down"}>
      {signed(value)}
    </strong>
  );
}

export function StatisticsPage() {
  const [params, setParams] = useSearchParams();
  const filters = getFilters(params);
  const [playerInput, setPlayerInput] = useState(filters.player);
  const [coachInput, setCoachInput] = useState(filters.coach);
  const debouncedPlayer = useDebouncedValue(playerInput);
  const debouncedCoach = useDebouncedValue(coachInput);

  const setFilter = useCallback(
    (key: keyof Filters, value: string | number | boolean) => {
      setParams((current) => {
        const next = new URLSearchParams(current);
        if (
          value === "" ||
          value === false ||
          (key === "offset" && value === 0)
        )
          next.delete(key);
        else next.set(key, String(value));
        if (key !== "offset") next.delete("offset");
        return next;
      });
    },
    [setParams],
  );

  useEffect(() => {
    if (debouncedPlayer !== filters.player)
      setFilter("player", debouncedPlayer);
  }, [debouncedPlayer, filters.player, setFilter]);

  useEffect(() => {
    if (debouncedCoach !== filters.coach) setFilter("coach", debouncedCoach);
  }, [debouncedCoach, filters.coach, setFilter]);

  const teams = useQuery({
    queryKey: ["teams"],
    queryFn: ({ signal }) => apiGetAll<Team>("/teams", {}, signal),
    staleTime: Infinity,
  });
  const assignments = useQuery({
    queryKey: ["assignments", "all"],
    queryFn: ({ signal }) =>
      apiGetAll<CoachAssignment>("/assignments", {}, signal),
    staleTime: Infinity,
  });

  const assignmentFiltering = Boolean(
    filters.coach || filters.role || filters.verification,
  );
  const needsClientPagination =
    assignmentFiltering || Boolean(filters.minDropbacks);
  const qbQuery = useQuery({
    queryKey: [
      "qbs",
      filters.player,
      filters.team,
      filters.season,
      filters.eligibility,
      filters.sort,
      needsClientPagination ? "all" : filters.offset,
    ],
    queryFn: ({ signal }) => {
      const values = {
        search: filters.player,
        team_id: filters.team,
        season: filters.season,
        eligible:
          filters.eligibility === "eligible"
            ? true
            : filters.eligibility === "ineligible"
              ? false
              : undefined,
        sort: filters.sort,
      };
      return needsClientPagination
        ? apiGetAll<QbSeason>("/qbs", values, signal).then((items) => ({
            items,
            total: items.length,
            limit: items.length || PAGE_SIZE,
            offset: 0,
          }))
        : apiGet<ApiPage<QbSeason>>(
            "/qbs",
            { ...values, limit: PAGE_SIZE, offset: filters.offset },
            signal,
          );
    },
  });

  const assignmentMap = useMemo(() => {
    const map = new Map<string, CoachAssignment[]>();
    assignments.data?.forEach((assignment) => {
      const key = `${assignment.team_id}-${assignment.season}`;
      map.set(key, [...(map.get(key) ?? []), assignment]);
    });
    return map;
  }, [assignments.data]);

  const filteredRows = useMemo(() => {
    const min = Number(filters.minDropbacks || 0);
    return (qbQuery.data?.items ?? []).filter((row) => {
      if (row.position !== "QB") return false;
      if (min && row.dropbacks < min) return false;
      if (!assignmentFiltering) return true;
      const staff = assignmentMap.get(`${row.team_id}-${row.season}`) ?? [];
      return staff.some(
        (assignment) =>
          (!filters.coach ||
            assignment.canonical_name
              .toLowerCase()
              .includes(filters.coach.toLowerCase())) &&
          (!filters.role || assignment.role === filters.role) &&
          (!filters.verification ||
            assignment.verification_status === filters.verification),
      );
    });
  }, [
    assignmentFiltering,
    assignmentMap,
    filters.coach,
    filters.minDropbacks,
    filters.role,
    filters.verification,
    qbQuery.data?.items,
  ]);

  const total = needsClientPagination
    ? filteredRows.length
    : (qbQuery.data?.total ?? 0);
  const rows = needsClientPagination
    ? filteredRows.slice(filters.offset, filters.offset + PAGE_SIZE)
    : filteredRows;

  const teamMap = new Map(
    teams.data?.map((team) => [team.team_id, team]) ?? [],
  );

  const isLoading =
    qbQuery.isLoading || assignments.isLoading || teams.isLoading;
  const error = qbQuery.error || assignments.error || teams.error;
  const retry = () => {
    void Promise.all([
      qbQuery.refetch(),
      assignments.refetch(),
      teams.refetch(),
    ]);
  };
  const clearFilters = () => {
    setPlayerInput("");
    setCoachInput("");
    setParams({ sort: "dropbacks" });
  };

  return (
    <DataErrorBoundary>
      <section className="page statistics-page">
        <div className="page-heading">
          <div>
            <p className="eyebrow">2010–2025 · Quarterback-team seasons</p>
            <h1>Performance above expectation</h1>
            <p>
              Compare actual quarterback output with a strictly preseason
              baseline, then inspect the source-backed staff context around each
              season.
            </p>
          </div>
          <aside className="formula-card" aria-label="PAE formula">
            <span>PAE</span>
            <strong>Actual EPA/dropback − Expected EPA/dropback</strong>
            <small>Positive values exceeded the model expectation.</small>
          </aside>
        </div>

        <details className="metric-glossary">
          <summary>How these metrics are defined</summary>
          <dl>
            <div>
              <dt>EPA</dt>
              <dd>
                Expected points added by a play relative to the prior game
                state.
              </dd>
            </div>
            <div>
              <dt>EPA/dropback</dt>
              <dd>
                QB EPA over attempts, sacks, and scrambles, excluding kneels and
                spikes.
              </dd>
            </div>
            <div>
              <dt>Expected EPA/dropback</dt>
              <dd>
                The strictly preseason, expanding-window model prediction.
              </dd>
            </div>
            <div>
              <dt>PAE</dt>
              <dd>
                Actual EPA/dropback minus preseason Expected EPA/dropback.
              </dd>
            </div>
            <div>
              <dt>CPOE</dt>
              <dd>
                Completion percentage over expectation on eligible attempts.
              </dd>
            </div>
            <div>
              <dt>Success rate</dt>
              <dd>Share of eligible dropbacks with positive EPA.</dd>
            </div>
            <div>
              <dt>Sack rate</dt>
              <dd>Sacks divided by pass attempts plus sacks.</dd>
            </div>
            <div>
              <dt>Eligibility / reliability</dt>
              <dd>
                Eligibility uses the 200-dropback publication threshold;
                reliability is a separate sample-support label and neither is a
                coach-effect claim.
              </dd>
            </div>
          </dl>
        </details>

        <form
          className="filter-panel"
          onSubmit={(event) => event.preventDefault()}
        >
          <label className="search-field">
            <span>Player</span>
            <Search aria-hidden="true" />
            <input
              value={playerInput}
              onChange={(event) => setPlayerInput(event.target.value)}
              placeholder="Search quarterbacks"
            />
          </label>
          <label className="search-field">
            <span>Coach</span>
            <Search aria-hidden="true" />
            <input
              value={coachInput}
              onChange={(event) => setCoachInput(event.target.value)}
              placeholder="Search coaching context"
            />
          </label>
          <label>
            <span>Team</span>
            <select
              value={filters.team}
              onChange={(event) => setFilter("team", event.target.value)}
            >
              <option value="">All teams</option>
              {teams.data?.map((team) => (
                <option key={team.team_id} value={team.team_id}>
                  {team.team_abbr} · {team.team_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Season</span>
            <select
              value={filters.season}
              onChange={(event) => setFilter("season", event.target.value)}
            >
              <option value="">All seasons</option>
              {Array.from({ length: 16 }, (_, index) => 2025 - index).map(
                (season) => (
                  <option key={season}>{season}</option>
                ),
              )}
            </select>
          </label>
          <label>
            <span>Role</span>
            <select
              value={filters.role}
              onChange={(event) => setFilter("role", event.target.value)}
            >
              <option value="">All roles</option>
              {roles.map((role) => (
                <option key={role} value={role}>
                  {roleLabel(role)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Evidence</span>
            <select
              value={filters.verification}
              onChange={(event) =>
                setFilter("verification", event.target.value)
              }
            >
              <option value="">All statuses</option>
              <option value="verified">Verified</option>
              <option value="provisional">Provisional</option>
              <option value="conflicting">Conflicting</option>
            </select>
          </label>
          <label>
            <span>Eligibility</span>
            <select
              value={filters.eligibility}
              onChange={(event) => setFilter("eligibility", event.target.value)}
            >
              <option value="">All samples</option>
              <option value="eligible">200+ dropbacks</option>
              <option value="ineligible">Under 200</option>
            </select>
          </label>
          <label>
            <span>Sort</span>
            <select
              value={filters.sort}
              onChange={(event) => setFilter("sort", event.target.value)}
            >
              <option value="dropbacks">Dropbacks</option>
              <option value="epa">Actual EPA</option>
              <option value="pae">PAE</option>
              <option value="passing_yards">Passing yards</option>
              <option value="passing_touchdowns">Passing touchdowns</option>
              <option value="interceptions">Interceptions</option>
              <option value="total_touchdowns">Total touchdowns</option>
              <option value="season">Most recent</option>
              <option value="name">Player name</option>
            </select>
          </label>
          <details className="more-filters">
            <summary>
              <SlidersHorizontal aria-hidden="true" /> More filters{" "}
              <ChevronDown aria-hidden="true" />
            </summary>
            <label>
              <span>Minimum dropbacks</span>
              <input
                type="number"
                min="0"
                max="800"
                step="25"
                value={filters.minDropbacks}
                onChange={(event) =>
                  setFilter("minDropbacks", event.target.value)
                }
                placeholder="No minimum"
              />
            </label>
            <label className="check-field">
              <input
                type="checkbox"
                checked={filters.expanded}
                onChange={(event) =>
                  setFilter("expanded", event.target.checked)
                }
              />
              <span>Show expanded metrics</span>
            </label>
          </details>
          <button
            className="button button-ghost clear-button"
            type="button"
            onClick={clearFilters}
          >
            <FilterX aria-hidden="true" /> Clear
          </button>
        </form>

        <div className="results-meta">
          <p>
            <strong>{total.toLocaleString()}</strong> QB-team seasons
          </p>
          <p>
            Coach filters identify team-season coaching context and preserve the
            assignment intervals and evidence status shown in each result. They
            do not claim exact weekly QB-coach overlap.
          </p>
        </div>

        {isLoading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState error={error} retry={retry} />
        ) : rows.length === 0 ? (
          <EmptyState>
            Try removing a coach, team, season, or volume filter.
          </EmptyState>
        ) : (
          <>
            <div className="table-frame">
              <table>
                <thead>
                  <tr>
                    <th>Quarterback</th>
                    <th>Team</th>
                    <th>Season</th>
                    <th>Record</th>
                    <th title="Actual EPA divided by eligible quarterback dropbacks">
                      Actual EPA/DB
                    </th>
                    <th title="Strictly preseason model expectation">
                      Expected EPA/DB
                    </th>
                    <th title="Actual minus expected EPA per dropback">PAE</th>
                    <th>CPOE</th>
                    <th>Pass yards</th>
                    <th>Pass TD</th>
                    <th>INT</th>
                    <th>Total TD</th>
                    <th>Dropbacks</th>
                    {filters.expanded && <th>Details</th>}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const key = `${row.player_id}-${row.team_id}-${row.season}`;
                    const staff = (
                      assignmentMap.get(`${row.team_id}-${row.season}`) ?? []
                    ).filter(
                      (assignment) =>
                        !filters.role || assignment.role === filters.role,
                    );
                    return (
                      <tr key={key}>
                        <td data-label="Quarterback">
                          <Link
                            className="primary-link"
                            to={`/qbs/${row.player_id}`}
                          >
                            {row.display_name}
                          </Link>
                          <small>
                            {row.games} games · {integer(row.starts)} starts
                          </small>
                        </td>
                        <td data-label="Team">
                          {teamMap.get(row.team_id)?.team_abbr ?? row.team_id}
                        </td>
                        <td data-label="Season">{row.season}</td>
                        <td data-label="Record">{starterRecord(row)}</td>
                        <td data-label="Actual EPA/DB">
                          {signed(row.epa_per_dropback)}
                        </td>
                        <td data-label="Expected EPA/DB">
                          {signed(row.expected_epa_per_dropback)}
                        </td>
                        <td data-label="PAE">
                          <PAECell value={row.performance_above_expectation} />
                        </td>
                        <td data-label="CPOE">{numberOrDash(row.cpoe)}</td>
                        <td data-label="Passing yards">
                          {integer(row.passing_yards)}
                        </td>
                        <td data-label="Passing touchdowns">
                          {integer(row.passing_touchdowns)}
                        </td>
                        <td data-label="Interceptions">
                          {integer(row.interceptions)}
                        </td>
                        <td data-label="Total touchdowns">
                          {integer(row.total_touchdowns)}
                        </td>
                        <td data-label="Dropbacks">
                          <strong>{integer(row.dropbacks)}</strong>
                        </td>
                        {filters.expanded && (
                          <td data-label="Details">
                            <details className="season-totals">
                              <summary>Performance, context, and staff</summary>
                              <span>
                                Sample:{" "}
                                {row.pae_eligibility_status ??
                                  (row.qualifies_default
                                    ? "eligible"
                                    : "ineligible")}{" "}
                                · {row.pae_reliability ?? "unavailable"}{" "}
                                reliability
                              </span>
                              <span>
                                Completion: {integer(row.completions)}/
                                {integer(row.attempts)} (
                                {percent(row.completion_percentage)}) · YPA:{" "}
                                {decimal(row.yards_per_attempt)} · ANY/A:{" "}
                                {decimal(row.adjusted_net_yards_per_attempt)}
                              </span>
                              <span>
                                Success: {percent(row.success_rate)} · Sacks:{" "}
                                {integer(row.sacks)} ({percent(row.sack_rate)})
                                · INT rate: {percent(row.interception_rate)} ·
                                TD rate: {percent(row.passing_touchdown_rate)}
                              </span>
                              <span>
                                Rushing: {integer(row.rushing_yards)} yards /{" "}
                                {integer(row.rushing_touchdowns)} TD · Total:{" "}
                                {integer(row.total_yards)} yards /{" "}
                                {integer(row.total_touchdowns)} TD · Fumbles:{" "}
                                {integer(row.fumbles)} (
                                {integer(row.fumbles_lost)} lost)
                              </span>
                              <span>
                                Team: {integer(row.team_points_scored)} points (
                                {decimal(row.team_points_per_game)} per game,
                                rank {integer(row.team_points_per_game_rank)}) ·{" "}
                                {integer(row.team_total_offensive_yards)}{" "}
                                offensive yards · EPA/play{" "}
                                {signed(row.team_offensive_epa_per_play)} (rank{" "}
                                {integer(row.team_offensive_epa_per_play_rank)})
                              </span>
                              <div className="coach-stack">
                                {staff.length ? (
                                  staff.map((assignment) => (
                                    <Link
                                      key={assignment.assignment_key}
                                      to={`/coaches/${assignment.coach_id}`}
                                    >
                                      {assignment.canonical_name}
                                      <small>
                                        {roleLabel(assignment.role)} · Weeks{" "}
                                        {assignment.start_week}–
                                        {assignment.end_week} ·{" "}
                                        {assignment.verification_status}
                                      </small>
                                    </Link>
                                  ))
                                ) : (
                                  <span>No published coaching assignment.</span>
                                )}
                              </div>
                            </details>
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination
              total={total}
              offset={filters.offset}
              limit={PAGE_SIZE}
              onChange={(offset) => setFilter("offset", offset)}
            />
          </>
        )}
      </section>
    </DataErrorBoundary>
  );
}

function numberOrDash(value: number | null): string {
  return value === null ? "—" : value.toFixed(1);
}

function decimal(value?: number | null): string {
  return value === null || value === undefined ? "—" : value.toFixed(2);
}

function starterRecord(row: QbSeason): string {
  if (
    typeof row.starter_wins !== "number" ||
    typeof row.starter_losses !== "number" ||
    typeof row.starter_ties !== "number"
  )
    return "—";
  return `${row.starter_wins}-${row.starter_losses}-${row.starter_ties}`;
}
