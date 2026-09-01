import type { Core } from "cytoscape";

export function applyGraphSelection(core: Core, selected: string | null) {
  const all = core.elements();
  all.removeClass("is-highlighted is-faded");
  all.unselect();
  if (!selected) return;
  const selectedNode = core.getElementById(selected);
  if (selectedNode.empty()) return;
  const connectedEdges = selectedNode.connectedEdges();
  const highlighted = selectedNode
    .union(connectedEdges)
    .union(connectedEdges.connectedNodes());
  highlighted.addClass("is-highlighted");
  all.difference(highlighted).addClass("is-faded");
  selectedNode.select();
}
