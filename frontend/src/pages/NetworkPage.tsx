import type { Core } from "cytoscape";
import { useQuery } from "@tanstack/react-query";
import { Focus, Search, ZoomIn, ZoomOut } from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiGetAll } from "../api/client";
import type {
  CoachAssignment,
  CoachRole,
  NetworkEdge,
  Team,
} from "../api/contracts";
import { EmptyState, ErrorState, LoadingState } from "../components/DataState";
import { NetworkGraph } from "../components/NetworkGraph";
import { StatusBadge } from "../components/StatusBadge";
import { roleLabel } from "../lib/format";

const roles: CoachRole[] = [
  "head_coach",
  "offensive_coordinator",
  "play_caller",
  "quarterbacks_coach",
];

export function NetworkPage() {
  const [params, setParams] = useSearchParams();
  const season = Number(params.get("season") ?? 2025);
  const teamId = params.get("team") ?? "";
  const verification = params.get("verification") ?? "";
  const role = params.get("role") ?? "";
  const search = params.get("search") ?? "";
  const [selected, setSelected] = useState<string | null>(null);
  const coreRef = useRef<Core | null>(null);
  const setFilter = (key: string, value: string | number) =>
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (value === "") next.delete(key);
      else next.set(key, String(value));
      return next;
    });
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
  const edges = useQuery({
    queryKey: ["network-edges", season, teamId, verification],
    queryFn: ({ signal }) =>
      apiGetAll<NetworkEdge>(
        "/network/edges",
        { season, team_id: teamId, verification_status: verification },
        signal,
      ),
  });
  const teamMap = useMemo(
    () => new Map(teams.data?.map((team) => [team.team_id, team]) ?? []),
    [teams.data],
  );
  const coachMap = useMemo(() => {
    const map = new Map<string, { id: string; name: string }>();
    assignments.data?.forEach((row) =>
      map.set(row.coach_id, { id: row.coach_id, name: row.canonical_name }),
    );
    return map;
  }, [assignments.data]);
  const filteredEdges = useMemo(
    () =>
      (edges.data ?? []).filter((edge) => {
        if (role && edge.source_role !== role && edge.target_role !== role)
          return false;
        if (search) {
          const source =
            coachMap.get(edge.source_coach_id)?.name.toLowerCase() ?? "";
          const target =
            coachMap.get(edge.target_coach_id)?.name.toLowerCase() ?? "";
          if (
            !source.includes(search.toLowerCase()) &&
            !target.includes(search.toLowerCase())
          )
            return false;
        }
        return true;
      }),
    [coachMap, edges.data, role, search],
  );
  const onSelect = useCallback((id: string) => setSelected(id), []);
  const register = useCallback((core: Core | null) => {
    coreRef.current = core;
  }, []);
  const selectedCoach =
    selected && !selected.startsWith("team:")
      ? coachMap.get(selected)
      : undefined;
  const selectedTeam = selected?.startsWith("team:")
    ? teamMap.get(selected.slice(5))
    : undefined;
  const selectedEdges = selected
    ? filteredEdges.filter((edge) =>
        [
          edge.source_coach_id,
          edge.target_coach_id,
          `team:${edge.team_id}`,
        ].includes(selected),
      )
    : [];
  const error = teams.error || assignments.error || edges.error;

  return (
    <section className="page network-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            Focused staff graph · Source-backed intervals
          </p>
          <h1>Coaching network</h1>
          <p>
            Explore coaches who served together during overlapping team-season
            intervals. Lines encode shared staff context—not influence,
            performance, or causation.
          </p>
        </div>
        <aside className="formula-card">
          <span>Default scope</span>
          <strong>One season at a time</strong>
          <small>Choose a team for a tighter, more readable graph.</small>
        </aside>
      </div>
      <div className="network-filters filter-panel">
        <label className="search-field">
          <span>Coach</span>
          <Search aria-hidden="true" />
          <input
            value={search}
            onChange={(event) => setFilter("search", event.target.value)}
            placeholder="Find a coach"
          />
        </label>
        <label>
          <span>Season</span>
          <select
            value={season}
            onChange={(event) => setFilter("season", event.target.value)}
          >
            {Array.from({ length: 16 }, (_, index) => 2025 - index).map(
              (value) => (
                <option key={value}>{value}</option>
              ),
            )}
          </select>
        </label>
        <label>
          <span>Team</span>
          <select
            value={teamId}
            onChange={(event) => setFilter("team", event.target.value)}
          >
            <option value="">All teams</option>
            {teams.data?.map((team) => (
              <option value={team.team_id} key={team.team_id}>
                {team.team_abbr} · {team.team_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Role</span>
          <select
            value={role}
            onChange={(event) => setFilter("role", event.target.value)}
          >
            <option value="">All roles</option>
            {roles.map((value) => (
              <option value={value} key={value}>
                {roleLabel(value)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Both assignments</span>
          <select
            value={verification}
            onChange={(event) => setFilter("verification", event.target.value)}
          >
            <option value="">Any evidence status</option>
            <option value="verified">Verified</option>
            <option value="provisional">Provisional</option>
          </select>
        </label>
        <button
          className="button button-secondary"
          type="button"
          onClick={() => {
            setParams({ season: "2025" });
            setSelected(null);
            coreRef.current?.fit(undefined, 30);
          }}
        >
          <Focus aria-hidden="true" /> Reset view
        </button>
      </div>
      {teams.isLoading || assignments.isLoading || edges.isLoading ? (
        <LoadingState label="Building focused network" />
      ) : error ? (
        <ErrorState error={error} retry={() => void edges.refetch()} />
      ) : !filteredEdges.length ? (
        <EmptyState>
          No overlapping staff connections match these filters.
        </EmptyState>
      ) : (
        <>
          <div className="network-layout">
            <div className="graph-panel">
              <div className="graph-toolbar">
                <p>
                  <strong>{filteredEdges.length}</strong> assignment connections
                  · {season}
                </p>
                <div>
                  <button
                    className="icon-button"
                    type="button"
                    onClick={() =>
                      coreRef.current?.zoom(coreRef.current.zoom() * 1.2)
                    }
                    aria-label="Zoom in"
                  >
                    <ZoomIn aria-hidden="true" />
                  </button>
                  <button
                    className="icon-button"
                    type="button"
                    onClick={() =>
                      coreRef.current?.zoom(coreRef.current.zoom() / 1.2)
                    }
                    aria-label="Zoom out"
                  >
                    <ZoomOut aria-hidden="true" />
                  </button>
                  <button
                    className="button button-ghost"
                    type="button"
                    onClick={() => coreRef.current?.fit(undefined, 30)}
                  >
                    Fit graph
                  </button>
                </div>
              </div>
              <NetworkGraph
                edges={filteredEdges}
                coaches={coachMap}
                teams={teamMap}
                selected={selected}
                onSelect={onSelect}
                register={register}
              />
              <div className="network-legend">
                <span>
                  <i className="legend-coach" /> Coach
                </span>
                <span>
                  <i className="legend-team" /> Team context
                </span>
                <span>
                  <i className="legend-provisional" /> Provisional edge
                </span>
              </div>
            </div>
            <aside className="selection-panel">
              {selectedCoach ? (
                <>
                  <p className="eyebrow">Selected coach</p>
                  <h2>{selectedCoach.name}</h2>
                  <p>
                    {selectedEdges.length} visible staff connections in this
                    filtered graph.
                  </p>
                  <Link
                    className="button button-secondary"
                    to={`/coaches/${selectedCoach.id}`}
                  >
                    Open coach profile
                  </Link>
                </>
              ) : selectedTeam ? (
                <>
                  <p className="eyebrow">Selected team</p>
                  <h2>{selectedTeam.team_name}</h2>
                  <p>
                    {selectedEdges.length} visible staff connections in {season}
                    .
                  </p>
                </>
              ) : (
                <>
                  <p className="eyebrow">Graph detail</p>
                  <h2>Select a node</h2>
                  <p>
                    Choose a coach or team hub to highlight its visible
                    connections and open source-backed details.
                  </p>
                </>
              )}
              {selectedEdges.length > 0 && (
                <ul>
                  {selectedEdges.slice(0, 10).map((edge) => (
                    <li
                      key={`${edge.source_assignment_key}-${edge.target_assignment_key}`}
                    >
                      <span>
                        {coachMap.get(edge.source_coach_id)?.name} ↔{" "}
                        {coachMap.get(edge.target_coach_id)?.name}
                      </span>
                      <small>
                        Weeks {edge.overlap_start_week}–{edge.overlap_end_week}
                      </small>
                    </li>
                  ))}
                </ul>
              )}
            </aside>
          </div>
          <section className="accessible-network">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Accessible graph alternative</p>
                <h2>Visible connections</h2>
              </div>
              <p>
                Each row preserves assignment status, confidence, interval, and
                shared-duty flags.
              </p>
            </div>
            <div className="connection-grid">
              {filteredEdges.map((edge) => (
                <article
                  key={`${edge.source_assignment_key}-${edge.target_assignment_key}`}
                >
                  <button
                    type="button"
                    onClick={() => setSelected(edge.source_coach_id)}
                  >
                    {coachMap.get(edge.source_coach_id)?.name ??
                      edge.source_coach_id}
                  </button>
                  <span>with</span>
                  <button
                    type="button"
                    onClick={() => setSelected(edge.target_coach_id)}
                  >
                    {coachMap.get(edge.target_coach_id)?.name ??
                      edge.target_coach_id}
                  </button>
                  <p>
                    {teamMap.get(edge.team_id)?.team_abbr ?? edge.team_id} ·
                    Weeks {edge.overlap_start_week}–{edge.overlap_end_week}
                  </p>
                  <div className="badge-row">
                    <StatusBadge value={edge.source_verification_status} />
                    <StatusBadge value={edge.target_verification_status} />
                    {(edge.source_is_shared || edge.target_is_shared) && (
                      <StatusBadge value="shared duty" />
                    )}
                  </div>
                </article>
              ))}
            </div>
          </section>
        </>
      )}
    </section>
  );
}
