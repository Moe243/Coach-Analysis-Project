import { expect, test } from "@playwright/test";
import { versions } from "../src/test/fixtures";

const cases = [
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
