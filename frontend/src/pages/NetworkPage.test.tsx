import axe from "axe-core";
import { fireEvent, screen } from "@testing-library/react";
import { NetworkPage } from "./NetworkPage";
import { installApiFixture, page } from "../test/fixtures";
import { renderRoute } from "../test/render";

vi.mock("../components/NetworkGraph", () => ({
  NetworkGraph: ({ onSelect }: { onSelect: (id: string) => void }) => (
    <button type="button" onClick={() => onSelect("coach-1")}>
      Test graph node
    </button>
  ),
}));

describe("NetworkPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("defaults to a focused season and preserves edge verification metadata", async () => {
    installApiFixture();
    renderRoute(<NetworkPage />, "/network?season=2020&team=team_hou");
    expect(
      await screen.findByRole("heading", { name: "Coaching network" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Season" })).toHaveValue(
      "2020",
    );
    expect(await screen.findByText("HOU · Weeks 4–4")).toBeInTheDocument();
    expect(screen.getByText("shared duty")).toBeInTheDocument();
    expect(screen.getAllByText("provisional").length).toBeGreaterThan(0);
  });

  it("offers a keyboard-accessible text alternative and coach selection", async () => {
    installApiFixture();
    renderRoute(<NetworkPage />, "/network?season=2020");
    fireEvent.click(
      await screen.findByRole("button", { name: "Test graph node" }),
    );
    expect(screen.getByText("Selected coach")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open coach profile" }),
    ).toHaveAttribute("href", "/coaches/coach-1");
  });

  it("renders a useful empty state", async () => {
    installApiFixture({ "/network/edges": page([]) });
    renderRoute(<NetworkPage />, "/network?season=2025");
    expect(
      await screen.findByText(
        "No overlapping staff connections match these filters.",
      ),
    ).toBeInTheDocument();
  });

  it("applies URL-backed role filtering", async () => {
    installApiFixture();
    renderRoute(
      <NetworkPage />,
      "/network?season=2020&role=quarterbacks_coach",
    );
    expect(
      await screen.findByText(
        "No overlapping staff connections match these filters.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Role")).toHaveValue("quarterbacks_coach");
  });

  it("has no automated accessibility violations in the populated state", async () => {
    installApiFixture();
    renderRoute(<NetworkPage />, "/network?season=2020");
    await screen.findByRole("heading", { name: "Visible connections" });
    const result = await axe.run(document.body, {
      rules: {
        region: { enabled: false },
        "color-contrast": { enabled: false },
      },
    });
    expect(result.violations).toEqual([]);
  });
});
