import type { ElementDefinition, Position } from "cytoscape";
import type {
  CoachAssignmentRelationship,
  CoachRole,
  QbTeamSeasonRelationship,
  Relationship,
  RelationshipExplorerResponse,
  RelationshipMode,
  RelationshipNode,
} from "../api/contracts";

export const coachRoles: CoachRole[] = [
  "head_coach",
  "offensive_coordinator",
  "play_caller",
  "quarterbacks_coach",
];

export const RELATIONSHIP_GRAPH_VERSION = "relationship-graph-v2";

export interface ExplorerFilters {
  roles: ReadonlySet<CoachRole>;
  showCoaches: boolean;
  showQuarterbacks: boolean;
  showTeamSeasons: boolean;
  eligibleOnly: boolean;
  minimumDropbacks: number;
  paeMinimum: number | null;
  paeMaximum: number | null;
  interimOnly: boolean;
  sharedOnly: boolean;
}

export interface RelationshipGraphModel {
  elements: ElementDefinition[];
  positions: Record<string, Position>;
  nodes: RelationshipNode[];
  relationships: Relationship[];
  relationshipById: Map<string, Relationship>;
  relationshipsByNode: Map<string, Relationship[]>;
  appearanceCount: number;
  continuityCount: number;
  graphVersion: string;
}

interface Appearance {
  id: string;
  canonicalId: string;
  kind: "coach" | "quarterback" | "team_season";
  label: string;
  season: number;
  teamId: string;
  role?: CoachRole;
  startWeek?: number;
}

const roleOrder = new Map(coachRoles.map((role, index) => [role, index]));

function keepRelationship(
  relationship: Relationship,
  filters: ExplorerFilters,
): boolean {
  if (relationship.relationship_type === "coach_assignment") {
    if (!filters.showCoaches || !filters.showTeamSeasons) return false;
    if (!filters.roles.has(relationship.role)) return false;
    if (filters.interimOnly && !relationship.is_interim) return false;
    if (filters.sharedOnly && !relationship.is_shared) return false;
    return true;
  }
  if (!filters.showQuarterbacks || !filters.showTeamSeasons) return false;
  if (filters.eligibleOnly && !relationship.qualifies_default) return false;
  if (relationship.dropbacks < filters.minimumDropbacks) return false;
  const pae = relationship.performance_above_expectation;
  if (
    filters.paeMinimum !== null &&
    (pae === null || pae < filters.paeMinimum)
  ) {
    return false;
  }
  if (
    filters.paeMaximum !== null &&
    (pae === null || pae > filters.paeMaximum)
  ) {
    return false;
  }
  return true;
}

function nodeLabel(node: RelationshipNode): string {
  return node.node_type === "coach"
    ? node.canonical_name
    : node.node_type === "quarterback"
      ? node.display_name
      : `${node.team_abbr} ${node.season}`;
}

function coachAppearanceId(relationship: CoachAssignmentRelationship): string {
  return `appearance:coach:${relationship.coach_id}:${relationship.assignment_key}`;
}

function qbAppearanceId(relationship: QbTeamSeasonRelationship): string {
  return `appearance:qb:${relationship.player_id}:${relationship.team_id}:${relationship.season}`;
}

function buildAppearances(
  nodes: RelationshipNode[],
  relationships: Relationship[],
): Appearance[] {
  const byId = new Map(nodes.map((node) => [node.node_id, node]));
  const values: Appearance[] = [];
  nodes
    .filter((node) => node.node_type === "team_season")
    .forEach((node) =>
      values.push({
        id: node.node_id,
        canonicalId: node.node_id,
        kind: "team_season",
        label: nodeLabel(node),
        season: node.season,
        teamId: node.team_id,
      }),
    );
  relationships.forEach((relationship) => {
    const source = byId.get(relationship.source_node_id);
    if (!source) return;
    if (relationship.relationship_type === "coach_assignment") {
      values.push({
        id: coachAppearanceId(relationship),
        canonicalId: relationship.source_node_id,
        kind: "coach",
        label: `${nodeLabel(source)} · ${relationship.role.replaceAll("_", " ")}`,
        season: relationship.season,
        teamId: relationship.team_id,
        role: relationship.role,
        startWeek: relationship.start_week,
      });
    } else {
      values.push({
        id: qbAppearanceId(relationship),
        canonicalId: relationship.source_node_id,
        kind: "quarterback",
        label: nodeLabel(source),
        season: relationship.season,
        teamId: relationship.team_id,
      });
    }
  });
  return [...new Map(values.map((value) => [value.id, value])).values()].sort(
    (left, right) =>
      left.season - right.season ||
      left.teamId.localeCompare(right.teamId) ||
      (roleOrder.get(left.role ?? "head_coach") ?? -1) -
        (roleOrder.get(right.role ?? "head_coach") ?? -1) ||
      (left.startWeek ?? 0) - (right.startWeek ?? 0) ||
      left.id.localeCompare(right.id),
  );
}

function chronologicalPositions(
  values: Appearance[],
  mode: Exclude<RelationshipMode, "full_network">,
): Record<string, Position> {
  const positions: Record<string, Position> = {};
  const seasons = [...new Set(values.map((value) => value.season))].sort(
    (left, right) => left - right,
  );
  const seasonIndex = new Map(seasons.map((season, index) => [season, index]));
  const groups = new Map<string, Appearance[]>();
  values.forEach((value) => {
    const key = `${value.season}:${value.teamId}:${value.kind}:${value.role ?? ""}`;
    groups.set(key, [...(groups.get(key) ?? []), value]);
  });
  values.forEach((value) => {
    const y = 120 + (seasonIndex.get(value.season) ?? 0) * 390;
    const peers = groups.get(
      `${value.season}:${value.teamId}:${value.kind}:${value.role ?? ""}`,
    )!;
    const offset = peers.findIndex((peer) => peer.id === value.id) * 42;
    if (value.kind === "team_season") {
      positions[value.id] = { x: mode === "team_history" ? 480 : 560, y };
    } else if (mode === "qb_journey") {
      positions[value.id] =
        value.kind === "quarterback"
          ? { x: 230, y }
          : { x: 790 + (roleOrder.get(value.role!) ?? 0) * 155, y: y + offset };
    } else if (mode === "coach_journey") {
      positions[value.id] =
        value.kind === "coach"
          ? { x: 230, y: y + offset }
          : { x: 840 + offset * 2, y };
    } else if (value.kind === "quarterback") {
      positions[value.id] = { x: 980 + offset * 2, y };
    } else {
      const xByRole = [140, 300, 660, 820];
      positions[value.id] = {
        x: xByRole[roleOrder.get(value.role!) ?? 0],
        y: y + offset,
      };
    }
  });
  return positions;
}

function fullNetworkPositions(values: Appearance[]): Record<string, Position> {
  const positions: Record<string, Position> = {};
  const seasons = [...new Set(values.map((value) => value.season))].sort(
    (left, right) => left - right,
  );
  const teams = [...new Set(values.map((value) => value.teamId))].sort();
  const seasonIndex = new Map(seasons.map((season, index) => [season, index]));
  const teamIndex = new Map(teams.map((team, index) => [team, index]));
  const peerIndex = new Map<string, number>();
  values.forEach((value) => {
    const x = 360 + (seasonIndex.get(value.season) ?? 0) * 760;
    const baseY = 180 + (teamIndex.get(value.teamId) ?? 0) * 250;
    const key = `${value.season}:${value.teamId}:${value.kind}:${value.role ?? ""}`;
    const index = peerIndex.get(key) ?? 0;
    peerIndex.set(key, index + 1);
    if (value.kind === "team_season") positions[value.id] = { x, y: baseY };
    else if (value.kind === "quarterback") {
      positions[value.id] = { x: x + 210, y: baseY + index * 38 };
    } else {
      positions[value.id] = {
        x: x - 240 + (roleOrder.get(value.role!) ?? 0) * 52,
        y: baseY + index * 38,
      };
    }
  });
  return positions;
}

function continuityElements(values: Appearance[]): ElementDefinition[] {
  const byIdentity = new Map<string, Appearance[]>();
  values
    .filter((value) => value.kind !== "team_season")
    .forEach((value) =>
      byIdentity.set(value.canonicalId, [
        ...(byIdentity.get(value.canonicalId) ?? []),
        value,
      ]),
    );
  const result: ElementDefinition[] = [];
  [...byIdentity.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .forEach(([canonicalId, identityValues]) => {
      identityValues.sort(
        (left, right) =>
          left.season - right.season ||
          left.teamId.localeCompare(right.teamId) ||
          (left.startWeek ?? 0) - (right.startWeek ?? 0) ||
          left.id.localeCompare(right.id),
      );
      identityValues.slice(1).forEach((value, index) => {
        const previous = identityValues[index];
        result.push({
          data: {
            id: `continuity:${canonicalId}:${index}:${previous.id}:${value.id}`,
            source: previous.id,
            target: value.id,
            kind: "identity_continuity",
            relationshipType: "visual_continuity",
            canonicalId,
            label: "Identity continuity",
          },
        });
      });
    });
  return result;
}

function factualElements(relationships: Relationship[]): ElementDefinition[] {
  return relationships.map((relationship) => {
    const coach = relationship.relationship_type === "coach_assignment";
    return {
      data: {
        id: `relationship:${relationship.relationship_id}`,
        source: coach
          ? coachAppearanceId(relationship)
          : qbAppearanceId(relationship),
        target: relationship.target_node_id,
        kind: relationship.relationship_type,
        relationshipType: "factual",
        verification: coach ? relationship.verification_status : "analytical",
        provisional: coach && relationship.is_provisional,
      },
    };
  });
}

export function buildRelationshipGraph(
  response: RelationshipExplorerResponse,
  filters: ExplorerFilters,
  compact = false,
): RelationshipGraphModel {
  void compact;
  const relationshipById = new Map<string, Relationship>();
  response.relationships.forEach((relationship) => {
    if (!relationshipById.has(relationship.relationship_id)) {
      relationshipById.set(relationship.relationship_id, relationship);
    }
  });
  const relationships = [...relationshipById.values()].filter((relationship) =>
    keepRelationship(relationship, filters),
  );
  const usedNodeIds = new Set(
    relationships.flatMap((relationship) => [
      relationship.source_node_id,
      relationship.target_node_id,
    ]),
  );
  const nodeById = new Map<string, RelationshipNode>();
  response.nodes.forEach((node) => {
    if (usedNodeIds.has(node.node_id) && !nodeById.has(node.node_id)) {
      nodeById.set(node.node_id, node);
    }
  });
  const nodes = [...nodeById.values()].sort((left, right) =>
    left.node_id.localeCompare(right.node_id),
  );
  const relationshipsByNode = new Map<string, Relationship[]>();
  relationships.forEach((relationship) => {
    [relationship.source_node_id, relationship.target_node_id].forEach(
      (nodeId) => {
        const values = relationshipsByNode.get(nodeId) ?? [];
        values.push(relationship);
        relationshipsByNode.set(nodeId, values);
      },
    );
  });
  const graphAppearances = buildAppearances(nodes, relationships);
  const positions =
    response.query.mode === "full_network"
      ? fullNetworkPositions(graphAppearances)
      : chronologicalPositions(graphAppearances, response.query.mode);
  const continuity = continuityElements(graphAppearances);
  const yearElements: ElementDefinition[] =
    response.query.mode === "full_network"
      ? [...new Set(graphAppearances.map((value) => value.season))]
          .sort((left, right) => left - right)
          .map((season, index) => ({
            data: {
              id: `year:${season}`,
              label: String(season),
              kind: "year",
              selectable: false,
            },
            position: { x: 360 + index * 760, y: 60 },
          }))
      : [];
  const nodeElements: ElementDefinition[] = graphAppearances.map(
    (appearance) => ({
      data: {
        id: appearance.id,
        canonicalId: appearance.canonicalId,
        label: appearance.label,
        kind: appearance.kind,
        season: appearance.season,
        teamId: appearance.teamId,
        role: appearance.role,
        appearance: appearance.kind !== "team_season",
      },
      position: positions[appearance.id],
    }),
  );
  return {
    elements: [
      ...yearElements,
      ...nodeElements,
      ...factualElements(relationships),
      ...continuity,
    ],
    positions,
    nodes,
    relationships,
    relationshipById,
    relationshipsByNode,
    appearanceCount: graphAppearances.filter(
      (appearance) => appearance.kind !== "team_season",
    ).length,
    continuityCount: continuity.length,
    graphVersion: RELATIONSHIP_GRAPH_VERSION,
  };
}

export function defaultExplorerFilters(): ExplorerFilters {
  return {
    roles: new Set(coachRoles),
    showCoaches: true,
    showQuarterbacks: true,
    showTeamSeasons: true,
    eligibleOnly: false,
    minimumDropbacks: 0,
    paeMinimum: null,
    paeMaximum: null,
    interimOnly: false,
    sharedOnly: false,
  };
}
