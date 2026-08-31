import { expect, test } from "@playwright/test";

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
  await page.goto("/statistics");
  await page.getByPlaceholder("Search coaching context").fill("Todd Bowles");
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

test("filters the network to edges whose two assignments are verified", async ({
  page,
}) => {
  await page.goto("/network?season=2020&team=team_hou");
  await page.getByLabel("Both assignments").selectOption("verified");
  await expect(page).toHaveURL(/verification=verified/);
  await expect(
    page.getByRole("heading", { name: "Visible connections" }),
  ).toBeVisible();
  await expect(page.getByText("provisional", { exact: true })).toHaveCount(0);
  await expect(
    page.getByText("verified", { exact: true }).first(),
  ).toBeVisible();
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

  const networkLink = page.getByRole("link", { name: "Coaching Network" });
  await networkLink.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/network/);
  await expect(
    page.getByRole("heading", { name: "Coaching network" }),
  ).toBeVisible();
});
