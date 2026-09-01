import type {
  CoachAssignmentRelationship,
  QbTeamSeasonRelationship,
  RelationshipExplorerResponse,
} from "../api/contracts";
import { relationshipExplorer } from "../test/fixtures";
import {
  buildRelationshipGraph,
  defaultExplorerFilters,
} from "./relationshipGraph";

function response(
  mode: RelationshipExplorerResponse["query"]["mode"] = "team_history",
) {
  return {
    ...relationshipExplorer,
    query: { ...relationshipExplorer.query, mode },
    nodes: relationshipExplorer.nodes.map((node) => ({ ...node })),
    relationships: relationshipExplorer.relationships.map((relationship) => ({
      ...relationship,
    })),
  } as RelationshipExplorerResponse;
}

function steelersHistory() {
  const fixture = response();
  fixture.nodes = fixture.nodes.filter(
    (node) => node.node_id !== "team-season:team_hou:2025",
  );
  fixture.nodes = fixture.nodes.map((node) =>
    node.node_id === "coach:coach-1" && node.node_type === "coach"
      ? {
          ...node,
          coach_id: "mike-tomlin",
          node_id: "coach:mike-tomlin",
          canonical_name: "Mike Tomlin",
        }
      : node.node_type === "team_season"
        ? {
            ...node,
            node_id: node.node_id.replace("team_den", "team_pit"),
            team_id: "team_pit",
            team_abbr: "PIT",
            team_name: "Pittsburgh Steelers",
          }
        : node,
  );
  fixture.relationships = fixture.relationships
    .filter(
      (relationship) =>
        relationship.relationship_id !== "qb-team-season:qb-1:team_hou:2025",
    )
    .map((relationship) => {
      if (relationship.relationship_type !== "coach_assignment") {
        return {
          ...relationship,
          target_node_id: relationship.target_node_id.replace(
            "team_den",
            "team_pit",
          ),
          team_id: "team_pit",
        };
      }
      if (relationship.relationship_id === "den-2024-hc-interim") {
        return {
          ...relationship,
          target_node_id: "team-season:team_pit:2024",
          team_id: "team_pit",
          role: "offensive_coordinator" as const,
        };
      }
      if (relationship.source_node_id === "coach:coach-1") {
        return {
          ...relationship,
          source_node_id: "coach:mike-tomlin",
          coach_id: "mike-tomlin",
          target_node_id:
            relationship.relationship_id === "hou-2025-oc"
              ? "team-season:team_pit:2025"
              : relationship.target_node_id.replace("team_den", "team_pit"),
          team_id: "team_pit",
          role: "head_coach" as const,
        };
      }
      return relationship;
    });
  return fixture;
}

describe("buildRelationshipGraph", () => {
  it("keeps one canonical coach node across years, teams, and roles", () => {
    const graph = buildRelationshipGraph(
      response("coach_journey"),
      defaultExplorerFilters(),
    );
    expect(
      graph.nodes.filter((node) => node.node_id === "coach:coach-1"),
    ).toHaveLength(1);
    const assignments = graph.relationships.filter(
      (row): row is CoachAssignmentRelationship =>
        row.relationship_type === "coach_assignment" &&
        row.coach_id === "coach-1",
    );
    expect(new Set(assignments.map((row) => row.team_id))).toEqual(
      new Set(["team_den", "team_hou"]),
    );
    expect(new Set(assignments.map((row) => row.role))).toEqual(
      new Set(["head_coach", "offensive_coordinator"]),
    );
  });

  it("keeps one canonical QB node across years and teams", () => {
    const graph = buildRelationshipGraph(
      response("qb_journey"),
      defaultExplorerFilters(),
    );
    expect(
      graph.nodes.filter((node) => node.node_id === "qb:qb-1"),
    ).toHaveLength(1);
    const qbRows = graph.relationships.filter(
      (row): row is QbTeamSeasonRelationship =>
        row.relationship_type === "qb_team_season" && row.player_id === "qb-1",
    );
    expect(new Set(qbRows.map((row) => row.season))).toEqual(
      new Set([2024, 2025]),
    );
    expect(new Set(qbRows.map((row) => row.team_id))).toEqual(
      new Set(["team_den", "team_hou"]),
    );
  });

  it("preserves multi-team same-season QB records and their complete-key PAE", () => {
    const graph = buildRelationshipGraph(
      response("qb_journey"),
      defaultExplorerFilters(),
    );
    const rows = graph.relationships.filter(
      (row): row is QbTeamSeasonRelationship =>
        row.relationship_type === "qb_team_season" &&
        row.player_id === "qb-1" &&
        row.season === 2025,
    );
    expect(rows).toHaveLength(2);
    expect(
      Object.fromEntries(
        rows.map((row) => [row.team_id, row.performance_above_expectation]),
      ),
    ).toEqual({
      team_den: 0.07,
      team_hou: -0.05,
    });
  });

  it("does not collapse distinct in-season assignment intervals", () => {
    const graph = buildRelationshipGraph(response(), defaultExplorerFilters());
    const rows = graph.relationships.filter(
      (row): row is CoachAssignmentRelationship =>
        row.relationship_type === "coach_assignment" &&
        row.team_id === "team_den" &&
        row.season === 2024,
    );
    expect(
      rows.map((row) => [row.assignment_key, row.start_week, row.end_week]),
    ).toEqual([
      ["den-2024-hc", 1, 9],
      ["den-2024-hc-interim", 10, 18],
    ]);
  });

  it("preserves interim, shared, verified, and provisional states", () => {
    const graph = buildRelationshipGraph(response(), defaultExplorerFilters());
    const assignments = graph.relationships.filter(
      (row): row is CoachAssignmentRelationship =>
        row.relationship_type === "coach_assignment",
    );
    expect(assignments.some((row) => row.is_interim)).toBe(true);
    expect(assignments.some((row) => row.is_shared)).toBe(true);
    expect(new Set(assignments.map((row) => row.verification_status))).toEqual(
      new Set(["verified", "provisional"]),
    );
  });

  it("applies coach-role filters without deleting independent QB facts", () => {
    const filters = defaultExplorerFilters();
    filters.roles = new Set(["quarterbacks_coach"]);
    const graph = buildRelationshipGraph(response(), filters);
    expect(
      graph.relationships.filter(
        (row) => row.relationship_type === "coach_assignment",
      ),
    ).toEqual([]);
    expect(
      graph.relationships.filter(
        (row) => row.relationship_type === "qb_team_season",
      ),
    ).toHaveLength(4);
  });

  it("applies interim and shared filters only to coach assignments", () => {
    const filters = defaultExplorerFilters();
    filters.interimOnly = true;
    filters.sharedOnly = true;
    const graph = buildRelationshipGraph(response(), filters);
    expect(
      graph.relationships.filter(
        (row) => row.relationship_type === "coach_assignment",
      ),
    ).toEqual([]);
    expect(
      graph.relationships.filter(
        (row) => row.relationship_type === "qb_team_season",
      ),
    ).toHaveLength(4);
  });

  it("applies QB eligibility, dropback, and PAE filters only to QB facts", () => {
    const filters = defaultExplorerFilters();
    filters.eligibleOnly = true;
    filters.minimumDropbacks = 200;
    filters.paeMinimum = 0.05;
    const graph = buildRelationshipGraph(response(), filters);
    const qbRows = graph.relationships.filter(
      (row) => row.relationship_type === "qb_team_season",
    );
    expect(qbRows.map((row) => row.relationship_id)).toEqual([
      "qb-team-season:qb-1:team_den:2025",
    ]);
    expect(
      graph.relationships.filter(
        (row) => row.relationship_type === "coach_assignment",
      ),
    ).toHaveLength(3);
  });

  it("keeps missing PAE null instead of converting it to zero", () => {
    const graph = buildRelationshipGraph(response(), defaultExplorerFilters());
    const row = graph.relationships.find(
      (relationship) =>
        relationship.relationship_id === "qb-team-season:qb-2:team_den:2025",
    );
    expect(row?.relationship_type).toBe("qb_team_season");
    if (row?.relationship_type === "qb_team_season") {
      expect(row.expected_epa_per_dropback).toBeNull();
      expect(row.performance_above_expectation).toBeNull();
    }
  });

  it("does not render duplicate nodes or relationships", () => {
    const duplicate = response();
    duplicate.nodes.push({ ...duplicate.nodes[0] });
    duplicate.relationships.push({ ...duplicate.relationships[0] });
    const graph = buildRelationshipGraph(duplicate, defaultExplorerFilters());
    expect(new Set(graph.nodes.map((node) => node.node_id)).size).toBe(
      graph.nodes.length,
    );
    expect(
      new Set(graph.relationships.map((row) => row.relationship_id)).size,
    ).toBe(graph.relationships.length);
  });

  it("generates byte-stable chronological positions for journey and history modes", () => {
    for (const mode of [
      "coach_journey",
      "qb_journey",
      "team_history",
    ] as const) {
      const first = buildRelationshipGraph(
        response(mode),
        defaultExplorerFilters(),
      );
      const second = buildRelationshipGraph(
        response(mode),
        defaultExplorerFilters(),
      );
      expect(JSON.stringify(first.positions)).toBe(
        JSON.stringify(second.positions),
      );
      if (mode !== "team_history") {
        expect(first.positions["team-season:team_den:2024"].x).toBeLessThan(
          first.positions["team-season:team_den:2025"].x,
        );
      }
    }
  });

  it("renders Mike Tomlin and a multi-season QB once with every season edge", () => {
    const graph = buildRelationshipGraph(
      steelersHistory(),
      defaultExplorerFilters(),
    );
    const visualNodes = graph.elements.filter(
      (element) => !element.data.source,
    );
    expect(
      visualNodes.filter((element) => element.data.id === "coach:mike-tomlin"),
    ).toHaveLength(1);
    expect(
      visualNodes.filter((element) => element.data.id === "qb:qb-1"),
    ).toHaveLength(1);
    expect(
      visualNodes.filter((element) =>
        String(element.data.id).startsWith("instance:"),
      ),
    ).toHaveLength(0);
    const edges = graph.elements.filter((element) => element.data.source);
    expect(
      edges
        .filter((element) => element.data.source === "coach:mike-tomlin")
        .map((element) => element.data.target),
    ).toEqual(
      expect.arrayContaining([
        "team-season:team_pit:2024",
        "team-season:team_pit:2025",
      ]),
    );
    expect(
      edges
        .filter((element) => element.data.target === "qb:qb-1")
        .map((element) => element.data.source),
    ).toEqual(
      expect.arrayContaining([
        "team-season:team_pit:2024",
        "team-season:team_pit:2025",
      ]),
    );
  });

  it("uses a top-to-bottom Dagre hierarchy for Team History", () => {
    const graph = buildRelationshipGraph(
      steelersHistory(),
      defaultExplorerFilters(),
    );
    const root = graph.positions["team:team_pit"];
    const headCoach = graph.positions["coach:mike-tomlin"];
    const seasons = [
      graph.positions["team-season:team_pit:2024"],
      graph.positions["team-season:team_pit:2025"],
    ];
    const coordinator = graph.positions["coach:coach-2"];
    const quarterback = graph.positions["qb:qb-1"];
    expect(root.y).toBeLessThan(headCoach.y);
    expect(seasons.every((position) => headCoach.y < position.y)).toBe(true);
    expect(seasons.every((position) => position.y < coordinator.y)).toBe(true);
    expect(coordinator.y).toBeLessThan(quarterback.y);
  });

  it("uses a deterministic bounded Full Network layout", () => {
    const first = buildRelationshipGraph(
      response("full_network"),
      defaultExplorerFilters(),
    );
    const second = buildRelationshipGraph(
      response("full_network"),
      defaultExplorerFilters(),
    );
    expect(first.positions).toEqual(second.positions);
    expect(first.positions["coach:coach-1"].x).toBeLessThan(
      first.positions["team-season:team_den:2024"].x,
    );
  });

  it("keeps Team History top-to-bottom on compact screens", () => {
    const wide = buildRelationshipGraph(
      response(),
      defaultExplorerFilters(),
      false,
    );
    const compact = buildRelationshipGraph(
      response(),
      defaultExplorerFilters(),
      true,
    );
    const id = "team-season:team_den:2024";
    expect(compact.positions[id]).toEqual(wide.positions[id]);
  });
});
