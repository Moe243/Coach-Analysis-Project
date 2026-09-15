import { askV2Response } from "../test/askV2Fixtures";
import {
  buildBoundedAskV2Context,
  clarificationQuestion,
  entityHref,
  formatAskV2Value,
} from "./askV2";

describe("Ask v2 presentation and context helpers", () => {
  it("bounds context deterministically without truncating visible questions", () => {
    const history = Array.from({ length: 10 }, (_, index) => ({
      question: `Question ${index} about Josh Allen`,
      response: askV2Response(),
    }));
    const result = buildBoundedAskV2Context(history);
    expect(result.trimmed).toBe(true);
    expect(result.context.turns).toHaveLength(8);
    expect(result.context.turns[0].content).toBe("Question 2 about Josh Allen");
    expect(result.context.turns.at(-1)?.content).toBe(
      "Question 9 about Josh Allen",
    );
    expect(result.context.entities).toEqual([{ kind: "qb", id: "00-0034857" }]);
  });

  it("enforces the context character and canonical entity limits", () => {
    const history = Array.from({ length: 8 }, (_, index) => ({
      question: `${index}-${"x".repeat(1_999)}`,
      response: askV2Response({
        entities: [
          {
            kind: "qb",
            id: `00-${String(index).padStart(7, "0")}`,
            display_name: `QB ${index}`,
          },
        ],
      }),
    }));
    const result = buildBoundedAskV2Context(history, {
      kind: "coach",
      id: "coach-andy-reid",
    });
    expect(
      result.context.turns.reduce((sum, turn) => sum + turn.content.length, 0),
    ).toBeLessThanOrEqual(8_000);
    expect(result.context.entities.length).toBeLessThanOrEqual(8);
    expect(result.context.entities).toContainEqual({
      kind: "coach",
      id: "coach-andy-reid",
    });
  });

  it("formats only typed rate units as percentages and preserves missing values", () => {
    expect(formatAskV2Value(0.643, "rate")).toBe("64.3%");
    expect(formatAskV2Value(0.643, "epa_per_dropback")).toBe("0.643");
    expect(formatAskV2Value(null, "rate")).toBe("Unavailable");
    expect(formatAskV2Value(651, "count")).toBe("651");
  });

  it("builds links exclusively from canonical IDs", () => {
    expect(
      entityHref({ kind: "qb", id: "00-0034857", display_name: "Ignored" }),
    ).toBe("/qbs/00-0034857");
    expect(
      entityHref({
        kind: "coach",
        id: "coach-andy-reid",
        display_name: "Ignored",
      }),
    ).toBe("/coaches/coach-andy-reid");
    expect(
      entityHref({ kind: "team", id: "team_min", display_name: "Ignored" }),
    ).toBe("/network?team_id=team_min");
  });

  it("uses a canonical display name for clarification without exposing the ID", () => {
    const candidate = {
      kind: "qb" as const,
      id: "00-0034857",
      display_name: "Josh Allen",
    };
    expect(clarificationQuestion("Allen performance 2022", candidate)).toBe(
      "Josh Allen performance 2022",
    );
  });
});
