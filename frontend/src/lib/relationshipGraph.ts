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

export const RELATIONSHIP_GRAPH_VERSION = "relationship-graph-v4";

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
  layer?: number;
  roles?: CoachRole[];
  branchIds: string[];
}

const roleOrder = new Map(coachRoles.map((role, index) => [role, index]));
const shortRoleLabels: Record<CoachRole, string> = {
  head_coach: "HC",
  offensive_coordinator: "OC",
  play_caller: "Play caller",
  quarterbacks_coach: "QB coach",
};

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
  mode: RelationshipMode,
  anchorId: string | null,
): Appearance[] {
  const byId = new Map(nodes.map((node) => [node.node_id, node]));
  const values: Appearance[] = [];
  nodes
    .filter((node) => node.node_type === "team_season")
    .forEach((node) => {
      const anchorRoles =
        mode === "coach_journey" && anchorId
          ? relationships
              .filter(
                (relationship): relationship is CoachAssignmentRelationship =>
                  relationship.relationship_type === "coach_assignment" &&
                  relationship.coach_id === anchorId &&
                  relationship.target_node_id === node.node_id,
              )
              .map((relationship) => shortRoleLabels[relationship.role])
          : [];
      values.push({
        id: node.node_id,
        canonicalId: node.node_id,
        kind: "team_season",
        label:
          mode === "coach_journey" || mode === "qb_journey"
            ? `${node.season} ${node.team_abbr}${anchorRoles.length ? `\n${[...new Set(anchorRoles)].join(" / ")}` : ""}`
            : nodeLabel(node),
        season: node.season,
        teamId: node.team_id,
        layer: 2,
        branchIds: [node.node_id],
      });
    });
  if (mode === "coach_journey" || mode === "qb_journey") {
    const relationshipsBySource = new Map<string, Relationship[]>();
    relationships.forEach((relationship) => {
      relationshipsBySource.set(relationship.source_node_id, [
        ...(relationshipsBySource.get(relationship.source_node_id) ?? []),
        relationship,
      ]);
    });
    [...relationshipsBySource.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .forEach(([sourceId, sourceRelationships]) => {
        const source = byId.get(sourceId);
        if (!source || source.node_type === "team_season") return;
        const first = [...sourceRelationships].sort(
          (left, right) =>
            left.season - right.season ||
            left.team_id.localeCompare(right.team_id) ||
            left.relationship_id.localeCompare(right.relationship_id),
        )[0];
        const roles = [
          ...new Set(
            sourceRelationships
              .filter(
                (relationship): relationship is CoachAssignmentRelationship =>
                  relationship.relationship_type === "coach_assignment",
              )
              .map((relationship) => relationship.role),
          ),
        ].sort(
          (left, right) =>
            (roleOrder.get(left) ?? 0) - (roleOrder.get(right) ?? 0),
        );
        const isJourneyAnchor =
          (mode === "coach_journey" && sourceId === `coach:${anchorId}`) ||
          (mode === "qb_journey" && sourceId === `qb:${anchorId}`);
        const layer = isJourneyAnchor
          ? 1
          : mode === "qb_journey" &&
              source.node_type === "coach" &&
              roles.includes("head_coach")
            ? 3
            : mode === "coach_journey" && source.node_type === "coach"
              ? 3
              : 4;
        values.push({
          id: sourceId,
          canonicalId: sourceId,
          kind: source.node_type === "coach" ? "coach" : "quarterback",
          label: nodeLabel(source),
          season: first.season,
          teamId: first.team_id,
          startWeek:
            first.relationship_type === "coach_assignment"
              ? first.start_week
              : undefined,
          layer,
          roles,
          branchIds: [
            ...new Set(
              sourceRelationships.map(
                (relationship) => relationship.target_node_id,
              ),
            ),
          ].sort(),
        });
      });
    return values;
  }
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
        roles: [relationship.role],
        branchIds: [relationship.target_node_id],
      });
    } else {
      values.push({
        id: qbAppearanceId(relationship),
        canonicalId: relationship.source_node_id,
        kind: "quarterback",
        label: nodeLabel(source),
        season: relationship.season,
        teamId: relationship.team_id,
        branchIds: [relationship.target_node_id],
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

function journeyPositions(
  values: Appearance[],
  relationships: Relationship[],
): Record<string, Position> {
  const positions: Record<string, Position> = {};
  const teamSeasons = values
    .filter((value) => value.kind === "team_season")
    .sort(
      (left, right) =>
        left.season - right.season ||
        left.teamId.localeCompare(right.teamId) ||
        left.id.localeCompare(right.id),
    );
  const teamX = new Map(
    teamSeasons.map((value, index) => [value.id, 220 + index * 260]),
  );
  teamSeasons.forEach((value) => {
    positions[value.id] = { x: teamX.get(value.id)!, y: 300 };
    value.layer = 2;
  });

  const centerX = teamSeasons.length
    ? [...teamX.values()].reduce((total, value) => total + value, 0) /
      teamSeasons.length
    : 220;
  const people = values.filter((value) => value.kind !== "team_season");
  const desired = people.map((value) => {
    const connected = relationships
      .filter(
        (relationship) => relationship.source_node_id === value.canonicalId,
      )
      .map((relationship) => teamX.get(relationship.target_node_id))
      .filter((position): position is number => position !== undefined);
    const connectedCenter = connected.length
      ? connected.reduce((total, position) => total + position, 0) /
        connected.length
      : centerX;
    const layer = value.layer ?? 4;
    value.layer = layer;
    return { value, connectedCenter, layer };
  });

  for (const layer of [1, 3, 4]) {
    const layerValues = desired
      .filter((entry) => entry.layer === layer)
      .sort(
        (left, right) =>
          left.connectedCenter - right.connectedCenter ||
          left.value.id.localeCompare(right.value.id),
      );
    let previousX = Number.NEGATIVE_INFINITY;
    layerValues.forEach((entry) => {
      const x =
        layer === 1
          ? centerX
          : Math.max(entry.connectedCenter, previousX + 180);
      positions[entry.value.id] = {
        x,
        y: layer === 1 ? 80 : layer === 3 ? 520 : 740,
      };
      previousX = x;
    });
  }
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
            branchIds: [
              ...new Set([...previous.branchIds, ...value.branchIds]),
            ],
          },
        });
      });
    });
  return result;
}

function assignmentLabel(relationship: CoachAssignmentRelationship): string {
  return `${shortRoleLabels[relationship.role]} · Weeks ${relationship.start_week}–${relationship.end_week}`;
}

function relationshipData(relationship: Relationship) {
  const coach = relationship.relationship_type === "coach_assignment";
  return {
    kind: relationship.relationship_type,
    relationshipId: relationship.relationship_id,
    verification: coach ? relationship.verification_status : "analytical",
    provisional: coach && relationship.is_provisional,
    role: coach ? relationship.role : undefined,
    startWeek: coach ? relationship.start_week : undefined,
    endWeek: coach ? relationship.end_week : undefined,
    branchIds: [relationship.target_node_id],
  };
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
        relationshipType: "factual",
        ...relationshipData(relationship),
      },
    };
  });
}

function journeyElements(
  relationships: Relationship[],
  mode: "coach_journey" | "qb_journey",
  anchorId: string | null,
): ElementDefinition[] {
  const coachAssignments = relationships.filter(
    (relationship): relationship is CoachAssignmentRelationship =>
      relationship.relationship_type === "coach_assignment",
  );
  const qbSeasons = relationships.filter(
    (relationship): relationship is QbTeamSeasonRelationship =>
      relationship.relationship_type === "qb_team_season",
  );
  const result: ElementDefinition[] = [];

  if (mode === "qb_journey") {
    const headCoaches = coachAssignments.filter(
      (relationship) => relationship.role === "head_coach",
    );
    qbSeasons.forEach((relationship) => {
      result.push({
        data: {
          id: `relationship:${relationship.relationship_id}`,
          source: relationship.source_node_id,
          target: relationship.target_node_id,
          relationshipType: "factual",
          layout: "journey",
          ...relationshipData(relationship),
        },
      });
    });
    headCoaches.forEach((relationship) => {
      result.push({
        data: {
          id: `relationship:${relationship.relationship_id}`,
          source: relationship.target_node_id,
          target: relationship.source_node_id,
          relationshipType: "factual",
          layout: "journey",
          label: assignmentLabel(relationship),
          ...relationshipData(relationship),
        },
      });
    });
    coachAssignments
      .filter((relationship) => relationship.role !== "head_coach")
      .forEach((relationship) => {
        const parents = headCoaches.filter(
          (headCoach) =>
            headCoach.target_node_id === relationship.target_node_id &&
            headCoach.start_week <= relationship.end_week &&
            relationship.start_week <= headCoach.end_week,
        );
        parents.forEach((headCoach) => {
          if (headCoach.source_node_id === relationship.source_node_id) return;
          result.push({
            data: {
              id: `relationship:${relationship.relationship_id}:via:${headCoach.assignment_key}`,
              source: headCoach.source_node_id,
              target: relationship.source_node_id,
              relationshipType: "visual_hierarchy",
              layout: "journey",
              label: assignmentLabel(relationship),
              ...relationshipData(relationship),
            },
          });
        });
      });
    return result;
  }

  const anchorNodeId = anchorId ? `coach:${anchorId}` : null;
  const anchorAssignments = coachAssignments.filter(
    (relationship) => relationship.source_node_id === anchorNodeId,
  );
  const supportingAssignments = coachAssignments.filter(
    (relationship) => relationship.source_node_id !== anchorNodeId,
  );
  anchorAssignments.forEach((relationship) => {
    result.push({
      data: {
        id: `relationship:${relationship.relationship_id}`,
        source: relationship.source_node_id,
        target: relationship.target_node_id,
        relationshipType: "factual",
        layout: "journey",
        label: assignmentLabel(relationship),
        ...relationshipData(relationship),
      },
    });
  });
  supportingAssignments.forEach((relationship) => {
    result.push({
      data: {
        id: `relationship:${relationship.relationship_id}`,
        source: relationship.target_node_id,
        target: relationship.source_node_id,
        relationshipType: "factual",
        layout: "journey",
        label: assignmentLabel(relationship),
        ...relationshipData(relationship),
      },
    });
  });
  qbSeasons.forEach((relationship) => {
    const supporting = supportingAssignments.filter(
      (assignment) => assignment.target_node_id === relationship.target_node_id,
    );
    if (!supporting.length) {
      result.push({
        data: {
          id: `relationship:${relationship.relationship_id}:without-staff-context`,
          source: relationship.target_node_id,
          target: relationship.source_node_id,
          relationshipType: "visual_hierarchy",
          layout: "journey",
          ...relationshipData(relationship),
        },
      });
      return;
    }
    supporting.forEach((assignment) => {
      result.push({
        data: {
          id: `relationship:${relationship.relationship_id}:via:${assignment.assignment_key}`,
          source: assignment.source_node_id,
          target: relationship.source_node_id,
          relationshipType: "visual_hierarchy",
          layout: "journey",
          kind: "qb_team_season_context",
          relationshipId: relationship.relationship_id,
          verification: "analytical",
          provisional: assignment.is_provisional,
          branchIds: [relationship.target_node_id],
        },
      });
    });
  });
  return result;
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
  const graphAppearances = buildAppearances(
    nodes,
    relationships,
    response.query.mode,
    response.query.mode === "coach_journey"
      ? response.query.coach_id
      : response.query.player_id,
  );
  const positions =
    response.query.mode === "full_network"
      ? fullNetworkPositions(graphAppearances)
      : response.query.mode === "coach_journey" ||
          response.query.mode === "qb_journey"
        ? journeyPositions(graphAppearances, relationships)
        : chronologicalPositions(graphAppearances, response.query.mode);
  const continuity =
    response.query.mode === "coach_journey" ||
    response.query.mode === "qb_journey"
      ? []
      : continuityElements(graphAppearances);
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
        roleBadges: appearance.roles?.map((role) => shortRoleLabels[role]),
        layer: appearance.layer,
        branchIds: appearance.branchIds,
        appearance: appearance.kind !== "team_season",
      },
      position: positions[appearance.id],
    }),
  );
  return {
    elements: [
      ...yearElements,
      ...nodeElements,
      ...(response.query.mode === "coach_journey" ||
      response.query.mode === "qb_journey"
        ? journeyElements(
            relationships,
            response.query.mode,
            response.query.mode === "coach_journey"
              ? response.query.coach_id
              : response.query.player_id,
          )
        : factualElements(relationships)),
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
