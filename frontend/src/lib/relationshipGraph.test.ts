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
    query: {
      ...relationshipExplorer.query,
      mode,
      coach_id: mode === "coach_journey" ? "coach-1" : null,
      player_id: mode === "qb_journey" ? "qb-1" : null,
    },
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
    const appearances = graph.elements.filter(
      (element) =>
        !element.data.source && element.data.canonicalId === "coach:coach-1",
    );
    expect(appearances).toHaveLength(1);
    expect(appearances[0].data.id).toBe("coach:coach-1");
    expect(appearances[0].data.layer).toBe(1);
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
    const appearances = graph.elements.filter(
      (element) =>
        !element.data.source && element.data.canonicalId === "qb:qb-1",
    );
    expect(appearances).toHaveLength(1);
    expect(appearances[0].data.id).toBe("qb:qb-1");
    expect(appearances[0].data.layer).toBe(1);
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

  it("keeps parallel journey assignments distinct without duplicating the coach", () => {
    const fixture = response("coach_journey");
    const assignment = fixture.relationships.find(
      (row): row is CoachAssignmentRelationship =>
        row.relationship_type === "coach_assignment" &&
        row.relationship_id === "den-2024-hc",
    )!;
    fixture.relationships.push({
      ...assignment,
      relationship_id: "den-2024-hc-return",
      assignment_key: "den-2024-hc-return",
      start_week: 10,
      end_week: 18,
    });
    const graph = buildRelationshipGraph(fixture, defaultExplorerFilters());
    expect(
      graph.elements.filter(
        (row) => !row.data.source && row.data.id === "coach:coach-1",
      ),
    ).toHaveLength(1);
    expect(
      graph.elements
        .filter(
          (row) =>
            row.data.source === "coach:coach-1" &&
            row.data.target === "team-season:team_den:2024",
        )
        .map((row) => row.data.label),
    ).toEqual(["HC · Weeks 1–9", "HC · Weeks 10–18"]);
  });

  it("keeps mixed head-coach and subordinate-role identities acyclic", () => {
    const fixture = response("coach_journey");
    const mixedRole = fixture.relationships.find(
      (relationship): relationship is CoachAssignmentRelationship =>
        relationship.relationship_type === "coach_assignment" &&
        relationship.source_node_id === "coach:coach-1" &&
        relationship.role !== "head_coach",
    );
    expect(mixedRole).toBeDefined();

    expect(() =>
      buildRelationshipGraph(fixture, defaultExplorerFilters()),
    ).not.toThrow();
    const graph = buildRelationshipGraph(fixture, defaultExplorerFilters());
    const mixedEdges = graph.elements.filter(
      (element) =>
        element.data.id === `relationship:${mixedRole!.relationship_id}`,
    );
    expect(mixedEdges).toHaveLength(1);
    expect(mixedEdges[0].data.source).toBe("coach:coach-1");
  });

  it("keeps journey seasons chronologically ordered across deterministic layers", () => {
    for (const mode of ["coach_journey", "qb_journey"] as const) {
      const first = buildRelationshipGraph(
        response(mode),
        defaultExplorerFilters(),
      );
      const second = buildRelationshipGraph(
        response(mode),
        defaultExplorerFilters(),
      );
      expect(first.positions).toEqual(second.positions);
      expect(first.positions["team-season:team_den:2024"].x).toBeLessThan(
        first.positions["team-season:team_den:2025"].x,
      );
      expect(first.positions["team-season:team_den:2024"].y).toBe(
        first.positions["team-season:team_den:2025"].y,
      );
    }
  });

  it("layers QB Journey from one QB through seasons, head coaches, and other coaches", () => {
    const fixture = response("qb_journey");
    const baseAssignment = fixture.relationships.find(
      (row): row is CoachAssignmentRelationship =>
        row.relationship_type === "coach_assignment" &&
        row.relationship_id === "den-2024-hc",
    )!;
    const assistants = [
      ["coach-3", "Coordinator Coach", "offensive_coordinator"],
      ["coach-4", "Quarterback Coach", "quarterbacks_coach"],
      ["coach-5", "Play Caller", "play_caller"],
    ] as const;
    assistants.forEach(([coachId, name, role]) => {
      fixture.nodes.push({
        node_id: `coach:${coachId}`,
        node_type: "coach",
        coach_id: coachId,
        canonical_name: name,
      });
      fixture.relationships.push({
        ...baseAssignment,
        relationship_id: `den-2024-${role}`,
        assignment_key: `den-2024-${role}`,
        source_node_id: `coach:${coachId}`,
        coach_id: coachId,
        role,
      });
    });
    const graph = buildRelationshipGraph(fixture, defaultExplorerFilters());
    expect(
      graph.elements.find((row) => row.data.id === "qb:qb-1")?.data.layer,
    ).toBe(1);
    expect(
      graph.elements.find((row) => row.data.id === "team-season:team_den:2024")
        ?.data.layer,
    ).toBe(2);
    expect(
      graph.elements.find((row) => row.data.id === "coach:coach-1")?.data.layer,
    ).toBe(3);
    assistants.forEach(([coachId]) => {
      expect(
        graph.elements.find((row) => row.data.id === `coach:${coachId}`)?.data
          .layer,
      ).toBe(4);
    });
    const hierarchyEdges = graph.elements.filter((row) => row.data.source);
    expect(
      hierarchyEdges.some(
        (row) =>
          row.data.source === "qb:qb-1" &&
          row.data.target === "team-season:team_den:2024",
      ),
    ).toBe(true);
    expect(
      hierarchyEdges.some(
        (row) =>
          row.data.source === "team-season:team_den:2024" &&
          row.data.target === "coach:coach-1" &&
          row.data.role === "head_coach",
      ),
    ).toBe(true);
    assistants.forEach(([coachId, , role]) => {
      expect(
        hierarchyEdges.some(
          (row) =>
            row.data.source === "coach:coach-1" &&
            row.data.target === `coach:${coachId}` &&
            row.data.role === role,
        ),
      ).toBe(true);
      expect(
        hierarchyEdges.some(
          (row) =>
            row.data.source === "team-season:team_den:2024" &&
            row.data.target === `coach:${coachId}`,
        ),
      ).toBe(false);
    });
    expect(
      hierarchyEdges.some(
        (row) =>
          assistants.some(
            ([coachId]) => row.data.source === `coach:${coachId}`,
          ) && String(row.data.target).startsWith("coach:"),
      ),
    ).toBe(false);
    expect(
      graph.elements.filter((row) => row.data.kind === "identity_continuity"),
    ).toHaveLength(0);
  });

  it("layers Coach Journey from one coach through seasons, staff context, and QBs", () => {
    const fixture = response("coach_journey");
    const supportingCoach = fixture.relationships.find(
      (row): row is CoachAssignmentRelationship =>
        row.relationship_type === "coach_assignment" &&
        row.source_node_id === "coach:coach-2",
    )!;
    fixture.relationships.push({
      ...supportingCoach,
      relationship_id: "hou-2025-hc",
      assignment_key: "hou-2025-hc",
      target_node_id: "team-season:team_hou:2025",
      team_id: "team_hou",
      season: 2025,
      start_week: 1,
      end_week: 18,
      is_interim: false,
    });
    const graph = buildRelationshipGraph(fixture, defaultExplorerFilters());
    expect(
      graph.elements.find((row) => row.data.id === "coach:coach-1")?.data.layer,
    ).toBe(1);
    expect(
      graph.elements.find((row) => row.data.id === "team-season:team_den:2024")
        ?.data.layer,
    ).toBe(2);
    expect(
      graph.elements.find((row) => row.data.id === "coach:coach-2")?.data.layer,
    ).toBe(3);
    expect(
      graph.elements.find((row) => row.data.id === "qb:qb-1")?.data.layer,
    ).toBe(4);
    expect(
      graph.elements.filter((row) => row.data.kind === "identity_continuity"),
    ).toHaveLength(0);
    const hierarchyEdges = graph.elements.filter((row) => row.data.source);
    expect(
      hierarchyEdges.some(
        (row) =>
          row.data.source === "coach:coach-1" &&
          row.data.target === "team-season:team_den:2024",
      ),
    ).toBe(true);
    expect(
      hierarchyEdges.some(
        (row) =>
          row.data.source === "team-season:team_den:2024" &&
          row.data.target === "coach:coach-2",
      ),
    ).toBe(true);
    expect(
      hierarchyEdges.some(
        (row) =>
          row.data.source === "coach:coach-2" && row.data.target === "qb:qb-1",
      ),
    ).toBe(true);
    expect(
      hierarchyEdges.some(
        (row) =>
          row.data.source === "coach:coach-1" &&
          String(row.data.target).startsWith("qb:"),
      ),
    ).toBe(false);
    expect(
      graph.elements.filter(
        (row) => !row.data.source && row.data.canonicalId === "coach:coach-2",
      ),
    ).toHaveLength(1);
    expect(
      graph.elements.filter(
        (row) => !row.data.source && row.data.canonicalId === "qb:qb-1",
      ),
    ).toHaveLength(1);
    expect(
      hierarchyEdges.filter(
        (row) =>
          row.data.source === "coach:coach-2" && row.data.target === "qb:qb-1",
      ),
    ).toHaveLength(2);
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

  it("keeps one canonical Mike Tomlin and QB identity behind chronological appearances", () => {
    const graph = buildRelationshipGraph(
      steelersHistory(),
      defaultExplorerFilters(),
    );
    const visualNodes = graph.elements.filter(
      (element) => !element.data.source && element.data.kind !== "year",
    );
    expect(
      graph.nodes.filter((node) => node.node_id === "coach:mike-tomlin"),
    ).toHaveLength(1);
    expect(
      graph.nodes.filter((node) => node.node_id === "qb:qb-1"),
    ).toHaveLength(1);
    expect(
      visualNodes.filter((element) =>
        String(element.data.id).startsWith("appearance:coach:mike-tomlin:"),
      ),
    ).toHaveLength(2);
    expect(
      visualNodes.filter((element) => element.data.canonicalId === "qb:qb-1"),
    ).toHaveLength(2);
    expect(
      graph.elements.filter(
        (element) =>
          element.data.kind === "identity_continuity" &&
          element.data.canonicalId === "coach:mike-tomlin",
      ),
    ).toHaveLength(1);
    expect(
      graph.elements.filter(
        (element) =>
          element.data.kind === "identity_continuity" &&
          element.data.canonicalId === "qb:qb-1",
      ),
    ).toHaveLength(1);
    expect(
      graph.elements.filter(
        (element) => element.data.relationshipType === "factual",
      ),
    ).toHaveLength(graph.relationships.length);
  });

  it("keeps Team History seasons vertical and people in stable season lanes", () => {
    const graph = buildRelationshipGraph(
      steelersHistory(),
      defaultExplorerFilters(),
    );
    const season2024 = graph.positions["team-season:team_pit:2024"];
    const season2025 = graph.positions["team-season:team_pit:2025"];
    expect(season2024.y).toBeLessThan(season2025.y);
    const tomlin2024 = graph.elements.find(
      (element) =>
        element.data.canonicalId === "coach:mike-tomlin" &&
        element.data.season === 2024,
    )!;
    const qb2025 = graph.elements.find(
      (element) =>
        element.data.canonicalId === "qb:qb-1" && element.data.season === 2025,
    )!;
    expect(tomlin2024.position?.y).toBe(season2024.y);
    expect(qb2025.position?.y).toBe(season2025.y);
  });

  it("keeps continuity edges separate from assignment and QB facts", () => {
    const graph = buildRelationshipGraph(
      steelersHistory(),
      defaultExplorerFilters(),
    );
    const factual = graph.elements.filter(
      (element) => element.data.relationshipType === "factual",
    );
    const continuity = graph.elements.filter(
      (element) => element.data.relationshipType === "visual_continuity",
    );
    expect(factual).toHaveLength(graph.relationships.length);
    expect(continuity.length).toBe(graph.continuityCount);
    expect(
      continuity.every((edge) => edge.data.kind === "identity_continuity"),
    ).toBe(true);
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
    const years = first.elements.filter(
      (element) => element.data.kind === "year",
    );
    expect(years.map((element) => element.data.label)).toEqual([
      "2024",
      "2025",
    ]);
    const coach2024 = first.elements.find(
      (element) =>
        element.data.canonicalId === "coach:coach-1" &&
        element.data.season === 2024,
    )!;
    expect(coach2024.position!.x).toBeLessThan(
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
