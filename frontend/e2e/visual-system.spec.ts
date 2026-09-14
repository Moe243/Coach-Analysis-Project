import { expect, test } from "@playwright/test";
import axe from "axe-core";

// Real local publication and pinned Ask snapshot, at every configured viewport.
// Screenshots are review artifacts, never analytical fixtures.
for (const view of [
  {
    name: "statistics",
    path: "/statistics?player=Baker&team=team_tb",
    heading: "Performance above expectation",
    ready: ".primary-link",
  },
  {
    name: "qb-profile",
    path: "/qbs/00-0034855",
    heading: "Baker Mayfield",
    ready: ".performance-chart",
  },
  {
    name: "coach-profile",
    path: "/coaches/coach-todd-bowles",
    heading: "Todd Bowles",
    ready: ".citation-list",
  },
  {
    name: "relationships",
    path: "/network?team_id=team_hou&start_season=2020&end_season=2020",
    heading: "Relationship Explorer",
    ready: ".relationship-card-grid article",
  },
  {
    name: "relationship-tree",
    path: "/network?team_id=team_hou&start_season=2020&end_season=2020&display=network",
    heading: "Relationship Explorer",
    ready: ".network-canvas canvas",
  },
  {
    name: "methodology",
    path: "/methodology",
    heading: "Does performance follow the coach?",
    ready: ".method-grid",
  },
  {
    name: "ask",
    path: "/ask",
    heading: "Ask Anything",
    ready: ".ask-page form",
  },
]) {
  test(`workstation contrast, keyboard focus and responsive surface: ${view.name}`, async ({
    page,
  }, testInfo) => {
    await page.goto(view.path);
    await expect(
      page.getByRole("heading", { name: view.heading, exact: true }),
    ).toBeVisible();
    // Real publication joins can exceed Playwright's 5s assertion default.
    // Still require rendered data; do not substitute fixtures on timeout.
    await expect(page.locator(view.ready).first()).toBeVisible({
      timeout: 20_000,
    });
    if (view.name === "ask") {
      await page
        .getByLabel("Your football question")
        .fill("Josh Allen projection 2026");
      await page.getByRole("button", { name: "Ask the data" }).click();
      await expect(
        page.getByRole("heading", { name: "SUPPORTED", exact: true }),
      ).toBeVisible();
      await expect(page.locator(".ask-record")).toHaveCount(1);
    }
    if (view.name === "relationship-tree") {
      await expect(page.locator(".network-canvas")).toHaveAttribute(
        "data-compact",
        "true",
      );
      await expect(page.locator(".network-canvas")).toHaveCSS(
        "height",
        "360px",
      );
      const entity = page.locator(".accessible-entity-list article").first();
      await entity.getByRole("button", { name: "Select", exact: true }).click();
      await expect(entity).toHaveClass(/is-selected/);
      await expect(entity).toHaveCSS("border-color", "rgb(200, 107, 50)");
      await expect(page.locator(".selection-panel")).toContainText("Selected");
    }
    const methodology = page.getByRole("link", {
      name: "Methodology",
      exact: true,
    });
    await expect(page.getByRole("link", { name: /skip to/i })).toHaveCount(1);
    await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute(
      "content",
      "#111315",
    );
    if (view.name === "statistics" && testInfo.project.name === "mobile") {
      const tracks = await page
        .locator(".filter-panel")
        .evaluate((element) =>
          getComputedStyle(element).gridTemplateColumns.split(" "),
        );
      expect(tracks).toHaveLength(2);
    }
    await page.keyboard.press("Tab");
    await methodology.focus();
    await expect(methodology).toBeFocused();
    await expect(methodology).toHaveCSS("outline-style", "solid");
    await expect(page.locator("html")).toHaveCSS(
      "background-color",
      "rgb(17, 19, 21)",
    );
    const overflow = await page.evaluate(() =>
      Array.from(document.querySelectorAll("main *"))
        .filter(
          (e) =>
            e.getBoundingClientRect().right > innerWidth &&
            !e.closest(".table-frame"),
        )
        .map((e) => ({
          tag: e.tagName,
          class: e.className,
          right: e.getBoundingClientRect().right,
        }))
        .slice(0, 12),
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      JSON.stringify(overflow),
    ).toBe(true);
    await page.addScriptTag({ content: axe.source });
    const violations = await page.evaluate(async () => {
      const axe = (window as unknown as { axe: typeof import("axe-core") }).axe;
      return (
        await axe.run(document, {
          runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
        })
      ).violations;
    });
    expect(
      violations.map((v) => ({
        id: v.id,
        nodes: v.nodes.map((n) => ({
          target: n.target,
          summary: n.failureSummary,
        })),
      })),
    ).toEqual([]);
    await page.screenshot({
      path: testInfo.outputPath(`${view.name}-${testInfo.project.name}.png`),
      fullPage: true,
    });
  });
}
