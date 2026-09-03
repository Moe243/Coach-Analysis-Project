import axe from "axe-core";
import { screen } from "@testing-library/react";
import { installApiFixture } from "../test/fixtures";
import { renderRoute } from "../test/render";
import { MethodologyPage } from "./MethodologyPage";

describe("MethodologyPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("explains Coach Effect conceptually without exposing a scoring equation", async () => {
    installApiFixture();
    renderRoute(<MethodologyPage />, "/methodology");

    expect(
      screen.getByRole("heading", {
        name: "Does performance follow the coach?",
      }),
    ).toBeInTheDocument();
    for (const heading of [
      "Measure performance against expectation",
      "Evaluate play-calling decisions",
      "Account for the environment",
      "Look for what follows the coach",
      "How to read Coach Effect",
    ]) {
      expect(
        screen.getByRole("heading", { name: heading }),
      ).toBeInTheDocument();
    }
    for (const label of [
      "Positive Coach Effect",
      "Near Average",
      "Negative Coach Effect",
      "Confidence",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(
      screen.getByText(/evidence-based observational coaching signal/i),
    ).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/Do not rank coaches/i);
    expect(document.body).not.toHaveTextContent(
      /component weights|residualization|shrinkage/i,
    );
    expect(await screen.findByText("api-v1.4")).toBeInTheDocument();
  });

  it("has no automated accessibility violations", async () => {
    installApiFixture();
    renderRoute(<MethodologyPage />, "/methodology");
    await screen.findByRole("heading", { name: "How to read Coach Effect" });
    await screen.findByText("api-v1.4");
    const result = await axe.run(document.body, {
      rules: {
        region: { enabled: false },
        "color-contrast": { enabled: false },
      },
    });
    expect(result.violations).toEqual([]);
  });
});
