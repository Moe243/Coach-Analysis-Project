import axe from "axe-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { askQuestionV2 } from "../api/askV2";
import { ApiError } from "../api/client";
import { AskV2AssistantTurn } from "../components/askV2/AskV2AssistantTurn";
import type { AskV2ConversationTurn } from "../hooks/useAskV2Conversation";
import {
  askV2Response,
  coachComparisonResponse,
  counterfactualResponse,
  partialAlignmentResponse,
} from "../test/askV2Fixtures";
import { renderRoute } from "../test/render";
import { AskPreviewPage } from "./AskPreviewPage";

vi.mock("../api/askV2", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/askV2")>();
  return { ...actual, askQuestionV2: vi.fn() };
});

async function submit(question: string) {
  const user = userEvent.setup();
  const input = screen.getByLabelText("Ask a football question");
  await user.type(input, question);
  await user.click(screen.getByRole("button", { name: /^Ask$/ }));
  return user;
}

function clarificationResponse() {
  return askV2Response({
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
}

describe("Ask Anything v2", () => {
  beforeEach(() => vi.mocked(askQuestionV2).mockReset());

  it("shows an answer-first experience with supported examples", () => {
    renderRoute(<AskPreviewPage />, "/ask");
    expect(screen.getByRole("heading", { name: "Ask Anything" })).toBeVisible();
    expect(screen.getByText("Evidence-led conversation")).toBeVisible();
    expect(
      screen.getByRole("button", { name: /How did Josh Allen perform/ }),
    ).toBeVisible();
    expect(screen.queryByText("Rookie forecast")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Ask$/ })).toBeDisabled();
    expect(screen.queryByText(/preview/i)).not.toBeInTheDocument();
  });

  it("submits an example and renders the direct answer before evidence", async () => {
    vi.mocked(askQuestionV2).mockResolvedValue(askV2Response());
    const user = userEvent.setup();
    renderRoute(<AskPreviewPage />, "/ask/preview");
    await user.click(
      screen.getByRole("button", { name: /How did Josh Allen perform/ }),
    );
    const answerRegion = await screen.findByRole("region", {
      name: "Answer to How did Josh Allen perform in 2022?",
    });
    const answer = within(answerRegion).getByText(
      /recorded 0.237 EPA\/dropback/,
    );
    expect(answer).toBeVisible();
    const evidence = screen.getByRole("heading", {
      name: "Strongest evidence",
    });
    expect(
      answer.compareDocumentPosition(evidence) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(askQuestionV2).toHaveBeenCalledWith(
      expect.objectContaining({
        question: "How did Josh Allen perform in 2022?",
      }),
      expect.any(AbortSignal),
    );
  });

  it("renders partial support as useful alignment before the unsupported portion", async () => {
    vi.mocked(askQuestionV2).mockResolvedValue(partialAlignmentResponse());
    renderRoute(<AskPreviewPage />, "/ask/preview");
    await submit("How would Kyler Murray fit Minnesota?");
    expect(await screen.findByText("Partially supported")).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Comparable dimensions" }),
    ).toBeVisible();
    expect(screen.getByText(/Descriptive alignment only/)).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "What the model can't estimate" }),
    ).toBeVisible();
    expect(screen.queryByText(/Fit Score/i)).not.toBeInTheDocument();
  });

  it("renders a complete unsupported answer as a scientific limit, not a broken page", async () => {
    vi.mocked(askQuestionV2).mockResolvedValue(
      askV2Response({
        answerability: "NOT_SUPPORTED",
        answer: "The project cannot produce a rookie forecast.",
        entities: [],
        evidence: [],
        propositions: [],
        uncertainty: [],
        unsupported_portions: [
          {
            description: "College-to-NFL rookie performance projection",
            reason_code: "C20_ROOKIE_MODEL_NOT_ESTIMABLE",
            explanation: "The available cohort cannot estimate this outcome.",
          },
        ],
        follow_ups: [],
      }),
    );
    renderRoute(<AskPreviewPage />, "/ask/preview");
    await submit("Project a rookie quarterback");
    expect(await screen.findByText("Not supported")).toBeVisible();
    expect(
      screen.getByText("The project cannot produce a rookie forecast."),
    ).toBeVisible();
    expect(screen.getByText(/available cohort cannot estimate/)).toBeVisible();
  });

  it("renders data-unavailable and missing numerical values without zeros", async () => {
    const response = askV2Response({
      answerability: "DATA_UNAVAILABLE",
      answer: "The requested metric is unavailable for that season.",
      evidence: [],
      propositions: [
        {
          ...askV2Response().propositions[0],
          value: null,
          qualifier: "Source not available",
        },
      ],
      uncertainty: [],
    });
    vi.mocked(askQuestionV2).mockResolvedValue(response);
    renderRoute(<AskPreviewPage />, "/ask/preview");
    const user = await submit("Show Josh Allen CPOE in 2010");
    expect(await screen.findByText("Data unavailable")).toBeVisible();
    await user.click(screen.getByText("Evidence & methodology"));
    expect(screen.getByText("Unavailable")).toBeVisible();
    expect(screen.queryByText("0.000")).not.toBeInTheDocument();
  });

  it("resolves ambiguity with a canonical context choice and no visible opaque ID", async () => {
    vi.mocked(askQuestionV2)
      .mockResolvedValueOnce(clarificationResponse())
      .mockResolvedValueOnce(askV2Response());
    renderRoute(<AskPreviewPage />, "/ask/preview");
    const user = await submit("Allen performance 2022");
    await user.click(await screen.findByRole("button", { name: "Josh Allen" }));
    const answerRegion = await screen.findByRole("region", {
      name: "Answer to Josh Allen",
    });
    expect(
      within(answerRegion).getByText(/recorded 0.237 EPA\/dropback/),
    ).toBeVisible();
    expect(screen.getAllByText("Josh Allen").length).toBeGreaterThan(0);
    expect(screen.queryByText("00-0034857")).not.toBeInTheDocument();
    const request = vi.mocked(askQuestionV2).mock.calls[1][0];
    expect(request.question).toBe("Josh Allen performance 2022");
    expect(request.context.entities).toContainEqual({
      kind: "qb",
      id: "00-0034857",
    });
  });

  it("builds bounded structured context for a natural follow-up", async () => {
    vi.mocked(askQuestionV2)
      .mockResolvedValueOnce(coachComparisonResponse())
      .mockResolvedValueOnce(coachComparisonResponse());
    renderRoute(<AskPreviewPage />, "/ask/preview");
    const user = await submit(
      "Who has stronger QB-development evidence, Andy Reid or Mike Tomlin?",
    );
    await screen.findByText("Comparison frame");
    await user.type(screen.getByLabelText("Ask a football question"), "Why?");
    await user.click(screen.getByRole("button", { name: /^Ask$/ }));
    await waitFor(() => expect(askQuestionV2).toHaveBeenCalledTimes(2));
    const followUp = vi.mocked(askQuestionV2).mock.calls[1][0];
    expect(followUp.context.turns).toEqual([
      {
        role: "user",
        content:
          "Who has stronger QB-development evidence, Andy Reid or Mike Tomlin?",
      },
    ]);
    expect(followUp.context.entities).toEqual([
      { kind: "coach", id: "coach-andy-reid" },
      { kind: "coach", id: "coach-mike-tomlin" },
    ]);
  });

  it("submits only backend-provided follow-up suggestions", async () => {
    vi.mocked(askQuestionV2)
      .mockResolvedValueOnce(coachComparisonResponse())
      .mockResolvedValueOnce(coachComparisonResponse());
    renderRoute(<AskPreviewPage />, "/ask/preview");
    const user = await submit(
      "Compare Andy Reid and Mike Tomlin with quarterbacks",
    );
    await user.click(
      await screen.findByRole("button", { name: /Explain why/ }),
    );
    await waitFor(() => expect(askQuestionV2).toHaveBeenCalledTimes(2));
    expect(vi.mocked(askQuestionV2).mock.calls[1][0].question).toBe("Why?");
  });

  it("shows uncertainty and safe provenance in expandable sections", async () => {
    vi.mocked(askQuestionV2).mockResolvedValue(askV2Response());
    renderRoute(<AskPreviewPage />, "/ask/preview");
    const user = await submit("How did Josh Allen perform in 2022?");
    expect(
      await screen.findByText(/High reliability · 651 dropbacks/),
    ).toBeVisible();
    await user.click(screen.getByText("Evidence & methodology"));
    expect(screen.getByText("Historical Fact")).toBeVisible();
    expect(screen.getByText("0.237")).toBeVisible();
    expect(screen.getByText(/Interval: -0.102 to 0.347/)).toBeVisible();
    await user.click(screen.getByText("Versions & provenance"));
    expect(screen.getByText("c19-test")).toBeVisible();
    expect(
      screen.queryByText(/OPENAI_API_KEY|DATABASE_URL|\/Users\//),
    ).not.toBeInTheDocument();
  });

  it("labels deterministic and grounded modes without changing analytical authority", async () => {
    vi.mocked(askQuestionV2)
      .mockResolvedValueOnce(askV2Response())
      .mockResolvedValueOnce(
        askV2Response({
          answer_mode: "grounded_ai",
          versions: {
            ...askV2Response().versions,
            answer_mode: "grounded_ai",
            planner_model_version: "gpt-test-planner",
            synthesizer_model_version: "gpt-test-synthesizer",
          },
        }),
      );
    renderRoute(<AskPreviewPage />, "/ask/preview");
    const user = await submit("How did Josh Allen perform in 2022?");
    expect(
      await screen.findByText("Deterministic", { selector: ".ask-v2-mode" }),
    ).toBeVisible();
    await user.type(
      screen.getByLabelText("Ask a football question"),
      "What about 2023?",
    );
    await user.click(screen.getByRole("button", { name: /^Ask$/ }));
    expect(
      await screen.findByText("Grounded AI", { selector: ".ask-v2-mode" }),
    ).toBeVisible();
    expect(screen.getAllByText(/Analytics first/)).toHaveLength(2);
  });

  it("renders comparisons neutrally with canonical profile links", async () => {
    vi.mocked(askQuestionV2).mockResolvedValue(coachComparisonResponse());
    renderRoute(<AskPreviewPage />, "/ask/preview");
    await submit("Compare Andy Reid and Mike Tomlin with quarterbacks");
    expect(await screen.findByText("Comparison frame")).toBeVisible();
    expect(screen.getByText(/No overall winner is implied/)).toBeVisible();
    expect(
      screen.getByRole("link", { name: "View Andy Reid" }),
    ).toHaveAttribute("href", "/coaches/coach-andy-reid");
  });

  it("renders counterfactual support before the alternate-career limitation", async () => {
    vi.mocked(askQuestionV2).mockResolvedValue(counterfactualResponse());
    renderRoute(<AskPreviewPage />, "/ask/preview");
    await submit("What if Chicago drafted Patrick Mahomes?");
    expect(await screen.findByText("What we can compare")).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "What we cannot estimate" }),
    ).toBeVisible();
    expect(screen.queryByText(/would have thrown/i)).not.toBeInTheDocument();
  });

  it("keeps successful turns visible when a later request fails and retries the exact snapshot", async () => {
    vi.mocked(askQuestionV2)
      .mockResolvedValueOnce(askV2Response())
      .mockRejectedValueOnce(new ApiError("Temporary server failure", 500))
      .mockResolvedValueOnce(
        askV2Response({ answer: "The retried answer is available." }),
      );
    renderRoute(<AskPreviewPage />, "/ask/preview");
    const user = await submit("How did Josh Allen perform in 2022?");
    await screen.findByRole("region", {
      name: "Answer to How did Josh Allen perform in 2022?",
    });
    await user.type(
      screen.getByLabelText("Ask a football question"),
      "What about 2023?",
    );
    await user.click(screen.getByRole("button", { name: /^Ask$/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Temporary server failure",
    );
    const priorAnswer = screen.getByRole("region", {
      name: "Answer to How did Josh Allen perform in 2022?",
    });
    expect(
      within(priorAnswer).getByText(/recorded 0.237 EPA\/dropback/),
    ).toBeVisible();
    const failedSnapshot = vi.mocked(askQuestionV2).mock.calls[1][0];
    await user.click(
      screen.getByRole("button", { name: "Retry this question" }),
    );
    expect(
      await screen.findByText("The retried answer is available."),
    ).toBeVisible();
    expect(vi.mocked(askQuestionV2).mock.calls[2][0]).toEqual(failedSnapshot);
  });

  it("clears conversation state and restores first-use examples", async () => {
    vi.mocked(askQuestionV2).mockResolvedValue(askV2Response());
    renderRoute(<AskPreviewPage />, "/ask/preview");
    const user = await submit("How did Josh Allen perform in 2022?");
    await screen.findByRole("region", {
      name: "Answer to How did Josh Allen perform in 2022?",
    });
    await user.click(screen.getByRole("button", { name: "New conversation" }));
    expect(
      screen.queryByRole("region", {
        name: "Answer to How did Josh Allen perform in 2022?",
      }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Evidence-led conversation")).toBeVisible();
  });

  it("renders backend text literally instead of executing arbitrary HTML", async () => {
    vi.mocked(askQuestionV2).mockResolvedValue(
      askV2Response({
        answer: '<img src=x onerror="window.__unsafe=true"> Supported text.',
      }),
    );
    renderRoute(<AskPreviewPage />, "/ask/preview");
    await submit("How did Josh Allen perform in 2022?");
    expect(await screen.findByText(/<img src=x/)).toBeVisible();
    expect(document.querySelector("img")).toBeNull();
  });

  it("has no automated accessibility violations in the error and retry state", async () => {
    const turn: AskV2ConversationTurn = {
      id: 1,
      question: "How did Josh Allen perform in 2022?",
      request: {
        question: "How did Josh Allen perform in 2022?",
        context: { turns: [], entities: [] },
      },
      status: "error",
      error: "Temporary server failure",
      contextTrimmed: false,
      retryAttempt: 0,
    };
    renderRoute(
      <AskV2AssistantTurn
        turn={turn}
        latest
        onClarify={() => undefined}
        onFollowUp={() => undefined}
        onRetry={() => undefined}
      />,
      "/ask/preview",
    );
    expect(screen.getByRole("alert")).toBeVisible();
    const result = await axe.run(document.body, {
      rules: {
        region: { enabled: false },
        "color-contrast": { enabled: false },
      },
    });
    expect(result.violations).toEqual([]);
  });

  it.each([
    ["first use", undefined],
    ["supported", askV2Response()],
    ["comparison", coachComparisonResponse()],
    ["clarification", clarificationResponse()],
    ["partial support", partialAlignmentResponse()],
  ])(
    "has no automated accessibility violations in the %s state",
    async (_name, response) => {
      if (response) vi.mocked(askQuestionV2).mockResolvedValue(response);
      renderRoute(<AskPreviewPage />, "/ask/preview");
      if (response) {
        await submit("Show the approved evidence");
        await screen.findByText(
          response.answerability === "CLARIFICATION_REQUIRED"
            ? "Clarification needed"
            : response.answer,
        );
      }
      const result = await axe.run(document.body, {
        rules: {
          region: { enabled: false },
          "color-contrast": { enabled: false },
        },
      });
      expect(result.violations).toEqual([]);
    },
  );
});
