import cytoscape, { type Core } from "cytoscape";
import { useEffect, useRef } from "react";
import type { NetworkEdge, Team } from "../api/contracts";

export interface GraphCoach {
  id: string;
  name: string;
}

export function NetworkGraph({
  edges,
  coaches,
  teams,
  selected,
  onSelect,
  register,
}: {
  edges: NetworkEdge[];
  coaches: Map<string, GraphCoach>;
  teams: Map<string, Team>;
  selected: string | null;
  onSelect: (id: string) => void;
  register: (core: Core | null) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const graph = useRef<Core | null>(null);
  useEffect(() => {
    if (!container.current) return;
    const teamIds = new Set(edges.map((edge) => edge.team_id));
    const coachIds = new Set(
      edges.flatMap((edge) => [edge.source_coach_id, edge.target_coach_id]),
    );
    const elements: cytoscape.ElementDefinition[] = [
      ...Array.from(coachIds).map((id) => ({
        data: { id, label: coaches.get(id)?.name ?? id, kind: "coach" },
      })),
      ...Array.from(teamIds).map((id) => ({
        data: {
          id: `team:${id}`,
          label: teams.get(id)?.team_abbr ?? id,
          kind: "team",
        },
      })),
      ...edges.map((edge) => ({
        data: {
          id: `${edge.source_assignment_key}:${edge.target_assignment_key}`,
          source: edge.source_coach_id,
          target: edge.target_coach_id,
          verification:
            edge.source_is_provisional || edge.target_is_provisional
              ? "provisional"
              : "verified",
        },
      })),
      ...Array.from(
        new Set(
          edges.flatMap((edge) => [
            `${edge.team_id}:${edge.source_coach_id}`,
            `${edge.team_id}:${edge.target_coach_id}`,
          ]),
        ),
      ).map((value) => {
        const [teamId, coachId] = value.split(":");
        return {
          data: {
            id: `context:${value}`,
            source: `team:${teamId}`,
            target: coachId,
            context: true,
          },
        };
      }),
    ];
    const core = cytoscape({
      container: container.current,
      elements,
      layout: {
        name: "cose",
        animate: false,
        randomize: true,
        componentSpacing: 55,
        nodeRepulsion: () => 5200,
      },
      minZoom: 0.35,
      maxZoom: 2.2,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "#1d6b5d",
            color: "#eaf8f3",
            label: "data(label)",
            "font-size": 10,
            "text-valign": "bottom",
            "text-margin-y": 7,
            width: 20,
            height: 20,
          },
        },
        {
          selector: 'node[kind="team"]',
          style: {
            shape: "round-rectangle",
            width: 38,
            height: 28,
            "background-color": "#e66f38",
            color: "#fff4ed",
            "font-weight": 800,
            "text-valign": "center",
            "text-margin-y": 0,
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.2,
            "line-color": "#708099",
            opacity: 0.45,
            "curve-style": "bezier",
          },
        },
        {
          selector: 'edge[verification="provisional"]',
          style: { "line-style": "dashed", "line-color": "#d7784d" },
        },
        {
          selector: "edge[context]",
          style: { width: 0.7, "line-color": "#38506e", opacity: 0.28 },
        },
        {
          selector: ":selected",
          style: {
            "border-width": 4,
            "border-color": "#ffffff",
            "overlay-color": "#6ee7b7",
            "overlay-opacity": 0.16,
            "overlay-padding": 8,
          },
        },
      ],
    });
    core.on("tap", "node", (event) => onSelect(event.target.id()));
    graph.current = core;
    register(core);
    return () => {
      graph.current = null;
      register(null);
      core.destroy();
    };
  }, [coaches, edges, onSelect, register, teams]);

  useEffect(() => {
    const core = graph.current;
    if (!core) return;
    core.elements().unselect();
    if (selected) core.getElementById(selected).select();
  }, [selected]);

  return (
    <div
      className="network-canvas"
      ref={container}
      role="img"
      aria-label="Interactive coaching staff network. Use the accessible connections list below for a text alternative."
    />
  );
}
