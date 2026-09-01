import type { Core } from "cytoscape";

export function applyGraphSelection(core: Core, selected: string | null) {
  const all = core.elements();
  all.removeClass("is-highlighted is-faded");
  all.unselect();
  if (!selected) return;
  const selectedNodes = core.nodes().filter((node) => {
    const canonicalId = node.data("canonicalId") as string | undefined;
    return node.id() === selected || canonicalId === selected;
  });
  if (selectedNodes.empty()) return;

  const selectedKinds = new Set(
    selectedNodes.map((node) => node.data("kind") as string | undefined),
  );
  const directlyConnectedEdges = selectedNodes.connectedEdges();
  const directlyConnectedNodes = directlyConnectedEdges.connectedNodes();
  const teamSeasons = selectedKinds.has("team_season")
    ? selectedNodes
    : directlyConnectedNodes.filter(
        (node) => node.data("kind") === "team_season",
      );
  const branchEdges = teamSeasons.connectedEdges();
  const highlighted = selectedNodes
    .union(directlyConnectedEdges)
    .union(directlyConnectedNodes)
    .union(teamSeasons)
    .union(branchEdges)
    .union(branchEdges.connectedNodes());
  highlighted.addClass("is-highlighted");
  all.difference(highlighted).addClass("is-faded");
  selectedNodes.select();
}
