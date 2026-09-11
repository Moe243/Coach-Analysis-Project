import axe from "axe-core";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { askQuestion, type AskAnswer } from "../api/ask";
import { ApiError } from "../api/client";
import { renderRoute } from "../test/render";
import { AskPage } from "./AskPage";

vi.mock("../api/ask", () => ({ askQuestion: vi.fn() }));

// Synthetic rendering fixture; never supplied as application fallback data.
function answer(overrides: Partial<AskAnswer> = {}): AskAnswer {
  return {
    contract_version: "ask-v1",
    intent: "QB_HISTORY",
    entities: [],
    season: 2022,
    requested_metric: null,
    status: "SUPPORTED",
    data_version: "test-snapshot",
    model_version: "test-model",
    metrics: [
      {
        quarterback_name: "Test QB",
        season: 2022,
        epa_per_dropback: 0.125,
        performance_above_expectation: null,
        reliability: "LOW",
      },
    ],
    uncertainty: [{ interval_low: -0.2, interval_high: 0.3 }],
    limitations: ["Observational only"],
    source_artifacts: [
      {
        artifact: "test-fixture",
        data_version: "test-snapshot",
        sha256: "test-checksum",
      },
    ],
    candidates: [],
    reason: null,
    available_alternative: null,
    explanation: "Evidence from approved historical observations.",
    ...overrides,
  };
}

async function submit(question = "Josh Allen performance 2022") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Your football question"), question);
  await user.click(screen.getByRole("button", { name: "Ask the data" }));
  return user;
}

describe("AskPage", () => {
  beforeEach(() => vi.mocked(askQuestion).mockReset());
  it("renders evidence, nulls, reliability, uncertainty and provenance", async () => {
    vi.mocked(askQuestion).mockResolvedValue(answer());
    renderRoute(<AskPage />, "/ask");
    const user = await submit();
    expect(
      await screen.findByRole("heading", { name: "SUPPORTED" }),
    ).toBeInTheDocument();
    for (const text of ["Unavailable", "0.1250", "LOW"])
      expect(screen.getAllByText(text).length).toBeGreaterThan(0);
    await user.click(screen.getByText("Versions and analytical sources"));
    expect(screen.getByText(/Snapshot: test-snapshot/)).toBeVisible();
    await user.click(screen.getByText("Uncertainty and Player State context"));
    expect(screen.getByText(/interval_low/)).toBeVisible();
  });
  it("shows refusal and alternatives without stale numerical output", async () => {
    vi.mocked(askQuestion)
      .mockResolvedValueOnce(answer())
      .mockResolvedValueOnce(
        answer({
          intent: "PLAYER_TEAM_SCENARIO",
          status: "NOT_SUPPORTED",
          metrics: [],
          uncertainty: [],
          explanation:
            "No validated scenario model. View the team-independent projection separately.",
        }),
      );
    renderRoute(<AskPage />, "/ask");
    const user = await submit();
    await screen.findByRole("heading", { name: "SUPPORTED" });
    await user.clear(screen.getByLabelText("Your football question"));
    await user.type(
      screen.getByLabelText("Your football question"),
      "What would Josh Allen do in Miami?",
    );
    await user.click(screen.getByRole("button", { name: "Ask the data" }));
    expect(
      await screen.findByRole("heading", { name: "NOT SUPPORTED" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("0.1250")).not.toBeInTheDocument();
    expect(screen.getByText(/No validated scenario model/)).toBeInTheDocument();
  });
  it("requires canonical candidate confirmation before lookup", async () => {
    vi.mocked(askQuestion)
      .mockResolvedValueOnce(
        answer({
          status: "CLARIFICATION_REQUIRED",
          metrics: [],
          candidates: [{ kind: "qb", id: "00-test", name: "Test QB" }],
        }),
      )
      .mockResolvedValueOnce(answer());
    renderRoute(<AskPage />, "/ask");
    const user = await submit("Allen performance 2022");
    await user.click(
      await screen.findByRole("button", { name: "Test QB (00-test)" }),
    );
    expect(vi.mocked(askQuestion).mock.calls.at(-1)?.[0]).toBe(
      "Allen performance 2022 [00-test]",
    );
  });
  it("retries explicitly without fallback data", async () => {
    vi.mocked(askQuestion)
      .mockRejectedValueOnce(new ApiError("Snapshot unavailable", 500))
      .mockResolvedValueOnce(answer());
    renderRoute(<AskPage />, "/ask");
    const user = await submit();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Snapshot unavailable",
    );
    await user.click(screen.getByRole("button", { name: "Retry question" }));
    expect(
      await screen.findByRole("heading", { name: "SUPPORTED" }),
    ).toBeInTheDocument();
    expect(askQuestion).toHaveBeenCalledTimes(2);
  });
  it("has no automated accessibility violations", async () => {
    vi.mocked(askQuestion).mockResolvedValue(answer());
    renderRoute(<AskPage />, "/ask");
    await submit();
    await screen.findByRole("heading", { name: "SUPPORTED" });
    const result = await axe.run(document.body, {
      rules: {
        region: { enabled: false },
        "color-contrast": { enabled: false },
      },
    });
    expect(result.violations).toEqual([]);
  });
});
