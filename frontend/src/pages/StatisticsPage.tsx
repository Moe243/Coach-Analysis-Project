import { useQueries, useQuery } from "@tanstack/react-query";
import { ChevronDown, FilterX, Search, SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, apiGet, apiGetAll } from "../api/client";
import type {
  ApiPage,
  CoachAssignment,
  CoachRole,
  QbPae,
  QbSeason,
  Team,
} from "../api/contracts";
import { DataErrorBoundary } from "../components/DataErrorBoundary";
import { EmptyState, ErrorState, LoadingState } from "../components/DataState";
import { Pagination } from "../components/Pagination";
import { StatusBadge } from "../components/StatusBadge";
import {
  integer,
  payloadNumber,
  percent,
  roleLabel,
  signed,
} from "../lib/format";
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
  sort: "name" | "season" | "dropbacks" | "epa";
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
    sort: ["name", "season", "dropbacks", "epa"].includes(sort ?? "")
      ? (sort as Filters["sort"])
      : "dropbacks",
    minDropbacks: params.get("minDropbacks") ?? "",
    expanded: params.get("expanded") === "true",
    offset: Math.max(0, Number(params.get("offset") ?? 0) || 0),
  };
}

function PAECell({ pae }: { pae?: QbPae }) {
  if (!pae) return <span title="No published value">—</span>;
  return (
    <strong
      className={
        pae.performance_above_expectation >= 0 ? "metric-up" : "metric-down"
      }
    >
      {signed(pae.performance_above_expectation)}
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

  const paeQueries = useQueries({
    queries: rows.map((row) => ({
      queryKey: ["qb-pae", row.player_id],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        apiGet<ApiPage<QbPae>>(
          `/qbs/${row.player_id}/pae`,
          { limit: 50 },
          signal,
        ).catch((error: unknown) => {
          if (error instanceof ApiError && error.status === 404) {
            return { items: [], total: 0, limit: 50, offset: 0 };
          }
          throw error;
        }),
      staleTime: Infinity,
    })),
  });
  const paeByKey = new Map<string, QbPae>();
  paeQueries.forEach((query) =>
    query.data?.items.forEach((pae) =>
      paeByKey.set(`${pae.player_id}-${pae.team_id}-${pae.season}`, pae),
    ),
  );
  const teamMap = new Map(
    teams.data?.map((team) => [team.team_id, team]) ?? [],
  );

  const paeLoading = paeQueries.some((query) => query.isLoading);
  const paeError = paeQueries.find((query) => query.error)?.error;
  const isLoading =
    qbQuery.isLoading || assignments.isLoading || teams.isLoading || paeLoading;
  const error = qbQuery.error || assignments.error || teams.error || paeError;
  const retry = () => {
    void Promise.all([
      qbQuery.refetch(),
      assignments.refetch(),
      teams.refetch(),
      ...paeQueries.map((query) => query.refetch()),
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
                    <th>Season / team</th>
                    <th>Coaching context</th>
                    <th title="Actual EPA divided by eligible quarterback dropbacks">
                      Actual EPA/DB
                    </th>
                    <th title="Strictly preseason model expectation">
                      Expected EPA/DB
                    </th>
                    <th title="Actual minus expected EPA per dropback">PAE</th>
                    <th>CPOE</th>
                    <th>Dropbacks</th>
                    <th>Sample</th>
                    {filters.expanded && <th>Success</th>}
                    {filters.expanded && <th>Sack rate</th>}
                    {filters.expanded && <th>INT rate</th>}
                    {filters.expanded && <th>TD rate</th>}
                    {filters.expanded && <th>Starter record</th>}
                    {filters.expanded && <th>Comp.</th>}
                    {filters.expanded && <th>Total yards</th>}
                    {filters.expanded && <th>Total TD</th>}
                    {filters.expanded && <th>Fumbles</th>}
                    {filters.expanded && <th>Team points</th>}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const key = `${row.player_id}-${row.team_id}-${row.season}`;
                    const pae = paeByKey.get(key);
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
                        <td data-label="Season / team">
                          <strong>{row.season}</strong>
                          <span>
                            {teamMap.get(row.team_id)?.team_abbr ?? row.team_id}
                          </span>
                        </td>
                        <td data-label="Coaching context">
                          <div className="coach-stack">
                            {staff.length ? (
                              staff.slice(0, 3).map((assignment) => (
                                <Link
                                  key={assignment.assignment_key}
                                  to={`/coaches/${assignment.coach_id}`}
                                >
                                  {assignment.canonical_name}
                                  <small>
                                    {roleLabel(assignment.role)} ·{" "}
                                    {assignment.verification_status}
                                  </small>
                                </Link>
                              ))
                            ) : (
                              <span>—</span>
                            )}
                            {staff.length > 3 && (
                              <small>+{staff.length - 3} more intervals</small>
                            )}
                          </div>
                        </td>
                        <td data-label="Actual EPA/DB">
                          {signed(row.epa_per_dropback)}
                        </td>
                        <td data-label="Expected EPA/DB">
                          {signed(pae?.expected_epa_per_dropback)}
                        </td>
                        <td data-label="PAE">
                          <PAECell pae={pae} />
                        </td>
                        <td data-label="CPOE">{numberOrDash(row.cpoe)}</td>
                        <td data-label="Dropbacks">
                          <strong>{integer(row.dropbacks)}</strong>
                        </td>
                        <td data-label="Sample">
                          <StatusBadge
                            value={
                              pae?.eligibility_status ??
                              (row.qualifies_default
                                ? "eligible"
                                : "ineligible")
                            }
                          />
                          {pae && <small>{pae.reliability} reliability</small>}
                        </td>
                        {filters.expanded && (
                          <td data-label="Success">
                            {percent(row.success_rate)}
                          </td>
                        )}
                        {filters.expanded && (
                          <td data-label="Sack rate">
                            {percent(row.sack_rate)}
                          </td>
                        )}
                        {filters.expanded && (
                          <td data-label="INT rate">
                            {percent(
                              payloadNumber(row.payload, "interception_rate"),
                            )}
                          </td>
                        )}
                        {filters.expanded && (
                          <td data-label="TD rate">
                            {percent(
                              payloadNumber(row.payload, "touchdown_rate"),
                            )}
                          </td>
                        )}
                        {filters.expanded && (
                          <td data-label="Starter record">
                            {starterRecord(row)}
                          </td>
                        )}
                        {filters.expanded && (
                          <td data-label="Completion percentage">
                            {percent(row.completion_percentage)}
                          </td>
                        )}
                        {filters.expanded && (
                          <td data-label="Total yards">
                            {integer(row.total_yards)}
                          </td>
                        )}
                        {filters.expanded && (
                          <td data-label="Total touchdowns">
                            {integer(row.total_touchdowns)}
                          </td>
                        )}
                        {filters.expanded && (
                          <td data-label="Fumbles">{integer(row.fumbles)}</td>
                        )}
                        {filters.expanded && (
                          <td data-label="Team points">
                            {integer(row.team_points_scored)}
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

function starterRecord(row: QbSeason): string {
  if (
    typeof row.starter_wins !== "number" ||
    typeof row.starter_losses !== "number" ||
    typeof row.starter_ties !== "number"
  )
    return "—";
  return `${row.starter_wins}-${row.starter_losses}-${row.starter_ties}`;
}
