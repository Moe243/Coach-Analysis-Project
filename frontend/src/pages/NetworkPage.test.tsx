import axe from "axe-core";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import type { Core, ElementDefinition } from "cytoscape";
import { NetworkPage } from "./NetworkPage";
import { installApiFixture, page, qbSeason } from "../test/fixtures";
import { renderRoute } from "../test/render";

const graphHarness = vi.hoisted(() => {
  const neighborhood = {};
  return {
    fit: vi.fn(),
    zoom: vi.fn(() => 1),
    neighborhood,
    nodes: vi.fn(() => ({
      filter: vi.fn(() => ({
        empty: () => false,
        closedNeighborhood: () => neighborhood,
      })),
    })),
  };
});

vi.mock("../components/NetworkGraph", () => ({
  NetworkGraph: ({
    elements,
    onSelect,
    selected,
    register,
  }: {
    elements: ElementDefinition[];
    onSelect: (id: string) => void;
    selected: string | null;
    register: (core: Core | null) => void;
  }) => {
    register(graphHarness as unknown as Core);
    return (
      <div data-testid="relationship-graph">
        {elements
          .filter((element) => !element.data.source)
          .map((element) => (
            <button
              key={String(element.data.id)}
              type="button"
              data-selected={
                selected === (element.data.canonicalId ?? element.data.id)
                  ? "true"
                  : "false"
              }
              onClick={() =>
                onSelect(String(element.data.canonicalId ?? element.data.id))
              }
            >
              Graph {String(element.data.label)}
            </button>
          ))}
      </div>
    );
  },
}));

describe("NetworkPage Relationship Explorer", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    graphHarness.fit.mockClear();
    graphHarness.nodes.mockClear();
  });

  it("excludes non-QBs from the QB Journey selector", async () => {
    const runningBack = {
      ...qbSeason,
      player_id: "rb-trick",
      display_name: "Trick Running Back",
      position: "RB" as never,
      dropbacks: 1,
      qualifies_default: false,
    };
    installApiFixture({ "/qbs": page([qbSeason, runningBack]) });
    renderRoute(
      <NetworkPage />,
      "/network?mode=qb_journey&player_id=qb-1&start_season=2024&end_season=2025",
    );
    const selector = screen.getByRole("combobox", {
      name: "Quarterback",
    });
    expect(
      await screen.findByRole("option", { name: "Test Quarterback" }),
    ).toBeInTheDocument();
    expect(selector).not.toHaveTextContent("Trick Running Back");
  });

  it.each([
    [
      "Coach Journey",
      "/network?mode=coach_journey&coach_id=coach-1&start_season=2024&end_season=2025",
      "/api/relationships/explorer?mode=coach_journey&coach_id=coach-1&start_season=2024&end_season=2025&include_provisional=true",
    ],
    [
      "QB Journey",
      "/network?mode=qb_journey&player_id=qb-1&start_season=2024&end_season=2025",
      "/api/relationships/explorer?mode=qb_journey&player_id=qb-1&start_season=2024&end_season=2025&include_provisional=true",
    ],
    [
      "Team History",
      "/network?mode=team_history&team_id=team_den&start_season=2024&end_season=2025",
      "/api/relationships/explorer?mode=team_history&team_id=team_den&start_season=2024&end_season=2025&include_provisional=true",
    ],
    [
      "Full Network",
      "/network?mode=full_network&anchor=team&team_id=team_den&start_season=2024&end_season=2025",
      "/api/relationships/explorer?mode=full_network&team_id=team_den&start_season=2024&end_season=2025&include_provisional=true",
    ],
  ])(
    "requests the published %s endpoint with the complete API contract",
    async (_mode, route, expectedRequest) => {
      const fetchMock = installApiFixture();
      renderRoute(<NetworkPage />, route);
      await screen.findByRole("heading", {
        name: "Relationship explorer list",
      });

      const explorerRequests = fetchMock.mock.calls
        .map(([input]) => String(input))
        .filter((request) => request.includes("/relationships/explorer"));
      expect(explorerRequests).toEqual([expectedRequest]);
    },
  );

  it("shows one coach across multiple teams in Coach Journey", async () => {
    installApiFixture();
    renderRoute(
      <NetworkPage />,
      "/network?mode=coach_journey&coach_id=coach-1&start_season=2024&end_season=2025",
    );
    expect(
      await screen.findByRole("heading", { name: "Relationship Explorer" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "View" })).toHaveValue(
      "coach_journey",
    );
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "Coach" })).toHaveValue(
        "coach-1",
      ),
    );
    expect(screen.getAllByText(/Test Coach →/)).toHaveLength(2);
    expect(screen.getByText(/Test Coach → DEN 2024/)).toBeInTheDocument();
    expect(screen.getByText(/Test Coach → HOU 2025/)).toBeInTheDocument();
  });

  it("shows one QB across years and distinct same-season teams with correct PAE", async () => {
    installApiFixture();
    renderRoute(
      <NetworkPage />,
      "/network?mode=qb_journey&player_id=qb-1&start_season=2024&end_season=2025",
    );
    await screen.findByRole("heading", { name: "Relationship explorer list" });
    expect(screen.getByText(/Test Quarterback → DEN 2024/)).toBeInTheDocument();
    expect(screen.getByText(/Test Quarterback → DEN 2025/)).toBeInTheDocument();
    expect(screen.getByText(/Test Quarterback → HOU 2025/)).toBeInTheDocument();
    expect(screen.getAllByText("+0.070").length).toBeGreaterThan(0);
    expect(screen.getAllByText("-0.050").length).toBeGreaterThan(0);
  });

  it("preserves Team History intervals, roles, interim, shared, and evidence states", async () => {
    installApiFixture();
    renderRoute(
      <NetworkPage />,
      "/network?mode=team_history&team_id=team_den&start_season=2024&end_season=2025",
    );
    await screen.findByRole("heading", { name: "Relationship explorer list" });
    expect(
      screen.getAllByText(/Head coach · Weeks 1–9/).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/Head coach · Weeks 10–18/).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("interim").length).toBeGreaterThan(0);
    expect(screen.getAllByText("verified").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Denver staff" })).toHaveAttribute(
      "href",
      "https://example.com/den",
    );
  });

  it("restores Full Network mode, anchor, years, evidence, and provisional URL state", async () => {
    installApiFixture();
    renderRoute(
      <NetworkPage />,
      "/network?mode=full_network&anchor=team&team_id=team_den&start_season=2024&end_season=2025&verification=verified&provisional=exclude",
    );
    await screen.findByRole("heading", { name: "Relationship explorer list" });
    expect(screen.getByRole("combobox", { name: "View" })).toHaveValue(
      "full_network",
    );
    expect(screen.getByRole("combobox", { name: "Start from" })).toHaveValue(
      "team",
    );
    expect(screen.getByRole("combobox", { name: "Team" })).toHaveValue(
      "team_den",
    );
    expect(screen.getByRole("combobox", { name: "Start season" })).toHaveValue(
      "2024",
    );
    expect(screen.getByRole("combobox", { name: "Evidence" })).toHaveValue(
      "verified",
    );
  });

  it("reconstructs every supported display filter and canonical selection from the URL", async () => {
    installApiFixture();
    renderRoute(
      <NetworkPage />,
      "/network?mode=team_history&team_id=team_den&start_season=2024&end_season=2025&roles=head_coach&verification=verified&provisional=exclude&coaches=hide&eligible=true&min_dropbacks=200&pae_min=0.01&pae_max=0.08&selected=qb%3Aqb-1&focus=qb%3Aqb-1",
    );
    expect(await screen.findByText("Selected quarterback")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Show & filter"));
    expect(screen.getByRole("checkbox", { name: "Head coach" })).toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: "Offensive coordinator" }),
    ).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Coaches" })).not.toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: "Include provisional" }),
    ).not.toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: "Eligible QBs only" }),
    ).toBeChecked();
    expect(
      screen.getByRole("spinbutton", { name: "Minimum dropbacks" }),
    ).toHaveValue(200);
    expect(screen.getByRole("spinbutton", { name: "Minimum PAE" })).toHaveValue(
      0.01,
    );
    expect(screen.getByRole("spinbutton", { name: "Maximum PAE" })).toHaveValue(
      0.08,
    );
    expect(screen.getByText("focused")).toBeInTheDocument();
  });

  it("keeps independent QB facts when a role filter removes every coach edge", async () => {
    installApiFixture();
    renderRoute(
      <NetworkPage />,
      "/network?mode=team_history&team_id=team_den&start_season=2024&end_season=2025&roles=quarterbacks_coach",
    );
    await screen.findByRole("heading", { name: "Relationship explorer list" });
    expect(screen.queryByText(/Assignment den-/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/QB-team-season qb-1 · team_den · 2024/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/QB-team-season qb-2 · team_den · 2025/),
    ).toBeInTheDocument();
  });

  it("renders unavailable PAE as an em dash instead of zero", async () => {
    installApiFixture();
    renderRoute(
      <NetworkPage />,
      "/network?mode=team_history&team_id=team_den&start_season=2025&end_season=2025",
    );
    const card = await screen.findByText(
      /QB-team-season qb-2 · team_den · 2025/,
    );
    const article = card.closest("article");
    expect(article).not.toBeNull();
    expect(article).toHaveTextContent("PAE—");
    expect(article).not.toHaveTextContent("PAE0.000");
  });

  it("selects and focuses through equivalent controls, then supports Back and Reset", async () => {
    installApiFixture();
    renderRoute(
      <NetworkPage />,
      "/network?mode=team_history&team_id=team_den&start_season=2024&end_season=2025",
    );
    const coachEntity = (
      await screen.findByText("Test Coach", {
        selector: ".accessible-entity-list strong",
      })
    ).closest("article");
    expect(coachEntity).not.toBeNull();
    fireEvent.click(coachEntity!.querySelectorAll("button")[0]);
    expect(screen.getByText("Selected coach")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open coach profile" }),
    ).toHaveAttribute("href", "/coaches/coach-1");
    fireEvent.click(screen.getByRole("button", { name: "Focus selected" }));
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "View" })).toHaveValue(
        "coach_journey",
      ),
    );
    expect(await screen.findByText("focused")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Back to prior focus" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "View" })).toHaveValue(
        "team_history",
      ),
    );
    await screen.findByRole("heading", { name: "Relationship explorer list" });
    fireEvent.click(screen.getByRole("button", { name: "Reset explorer" }));
    expect(screen.getByText("Select an entity")).toBeInTheDocument();
  });

  it("clears a selected coach when filtering removes it but leaves QB facts", async () => {
    installApiFixture();
    renderRoute(
      <NetworkPage />,
      "/network?mode=team_history&team_id=team_den&start_season=2024&end_season=2025&selected=coach%3Acoach-1",
    );
    await screen.findByText("Selected coach");
    fireEvent.click(screen.getByText("Show & filter"));
    for (const checkbox of screen.getAllByRole("checkbox", {
      name: /Head coach|Offensive coordinator|Play-caller|QB coach/,
    })) {
      fireEvent.click(checkbox);
    }
    await waitFor(() =>
      expect(screen.getByText("Select an entity")).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/QB-team-season qb-1 · team_den · 2024/),
    ).toBeInTheDocument();
  });

  it("restores and preserves a visible QB selection when coach filters rebuild the graph", async () => {
    installApiFixture();
    renderRoute(
      <NetworkPage />,
      "/network?mode=team_history&team_id=team_den&start_season=2024&end_season=2025&display=network&selected=qb%3Aqb-1",
    );
    expect(await screen.findByText("Selected quarterback")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open QB profile" }),
    ).toHaveAttribute("href", "/qbs/qb-1");
    fireEvent.click(screen.getByText("Show & filter"));
    fireEvent.click(screen.getByRole("checkbox", { name: "Head coach" }));
    expect(await screen.findByText("Selected quarterback")).toBeInTheDocument();
    expect(
      screen
        .getByTestId("relationship-graph")
        .querySelector('[data-selected="true"]'),
    ).toHaveTextContent("Graph Test Quarterback");
    expect(
      screen.getByRole("link", { name: "Open QB profile" }),
    ).toHaveAttribute("href", "/qbs/qb-1");
  });

  it("defaults Team History to the chronological timeline", async () => {
    installApiFixture();
    renderRoute(
      <NetworkPage />,
      "/network?mode=team_history&team_id=team_den&start_season=2024&end_season=2025",
    );
    expect(
      await screen.findByLabelText("Chronological relationship timeline"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Timeline" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const seasons = screen
      .getAllByRole("button")
      .filter((button) => button.classList.contains("timeline-anchor"));
    expect(seasons.map((button) => button.textContent)).toEqual([
      expect.stringContaining("2024"),
      expect.stringContaining("2025"),
      expect.stringContaining("2025"),
    ]);
  });

  it("locks Journey modes to the fixed hierarchy view", async () => {
    installApiFixture();
    renderRoute(
      <NetworkPage />,
      "/network?mode=qb_journey&player_id=qb-1&start_season=2024&end_season=2025&display=timeline",
    );
    expect(await screen.findByTestId("relationship-graph")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hierarchy" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(
      screen.queryByLabelText("Chronological relationship timeline"),
    ).not.toBeInTheDocument();
  });

  it("offers the deterministic chronological graph as a Tree display", async () => {
    installApiFixture();
    renderRoute(
      <NetworkPage />,
      "/network?mode=team_history&team_id=team_den&start_season=2024&end_season=2025",
    );
    await screen.findByLabelText("Chronological relationship timeline");
    fireEvent.click(screen.getByRole("button", { name: "Tree" }));
    expect(await screen.findByTestId("relationship-graph")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tree" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("requests the complete supported Full Network without an anchor", async () => {
    const fetchMock = installApiFixture();
    renderRoute(
      <NetworkPage />,
      "/network?mode=full_network&anchor=all&start_season=2010&end_season=2025",
    );
    await screen.findByRole("heading", { name: "Relationship explorer list" });
    expect(screen.getByRole("combobox", { name: "Start from" })).toHaveValue(
      "all",
    );
    const requests = fetchMock.mock.calls
      .map(([input]) => String(input))
      .filter((request) => request.includes("/relationships/explorer"));
    expect(requests).toEqual([
      "/api/relationships/explorer?mode=full_network&start_season=2010&end_season=2025&include_provisional=true",
    ]);
  });

  it("fits the complete Full Network on demand", async () => {
    installApiFixture();
    renderRoute(
      <NetworkPage />,
      "/network?mode=full_network&anchor=team&team_id=team_den&start_season=2024&end_season=2025",
    );
    fireEvent.click(await screen.findByRole("button", { name: "Fit All" }));
    expect(graphHarness.fit).toHaveBeenCalledWith(undefined, 36);
  });

  it.each([
    ["Test Coach", "Selected coach", "/coaches/coach-1"],
    ["Test Quarterback", "Selected quarterback", "/qbs/qb-1"],
  ])(
    "searches the Full Network by canonical identity and selects %s",
    async (name, detailLabel, profilePath) => {
      installApiFixture();
      renderRoute(
        <NetworkPage />,
        "/network?mode=full_network&anchor=team&team_id=team_den&start_season=2024&end_season=2025",
      );
      const search = await screen.findByPlaceholderText("Search coach or QB");
      fireEvent.change(search, { target: { value: name } });
      fireEvent.click(
        await screen.findByRole("option", { name: new RegExp(name) }),
      );
      expect(await screen.findByText(detailLabel)).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: /Open .* profile/ }),
      ).toHaveAttribute("href", profilePath);
      await waitFor(() =>
        expect(graphHarness.fit).toHaveBeenCalledWith(
          graphHarness.neighborhood,
          84,
        ),
      );
      fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
      expect(screen.getByText("Select an entity")).toBeInTheDocument();
      expect(graphHarness.fit).toHaveBeenCalledWith(undefined, 36);
    },
  );

  it("explains a 413 response and never presents a partial graph", async () => {
    const base = installApiFixture();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/relationships/explorer")) {
          return new Response(
            JSON.stringify({
              detail: "Relationship scope is too large; narrow it",
            }),
            {
              status: 413,
              headers: { "Content-Type": "application/json" },
            },
          );
        }
        return base(input);
      }),
    );
    renderRoute(
      <NetworkPage />,
      "/network?mode=team_history&team_id=team_den&start_season=2024&end_season=2025",
    );
    expect(
      await screen.findByText("Relationship scope is too large"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/No partial graph was returned/),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("relationship-graph")).not.toBeInTheDocument();
  });

  it("retries all lookup dependencies and the explorer request", async () => {
    const fixture = installApiFixture();
    let failed = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes("/relationships/explorer") && !failed) {
        failed = true;
        return new Response(
          JSON.stringify({ detail: "Explorer unavailable" }),
          {
            status: 503,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      return fixture(input);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute(
      <NetworkPage />,
      "/network?mode=team_history&team_id=team_den&start_season=2024&end_season=2025",
    );
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(
      await screen.findByRole("heading", {
        name: "Relationship explorer list",
      }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter(([input]) =>
          String(input).includes("/relationships/explorer"),
        ),
      ).toHaveLength(2);
    });
  });

  it("has no automated accessibility violations and avoids causal coach claims", async () => {
    installApiFixture();
    renderRoute(
      <NetworkPage />,
      "/network?mode=team_history&team_id=team_den&start_season=2024&end_season=2025",
    );
    await screen.findByRole("heading", { name: "Relationship explorer list" });
    expect(screen.getByText(/not influence or causation/)).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/coach produced/i);
    const result = await axe.run(document.body, {
      rules: {
        region: { enabled: false },
        "color-contrast": { enabled: false },
      },
    });
    expect(result.violations).toEqual([]);
  });
});
