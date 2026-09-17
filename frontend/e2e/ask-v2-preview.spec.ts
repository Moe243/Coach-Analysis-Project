import { expect, test, type Page } from "@playwright/test";
import axe from "axe-core";
import type { AskV2Response } from "../src/api/askV2";
import {
  askV2Response,
  coachComparisonResponse,
  counterfactualResponse,
  partialAlignmentResponse,
} from "../src/test/askV2Fixtures";
import { versions } from "../src/test/fixtures";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/versions", (route) =>
    route.fulfill({ json: versions }),
  );
});

const clarificationResponse = askV2Response({
  answerability: "CLARIFICATION_REQUIRED",
  answer: "I need a more specific canonical player before looking up data.",
  entities: [],
  clarification_candidates: [
    { kind: "qb", id: "00-0032434", display_name: "Brandon Allen" },
    { kind: "qb", id: "00-0034857", display_name: "Josh Allen" },
  ],
  evidence: [],
  propositions: [],
  uncertainty: [],
  limitations: [],
  follow_ups: [],
});

async function mockAskV2(
  page: Page,
  responseFor: (question: string) => AskV2Response,
) {
  await page.route("**/api/ask/v2", async (route) => {
    const request = route.request().postDataJSON() as { question: string };
    await route.fulfill({ json: responseFor(request.question) });
  });
}

async function submit(page: Page, question: string) {
  await page.getByLabel("Ask a football question").fill(question);
  await page.getByRole("button", { name: "Ask", exact: true }).click();
}

async function expectNoAxeViolations(page: Page) {
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const loaded = await page.evaluate(() => "axe" in window);
  if (!loaded) await page.addScriptTag({ content: axe.source });
  const violations = await page.evaluate(async () => {
    const browserAxe = (window as unknown as { axe: typeof import("axe-core") })
      .axe;
    return (await browserAxe.run(document)).violations.map((violation) => ({
      id: violation.id,
      targets: violation.nodes.map((node) => node.target),
    }));
  });
  expect(violations).toEqual([]);
}

test("primary, preview-alias, and legacy routes preserve browser navigation", async ({
  page,
}) => {
  await page.goto("/ask/preview");
  await expect(page).toHaveURL(/\/ask$/);
  await expect(
    page.getByRole("heading", { name: "Ask Anything" }),
  ).toBeVisible();
  await expect(page.getByText(/Conversation preview/i)).toHaveCount(0);

  await page.goto("/ask/legacy");
  await expect(
    page.getByRole("heading", { name: "Query the analytics system" }),
  ).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/ask$/);
  await expect(page.getByText("Evidence-led conversation")).toBeVisible();
  const composerBounds = await page
    .getByLabel("Ask a football question")
    .boundingBox();
  expect(composerBounds).not.toBeNull();
  expect(composerBounds!.y + composerBounds!.height).toBeLessThan(
    page.viewportSize()!.height,
  );
  await page.goForward();
  await expect(page).toHaveURL(/\/ask\/legacy$/);
});

test("Josh Allen answer leads with key numbers and supports a contextual follow-up", async ({
  page,
}) => {
  await mockAskV2(page, (question) =>
    question.includes("2023")
      ? askV2Response({
          answer: "Josh Allen recorded 0.202 EPA/dropback for Buffalo in 2023.",
          follow_ups: [],
        })
      : askV2Response(),
  );
  await page.goto("/ask");
  await expectNoAxeViolations(page);
  await submit(page, "How did Josh Allen perform in 2022?");
  await expect(
    page.getByRole("region", {
      name: "Answer to How did Josh Allen perform in 2022?",
    }),
  ).toContainText("0.237 EPA/dropback");
  await expect(
    page.getByRole("heading", { name: "Key numbers" }),
  ).toBeVisible();
  await expect(
    page.locator(".ask-v2-explore-grid").first().locator(":scope > *"),
  ).toHaveCount(4);
  await expect(
    page.getByRole("link", { name: /View Josh Allen's career tree/ }),
  ).toHaveAttribute(
    "href",
    "/network?mode=qb_journey&player_id=00-0034857&start_season=2010&end_season=2025&selected=qb%3A00-0034857",
  );
  await expectNoAxeViolations(page);
  await page.getByRole("button", { name: "View 2023" }).click();
  await expect(
    page.getByRole("region", {
      name: "Answer to How did Josh Allen perform in 2023?",
    }),
  ).toContainText("0.202 EPA/dropback");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("Reid versus Tomlin remains neutral and carries context into Why", async ({
  page,
}, testInfo) => {
  const requests: Array<{ question: string; context: unknown }> = [];
  await page.route("**/api/ask/v2", async (route) => {
    const request = route.request().postDataJSON() as {
      question: string;
      context: unknown;
    };
    requests.push(request);
    await route.fulfill({ json: coachComparisonResponse() });
  });
  await page.goto("/ask");
  await submit(
    page,
    "Who has stronger QB-development evidence, Andy Reid or Mike Tomlin?",
  );
  await expect(page.getByText(/Andy Reid has clearer/)).toBeVisible();
  await expect(
    page.getByText(/not proof of better QB development/),
  ).toBeVisible();
  await expect(
    page.locator(".ask-v2-explore-grid").first().locator(":scope > *"),
  ).toHaveCount(4);
  await expectNoAxeViolations(page);
  await submit(page, "Why?");
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[1].context).toMatchObject({
    turns: [
      {
        role: "user",
        content:
          "Who has stronger QB-development evidence, Andy Reid or Mike Tomlin?",
      },
    ],
  });
  if (testInfo.project.name === "mobile") {
    const columns = await page
      .locator(".ask-v2-explore-grid")
      .first()
      .evaluate((element) =>
        getComputedStyle(element).gridTemplateColumns.split(" "),
      );
    expect(columns).toHaveLength(1);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  }
});

test("partial alignment and counterfactual questions remain useful without fake scores", async ({
  page,
}) => {
  await mockAskV2(page, (question) =>
    question.includes("Chicago")
      ? counterfactualResponse()
      : partialAlignmentResponse(),
  );
  await page.goto("/ask");
  await submit(page, "How would Kyler Murray fit Minnesota?");
  await expect(
    page.getByText(/measured tendencies can be compared/),
  ).toBeVisible();
  await expect(
    page.getByRole("link", {
      name: /Explore Kyler Murray \+ Minnesota Vikings/,
    }),
  ).toHaveAttribute(
    "href",
    "/network?mode=full_network&anchor=all&start_season=2021&end_season=2025&selected=qb%3A00-0035228&highlights=qb%3A00-0035228%2Cteam-season%3Ateam_min%3A2021%2Cteam-season%3Ateam_min%3A2022%2Cteam-season%3Ateam_min%3A2023%2Cteam-season%3Ateam_min%3A2024%2Cteam-season%3Ateam_min%3A2025",
  );
  await expect(page.getByText(/Fit Score/i)).toHaveCount(0);
  await expectNoAxeViolations(page);
  await submit(page, "What if Chicago drafted Patrick Mahomes?");
  await expect(
    page.getByText(/cannot reliably estimate an alternate career/),
  ).toBeVisible();
});

test("ambiguous player input resolves through canonical context without exposing IDs", async ({
  page,
}) => {
  await mockAskV2(page, (question) =>
    question === "Allen performance 2022"
      ? clarificationResponse
      : askV2Response(),
  );
  await page.goto("/ask");
  await submit(page, "Allen performance 2022");
  await expect(page.getByText("Which one did you mean?")).toBeVisible();
  await expectNoAxeViolations(page);
  await page.getByRole("button", { name: "Josh Allen" }).click();
  await expect(
    page.getByRole("region", { name: "Answer to Josh Allen" }),
  ).toContainText("0.237 EPA/dropback");
  await expect(page.getByText("00-0034857")).toHaveCount(0);
});

test("failed evidence request is an accessible retry state", async ({
  page,
}) => {
  await page.route("**/api/ask/v2", (route) =>
    route.fulfill({
      status: 500,
      json: { detail: "Temporary server failure" },
    }),
  );
  await page.goto("/ask");
  await submit(page, "How did Josh Allen perform in 2022?");
  await expect(page.getByRole("alert")).toContainText(
    "Published data could not be loaded",
  );
  await expect(
    page.getByRole("button", { name: "Retry this question" }),
  ).toBeVisible();
  await expectNoAxeViolations(page);
});
