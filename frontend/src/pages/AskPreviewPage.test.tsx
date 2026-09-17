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
    answer: "I need a more specific player name before I look up evidence.",
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

  it("does not collapse multiple team stints into a misleading season key number", async () => {
    const response = askV2Response();
    vi.mocked(askQuestionV2).mockResolvedValue(
      askV2Response({
        answer:
          "Trent Edwards had separate Buffalo and Jacksonville records in 2010.",
        propositions: [
          {
            ...response.propositions[0],
            subject: "Trent Edwards",
            season: 2010,
            value: -0.1,
          },
          {
            ...response.propositions[0],
            proposition_id: "second-stint",
            subject: "Trent Edwards",
            season: 2010,
            value: -0.2,
          },
        ],
      }),
    );
    renderRoute(<AskPreviewPage />, "/ask");
    await submit("How did Trent Edwards perform in 2010?");
    await screen.findByText(/separate Buffalo and Jacksonville/);
    expect(
      screen.queryByRole("heading", { name: "Key numbers" }),
    ).not.toBeInTheDocument();
  });

  it("creates only one follow-up from a double-click even without a pending request", async () => {
    const followUp = vi.fn();
    renderRoute(
      <AskV2AssistantTurn
        turn={{
          id: 1,
          question: "How did Josh Allen perform in 2022?",
          request: {
            question: "How did Josh Allen perform in 2022?",
            context: { turns: [], entities: [] },
          },
          status: "success",
          response: askV2Response(),
          contextTrimmed: false,
          retryAttempt: 0,
        }}
        latest
        onClarify={vi.fn()}
        onFollowUp={followUp}
        onRetry={vi.fn()}
      />,
    );
    await userEvent
      .setup()
      .dblClick(screen.getAllByRole("button", { name: /Ask follow-up/ })[0]);
    expect(followUp).toHaveBeenCalledTimes(1);
  });

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
    expect(
      screen.getByLabelText("Ask a football question").compareDocumentPosition(
        screen.getByRole("heading", {
          name: "Start with a question the project can answer",
        }),
      ) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("submits an example and renders the direct answer before key numbers", async () => {
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
    expect(
      screen.getByText(
        /EPA\/dropback estimates expected scoring value added per passing dropback/,
      ),
    ).toBeVisible();
    const keyNumbers = screen.getByRole("heading", {
      name: "Key numbers",
    });
    expect(
      answer.compareDocumentPosition(keyNumbers) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    const exploration = screen.getByRole("heading", { name: "Keep exploring" })
      .parentElement?.parentElement;
    expect(
      exploration?.querySelectorAll(".ask-v2-explore-grid > *"),
    ).toHaveLength(4);
    expect(
      screen.getByRole("link", { name: /View Josh Allen's career tree/ }),
    ).toHaveAttribute(
      "href",
      "/network?mode=qb_journey&player_id=00-0034857&start_season=2010&end_season=2025&selected=qb%3A00-0034857",
    );
    expect(
      screen.getByRole("link", { name: /View Josh Allen's 2022 statistics/ }),
    ).toHaveAttribute("href", "/statistics?player=Josh+Allen&season=2022");
    expect(askQuestionV2).toHaveBeenCalledWith(
      expect.objectContaining({
        question: "How did Josh Allen perform in 2022?",
      }),
      expect.any(AbortSignal),
    );
  });

  it("explains PAE inline without exposing a methodology wall", async () => {
    vi.mocked(askQuestionV2).mockResolvedValue(
      askV2Response({
        answer:
          "Josh Allen recorded 0.237 EPA/dropback and outperformed expectation by 0.115 PAE.",
      }),
    );
    renderRoute(<AskPreviewPage />, "/ask");
    await submit("How did Josh Allen perform in 2022?");
    expect(
      await screen.findByText((_, element) =>
        Boolean(
          element?.classList.contains("ask-v2-metric-explainer") &&
          element.textContent?.includes(
            "PAE is actual EPA/dropback minus the preseason expectation.",
          ),
        ),
      ),
    ).toBeVisible();
  });

  it("connects a Rodgers coaching answer to both canonical journeys and their bounded graph", async () => {
    vi.mocked(askQuestionV2).mockResolvedValue(
      askV2Response({
        answer:
          "Mike McCarthy was the verified head coach around several of Aaron Rodgers' strongest observed seasons.",
        entities: [
          { kind: "qb", id: "qb-rodgers", display_name: "Aaron Rodgers" },
          {
            kind: "coach",
            id: "coach-mike-mccarthy",
            display_name: "Mike McCarthy",
          },
        ],
        evidence: [],
        propositions: [
          {
            ...askV2Response().propositions[0],
            proposition_id: "rodgers-2011",
            subject: "Aaron Rodgers",
            season: 2011,
          },
        ],
        follow_ups: [
          {
            label: "How did the coaching context change?",
            question: "How did Aaron Rodgers' coaching context change?",
          },
        ],
      }),
    );
    renderRoute(<AskPreviewPage />, "/ask");
    await submit("Who was coaching Aaron Rodgers during his best seasons?");
    expect(
      await screen.findByText(/Mike McCarthy was the verified/),
    ).toBeVisible();
    expect(screen.queryByText(/evidence_qb_2022/)).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Aaron Rodgers' career tree/ }),
    ).toHaveAttribute(
      "href",
      "/network?mode=qb_journey&player_id=qb-rodgers&start_season=2010&end_season=2025&selected=qb%3Aqb-rodgers",
    );
    expect(
      screen.getByRole("link", { name: /Mike McCarthy's coach tree/ }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", {
        name: /Explore Aaron Rodgers \+ Mike McCarthy/,
      }),
    ).toHaveAttribute(
      "href",
      expect.stringContaining(
        "highlights=qb%3Aqb-rodgers%2Ccoach%3Acoach-mike-mccarthy",
      ),
    );
    const exploration = screen.getByRole("heading", { name: "Keep exploring" })
      .parentElement?.parentElement;
    expect(
      exploration?.querySelectorAll(".ask-v2-explore-grid > *"),
    ).toHaveLength(4);
  });

  it("limits a Rodgers and Favre answer to four actions distributed across both quarterbacks", async () => {
    vi.mocked(askQuestionV2).mockResolvedValue(
      askV2Response({
        answer:
          "Rodgers and Favre each have distinct Green Bay quarterback histories that can be compared descriptively.",
        entities: [
          { kind: "qb", id: "qb-rodgers", display_name: "Aaron Rodgers" },
          { kind: "qb", id: "qb-favre", display_name: "Brett Favre" },
        ],
        propositions: [],
        evidence: [],
        follow_ups: [],
      }),
    );
    renderRoute(<AskPreviewPage />, "/ask");
    await submit("Compare Aaron Rodgers and Brett Favre");
    expect(await screen.findByText(/distinct Green Bay/)).toBeVisible();
    expect(
      screen.getByRole("link", { name: /Aaron Rodgers' career tree/ }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: /Brett Favre's career tree/ }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", {
        name: /Compare the coaches around their best seasons/,
      }),
    ).toBeVisible();
    const exploration = screen.getByRole("heading", { name: "Keep exploring" })
      .parentElement?.parentElement;
    expect(
      exploration?.querySelectorAll(".ask-v2-explore-grid > *"),
    ).toHaveLength(4);
  });

  it("renders partial support as a useful answer with one natural limitation", async () => {
    vi.mocked(askQuestionV2).mockResolvedValue(partialAlignmentResponse());
    renderRoute(<AskPreviewPage />, "/ask/preview");
    await submit("How would Kyler Murray fit Minnesota?");
    expect(
      await screen.findByText(/measured tendencies can be compared/),
    ).toBeVisible();
    expect(
      screen.getByText(/cannot reliably estimate performance in a different/),
    ).toBeVisible();
    expect(screen.queryByText(/\bC17\b/)).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Keep exploring" }),
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
    expect(
      await screen.findByText("The project cannot produce a rookie forecast."),
    ).toBeVisible();
    expect(
      screen.getByText(/cannot support a reliable college-to-NFL/),
    ).toBeVisible();
    expect(screen.queryByText("NOT_SUPPORTED")).not.toBeInTheDocument();
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
    await submit("Show Josh Allen CPOE in 2010");
    expect(
      await screen.findByText(/requested metric is unavailable/),
    ).toBeVisible();
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
    await screen.findByText(/Andy Reid has clearer/);
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

  it("replaces the comparison counterpart after a contextual McVay turn", async () => {
    const reidMcVay = coachComparisonResponse();
    reidMcVay.entities = [
      { kind: "coach", id: "coach-andy-reid", display_name: "Andy Reid" },
      { kind: "coach", id: "coach-sean-mcvay", display_name: "Sean McVay" },
    ];
    vi.mocked(askQuestionV2)
      .mockResolvedValueOnce(coachComparisonResponse())
      .mockResolvedValueOnce(coachComparisonResponse())
      .mockResolvedValueOnce(reidMcVay)
      .mockResolvedValueOnce(reidMcVay);
    renderRoute(<AskPreviewPage />, "/ask");
    const user = await submit("Compare Andy Reid and Mike Tomlin");
    await screen.findByText(/Andy Reid has clearer/);
    await user.type(screen.getByLabelText("Ask a football question"), "Why?");
    await user.click(screen.getByRole("button", { name: /^Ask$/ }));
    await waitFor(() => expect(askQuestionV2).toHaveBeenCalledTimes(2));
    await user.type(
      screen.getByLabelText("Ask a football question"),
      "What about McVay?",
    );
    await user.click(screen.getByRole("button", { name: /^Ask$/ }));
    await waitFor(() => expect(askQuestionV2).toHaveBeenCalledTimes(3));
    await user.type(screen.getByLabelText("Ask a football question"), "Why?");
    await user.click(screen.getByRole("button", { name: /^Ask$/ }));
    await waitFor(() => expect(askQuestionV2).toHaveBeenCalledTimes(4));
    expect(vi.mocked(askQuestionV2).mock.calls[3][0].context.entities).toEqual([
      { kind: "coach", id: "coach-andy-reid" },
      { kind: "coach", id: "coach-sean-mcvay" },
    ]);
  });

  it("carries an observed season into a next-season follow-up without inventing evidence", async () => {
    const season2011 = askV2Response({
      answer: "Aaron Rodgers' observed 2011 season is available.",
      entities: [
        { kind: "qb", id: "qb-rodgers", display_name: "Aaron Rodgers" },
      ],
      propositions: [{ ...askV2Response().propositions[0], season: 2011 }],
    });
    const season2012 = askV2Response({
      answer: "Aaron Rodgers' observed 2012 season is available.",
      entities: season2011.entities,
      propositions: [{ ...askV2Response().propositions[0], season: 2012 }],
    });
    vi.mocked(askQuestionV2)
      .mockResolvedValueOnce(season2011)
      .mockResolvedValueOnce(season2012);
    renderRoute(<AskPreviewPage />, "/ask");
    const user = await submit("Tell me about Aaron Rodgers in 2011");
    await screen.findByText(/observed 2011 season/);
    await user.type(
      screen.getByLabelText("Ask a football question"),
      "What about the next season?",
    );
    await user.click(screen.getByRole("button", { name: /^Ask$/ }));
    expect(await screen.findByText(/observed 2012 season/)).toBeVisible();
    const request = vi.mocked(askQuestionV2).mock.calls[1][0];
    expect(request.context.entities).toEqual([
      { kind: "qb", id: "qb-rodgers" },
    ]);
    expect(request.context.seasons).toEqual({
      start_season: 2011,
      end_season: 2011,
    });
  });

  it("submits an entity-specific allowlisted follow-up with canonical context", async () => {
    vi.mocked(askQuestionV2)
      .mockResolvedValueOnce(coachComparisonResponse())
      .mockResolvedValueOnce(coachComparisonResponse());
    renderRoute(<AskPreviewPage />, "/ask/preview");
    const user = await submit(
      "Compare Andy Reid and Mike Tomlin with quarterbacks",
    );
    await user.click(
      await screen.findByRole("button", {
        name: /Which QB histories connect to Andy Reid/,
      }),
    );
    await waitFor(() => expect(askQuestionV2).toHaveBeenCalledTimes(2));
    expect(vi.mocked(askQuestionV2).mock.calls[1][0].question).toBe(
      "Which quarterbacks shared Andy Reid's team-seasons?",
    );
    expect(vi.mocked(askQuestionV2).mock.calls[1][0].context.entities).toEqual([
      { kind: "coach", id: "coach-andy-reid" },
      { kind: "coach", id: "coach-mike-tomlin" },
    ]);
    expect(document.activeElement).toHaveAttribute("id", "answer-2");
  });

  it("shows useful numbers while keeping internal evidence machinery private", async () => {
    vi.mocked(askQuestionV2).mockResolvedValue(askV2Response());
    renderRoute(<AskPreviewPage />, "/ask/preview");
    await submit("How did Josh Allen perform in 2022?");
    expect(
      await screen.findByRole("heading", { name: "Key numbers" }),
    ).toBeVisible();
    expect(screen.getByText("0.237", { selector: "strong" })).toBeVisible();
    expect(
      screen.queryByText("Evidence & methodology"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Versions & provenance")).not.toBeInTheDocument();
    expect(screen.queryByText("Historical Fact")).not.toBeInTheDocument();
    expect(screen.queryByText("evidence_qb_2022")).not.toBeInTheDocument();
    expect(screen.queryByText("c19-test")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/OPENAI_API_KEY|DATABASE_URL|\/Users\//),
    ).not.toBeInTheDocument();
  });

  it("does not surface a number whose conclusion permission is denied", async () => {
    const denied = askV2Response();
    denied.conclusion_permissions = denied.conclusion_permissions.map(
      (permission) => ({ ...permission, decision: "DENIED" }),
    );
    vi.mocked(askQuestionV2).mockResolvedValue(denied);
    renderRoute(<AskPreviewPage />, "/ask");
    await submit("How did Josh Allen perform in 2022?");
    await screen.findByText(/recorded 0.237 EPA\/dropback/);
    expect(
      screen.queryByRole("heading", { name: "Key numbers" }),
    ).not.toBeInTheDocument();
  });

  it("translates bounded-evidence machinery into a natural public limitation", async () => {
    vi.mocked(askQuestionV2).mockResolvedValue(
      askV2Response({
        limitations: [
          "BOUNDED_SCOPE: 21 evidence records are not represented; narrow the request.",
        ],
      }),
    );
    renderRoute(<AskPreviewPage />, "/ask");
    await submit("How did Josh Allen perform in 2022?");
    expect(
      await screen.findByText(/focused sample of the published history/),
    ).toBeVisible();
    expect(
      screen.queryByText(/BOUNDED_SCOPE|21 evidence records/),
    ).not.toBeInTheDocument();
  });

  it("does not turn internal context coverage counts into a public performance grid", async () => {
    const response = coachComparisonResponse();
    response.propositions = [
      {
        ...askV2Response().propositions[0],
        metric: "distinct_qb_team_seasons",
        value: 38,
        unit: "count",
      },
    ];
    response.conclusion_permissions = askV2Response().conclusion_permissions;
    vi.mocked(askQuestionV2).mockResolvedValue(response);
    renderRoute(<AskPreviewPage />, "/ask");
    await submit("Compare Andy Reid and Mike Tomlin.");
    await screen.findByText(/Andy Reid has clearer/);
    expect(
      screen.queryByRole("heading", { name: "Key numbers" }),
    ).not.toBeInTheDocument();
  });

  it("does not misattribute a comparison's environment value to its player", async () => {
    const response = partialAlignmentResponse();
    response.propositions = response.propositions.map((proposition) => ({
      ...proposition,
      subject: "Kyler Murray",
      value: 0.028,
      predicate: "descriptive_player_scheme_alignment",
    }));
    vi.mocked(askQuestionV2).mockResolvedValue(response);
    renderRoute(<AskPreviewPage />, "/ask");
    await submit("How would Kyler Murray fit Minnesota?");
    await screen.findByText(/measured tendencies can be compared/);
    expect(
      screen.queryByRole("heading", { name: "Key numbers" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("2.8%", { selector: "strong" }),
    ).not.toBeInTheDocument();
  });

  it("does not expose provider mode while preserving the same public answer", async () => {
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
    await screen.findByText(/recorded 0.237 EPA\/dropback/);
    expect(screen.queryByText("Deterministic")).not.toBeInTheDocument();
    await user.type(
      screen.getByLabelText("Ask a football question"),
      "What about 2023?",
    );
    await user.click(screen.getByRole("button", { name: /^Ask$/ }));
    await waitFor(() => expect(askQuestionV2).toHaveBeenCalledTimes(2));
    expect(screen.queryByText("Grounded AI")).not.toBeInTheDocument();
    expect(screen.queryByText(/gpt-test/)).not.toBeInTheDocument();
  });

  it("renders comparisons neutrally with canonical exploration links", async () => {
    vi.mocked(askQuestionV2).mockResolvedValue(coachComparisonResponse());
    renderRoute(<AskPreviewPage />, "/ask/preview");
    await submit("Compare Andy Reid and Mike Tomlin with quarterbacks");
    expect(await screen.findByText(/Andy Reid has clearer/)).toBeVisible();
    expect(
      screen.getByText(/not proof of better QB development/),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: /View Andy Reid's coach tree/ }),
    ).toHaveAttribute(
      "href",
      "/network?mode=coach_journey&coach_id=coach-andy-reid&start_season=2010&end_season=2025&selected=coach%3Acoach-andy-reid",
    );
    expect(
      screen.queryByText(/comparison_winner_allowed/i),
    ).not.toBeInTheDocument();
  });

  it("renders counterfactual support before the alternate-career limitation", async () => {
    vi.mocked(askQuestionV2).mockResolvedValue(counterfactualResponse());
    renderRoute(<AskPreviewPage />, "/ask/preview");
    await submit("What if Chicago drafted Patrick Mahomes?");
    expect(
      await screen.findByText(/actual history with Chicago/),
    ).toBeVisible();
    expect(
      screen.getByText(/cannot reliably estimate an alternate/),
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
      "The answer could not be loaded. Please retry this question.",
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
        await screen.findByText(response.answer);
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
