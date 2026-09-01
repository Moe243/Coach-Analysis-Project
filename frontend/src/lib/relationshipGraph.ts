import type { ElementDefinition, Position } from "cytoscape";
import { graphlib, layout as runDagreLayout } from "@dagrejs/dagre";
import type {
  CoachAssignmentRelationship,
  CoachRole,
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

function chronologicalPositions(
  nodes: RelationshipNode[],
  relationships: Relationship[],
  mode: Exclude<RelationshipMode, "full_network">,
): Record<string, Position> {
  const positions: Record<string, Position> = {};
  const teamSeasons = nodes
    .filter((node) => node.node_type === "team_season")
    .sort(
      (left, right) =>
        left.season - right.season ||
        left.team_id.localeCompare(right.team_id) ||
        left.node_id.localeCompare(right.node_id),
    );
  const seasons = [...new Set(teamSeasons.map((node) => node.season))];
  const seasonIndex = new Map(seasons.map((season, index) => [season, index]));
  const seasonCounts = new Map<number, number>();
  teamSeasons.forEach((node) => {
    const index = seasonCounts.get(node.season) ?? 0;
    seasonCounts.set(node.season, index + 1);
    positions[node.node_id] = {
      x: 300 + (seasonIndex.get(node.season) ?? 0) * 260,
      y: 220 + index * 130,
    };
  });

  const coachNodes = nodes
    .filter((node) => node.node_type === "coach")
    .sort((left, right) => left.node_id.localeCompare(right.node_id));
  const qbNodes = nodes
    .filter((node) => node.node_type === "quarterback")
    .sort((left, right) => left.node_id.localeCompare(right.node_id));
  const maxX = Math.max(300, ...Object.values(positions).map(({ x }) => x));

  coachNodes.forEach((node, index) => {
    const linked = relationships.filter(
      (relationship) =>
        relationship.relationship_type === "coach_assignment" &&
        relationship.source_node_id === node.node_id,
    ) as CoachAssignmentRelationship[];
    const earliestRole = linked
      .map((relationship) => roleOrder.get(relationship.role) ?? 9)
      .sort((left, right) => left - right)[0];
    positions[node.node_id] =
      mode === "coach_journey" && index === 0
        ? { x: 70, y: 220 }
        : {
            x: maxX + 250,
            y: 70 + (earliestRole ?? 9) * 70 + index * 18,
          };
  });
  qbNodes.forEach((node, index) => {
    positions[node.node_id] =
      mode === "qb_journey" && index === 0
        ? { x: 70, y: 360 }
        : { x: maxX + 250, y: 390 + index * 58 };
  });
  return positions;
}

function fullNetworkPositions(
  nodes: RelationshipNode[],
): Record<string, Position> {
  const positions: Record<string, Position> = {};
  const grouped: Record<RelationshipNode["node_type"], RelationshipNode[]> = {
    coach: [],
    quarterback: [],
    team_season: [],
  };
  nodes.forEach((node) => grouped[node.node_type].push(node));
  (Object.keys(grouped) as RelationshipNode["node_type"][]).forEach((kind) =>
    grouped[kind].sort((left, right) =>
      left.node_id.localeCompare(right.node_id),
    ),
  );
  const columns: Record<RelationshipNode["node_type"], number> = {
    coach: 90,
    team_season: 430,
    quarterback: 770,
  };
  (Object.keys(grouped) as RelationshipNode["node_type"][]).forEach((kind) => {
    grouped[kind].forEach((node, index) => {
      positions[node.node_id] = { x: columns[kind], y: 90 + index * 82 };
    });
  });
  return positions;
}

function nodeLabel(node: RelationshipNode): string {
  return node.node_type === "coach"
    ? node.canonical_name
    : node.node_type === "quarterback"
      ? node.display_name
      : `${node.team_abbr} ${node.season}`;
}

function teamHistoryDagre(
  nodes: RelationshipNode[],
  relationships: Relationship[],
): { elements: ElementDefinition[]; positions: Record<string, Position> } {
  const teamSeasons = nodes
    .filter((node) => node.node_type === "team_season")
    .sort(
      (left, right) =>
        left.season - right.season ||
        left.team_id.localeCompare(right.team_id) ||
        left.node_id.localeCompare(right.node_id),
    );
  const firstTeam = teamSeasons[0];
  const teamRootId = firstTeam ? `team:${firstTeam.team_id}` : "team:history";
  const dagre = new graphlib.Graph({ multigraph: true })
    .setGraph({
      rankdir: "TB",
      ranker: "network-simplex",
      nodesep: 76,
      edgesep: 28,
      ranksep: 105,
      marginx: 40,
      marginy: 40,
    })
    .setDefaultEdgeLabel(() => ({}));
  dagre.setNode(teamRootId, { width: 150, height: 42 });
  nodes.forEach((node) =>
    dagre.setNode(node.node_id, {
      width: node.node_type === "team_season" ? 82 : 118,
      height: node.node_type === "team_season" ? 44 : 38,
    }),
  );

  const headCoachIds = new Set<string>();
  relationships.forEach((relationship) => {
    if (relationship.relationship_type === "coach_assignment") {
      const isHeadCoach = relationship.role === "head_coach";
      if (isHeadCoach) headCoachIds.add(relationship.source_node_id);
      dagre.setEdge(
        isHeadCoach ? relationship.source_node_id : relationship.target_node_id,
        isHeadCoach ? relationship.target_node_id : relationship.source_node_id,
        { minlen: 1, weight: isHeadCoach ? 8 : 4 },
        relationship.relationship_id,
      );
    } else {
      dagre.setEdge(
        relationship.target_node_id,
        relationship.source_node_id,
        { minlen: 2, weight: 2 },
        relationship.relationship_id,
      );
    }
  });
  [...headCoachIds]
    .sort()
    .forEach((coachId) =>
      dagre.setEdge(
        teamRootId,
        coachId,
        { minlen: 1, weight: 10 },
        `root:${coachId}`,
      ),
    );
  teamSeasons.forEach((teamSeason) => {
    const hasHeadCoach = relationships.some(
      (relationship) =>
        relationship.relationship_type === "coach_assignment" &&
        relationship.role === "head_coach" &&
        relationship.target_node_id === teamSeason.node_id,
    );
    if (!hasHeadCoach) {
      dagre.setEdge(
        teamRootId,
        teamSeason.node_id,
        { minlen: 2, weight: 1 },
        `root:${teamSeason.node_id}`,
      );
    }
  });
  runDagreLayout(dagre);

  const positions: Record<string, Position> = Object.fromEntries(
    dagre.nodes().map((id) => {
      const node = dagre.node(id) as { x: number; y: number };
      return [id, { x: node.x, y: node.y }];
    }),
  );
  const elements: ElementDefinition[] = [
    {
      data: {
        id: teamRootId,
        label: firstTeam?.team_name ?? "Team",
        kind: "team",
        selectable: false,
      },
      position: positions[teamRootId],
    },
    ...nodes.map((node) => ({
      data: {
        id: node.node_id,
        canonicalId: node.node_id,
        label: nodeLabel(node),
        kind: node.node_type,
        season: node.node_type === "team_season" ? node.season : undefined,
      },
      position: positions[node.node_id],
    })),
    ...relationships.map((relationship) => {
      const headCoach =
        relationship.relationship_type === "coach_assignment" &&
        relationship.role === "head_coach";
      return {
        data: {
          id: `relationship:${relationship.relationship_id}`,
          source: headCoach
            ? relationship.source_node_id
            : relationship.target_node_id,
          target: headCoach
            ? relationship.target_node_id
            : relationship.source_node_id,
          kind: relationship.relationship_type,
          layout: "dagre",
          verification:
            relationship.relationship_type === "coach_assignment"
              ? relationship.verification_status
              : "analytical",
          provisional:
            relationship.relationship_type === "coach_assignment" &&
            relationship.is_provisional,
        },
      };
    }),
    ...[...headCoachIds].sort().map((coachId) => ({
      data: {
        id: `hierarchy:${teamRootId}:${coachId}`,
        source: teamRootId,
        target: coachId,
        kind: "team_head_coach",
        layout: "dagre",
      },
    })),
  ];
  return { elements, positions };
}

export function buildRelationshipGraph(
  response: RelationshipExplorerResponse,
  filters: ExplorerFilters,
  compact = false,
): RelationshipGraphModel {
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
  const dagre =
    response.query.mode === "team_history"
      ? teamHistoryDagre(nodes, relationships)
      : null;
  let positions = dagre
    ? dagre.positions
    : response.query.mode === "full_network"
      ? fullNetworkPositions(nodes)
      : chronologicalPositions(nodes, relationships, response.query.mode);
  if (compact && response.query.mode !== "team_history") {
    positions = Object.fromEntries(
      Object.entries(positions).map(([id, position]) => [
        id,
        { x: position.y, y: position.x },
      ]),
    );
  }
  const elements: ElementDefinition[] = dagre
    ? dagre.elements
    : [
        ...nodes.map((node) => ({
          data: {
            id: node.node_id,
            canonicalId: node.node_id,
            label: nodeLabel(node),
            kind: node.node_type,
            season: node.node_type === "team_season" ? node.season : undefined,
          },
          position: positions[node.node_id],
        })),
        ...relationships.map((relationship) => ({
          data: {
            id: `relationship:${relationship.relationship_id}`,
            source: relationship.source_node_id,
            target: relationship.target_node_id,
            kind: relationship.relationship_type,
            verification:
              relationship.relationship_type === "coach_assignment"
                ? relationship.verification_status
                : "analytical",
            provisional:
              relationship.relationship_type === "coach_assignment" &&
              relationship.is_provisional,
          },
        })),
      ];
  return {
    elements,
    positions,
    nodes,
    relationships,
    relationshipById,
    relationshipsByNode,
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
