import axe from "axe-core";
import { fireEvent, screen } from "@testing-library/react";
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
    renderRoute(<StatisticsPage />);
    fireEvent.click(await screen.findByText("More filters"));
    fireEvent.click(
      screen.getByRole("checkbox", { name: "Show expanded metrics" }),
    );
    expect(
      screen.getByRole("columnheader", { name: "INT rate" }),
    ).toBeInTheDocument();
    expect(screen.getByText("2.0%")).toBeInTheDocument();
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
