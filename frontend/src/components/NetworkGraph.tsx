import type { Core, ElementDefinition } from "cytoscape";
import { useEffect, useRef } from "react";
import { applyGraphSelection } from "./networkSelection";

export function NetworkGraph({
  elements,
  selected,
  onSelect,
  register,
}: {
  elements: ElementDefinition[];
  selected: string | null;
  onSelect: (id: string) => void;
  register: (core: Core | null) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const graph = useRef<Core | null>(null);
  const selectedRef = useRef(selected);
  const onSelectRef = useRef(onSelect);
  selectedRef.current = selected;
  onSelectRef.current = onSelect;

  useEffect(() => {
    let disposed = false;
    let core: Core | null = null;
    if (!container.current) return;
    void import("cytoscape").then(({ default: cytoscape }) => {
      if (disposed || !container.current) return;
      core = cytoscape({
        container: container.current,
        elements,
        layout: { name: "preset", animate: false, fit: true, padding: 44 },
        minZoom: 0.25,
        maxZoom: 2.4,
        style: [
          {
            selector: "node",
            style: {
              "background-color": "#0d7c66",
              color: "#eaf8f3",
              label: "data(label)",
              "font-size": 10,
              "font-weight": 700,
              "text-valign": "bottom",
              "text-margin-y": 8,
              "text-wrap": "wrap",
              "text-max-width": "105px",
              width: 24,
              height: 24,
            },
          },
          {
            selector: 'node[kind="quarterback"]',
            style: {
              shape: "diamond",
              "background-color": "#315ed1",
              width: 28,
              height: 28,
            },
          },
          {
            selector: 'node[kind="team_season"]',
            style: {
              shape: "round-rectangle",
              width: 62,
              height: 34,
              "background-color": "#db5f2b",
              color: "#fff4ed",
              "font-weight": 800,
              "text-valign": "center",
              "text-margin-y": 0,
            },
          },
          {
            selector: "edge",
            style: {
              width: 1.4,
              "line-color": "#708099",
              opacity: 0.62,
              "curve-style": "bezier",
              "target-arrow-shape": "triangle",
              "target-arrow-color": "#708099",
              "arrow-scale": 0.65,
            },
          },
          {
            selector: 'edge[kind="qb_team_season"]',
            style: {
              "line-color": "#5f83e2",
              "target-arrow-color": "#5f83e2",
            },
          },
          {
            selector: 'edge[provisional="true"]',
            style: { "line-style": "dashed", "line-color": "#e89068" },
          },
          {
            selector: 'node[kind="team"]',
            style: {
              shape: "round-rectangle",
              width: 120,
              height: 34,
              "background-color": "#17233a",
              "text-valign": "center",
              "text-margin-y": 0,
            },
          },
          {
            selector: 'edge[layout="dagre"]',
            style: {
              "curve-style": "taxi",
              "taxi-direction": "downward",
              "taxi-turn": 28,
            },
          },
          {
            selector: ":selected",
            style: {
              "border-width": 4,
              "border-color": "#ffffff",
              "overlay-color": "#6ee7b7",
              "overlay-opacity": 0.18,
              "overlay-padding": 8,
            },
          },
          { selector: ".is-highlighted", style: { opacity: 1, "z-index": 10 } },
          {
            selector: "edge.is-highlighted",
            style: {
              width: 3,
              "line-color": "#6ee7b7",
              "target-arrow-color": "#6ee7b7",
            },
          },
          { selector: ".is-faded", style: { opacity: 0.09 } },
        ],
      });
      core.on("tap", "node", (event) => {
        if (event.target.data("selectable") === false) return;
        onSelectRef.current(
          (event.target.data("canonicalId") as string | undefined) ??
            event.target.id(),
        );
      });
      graph.current = core;
      register(core);
      applyGraphSelection(core, selectedRef.current);
    });
    return () => {
      disposed = true;
      graph.current = null;
      register(null);
      core?.destroy();
    };
  }, [elements, register]);

  useEffect(() => {
    if (graph.current) applyGraphSelection(graph.current, selected);
  }, [selected]);

  return (
    <div
      className="network-canvas"
      ref={container}
      role="img"
      aria-label="Interactive Relationship Explorer. The relationship explorer list below provides the same entities, evidence, and actions."
    />
  );
}
