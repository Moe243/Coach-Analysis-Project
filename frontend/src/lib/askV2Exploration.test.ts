import {
  askV2Response,
  coachComparisonResponse,
  partialAlignmentResponse,
} from "../test/askV2Fixtures";
import { buildKeepExploringActions } from "./askV2Exploration";

describe("Ask v2 connected exploration", () => {
  it("does not offer the just-answered coach question again as a continuation", () => {
    const question = "Which quarterbacks shared Mike McCarthy's team-seasons?";
    const actions = buildKeepExploringActions(
      askV2Response({
        entities: [
          {
            kind: "coach",
            id: "coach-mike-mccarthy",
            display_name: "Mike McCarthy",
          },
        ],
        propositions: [],
        evidence: [],
        follow_ups: [
          {
            label: "Show verified offensive roles",
            question: "Show verified offensive roles",
          },
        ],
      }),
      question,
    );
    expect(actions).toHaveLength(4);
    expect(actions.some((action) => action.question === question)).toBe(false);
    expect(actions[3].id).toBe("coach-network");
  });
  it("offers a coach four specific continuations rather than a generic Why button", () => {
    const actions = buildKeepExploringActions(
      askV2Response({
        entities: [
          {
            kind: "coach",
            id: "coach-mike-mccarthy",
            display_name: "Mike McCarthy",
          },
        ],
        propositions: [],
        evidence: [],
        follow_ups: [],
      }),
    );
    expect(actions).toHaveLength(4);
    expect(actions.map((action) => action.question).filter(Boolean)).toEqual([
      "Which quarterbacks shared Mike McCarthy's team-seasons?",
    ]);
    expect(actions[3].href).toContain(
      "mode=full_network&anchor=coach&coach_id=coach-mike-mccarthy",
    );
    expect(
      actions.some((action) =>
        /canonical|Explain the result/.test(action.description + action.label),
      ),
    ).toBe(false);
  });
  it("builds exactly four canonical QB actions with season-aware URLs", () => {
    const actions = buildKeepExploringActions(askV2Response());
    expect(actions).toHaveLength(4);
    expect(actions.map((action) => action.href).filter(Boolean)).toEqual([
      "/network?mode=qb_journey&player_id=00-0034857&start_season=2010&end_season=2025&selected=qb%3A00-0034857",
      "/statistics?player=Josh+Allen&season=2022",
    ]);
    expect(actions[2]).toMatchObject({
      kind: "ask",
      question: "How did Josh Allen perform in 2023?",
      entities: [{ kind: "qb", id: "00-0034857" }],
      seasons: { start_season: 2022, end_season: 2022 },
    });
  });

  it("opens QB plus team context with the canonical QB selected", () => {
    const actions = buildKeepExploringActions(partialAlignmentResponse());
    expect(actions).toHaveLength(4);
    expect(actions[0]).toMatchObject({
      kind: "navigate",
      href: "/network?mode=qb_journey&player_id=00-0035228&start_season=2010&end_season=2025&selected=qb%3A00-0035228",
    });
    expect(actions[1]).toMatchObject({
      kind: "navigate",
      href: "/network?mode=team_history&team_id=team_min&start_season=2010&end_season=2025",
    });
    expect(actions[2]).toMatchObject({
      kind: "navigate",
      href: "/network?mode=full_network&anchor=all&start_season=2021&end_season=2025&selected=qb%3A00-0035228&highlights=qb%3A00-0035228%2Cteam-season%3Ateam_min%3A2021%2Cteam-season%3Ateam_min%3A2022%2Cteam-season%3Ateam_min%3A2023%2Cteam-season%3Ateam_min%3A2024%2Cteam-season%3Ateam_min%3A2025",
    });
    expect(actions).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          kind: "ask",
          question: "Which parts are descriptive rather than predictive?",
        }),
      ]),
    );
  });

  it("keeps two-coach comparisons canonical without inventing a multi-anchor route", () => {
    const actions = buildKeepExploringActions(coachComparisonResponse());
    expect(actions).toHaveLength(4);
    expect(actions.map((action) => action.href).filter(Boolean)).toEqual([
      "/network?mode=coach_journey&coach_id=coach-andy-reid&start_season=2010&end_season=2025&selected=coach%3Acoach-andy-reid",
      "/network?mode=coach_journey&coach_id=coach-mike-tomlin&start_season=2010&end_season=2025&selected=coach%3Acoach-mike-tomlin",
      "/network?mode=full_network&anchor=all&start_season=2021&end_season=2025&selected=coach%3Acoach-andy-reid&highlights=coach%3Acoach-andy-reid%2Ccoach%3Acoach-mike-tomlin",
    ]);
    expect(actions[3]).toMatchObject({
      kind: "ask",
      question: "Which quarterbacks shared Andy Reid's team-seasons?",
    });
  });

  it("uses a bounded full-network deep link for QB and coach context", () => {
    const response = askV2Response({
      entities: [
        { kind: "qb", id: "qb-rodgers", display_name: "Aaron Rodgers" },
        { kind: "coach", id: "coach-lafleur", display_name: "Matt LaFleur" },
      ],
      propositions: [
        { ...askV2Response().propositions[0], season: 2019 },
        {
          ...askV2Response().propositions[0],
          proposition_id: "prop-latest",
          season: 2025,
        },
      ],
      follow_ups: [],
    });
    expect(buildKeepExploringActions(response)[2].href).toBe(
      "/network?mode=full_network&anchor=all&start_season=2021&end_season=2025&selected=qb%3Aqb-rodgers&highlights=qb%3Aqb-rodgers%2Ccoach%3Acoach-lafleur",
    );
  });

  it("keeps multiple quarterbacks canonical and exposes each journey only once", () => {
    const response = askV2Response({
      entities: [
        { kind: "qb", id: "qb-rodgers", display_name: "Aaron Rodgers" },
        { kind: "qb", id: "qb-favre", display_name: "Brett Favre" },
      ],
      propositions: [],
      follow_ups: [],
    });
    const actions = buildKeepExploringActions(response);
    expect(actions).toHaveLength(4);
    expect(
      actions.filter((action) => action.href?.includes("player_id=qb-rodgers")),
    ).toHaveLength(1);
    expect(
      actions.filter((action) => action.href?.includes("player_id=qb-favre")),
    ).toHaveLength(1);
    expect(actions[3]).toMatchObject({
      kind: "ask",
      question:
        "Which coaches were involved in Aaron Rodgers' and Brett Favre's best seasons?",
    });
  });

  it("does not manufacture exploration context for unresolved clarification", () => {
    expect(
      buildKeepExploringActions(
        askV2Response({
          answerability: "CLARIFICATION_REQUIRED",
          entities: [],
          propositions: [],
        }),
      ),
    ).toEqual([]);
  });

  it("does not scope a retired QB's multi-entity link to only the other QB's latest season", () => {
    const response = askV2Response({
      entities: [
        { kind: "qb", id: "00-0023459", display_name: "Aaron Rodgers" },
        { kind: "qb", id: "00-0005106", display_name: "Brett Favre" },
      ],
      propositions: [
        {
          ...askV2Response().propositions[0],
          subject: "Aaron Rodgers",
          season: 2025,
        },
        {
          ...askV2Response().propositions[0],
          subject: "Brett Favre",
          season: 2010,
          proposition_id: "favre-2010",
        },
      ],
    });
    const url = new URL(
      buildKeepExploringActions(response)[2].href!,
      "https://local.test",
    );
    expect(url.searchParams.get("start_season")).toBe("2010");
    expect(url.searchParams.get("end_season")).toBe("2010");
    expect(url.searchParams.get("highlights")).toBe(
      "qb:00-0023459,qb:00-0005106",
    );
  });

  it("keeps projection follow-up context but never sends future seasons to historical pages", () => {
    const actions = buildKeepExploringActions(
      askV2Response({
        propositions: [{ ...askV2Response().propositions[0], season: 2026 }],
      }),
    );
    expect(actions[0].href).toBe(
      "/network?mode=qb_journey&player_id=00-0034857&start_season=2010&end_season=2025&selected=qb%3A00-0034857",
    );
    expect(actions[1].href).toBe("/statistics?player=Josh+Allen");
    expect(actions[1].label).toBe("View Josh Allen's statistics");
    expect(actions[2].seasons).toEqual({
      start_season: 2026,
      end_season: 2026,
    });
  });
});
