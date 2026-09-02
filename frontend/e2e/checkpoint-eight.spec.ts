import { expect, test, type Page } from "@playwright/test";
import { relationshipExplorer } from "../src/test/fixtures";

async function useDeterministicRelationshipFixture(page: Page) {
  await page.route("**/api/relationships/explorer?**", async (route) => {
    const url = new URL(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...relationshipExplorer,
        query: {
          ...relationshipExplorer.query,
          mode: url.searchParams.get("mode"),
          coach_id: url.searchParams.get("coach_id"),
          player_id: url.searchParams.get("player_id"),
          team_id: url.searchParams.get("team_id"),
          start_season: Number(url.searchParams.get("start_season")),
          end_season: Number(url.searchParams.get("end_season")),
          verification_status: url.searchParams.get("verification_status"),
          include_provisional:
            url.searchParams.get("include_provisional") === "true",
        },
      }),
    });
  });
}

test("searches for a quarterback and opens the published profile", async ({
  page,
}) => {
  await page.goto("/statistics");
  await page.getByPlaceholder("Search quarterbacks").fill("Baker");
  const quarterback = page
    .getByRole("link", { name: "Baker Mayfield" })
    .first();
  await expect(quarterback).toBeVisible();
  await quarterback.click();
  await expect(page).toHaveURL(/\/qbs\/00-0034855$/);
  await expect(
    page.getByRole("heading", { name: "Baker Mayfield" }),
  ).toBeVisible();
});

test("filters quarterback seasons by team and season with URL state", async ({
  page,
}) => {
  await page.goto("/statistics");
  await page.getByLabel("Team").selectOption("team_tb");
  await page.getByLabel("Season").selectOption("2025");
  await expect(page).toHaveURL(/team=team_tb/);
  await expect(page).toHaveURL(/season=2025/);
  const quarterback = page.getByRole("link", { name: "Baker Mayfield" });
  await expect(quarterback).toBeVisible();
  await expect(
    quarterback
      .locator("xpath=ancestor::tr")
      .getByText("2025", { exact: true }),
  ).toBeVisible();
});

test("shows PAE with its formula and out-of-sample explanation", async ({
  page,
}) => {
  await page.goto("/statistics?player=Baker&team=team_tb");
  await expect(page.getByLabel("PAE formula")).toContainText(
    "Actual EPA/dropback − Expected EPA/dropback",
  );
  await page.getByRole("link", { name: "Baker Mayfield" }).first().click();
  await expect(
    page.getByText("Out-of-sample expectations only."),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Actual vs expected EPA/dropback" }),
  ).toBeVisible();
});

test("searches for a coach and opens connected quarterback context", async ({
  page,
}) => {
  await page.goto("/statistics?expanded=true");
  await page.getByPlaceholder("Search coaching context").fill("Todd Bowles");
  await expect(page).toHaveURL(/coach=Todd(?:\+|%20)Bowles/);
  await expect(page.getByText("Loading published data")).toHaveCount(0, {
    timeout: 20_000,
  });
  await page.getByText("Performance, context, and staff").first().click();
  const coach = page.getByRole("link", { name: "Todd Bowles" }).first();
  await expect(coach).toBeVisible();
  await coach.click();
  await expect(
    page.getByRole("heading", { name: "Todd Bowles" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Team-season overlap" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Baker Mayfield" }).first(),
  ).toBeVisible();
});

test("explores a verified team history with interval-preserving relationship cards", async ({
  page,
}) => {
  await useDeterministicRelationshipFixture(page);
  await page.goto(
    "/network?mode=team_history&team_id=team_tb&start_season=2024&end_season=2025",
  );
  await page
    .getByRole("combobox", { name: "Evidence", exact: true })
    .selectOption("verified");
  await expect(page).toHaveURL(/verification=verified/);
  await expect(
    page.getByRole("heading", { name: "Relationship explorer list" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await expect(
    page.getByText("verified", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText(/Weeks \d+–\d+/).first()).toBeVisible();
});

test("restores Coach Journey, QB Journey, and Full Network from URL state", async ({
  page,
}) => {
  await useDeterministicRelationshipFixture(page);
  await page.goto(
    "/network?mode=coach_journey&coach_id=coach-todd-bowles&start_season=2023&end_season=2025",
  );
  await expect(page.getByLabel("View")).toHaveValue("coach_journey");
  await expect(
    page.getByRole("heading", { name: "Relationship explorer list" }),
  ).toBeVisible();
  await page.getByLabel("View").selectOption("qb_journey");
  await page
    .getByRole("combobox", { name: "Quarterback", exact: true })
    .selectOption("00-0034855");
  await expect(page).toHaveURL(/mode=qb_journey/);
  await expect(page).toHaveURL(/player_id=00-0034855/);
  await expect(
    page.getByRole("heading", { name: "Relationship explorer list" }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "View", exact: true })
    .selectOption("full_network");
  await page
    .getByRole("combobox", { name: "Start from", exact: true })
    .selectOption("team");
  await page
    .getByRole("combobox", { name: "Team", exact: true })
    .selectOption("team_tb");
  await expect(page).toHaveURL(/mode=full_network/);
  await expect(
    page.getByRole("heading", { name: "Relationship explorer list" }),
  ).toBeVisible();
});

test("supports accessible Select, Focus, Reset, and Back actions", async ({
  page,
}) => {
  await useDeterministicRelationshipFixture(page);
  await page.goto(
    "/network?mode=team_history&team_id=team_tb&start_season=2024&end_season=2025",
  );
  const entity = page.locator(".accessible-entity-list article").first();
  await entity.getByRole("button", { name: "Select" }).click();
  await expect(page.locator(".selection-panel")).toContainText("Selected");
  await page.getByRole("button", { name: "Focus selected" }).click();
  await expect(page).toHaveURL(/focus=/);
  await page.getByRole("button", { name: "Back to prior focus" }).click();
  await expect(page).toHaveURL(/mode=team_history/);
  await page.getByRole("button", { name: "Reset explorer" }).click();
  await expect(page.locator(".selection-panel")).toContainText(
    "Select an entity",
  );
});

test("keeps QB facts visible when coach role filters remove assignment cards", async ({
  page,
}) => {
  await useDeterministicRelationshipFixture(page);
  await page.goto(
    "/network?mode=team_history&team_id=team_tb&start_season=2024&end_season=2025&roles=quarterbacks_coach",
  );
  await expect(page.getByText(/QB-team-season/).first()).toBeVisible();
  await expect(page.getByText(/^Assignment /)).toHaveCount(0);
});

test("shows a complete 413 boundary state and asks for a narrower scope", async ({
  page,
}) => {
  await page.route("**/api/relationships/explorer?**", async (route) => {
    await route.fulfill({
      status: 413,
      contentType: "application/json",
      body: JSON.stringify({
        detail: "Relationship scope is too large; narrow it",
      }),
    });
  });
  await page.goto(
    "/network?mode=team_history&team_id=team_tb&start_season=2024&end_season=2025",
  );
  await expect(
    page.getByText("Relationship scope is too large", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/No partial graph was returned/)).toBeVisible();
  await expect(page.locator(".network-canvas")).toHaveCount(0);
});

test("presents coach impact as exploratory and suppressed", async ({
  page,
}) => {
  await page.goto("/coaches/coach-todd-bowles");
  await expect(
    page.getByText("Coach effects are exploratory and suppressed."),
  ).toBeVisible();
  await expect(page.getByText("suppressed exploratory")).toBeVisible();
  await expect(
    page.getByText(/No row on this page is a publishable ranking/),
  ).toBeVisible();
});

test("supports keyboard navigation and responsive result presentation", async ({
  page,
}, testInfo) => {
  await page.goto("/statistics?player=Baker&team=team_tb");
  const skipLink = page.getByRole("link", { name: "Skip to main content" });
  await skipLink.focus();
  await expect(skipLink).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();

  const row = page
    .getByRole("link", { name: "Baker Mayfield" })
    .first()
    .locator("xpath=ancestor::tr");
  await expect(row).toBeVisible();
  await expect(row).toHaveCSS(
    "display",
    testInfo.project.name === "mobile" ? "block" : "table-row",
  );

  const networkLink = page.getByRole("link", { name: "Relationship Explorer" });
  await networkLink.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/network/);
  await expect(
    page.getByRole("heading", { name: "Relationship Explorer" }),
  ).toBeVisible();
});
