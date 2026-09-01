import type { Core } from "cytoscape";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Focus,
  RotateCcw,
  Search,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, apiGet, apiGetAll } from "../api/client";
import type {
  CoachRole,
  CoachSummary,
  QbSeason,
  QbTeamSeasonRelationship,
  Relationship,
  RelationshipExplorerResponse,
  RelationshipMode,
  RelationshipNode,
  Team,
  VerificationStatus,
} from "../api/contracts";
import { EmptyState, ErrorState, LoadingState } from "../components/DataState";
import { NetworkGraph } from "../components/NetworkGraph";
import { StatusBadge } from "../components/StatusBadge";
import { integer, roleLabel, signed } from "../lib/format";
import {
  buildRelationshipGraph,
  coachRoles,
  type ExplorerFilters,
} from "../lib/relationshipGraph";

const seasons = Array.from({ length: 16 }, (_, index) => 2025 - index);
const modeLabels: Record<RelationshipMode, string> = {
  coach_journey: "Coach Journey",
  qb_journey: "QB Journey",
  team_history: "Team History",
  full_network: "Full Network",
};
const modeDescriptions: Record<RelationshipMode, string> = {
  coach_journey:
    "Follow one canonical coach across teams, seasons, roles, and QB contexts.",
  qb_journey:
    "Follow one canonical quarterback across every visible QB-team-season record.",
  team_history:
    "Read a team's coaching assignments and QB facts in chronological season lanes.",
  full_network:
    "Explore a bounded coach, quarterback, or team neighborhood without loading league history.",
};
const validModes = new Set(Object.keys(modeLabels));
const validVerifications = new Set<VerificationStatus>([
  "unverified",
  "provisional",
  "verified",
  "conflicting",
]);

function nullableNumber(value: string | null): number | null {
  if (value === null || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function nodeLabel(node: RelationshipNode): string {
  if (node.node_type === "coach") return node.canonical_name;
  if (node.node_type === "quarterback") return node.display_name;
  return `${node.team_abbr} ${node.season}`;
}

function relationshipTitle(
  relationship: Relationship,
  nodes: Map<string, RelationshipNode>,
): string {
  const source = nodes.get(relationship.source_node_id);
  const target = nodes.get(relationship.target_node_id);
  return `${source ? nodeLabel(source) : relationship.source_node_id} → ${target ? nodeLabel(target) : relationship.target_node_id}`;
}

function RelationshipBadges({ relationship }: { relationship: Relationship }) {
  if (relationship.relationship_type === "qb_team_season") {
    return (
      <div className="badge-row">
        <StatusBadge
          value={relationship.qualifies_default ? "eligible" : "ineligible"}
        />
        {relationship.reliability && (
          <StatusBadge value={relationship.reliability} />
        )}
        {relationship.is_out_of_sample && <StatusBadge value="out of sample" />}
      </div>
    );
  }
  return (
    <div className="badge-row">
      <StatusBadge value={relationship.verification_status} />
      <StatusBadge value={`${relationship.confidence_level} confidence`} />
      {relationship.is_interim && <StatusBadge value="interim" />}
      {relationship.is_shared && <StatusBadge value="shared duty" />}
      {relationship.is_retained && <StatusBadge value="retained" />}
      {relationship.is_provisional && (
        <StatusBadge value="provisional evidence" />
      )}
    </div>
  );
}

function QbMetrics({
  relationship,
}: {
  relationship: QbTeamSeasonRelationship;
}) {
  return (
    <dl className="relationship-metrics">
      <div>
        <dt>Dropbacks</dt>
        <dd>{integer(relationship.dropbacks)}</dd>
      </div>
      <div>
        <dt>Actual EPA/dropback</dt>
        <dd>{signed(relationship.actual_epa_per_dropback)}</dd>
      </div>
      <div>
        <dt>Expected EPA/dropback</dt>
        <dd>{signed(relationship.expected_epa_per_dropback)}</dd>
      </div>
      <div>
        <dt>PAE</dt>
        <dd>{signed(relationship.performance_above_expectation)}</dd>
      </div>
    </dl>
  );
}

export function NetworkPage() {
  const [params, setParams] = useSearchParams();
  const rawMode = params.get("mode") ?? "team_history";
  const mode = (
    validModes.has(rawMode) ? rawMode : "team_history"
  ) as RelationshipMode;
  const startSeason = Number(params.get("start_season") ?? 2020);
  const endSeason = Number(params.get("end_season") ?? 2025);
  const coachId = params.get("coach_id") ?? "";
  const playerId = params.get("player_id") ?? "";
  const teamId = params.get("team_id") ?? "";
  const anchorType = params.get("anchor") ?? "team";
  const selected = params.get("selected");
  const focused = params.get("focus");
  const verificationValue = params.get("verification") ?? "";
  const verification = validVerifications.has(
    verificationValue as VerificationStatus,
  )
    ? (verificationValue as VerificationStatus)
    : "";
  const includeProvisional = params.get("provisional") !== "exclude";
  const roleParameter = params.get("roles") ?? coachRoles.join(",");
  const roles = useMemo(
    () =>
      new Set(
        roleParameter
          .split(",")
          .filter((role): role is CoachRole =>
            coachRoles.includes(role as CoachRole),
          ),
      ),
    [roleParameter],
  );
  const showCoaches = params.get("coaches") !== "hide";
  const showQuarterbacks = params.get("quarterbacks") !== "hide";
  const showTeamSeasons = params.get("team_seasons") !== "hide";
  const eligibleOnly = params.get("eligible") === "true";
  const minimumDropbacks = Math.max(
    0,
    Number(params.get("min_dropbacks") ?? 0) || 0,
  );
  const paeMinimum = nullableNumber(params.get("pae_min"));
  const paeMaximum = nullableNumber(params.get("pae_max"));
  const interimOnly = params.get("interim") === "only";
  const sharedOnly = params.get("shared") === "only";
  const coreRef = useRef<Core | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [compact, setCompact] = useState(
    () => typeof window !== "undefined" && window.innerWidth <= 800,
  );

  const setUrl = useCallback(
    (updates: Record<string, string | number | boolean | null>) => {
      setParams((current) => {
        const next = new URLSearchParams(current);
        Object.entries(updates).forEach(([key, value]) => {
          if (value === null || value === "" || value === false)
            next.delete(key);
          else next.set(key, String(value));
        });
        return next;
      });
    },
    [setParams],
  );

  useEffect(() => {
    const onResize = () => setCompact(window.innerWidth <= 800);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const teams = useQuery({
    queryKey: ["teams"],
    queryFn: ({ signal }) => apiGetAll<Team>("/teams", {}, signal),
    staleTime: Infinity,
  });
  const coaches = useQuery({
    queryKey: ["coaches", "explorer-options"],
    queryFn: ({ signal }) => apiGetAll<CoachSummary>("/coaches", {}, signal),
    staleTime: Infinity,
  });
  const quarterbacks = useQuery({
    queryKey: ["qbs", "explorer-options"],
    queryFn: ({ signal }) => apiGetAll<QbSeason>("/qbs", {}, signal),
    staleTime: Infinity,
  });
  const coachOptions = useMemo(
    () =>
      [
        ...new Map(
          (coaches.data ?? []).map((coach) => [coach.coach_id, coach]),
        ).values(),
      ].sort((left, right) =>
        left.canonical_name.localeCompare(right.canonical_name),
      ),
    [coaches.data],
  );
  const quarterbackOptions = useMemo(
    () =>
      [
        ...new Map(
          (quarterbacks.data ?? []).map((qb) => [qb.player_id, qb]),
        ).values(),
      ].sort((left, right) =>
        left.display_name.localeCompare(right.display_name),
      ),
    [quarterbacks.data],
  );
  const teamOptions = useMemo(
    () =>
      [...(teams.data ?? [])].sort((left, right) =>
        left.team_abbr.localeCompare(right.team_abbr),
      ),
    [teams.data],
  );

  const anchor =
    mode === "coach_journey"
      ? coachId
      : mode === "qb_journey"
        ? playerId
        : mode === "team_history"
          ? teamId
          : anchorType === "coach"
            ? coachId
            : anchorType === "qb"
              ? playerId
              : teamId;
  const invalidUrl =
    !validModes.has(rawMode) ||
    !Number.isInteger(startSeason) ||
    !Number.isInteger(endSeason) ||
    startSeason < 2010 ||
    endSeason > 2025 ||
    startSeason > endSeason ||
    (mode === "full_network" && endSeason - startSeason + 1 > 5) ||
    (verificationValue !== "" && !verification);
  const ready = Boolean(anchor) && !invalidUrl;

  const explorer = useQuery({
    queryKey: [
      "relationship-explorer",
      mode,
      coachId,
      playerId,
      teamId,
      anchorType,
      startSeason,
      endSeason,
      verification,
      includeProvisional,
    ],
    queryFn: ({ signal }) =>
      apiGet<RelationshipExplorerResponse>(
        "/relationships/explorer",
        {
          mode,
          coach_id:
            mode === "coach_journey" ||
            (mode === "full_network" && anchorType === "coach")
              ? coachId
              : undefined,
          player_id:
            mode === "qb_journey" ||
            (mode === "full_network" && anchorType === "qb")
              ? playerId
              : undefined,
          team_id:
            mode === "team_history" ||
            (mode === "full_network" && anchorType === "team")
              ? teamId
              : undefined,
          start_season: startSeason,
          end_season: endSeason,
          verification_status: verification || undefined,
          include_provisional: includeProvisional,
        },
        signal,
      ),
    enabled: ready,
  });

  const filters: ExplorerFilters = useMemo(
    () => ({
      roles,
      showCoaches,
      showQuarterbacks,
      showTeamSeasons,
      eligibleOnly,
      minimumDropbacks,
      paeMinimum,
      paeMaximum,
      interimOnly,
      sharedOnly,
    }),
    [
      eligibleOnly,
      interimOnly,
      minimumDropbacks,
      paeMaximum,
      paeMinimum,
      roles,
      sharedOnly,
      showCoaches,
      showQuarterbacks,
      showTeamSeasons,
    ],
  );
  const graph = useMemo(
    () =>
      explorer.data
        ? buildRelationshipGraph(explorer.data, filters, compact)
        : null,
    [compact, explorer.data, filters],
  );
  const nodeMap = useMemo(
    () => new Map(graph?.nodes.map((node) => [node.node_id, node]) ?? []),
    [graph?.nodes],
  );
  const selectedNode = selected ? nodeMap.get(selected) : undefined;
  const selectedRelationships = selected
    ? (graph?.relationshipsByNode.get(selected) ?? [])
    : [];

  useEffect(() => {
    if (selected && graph && !nodeMap.has(selected)) setUrl({ selected: null });
  }, [graph, nodeMap, selected, setUrl]);

  const register = useCallback((core: Core | null) => {
    coreRef.current = core;
  }, []);
  const selectNode = useCallback(
    (nodeId: string) => setUrl({ selected: nodeId }),
    [setUrl],
  );
  const focusNode = useCallback(
    (nodeId: string) => {
      const node = nodeMap.get(nodeId);
      if (!node) return;
      setHistory((current) => [...current, params.toString()]);
      if (node.node_type === "coach") {
        setUrl({
          mode: "coach_journey",
          coach_id: node.coach_id,
          selected: nodeId,
          focus: nodeId,
        });
      } else if (node.node_type === "quarterback") {
        setUrl({
          mode: "qb_journey",
          player_id: node.player_id,
          selected: nodeId,
          focus: nodeId,
        });
      } else {
        setUrl({
          mode: "team_history",
          team_id: node.team_id,
          start_season: node.season,
          end_season: node.season,
          selected: nodeId,
          focus: nodeId,
        });
      }
    },
    [nodeMap, params, setUrl],
  );
  const goBack = () => {
    const previous = history.at(-1);
    if (!previous) return;
    setHistory((current) => current.slice(0, -1));
    setParams(new URLSearchParams(previous));
  };
  const reset = () => {
    setUrl({
      selected: null,
      focus: null,
      roles: null,
      verification: null,
      provisional: null,
      coaches: null,
      quarterbacks: null,
      team_seasons: null,
      eligible: null,
      min_dropbacks: null,
      pae_min: null,
      pae_max: null,
      interim: null,
      shared: null,
    });
    coreRef.current?.fit(undefined, 36);
  };
  const updateRole = (role: CoachRole, checked: boolean) => {
    const next = new Set(roles);
    if (checked) next.add(role);
    else next.delete(role);
    setUrl({ roles: coachRoles.filter((value) => next.has(value)).join(",") });
  };
  const lookupError = teams.error || coaches.error || quarterbacks.error;
  const error = lookupError || explorer.error;
  const retry = () => {
    void Promise.all([
      teams.refetch(),
      coaches.refetch(),
      quarterbacks.refetch(),
      ...(ready ? [explorer.refetch()] : []),
    ]);
  };

  return (
    <section className="page network-page relationship-explorer">
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            Canonical entities · Source-backed intervals · API v1.2
          </p>
          <h1>Relationship Explorer</h1>
          <p>
            Trace coaches and quarterbacks through authoritative team-seasons.
            Connections describe team-season context and source-backed
            assignments—not influence or causation.
          </p>
        </div>
        <aside className="formula-card" aria-label="PAE interpretation">
          <span>QB context</span>
          <strong>Actual EPA/dropback − Expected EPA/dropback = PAE</strong>
          <small>
            QB performance relative to preseason expectation in this
            team/coaching environment.
          </small>
        </aside>
      </div>

      <div className="explorer-primary-controls filter-panel">
        <label>
          <span>View</span>
          <select
            value={mode}
            onChange={(event) =>
              setUrl({ mode: event.target.value, selected: null, focus: null })
            }
          >
            {Object.entries(modeLabels).map(([value, label]) => (
              <option value={value} key={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {mode === "full_network" && (
          <label>
            <span>Start from</span>
            <select
              value={anchorType}
              onChange={(event) => setUrl({ anchor: event.target.value })}
            >
              <option value="coach">Coach</option>
              <option value="qb">Quarterback</option>
              <option value="team">Team</option>
            </select>
          </label>
        )}
        {(mode === "coach_journey" ||
          (mode === "full_network" && anchorType === "coach")) && (
          <label className="explorer-focus-control">
            <span>Coach</span>
            <select
              value={coachId}
              onChange={(event) =>
                setUrl({ coach_id: event.target.value, selected: null })
              }
            >
              <option value="">Choose a coach</option>
              {coachOptions.map((coach) => (
                <option value={coach.coach_id} key={coach.coach_id}>
                  {coach.canonical_name}
                </option>
              ))}
            </select>
          </label>
        )}
        {(mode === "qb_journey" ||
          (mode === "full_network" && anchorType === "qb")) && (
          <label className="explorer-focus-control">
            <span>Quarterback</span>
            <select
              value={playerId}
              onChange={(event) =>
                setUrl({ player_id: event.target.value, selected: null })
              }
            >
              <option value="">Choose a quarterback</option>
              {quarterbackOptions.map((qb) => (
                <option value={qb.player_id} key={qb.player_id}>
                  {qb.display_name}
                </option>
              ))}
            </select>
          </label>
        )}
        {(mode === "team_history" ||
          (mode === "full_network" && anchorType === "team")) && (
          <label className="explorer-focus-control">
            <span>Team</span>
            <select
              value={teamId}
              onChange={(event) =>
                setUrl({ team_id: event.target.value, selected: null })
              }
            >
              <option value="">Choose a team</option>
              {teamOptions.map((team) => (
                <option value={team.team_id} key={team.team_id}>
                  {team.team_abbr} · {team.team_name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          <span>Start season</span>
          <select
            value={startSeason}
            onChange={(event) => setUrl({ start_season: event.target.value })}
          >
            {seasons.map((season) => (
              <option key={season}>{season}</option>
            ))}
          </select>
        </label>
        <label>
          <span>End season</span>
          <select
            value={endSeason}
            onChange={(event) => setUrl({ end_season: event.target.value })}
          >
            {seasons.map((season) => (
              <option key={season}>{season}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Evidence</span>
          <select
            value={verification}
            onChange={(event) => {
              const value = event.target.value;
              setUrl({
                verification: value,
                provisional:
                  value === "provisional"
                    ? "include"
                    : params.get("provisional"),
              });
            }}
          >
            <option value="">Any status</option>
            <option value="verified">Verified</option>
            <option value="provisional">Provisional</option>
            <option value="conflicting">Conflicting</option>
            <option value="unverified">Unverified</option>
          </select>
        </label>
        <details className="explorer-advanced">
          <summary>
            <Search aria-hidden="true" /> Show & filter
          </summary>
          <div className="explorer-advanced-grid">
            <fieldset>
              <legend>Coach roles</legend>
              {coachRoles.map((role) => (
                <label key={role}>
                  <input
                    type="checkbox"
                    checked={roles.has(role)}
                    onChange={(event) => updateRole(role, event.target.checked)}
                  />
                  {roleLabel(role)}
                </label>
              ))}
            </fieldset>
            <fieldset>
              <legend>Entities & evidence</legend>
              <label>
                <input
                  type="checkbox"
                  checked={showCoaches}
                  onChange={(event) =>
                    setUrl({ coaches: event.target.checked ? null : "hide" })
                  }
                />{" "}
                Coaches
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={showQuarterbacks}
                  onChange={(event) =>
                    setUrl({
                      quarterbacks: event.target.checked ? null : "hide",
                    })
                  }
                />{" "}
                Quarterbacks
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={showTeamSeasons}
                  onChange={(event) =>
                    setUrl({
                      team_seasons: event.target.checked ? null : "hide",
                    })
                  }
                />{" "}
                Team-Seasons
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={includeProvisional}
                  onChange={(event) =>
                    setUrl({
                      provisional: event.target.checked ? "include" : "exclude",
                      verification: event.target.checked
                        ? verification
                        : verification === "provisional"
                          ? null
                          : verification,
                    })
                  }
                />{" "}
                Include provisional
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={interimOnly}
                  onChange={(event) =>
                    setUrl({ interim: event.target.checked ? "only" : null })
                  }
                />{" "}
                Interim assignments only
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={sharedOnly}
                  onChange={(event) =>
                    setUrl({ shared: event.target.checked ? "only" : null })
                  }
                />{" "}
                Shared duties only
              </label>
            </fieldset>
            <fieldset>
              <legend>QB facts</legend>
              <label>
                <input
                  type="checkbox"
                  checked={eligibleOnly}
                  onChange={(event) =>
                    setUrl({ eligible: event.target.checked ? "true" : null })
                  }
                />{" "}
                Eligible QBs only
              </label>
              <label className="stacked-input">
                <span>Minimum dropbacks</span>
                <input
                  type="number"
                  min="0"
                  value={minimumDropbacks}
                  onChange={(event) =>
                    setUrl({ min_dropbacks: event.target.value })
                  }
                />
              </label>
              <label className="stacked-input">
                <span>Minimum PAE</span>
                <input
                  type="number"
                  step="0.01"
                  value={paeMinimum ?? ""}
                  onChange={(event) => setUrl({ pae_min: event.target.value })}
                />
              </label>
              <label className="stacked-input">
                <span>Maximum PAE</span>
                <input
                  type="number"
                  step="0.01"
                  value={paeMaximum ?? ""}
                  onChange={(event) => setUrl({ pae_max: event.target.value })}
                />
              </label>
            </fieldset>
          </div>
        </details>
      </div>

      <div className="explorer-mode-strip">
        <div>
          <span>Current view</span>
          <strong>{modeLabels[mode]}</strong>
          <p>{modeDescriptions[mode]}</p>
        </div>
        <div className="explorer-actions" aria-label="Explorer navigation">
          <button
            className="button button-secondary"
            type="button"
            disabled={!selectedNode}
            onClick={() => selectedNode && focusNode(selectedNode.node_id)}
          >
            <Focus aria-hidden="true" /> Focus
          </button>
          <button className="button button-ghost" type="button" onClick={reset}>
            <RotateCcw aria-hidden="true" /> Reset
          </button>
          <button
            className="button button-ghost"
            type="button"
            disabled={!history.length}
            onClick={goBack}
          >
            <ArrowLeft aria-hidden="true" /> Back
          </button>
        </div>
      </div>

      {invalidUrl ? (
        <EmptyState title="Invalid explorer URL">
          Use seasons from 2010–2025, keep the start before the end, and limit
          Full Network to five seasons.
        </EmptyState>
      ) : lookupError || (ready && explorer.isLoading) ? (
        lookupError ? (
          <ErrorState error={lookupError} retry={retry} />
        ) : (
          <LoadingState label="Building Relationship Explorer" />
        )
      ) : error ? (
        error instanceof ApiError && error.status === 413 ? (
          <div className="state-panel state-error" role="alert">
            <Search aria-hidden="true" />
            <div>
              <strong>Relationship scope is too large</strong>
              <p>
                {error.message}. Narrow the year range, team, roles, evidence,
                or focused entity. No partial graph was returned.
              </p>
              <button
                className="button button-secondary"
                type="button"
                onClick={retry}
              >
                Retry narrowed scope
              </button>
            </div>
          </div>
        ) : (
          <ErrorState error={error as Error} retry={retry} />
        )
      ) : !ready ? (
        <EmptyState
          title={`Choose a ${mode === "qb_journey" ? "quarterback" : mode === "coach_journey" ? "coach" : "team"}`}
        >
          Select a canonical anchor to build this bounded relationship view.
        </EmptyState>
      ) : !graph || graph.relationships.length === 0 ? (
        <EmptyState title="No visible relationships">
          No relationships match these filters. QB facts without visible coach
          assignments are valid and remain visible whenever they meet the QB
          filters.
        </EmptyState>
      ) : (
        <>
          <div className="network-layout">
            <div className="graph-panel">
              <div className="graph-toolbar">
                <p>
                  <strong>{graph.nodes.length}</strong> canonical entities ·{" "}
                  <strong>{graph.relationships.length}</strong> relationships ·{" "}
                  {startSeason}–{endSeason}
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
                    onClick={() => coreRef.current?.fit(undefined, 36)}
                  >
                    Fit graph
                  </button>
                </div>
              </div>
              <NetworkGraph
                elements={graph.elements}
                selected={selected ?? null}
                onSelect={selectNode}
                register={register}
              />
              <div className="network-legend">
                <span>
                  <i className="legend-coach" /> Coach
                </span>
                <span>
                  <i className="legend-qb" /> Quarterback
                </span>
                <span>
                  <i className="legend-team" /> Team-Season
                </span>
                <span>
                  <i className="legend-provisional" /> Provisional assignment
                </span>
              </div>
            </div>
            <aside className="selection-panel" aria-live="polite">
              {selectedNode ? (
                <>
                  <p className="eyebrow">
                    Selected {selectedNode.node_type.replace("_", " ")}
                  </p>
                  <h2>{nodeLabel(selectedNode)}</h2>
                  {focused === selectedNode.node_id && (
                    <StatusBadge value="focused" />
                  )}
                  <p>
                    {selectedRelationships.length} visible relationship
                    {selectedRelationships.length === 1 ? "" : "s"}. Unrelated
                    graph elements are faded.
                  </p>
                  {selectedNode.node_type === "coach" && (
                    <Link
                      className="button button-secondary"
                      to={`/coaches/${selectedNode.coach_id}`}
                    >
                      Open coach profile
                    </Link>
                  )}
                  {selectedNode.node_type === "quarterback" && (
                    <Link
                      className="button button-secondary"
                      to={`/qbs/${selectedNode.player_id}`}
                    >
                      Open QB profile
                    </Link>
                  )}
                  {selectedRelationships.map((relationship) => (
                    <div
                      className="selection-relationship"
                      key={relationship.relationship_id}
                    >
                      <strong>
                        {relationshipTitle(relationship, nodeMap)}
                      </strong>
                      {relationship.relationship_type === "coach_assignment" ? (
                        <small>
                          {roleLabel(relationship.role)} · Weeks{" "}
                          {relationship.start_week}–{relationship.end_week} ·{" "}
                          {relationship.interval_basis.replaceAll("_", " ")}
                        </small>
                      ) : (
                        <QbMetrics relationship={relationship} />
                      )}
                      <RelationshipBadges relationship={relationship} />
                    </div>
                  ))}
                </>
              ) : (
                <>
                  <p className="eyebrow">Explorer detail</p>
                  <h2>Select an entity</h2>
                  <p>
                    Select a coach, quarterback, or Team-Season in the graph or
                    accessible explorer. Its direct context will highlight here
                    and in the graph.
                  </p>
                </>
              )}
            </aside>
          </div>

          <section
            className="accessible-network"
            aria-labelledby="relationship-list-heading"
          >
            <div className="section-heading">
              <div>
                <p className="eyebrow">Equivalent keyboard exploration</p>
                <h2 id="relationship-list-heading">
                  Relationship explorer list
                </h2>
              </div>
              <p>
                Every card preserves the authoritative relationship grain and
                the same Select and Focus actions.
              </p>
            </div>
            <div
              className="accessible-entity-list"
              aria-label="Visible canonical entities"
            >
              {graph.nodes.map((node) => (
                <article
                  key={node.node_id}
                  className={
                    selected === node.node_id ? "is-selected" : undefined
                  }
                  aria-current={selected === node.node_id ? "true" : undefined}
                >
                  <span>{node.node_type.replace("_", " ")}</span>
                  <strong>{nodeLabel(node)}</strong>
                  <div>
                    <button
                      type="button"
                      onClick={() => selectNode(node.node_id)}
                    >
                      Select
                    </button>
                    <button
                      type="button"
                      onClick={() => focusNode(node.node_id)}
                    >
                      Focus
                    </button>
                  </div>
                </article>
              ))}
            </div>
            <div className="connection-grid relationship-card-grid">
              {graph.relationships.map((relationship) => (
                <article key={relationship.relationship_id}>
                  <p className="relationship-grain">
                    {relationship.relationship_type === "coach_assignment"
                      ? `Assignment ${relationship.assignment_key}`
                      : `QB-team-season ${relationship.player_id} · ${relationship.team_id} · ${relationship.season}`}
                  </p>
                  <h3>{relationshipTitle(relationship, nodeMap)}</h3>
                  {relationship.relationship_type === "coach_assignment" ? (
                    <>
                      <p>
                        {roleLabel(relationship.role)} · Weeks{" "}
                        {relationship.start_week}–{relationship.end_week} ·{" "}
                        {relationship.interval_basis.replaceAll("_", " ")}
                      </p>
                      <p>
                        Source-backed coaching assignment for this stated
                        interval. QB connections on the same Team-Season are
                        team-season context, not exact weekly overlap.
                      </p>
                      <RelationshipBadges relationship={relationship} />
                      <p>
                        {relationship.citations.length} source citation
                        {relationship.citations.length === 1 ? "" : "s"}{" "}
                        available.
                      </p>
                      {relationship.citations.length > 0 && (
                        <ul className="relationship-citations">
                          {relationship.citations.map((citation) => (
                            <li key={citation.source_url}>
                              <a
                                href={citation.source_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {citation.source_title ??
                                  "Open assignment source"}
                              </a>
                              {citation.evidence_locator && (
                                <small>{citation.evidence_locator}</small>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}
                    </>
                  ) : (
                    <>
                      <p>
                        QB performance relative to preseason expectation in this
                        team/coaching environment.
                      </p>
                      <QbMetrics relationship={relationship} />
                      <RelationshipBadges relationship={relationship} />
                      <small>
                        Metric {relationship.metric_version} · Model{" "}
                        {relationship.model_version ?? "unavailable"} ·
                        Publication {relationship.publication_version}
                      </small>
                    </>
                  )}
                  <div className="relationship-actions">
                    <button
                      type="button"
                      onClick={() => selectNode(relationship.source_node_id)}
                    >
                      Select{" "}
                      {relationship.relationship_type === "coach_assignment"
                        ? "coach"
                        : "QB"}
                    </button>
                    <button
                      type="button"
                      onClick={() => selectNode(relationship.target_node_id)}
                    >
                      Select Team-Season
                    </button>
                  </div>
                </article>
              ))}
            </div>
            <div
              className="accessible-explorer-navigation"
              aria-label="Accessible explorer navigation"
            >
              <button
                className="button button-secondary"
                type="button"
                disabled={!selectedNode}
                onClick={() => selectedNode && focusNode(selectedNode.node_id)}
              >
                Focus selected
              </button>
              <button
                className="button button-ghost"
                type="button"
                onClick={reset}
              >
                Reset explorer
              </button>
              <button
                className="button button-ghost"
                type="button"
                disabled={!history.length}
                onClick={goBack}
              >
                Back to prior focus
              </button>
            </div>
          </section>
        </>
      )}
    </section>
  );
}
