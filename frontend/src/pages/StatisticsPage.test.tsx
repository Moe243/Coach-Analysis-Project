import axe from "axe-core";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { useLocation } from "react-router-dom";
import { StatisticsPage } from "./StatisticsPage";
import { installApiFixture, page } from "../test/fixtures";
import { renderRoute } from "../test/render";

describe("StatisticsPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders PAE, evidence, team abbreviation, and eligibility from the API", async () => {
    installApiFixture();
    renderRoute(<StatisticsPage />, "/statistics?season=2025");
    expect(
      await screen.findByRole("link", { name: "Test Quarterback" }),
    ).toBeInTheDocument();
    expect(screen.getByText("+0.070")).toBeInTheDocument();
    expect(screen.getByText("DEN")).toBeInTheDocument();
    expect(screen.getByText("eligible")).toBeInTheDocument();
    expect(screen.getByText(/Head coach · verified/)).toBeInTheDocument();
  });

  it("shows an empty state for no matching rows", async () => {
    installApiFixture({ "/qbs": page([]) });
    renderRoute(<StatisticsPage />);
    expect(await screen.findByText("No records match")).toBeInTheDocument();
  });

  it("shows a loading state while API requests are pending", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => undefined)),
    );
    renderRoute(<StatisticsPage />);
    expect(screen.getByText("Loading published data")).toBeInTheDocument();
  });

  it("shows a retryable error without fallback data", async () => {
    installApiFixture({ "/qbs": new Error("Database unavailable") });
    renderRoute(<StatisticsPage />);
    expect(
      await screen.findByText("Published data could not be loaded"),
    ).toBeInTheDocument();
    expect(screen.getByText("Database unavailable")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Test Quarterback" }),
    ).not.toBeInTheDocument();
  });

  it("retries every required statistics query after a dependency failure", async () => {
    const fixture = installApiFixture();
    let failedAssignments = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(String(input), "http://app.test").pathname;
      if (path.endsWith("/assignments") && !failedAssignments) {
        failedAssignments = true;
        return new Response(
          JSON.stringify({ detail: "Assignments unavailable" }),
          {
            status: 503,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      return fixture(input);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute(<StatisticsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(
      await screen.findByRole("link", { name: "Test Quarterback" }),
    ).toBeInTheDocument();
    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(
        ([input]) => new URL(String(input), "http://app.test").pathname,
      );
      expect(
        paths.filter((path) => path.endsWith("/assignments")),
      ).toHaveLength(2);
      expect(paths.filter((path) => path.endsWith("/teams"))).toHaveLength(2);
      expect(paths.filter((path) => path.endsWith("/qbs"))).toHaveLength(2);
    });
  });

  it("filters the complete client result by minimum dropbacks", async () => {
    installApiFixture();
    renderRoute(<StatisticsPage />, "/statistics?minDropbacks=700");
    expect(await screen.findByText("No records match")).toBeInTheDocument();
  });

  it("restores URL-backed team, season, role, evidence, eligibility, and sort filters", async () => {
    installApiFixture();
    renderRoute(
      <StatisticsPage />,
      "/statistics?team=team_den&season=2025&role=head_coach&verification=verified&eligibility=eligible&sort=epa",
    );
    await screen.findByRole("link", { name: "Test Quarterback" });
    expect(screen.getByLabelText("Team")).toHaveValue("team_den");
    expect(screen.getByLabelText("Season")).toHaveValue("2025");
    expect(screen.getByLabelText("Role")).toHaveValue("head_coach");
    expect(screen.getByLabelText("Evidence")).toHaveValue("verified");
    expect(screen.getByLabelText("Eligibility")).toHaveValue("eligible");
    expect(screen.getByLabelText("Sort")).toHaveValue("epa");
  });

  it("applies role and evidence filters without fabricating fallback rows", async () => {
    installApiFixture();
    renderRoute(
      <StatisticsPage />,
      "/statistics?role=play_caller&verification=verified",
    );
    expect(await screen.findByText("No records match")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Test Quarterback" }),
    ).not.toBeInTheDocument();
  });

  it("reveals expanded metric controls accessibly", async () => {
    installApiFixture();
    function LocationProbe() {
      return <output data-testid="location">{useLocation().search}</output>;
    }
    renderRoute(
      <>
        <StatisticsPage />
        <LocationProbe />
      </>,
    );
    fireEvent.click(await screen.findByText("More filters"));
    fireEvent.click(
      screen.getByRole("checkbox", { name: "Show expanded metrics" }),
    );
    expect(
      await screen.findByRole("columnheader", { name: "INT rate" }),
    ).toBeInTheDocument();
    expect(screen.getByText("2.0%")).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("expanded=true");
  });

  it("restores expanded metrics from the URL", async () => {
    installApiFixture();
    renderRoute(<StatisticsPage />, "/statistics?expanded=true");
    fireEvent.click(await screen.findByText("More filters"));
    expect(
      screen.getByRole("checkbox", { name: "Show expanded metrics" }),
    ).toBeChecked();
    expect(
      await screen.findByRole("columnheader", { name: "Success" }),
    ).toBeInTheDocument();
  });

  it("describes coach filtering as team-season context rather than exact overlap", async () => {
    installApiFixture();
    renderRoute(<StatisticsPage />);
    expect(
      await screen.findByText(/do not claim exact weekly QB-coach overlap/i),
    ).toBeInTheDocument();
  });

  it("has no automated accessibility violations in the populated state", async () => {
    installApiFixture();
    renderRoute(<StatisticsPage />);
    await screen.findByRole("link", { name: "Test Quarterback" });
    const result = await axe.run(document.body, {
      rules: {
        region: { enabled: false },
        "color-contrast": { enabled: false },
      },
    });
    expect(result.violations).toEqual([]);
  });
});
