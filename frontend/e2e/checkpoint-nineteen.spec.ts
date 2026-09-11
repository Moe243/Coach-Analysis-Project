import { expect, test } from "@playwright/test";

// Real local /ask API with the approved C19 snapshot; no intercepted analytical response.
test("Ask returns versioned history, source evidence and no scenario numbers", async ({
  page,
}) => {
  await page.goto("/ask");
  const input = page.getByLabel("Your football question");
  await input.fill("How did Josh Allen perform in 2022?");
  const response = page.waitForResponse(
    (r) => r.url().endsWith("/api/ask") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Ask the data" }).click();
  const resolved = await response;
  expect(resolved.status()).toBe(200);
  const body = await resolved.json();
  expect(body.metrics[0].performance_above_expectation).toBeCloseTo(
    0.1146126191264755,
    12,
  );
  await expect(
    page.getByRole("heading", { name: "SUPPORTED", exact: true }),
  ).toBeVisible();
  await page.getByText("Versions and analytical sources").click();
  await expect(page.getByText(/Snapshot: c19-/)).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await input.fill("What would Kyler Murray do in Minnesota?");
  await page.getByRole("button", { name: "Ask the data" }).click();
  await expect(
    page.getByRole("heading", { name: "NOT SUPPORTED", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".ask-record")).toHaveCount(0);
  await expect(page.getByText(/no validated Player × Scheme/i)).toBeVisible();
});

test("Ask resolves ambiguity and reads the frozen team-independent projection", async ({
  page,
}) => {
  await page.goto("/ask");
  await page
    .getByLabel("Your football question")
    .fill("Allen performance 2022");
  await page.getByRole("button", { name: "Ask the data" }).click();
  await expect(
    page.getByRole("heading", { name: "CLARIFICATION REQUIRED" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Josh Allen \(00-/ }).click();
  await expect(
    page.getByRole("heading", { name: "SUPPORTED", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Your football question")
    .fill("Josh Allen projection 2026");
  await page.getByRole("button", { name: "Ask the data" }).click();
  await expect(
    page.getByText(/TEAM-INDEPENDENT RESEARCH PROJECTION\. Frozen/),
  ).toBeVisible();
  await expect(page.locator(".ask-record")).toHaveCount(1);
  await expect(
    page.getByRole("link", { name: "Josh Allen profile" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
