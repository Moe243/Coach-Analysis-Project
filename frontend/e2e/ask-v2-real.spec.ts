import { expect, test } from "@playwright/test";
import { versions } from "../src/test/fixtures";

const cases = [
  {
    question: "Who was coaching Aaron Rodgers during his best seasons?",
    answerability: "SUPPORTED",
    reason: null,
  },
  {
    question: "Compare Aaron Rodgers and Brett Favre.",
    answerability: "SUPPORTED",
    reason: null,
  },
  {
    question: "How did Josh Allen perform in 2022?",
    answerability: "SUPPORTED",
    reason: null,
  },
  {
    question: "Is Lamar Jackson mobile?",
    answerability: "SUPPORTED",
    reason: null,
  },
  {
    question:
      "Who has stronger QB-development evidence, Andy Reid or Mike Tomlin?",
    answerability: "PARTIALLY_SUPPORTED",
    reason: "DEVELOPMENT_CONCLUSION_NOT_PERMITTED",
  },
  {
    question: "How would Kyler Murray fit Minnesota?",
    answerability: "PARTIALLY_SUPPORTED",
    reason: "C17_SCENARIO_NOT_SUPPORTED",
  },
  {
    question: "What if Chicago drafted Patrick Mahomes?",
    answerability: "PARTIALLY_SUPPORTED",
    reason: "C18_COUNTERFACTUAL_NOT_IMPLEMENTED",
  },
  {
    question: "What does the model project for Josh Allen in 2026?",
    answerability: "SUPPORTED",
    reason: null,
  },
];

test.beforeEach(async ({ page }) => {
  await page.route("**/api/versions", (route) =>
    route.fulfill({ json: versions }),
  );
});

test("real coaching context opens the career tree and preserves conversational comparison", async ({
  page,
}) => {
  await page.goto("/ask");
  const question = page.getByLabel("Ask a football question");
  const send = async (text: string) => {
    await question.fill(text);
    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/ask/v2") &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    return response.json();
  };
  const rodgers = await send(
    "Who was coaching Aaron Rodgers during his best seasons?",
  );
  expect(rodgers.entities.map((entity: { id: string }) => entity.id)).toContain(
    "coach-mike-mccarthy",
  );
  expect(
    rodgers.entities.map((entity: { id: string }) => entity.id),
  ).not.toContain("team_was");
  await expect(
    page.locator(".ask-v2-explore-grid").locator("a, button"),
  ).toHaveCount(4);
  await page
    .getByRole("link", { name: /View Aaron Rodgers' career tree/ })
    .click();
  await expect(page).toHaveURL(/mode=qb_journey.*player_id=00-0023459/);
  await expect(
    page.getByRole("combobox", { name: "Quarterback", exact: true }),
  ).toHaveValue("00-0023459");
  await page.reload();
  await expect(
    page.getByRole("combobox", { name: "Quarterback", exact: true }),
  ).toHaveValue("00-0023459");
  await page.goto("/ask");
  await send(
    "Compare Andy Reid and Mike Tomlin's evidence around quarterback development.",
  );
  await send("Why?");
  const replacement = await send("What about McVay?");
  expect(
    replacement.entities.map((entity: { id: string }) => entity.id),
  ).toEqual(["coach-andy-reid", "coach-sean-mcvay"]);
  expect(replacement.answerability).toBe("PARTIALLY_SUPPORTED");
  expect(replacement.answer_mode).toBe("deterministic");
  await expect(
    page.getByRole("link", { name: /View Sean McVay's coach tree/ }),
  ).toBeVisible();
});

test("migrated /ask uses the real frozen deterministic Ask v2 backend", async ({
  page,
}) => {
  for (const item of cases) {
    await page.goto("/ask");
    await page.getByLabel("Ask a football question").fill(item.question);
    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/ask/v2") &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    const body = (await response.json()) as {
      answerability: string;
      answer_mode: string;
      reason_code: string | null;
    };
    expect(body.answer_mode).toBe("deterministic");
    expect(body.answerability).toBe(item.answerability);
    expect(body.reason_code).toBe(item.reason);
    await expect(
      page.getByRole("region", { name: `Answer to ${item.question}` }),
    ).toBeVisible();
  }
});

test("real Ask links restore statistics, team history, and both historical QBs", async ({
  page,
}) => {
  const ask = async (question: string) => {
    await page.goto("/ask");
    await page.getByLabel("Ask a football question").fill(question);
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Keep exploring" }),
    ).toBeVisible();
  };
  await ask("How did Josh Allen perform in 2022?");
  await page.getByRole("link", { name: /2022 statistics/ }).click();
  await page.reload();
  await expect(page.getByLabel("Player", { exact: true })).toHaveValue(
    "Josh Allen",
  );
  await expect(
    page.getByRole("combobox", { name: "Season", exact: true }),
  ).toHaveValue("2022");

  await ask("How would Kyler Murray fit Minnesota?");
  await page
    .getByRole("link", { name: /View Minnesota Vikings history/ })
    .click();
  await page.reload();
  await expect(
    page.getByRole("combobox", { name: "Team", exact: true }),
  ).toHaveValue("team_min");
  await expect(
    page.getByRole("combobox", { name: "View", exact: true }),
  ).toHaveValue("team_history");

  await ask("Compare Aaron Rodgers and Brett Favre.");
  await page
    .getByRole("link", { name: /Explore Aaron Rodgers \+ Brett Favre/ })
    .click();
  await page.reload();
  await expect(page).toHaveURL(/end_season=2010/);
  await expect(page).toHaveURL(/highlights=qb%3A00-0023459%2Cqb%3A00-0005106/);
  await expect(
    page.getByRole("combobox", { name: "View", exact: true }),
  ).toHaveValue("full_network");
  for (const name of ["Aaron Rodgers", "Brett Favre"]) {
    await expect(
      page.locator(".accessible-entity-list article").filter({ hasText: name }),
    ).toBeVisible();
  }
});
