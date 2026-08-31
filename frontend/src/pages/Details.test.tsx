import axe from "axe-core";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { CoachDetailPage } from "./CoachDetailPage";
import { QbDetailPage } from "./QbDetailPage";
import { installApiFixture } from "../test/fixtures";
import { renderRoute } from "../test/render";

describe("detail pages", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows a QB history with actual, expected, PAE, coaching status, and model version", async () => {
    installApiFixture();
    renderRoute(
      <Routes>
        <Route path="/qbs/:playerId" element={<QbDetailPage />} />
      </Routes>,
      "/qbs/qb-1",
    );
    expect(
      await screen.findByRole("heading", { name: "Test Quarterback" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Out-of-sample expectations only."),
    ).toBeInTheDocument();
    expect(screen.getAllByText("+0.070").length).toBeGreaterThan(0);
    expect(screen.getByText("expected-test")).toBeInTheDocument();
    expect(screen.getByText("Head coach · Weeks 1–18")).toBeInTheDocument();
  });

  it("labels coach impact as exploratory and suppressed and links citations", async () => {
    installApiFixture();
    renderRoute(
      <Routes>
        <Route path="/coaches/:coachId" element={<CoachDetailPage />} />
      </Routes>,
      "/coaches/coach-1",
    );
    expect(
      await screen.findByRole("heading", { name: "Test Coach" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Coach effects are exploratory and suppressed."),
    ).toBeInTheDocument();
    expect(screen.getByText("suppressed exploratory")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View source/ })).toHaveAttribute(
      "href",
      "https://example.com/source",
    );
  });

  it("has no automated accessibility violations on both detail routes", async () => {
    installApiFixture();
    const qb = renderRoute(
      <Routes>
        <Route path="/qbs/:playerId" element={<QbDetailPage />} />
      </Routes>,
      "/qbs/qb-1",
    );
    await screen.findByRole("heading", { name: "Test Quarterback" });
    let result = await axe.run(document.body, {
      rules: {
        region: { enabled: false },
        "color-contrast": { enabled: false },
      },
    });
    expect(result.violations).toEqual([]);
    qb.unmount();

    renderRoute(
      <Routes>
        <Route path="/coaches/:coachId" element={<CoachDetailPage />} />
      </Routes>,
      "/coaches/coach-1",
    );
    await screen.findByRole("heading", { name: "Test Coach" });
    result = await axe.run(document.body, {
      rules: {
        region: { enabled: false },
        "color-contrast": { enabled: false },
      },
    });
    expect(result.violations).toEqual([]);
  });
});
