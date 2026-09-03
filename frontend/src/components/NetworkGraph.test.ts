import cytoscape, { type ElementDefinition } from "cytoscape";
import { createElement } from "react";
import { render, waitFor } from "@testing-library/react";
import { NetworkGraph } from "./NetworkGraph";
import { applyGraphSelection } from "./networkSelection";

vi.mock("cytoscape", async (importOriginal) => {
  const actual = await importOriginal<typeof import("cytoscape")>();
  const createCore = (actual as unknown as { default: typeof cytoscape })
    .default;
  return {
    ...actual,
    default: vi.fn((options: cytoscape.CytoscapeOptions = {}) =>
      createCore({
        ...options,
        container: undefined,
        headless: true,
        styleEnabled: true,
        layout: { name: "preset" },
      }),
    ),
  };
});

describe("applyGraphSelection", () => {
  function branchCore() {
    return cytoscape({
      headless: true,
      elements: [
        {
          data: {
            id: "appearance:qb:a:one",
            canonicalId: "qb:a",
            kind: "quarterback",
          },
        },
        {
          data: {
            id: "appearance:qb:b:two",
            canonicalId: "qb:b",
            kind: "quarterback",
          },
        },
        {
          data: {
            id: "appearance:coach:a:one",
            canonicalId: "coach:a",
            kind: "coach",
          },
        },
        {
          data: {
            id: "appearance:coach:b:two",
            canonicalId: "coach:b",
            kind: "coach",
          },
        },
        { data: { id: "team:one", kind: "team_season" } },
        { data: { id: "team:two", kind: "team_season" } },
        {
          data: {
            id: "qb-one",
            source: "appearance:qb:a:one",
            target: "team:one",
          },
        },
        {
          data: {
            id: "qb-two",
            source: "appearance:qb:b:two",
            target: "team:two",
          },
        },
        {
          data: {
            id: "coach-one",
            source: "appearance:coach:a:one",
            target: "team:one",
          },
        },
        {
          data: {
            id: "coach-two",
            source: "appearance:coach:b:two",
            target: "team:two",
          },
        },
      ],
    });
  }

  it("expands a selected QB through its team-season to every coach in that branch", () => {
    const core = branchCore();
    applyGraphSelection(core, "qb:a");
    for (const id of [
      "appearance:qb:a:one",
      "team:one",
      "appearance:coach:a:one",
      "qb-one",
      "coach-one",
    ]) {
      expect(core.getElementById(id).hasClass("is-highlighted")).toBe(true);
    }
    for (const id of [
      "appearance:qb:b:two",
      "team:two",
      "appearance:coach:b:two",
      "qb-two",
      "coach-two",
    ]) {
      expect(core.getElementById(id).hasClass("is-faded")).toBe(true);
    }
    core.destroy();
  });

  it("expands a selected coach through its team-season to every QB in that branch", () => {
    const core = branchCore();
    applyGraphSelection(core, "coach:a");
    for (const id of [
      "appearance:coach:a:one",
      "team:one",
      "appearance:qb:a:one",
      "coach-one",
      "qb-one",
    ]) {
      expect(core.getElementById(id).hasClass("is-highlighted")).toBe(true);
    }
    for (const id of [
      "appearance:coach:b:two",
      "team:two",
      "appearance:qb:b:two",
      "coach-two",
      "qb-two",
    ]) {
      expect(core.getElementById(id).hasClass("is-faded")).toBe(true);
    }
    core.destroy();
  });

  it("highlights the selected node, connected context, and edges while fading unrelated elements", () => {
    const core = cytoscape({
      headless: true,
      elements: [
        { data: { id: "coach-a" } },
        { data: { id: "coach-b" } },
        { data: { id: "coach-c" } },
        { data: { id: "team:one" } },
        { data: { id: "team:two" } },
        { data: { id: "staff-a-b", source: "coach-a", target: "coach-b" } },
        { data: { id: "context-a", source: "team:one", target: "coach-a" } },
        { data: { id: "context-c", source: "team:two", target: "coach-c" } },
      ],
    });

    applyGraphSelection(core, "coach-a");

    for (const id of [
      "coach-a",
      "coach-b",
      "team:one",
      "staff-a-b",
      "context-a",
    ]) {
      expect(core.getElementById(id).hasClass("is-highlighted")).toBe(true);
      expect(core.getElementById(id).hasClass("is-faded")).toBe(false);
    }
    for (const id of ["coach-c", "team:two", "context-c"]) {
      expect(core.getElementById(id).hasClass("is-faded")).toBe(true);
    }
    expect(core.getElementById("coach-a").selected()).toBe(true);

    applyGraphSelection(core, null);
    expect(core.elements(".is-highlighted, .is-faded")).toHaveLength(0);
    expect(core.$(":selected")).toHaveLength(0);
    core.destroy();
  });

  it("reapplies selection and neighborhood classes after graph reconstruction", async () => {
    const elements: ElementDefinition[] = [
      { data: { id: "coach:a", label: "A" }, position: { x: 10, y: 10 } },
      { data: { id: "coach:b", label: "B" }, position: { x: 30, y: 10 } },
      { data: { id: "coach:c", label: "C" }, position: { x: 10, y: 40 } },
      {
        data: { id: "team-season:t:2020", label: "T 2020" },
        position: { x: 20, y: 20 },
      },
      {
        data: { id: "team-season:u:2020", label: "U 2020" },
        position: { x: 40, y: 40 },
      },
      {
        data: {
          id: "relationship:a",
          source: "coach:a",
          target: "team-season:t:2020",
        },
      },
      {
        data: {
          id: "relationship:b",
          source: "coach:b",
          target: "team-season:t:2020",
        },
      },
      {
        data: {
          id: "relationship:c",
          source: "coach:c",
          target: "team-season:u:2020",
        },
      },
    ];
    let activeCore: cytoscape.Core | null = null;
    const register = vi.fn((core: cytoscape.Core | null) => {
      activeCore = core;
    });
    const props = { onSelect: vi.fn(), register };
    const view = render(
      createElement(NetworkGraph, { ...props, elements, selected: "coach:a" }),
    );
    await waitFor(() => expect(activeCore).not.toBeNull());
    const originalCore = activeCore!;
    expect(originalCore.getElementById("coach:a").selected()).toBe(true);

    view.rerender(
      createElement(NetworkGraph, {
        ...props,
        elements: elements.map((element) => ({ ...element })),
        selected: "coach:a",
      }),
    );
    await waitFor(() => expect(activeCore).not.toBe(originalCore));
    const rebuiltCore = activeCore!;
    expect(rebuiltCore.getElementById("coach:a").selected()).toBe(true);
    for (const id of ["coach:a", "team-season:t:2020", "relationship:a"]) {
      expect(rebuiltCore.getElementById(id).hasClass("is-highlighted")).toBe(
        true,
      );
    }
    for (const id of ["coach:c", "team-season:u:2020", "relationship:c"]) {
      expect(rebuiltCore.getElementById(id).hasClass("is-faded")).toBe(true);
    }
  });
});
