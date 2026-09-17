import type { Core, ElementDefinition } from "cytoscape";
import { useEffect, useRef } from "react";
import { applyGraphSelection } from "./networkSelection";

export function NetworkGraph({
  elements,
  selected,
  highlighted,
  onSelect,
  register,
}: {
  elements: ElementDefinition[];
  selected: string | null;
  highlighted?: readonly string[];
  onSelect: (id: string) => void;
  register: (core: Core | null) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const graph = useRef<Core | null>(null);
  const selectedRef = useRef<string | readonly string[] | null>(
    highlighted?.length ? highlighted : selected,
  );
  const onSelectRef = useRef(onSelect);
  selectedRef.current = highlighted?.length ? highlighted : selected;
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
        minZoom: 0.02,
        maxZoom: 2.4,
        style: [
          {
            selector: "node",
            style: {
              "background-color": "#c86b32",
              color: "#f2f0ea",
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
              "background-color": "#d6b36a",
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
              "background-color": "#7e9b76",
              color: "#111315",
              "font-weight": 800,
              "text-valign": "center",
              "text-margin-y": 0,
            },
          },
          {
            selector: 'node[kind="year"]',
            style: {
              shape: "round-rectangle",
              width: 76,
              height: 32,
              "background-color": "#202428",
              "border-width": 2,
              "border-color": "#c86b32",
              "text-valign": "center",
              "text-margin-y": 0,
            },
          },
          {
            selector: "edge",
            style: {
              width: 1.4,
              "line-color": "#a7adb3",
              opacity: 0.8,
              "curve-style": "bezier",
              "target-arrow-shape": "triangle",
              "target-arrow-color": "#a7adb3",
              "arrow-scale": 0.65,
            },
          },
          {
            selector: 'edge[kind="qb_team_season"]',
            style: {
              "line-color": "#a7adb3",
              "target-arrow-color": "#a7adb3",
            },
          },
          {
            selector: 'edge[provisional="true"]',
            style: { "line-style": "dashed", "line-color": "#a7adb3" },
          },
          {
            selector: 'edge[kind="identity_continuity"]',
            style: {
              "line-style": "dotted",
              "line-color": "#a7adb3",
              "target-arrow-shape": "none",
              width: 2,
              opacity: 0.8,
            },
          },
          {
            selector: 'node[kind="team"]',
            style: {
              shape: "round-rectangle",
              width: 120,
              height: 34,
              "background-color": "#202428",
              "text-valign": "center",
              "text-margin-y": 0,
            },
          },
          {
            selector: 'edge[layout="journey"]',
            style: {
              "curve-style": "straight",
              "target-arrow-shape": "none",
            },
          },
          {
            selector: 'edge[layout="journey"][kind="coach_assignment"]',
            style: {
              label: "data(label)",
              color: "#f2f0ea",
              "font-size": 8,
              "text-background-color": "#202428",
              "text-background-opacity": 0.86,
              "text-background-padding": "2px",
              "text-rotation": "autorotate",
            },
          },
          {
            selector: ":selected",
            style: {
              "border-width": 4,
              "border-color": "#c86b32",
              "overlay-color": "#c86b32",
              "overlay-opacity": 0,
              "overlay-padding": 8,
            },
          },
          { selector: ".is-highlighted", style: { opacity: 1, "z-index": 10 } },
          {
            selector: "edge.is-highlighted",
            style: {
              width: 3,
              "line-color": "#c86b32",
              "target-arrow-color": "#c86b32",
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
      const initialIds = new Set(
        Array.isArray(selectedRef.current)
          ? selectedRef.current
          : selectedRef.current
            ? [selectedRef.current]
            : [],
      );
      const initialNodes = core.nodes().filter((node) => {
        const canonicalId = node.data("canonicalId") as string | undefined;
        return (
          initialIds.has(node.id()) ||
          Boolean(canonicalId && initialIds.has(canonicalId))
        );
      });
      if (!initialNodes.empty()) core.fit(core.elements(".is-highlighted"), 84);
    });
    return () => {
      disposed = true;
      graph.current = null;
      register(null);
      core?.destroy();
    };
  }, [elements, register]);

  useEffect(() => {
    if (graph.current)
      applyGraphSelection(
        graph.current,
        highlighted?.length ? highlighted : selected,
      );
  }, [highlighted, selected]);

  return (
    <div
      className="network-canvas"
      data-compact={
        elements.filter((element) => !element.data.source).length <= 20
      }
      ref={container}
      role="img"
      aria-label="Interactive Relationship Explorer. The relationship explorer list below provides the same entities, evidence, and actions."
    />
  );
}
