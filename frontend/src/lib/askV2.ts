import type {
  AskV2CanonicalEntity,
  AskV2ConversationContext,
  AskV2Proposition,
  AskV2ResolvedEntity,
  AskV2Response,
  AskV2Scalar,
  AskV2Uncertainty,
} from "../api/askV2";

export const ASK_V2_MAX_CONTEXT_TURNS = 8;
export const ASK_V2_MAX_CONTEXT_CHARACTERS = 8_000;
export const ASK_V2_MAX_ENTITIES = 8;

export interface ContextSourceTurn {
  question: string;
  response?: AskV2Response;
}

export interface BoundedContextResult {
  context: AskV2ConversationContext;
  trimmed: boolean;
}

function entityKey(entity: AskV2CanonicalEntity) {
  return `${entity.kind}:${entity.id}`;
}

function latestSeasonContext(
  turn: ContextSourceTurn | undefined,
): AskV2ConversationContext["seasons"] {
  if (!turn?.response) return undefined;
  const evidenceSeasons = new Set(
    turn.response.propositions
      .map((proposition) => proposition.season)
      .filter((season): season is number => season !== null),
  );
  if (evidenceSeasons.size === 1) {
    const season = [...evidenceSeasons][0];
    return { start_season: season, end_season: season };
  }
  const questionSeasons = new Set(
    [...turn.question.matchAll(/\b20\d{2}\b/g)]
      .map(([value]) => Number(value))
      .filter((season) => season >= 2010 && season <= 2026),
  );
  if (questionSeasons.size === 1) {
    const season = [...questionSeasons][0];
    return { start_season: season, end_season: season };
  }
  return undefined;
}

export function buildBoundedAskV2Context(
  history: readonly ContextSourceTurn[],
  additionalEntity?: AskV2CanonicalEntity,
): BoundedContextResult {
  const eligible = history.filter((turn) => turn.response);
  const selected: ContextSourceTurn[] = [];
  let characters = 0;
  for (let index = eligible.length - 1; index >= 0; index -= 1) {
    const turn = eligible[index];
    if (
      selected.length === ASK_V2_MAX_CONTEXT_TURNS ||
      characters + turn.question.length > ASK_V2_MAX_CONTEXT_CHARACTERS
    ) {
      continue;
    }
    selected.unshift(turn);
    characters += turn.question.length;
  }

  const entities: AskV2CanonicalEntity[] = [];
  const seen = new Set<string>();
  const addEntity = (entity: AskV2CanonicalEntity) => {
    const key = entityKey(entity);
    if (!seen.has(key) && entities.length < ASK_V2_MAX_ENTITIES) {
      seen.add(key);
      entities.push({ kind: entity.kind, id: entity.id });
    }
  };
  if (additionalEntity) addEntity(additionalEntity);
  const latestEntities = selected.at(-1)?.response?.entities ?? [];
  for (const entity of latestEntities) addEntity(entity);
  const seasons = latestSeasonContext(selected.at(-1));

  return {
    context: {
      turns: selected.map((turn) => ({
        role: "user" as const,
        content: turn.question,
      })),
      entities: entities.sort((left, right) =>
        entityKey(left).localeCompare(entityKey(right)),
      ),
      ...(seasons ? { seasons } : {}),
    },
    trimmed: selected.length < eligible.length,
  };
}

export function entityHref(entity: AskV2ResolvedEntity): string {
  if (entity.kind === "qb") return `/qbs/${encodeURIComponent(entity.id)}`;
  if (entity.kind === "coach")
    return `/coaches/${encodeURIComponent(entity.id)}`;
  return `/network?team_id=${encodeURIComponent(entity.id)}`;
}

export function humanize(value: string): string {
  return value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/(^|\s)\S/g, (character) => character.toUpperCase());
}

const metricLabels: Readonly<Record<string, string>> = {
  epa_per_dropback: "EPA/dropback",
  performance_above_expectation: "PAE",
  cpoe: "CPOE",
  pcae: "PCAE",
  proe: "PROE",
  recent_scramble_rate: "Recent scramble rate",
  recent_shotgun_rate: "Recent shotgun rate",
  recent_average_air_yards: "Recent average air yards",
  recent_target_depth_short_rate: "Recent short-target rate",
  recent_target_depth_intermediate_rate: "Recent intermediate-target rate",
  recent_target_depth_deep_rate: "Recent deep-target rate",
  target_depth_short_rate: "Short-target rate",
  target_depth_intermediate_rate: "Intermediate-target rate",
  target_depth_deep_rate: "Deep-target rate",
};

export function metricLabel(value: string): string {
  return metricLabels[value] ?? humanize(value);
}

export function formatAskV2Value(
  value: AskV2Scalar,
  unit: string | null,
): string {
  if (value === null) return "Unavailable";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string") return value;
  if (unit === "rate" || unit === "proportion" || unit === "rate_difference")
    return `${(value * 100).toFixed(1)}%`;
  if (unit === "percentage_points") return `${value.toFixed(1)} pp`;
  if (unit === "count") return Math.round(value).toLocaleString("en-US");
  if (unit === "epa_per_dropback") return value.toFixed(3);
  return Number.isInteger(value)
    ? value.toLocaleString("en-US")
    : value.toFixed(3);
}

export function propositionUncertainty(
  proposition: AskV2Proposition,
  uncertainty: readonly AskV2Uncertainty[],
): AskV2Uncertainty | undefined {
  return uncertainty.find(
    (item) => item.uncertainty_id === proposition.uncertainty_id,
  );
}

export function isComparisonResponse(response: AskV2Response): boolean {
  return (
    response.entities.length >= 2 &&
    (response.propositions.some(
      (item) => item.kind === "DESCRIPTIVE_COMPARISON",
    ) ||
      response.propositions.some(
        (item) => item.kind === "NUMERICAL_COMPARISON_WINNER",
      ) ||
      response.unsupported_portions.some((item) =>
        item.reason_code.includes("DEVELOPMENT_CONCLUSION"),
      ))
  );
}

export function isAlignmentResponse(response: AskV2Response): boolean {
  return response.propositions.some(
    (item) => item.kind === "PLAYER_SCHEME_DESCRIPTIVE_ALIGNMENT",
  );
}

export function isCounterfactualResponse(response: AskV2Response): boolean {
  return response.unsupported_portions.some(
    (item) => item.reason_code === "C18_COUNTERFACTUAL_NOT_IMPLEMENTED",
  );
}

export function clarificationQuestion(
  originalQuestion: string,
  entity: AskV2ResolvedEntity,
): string {
  const surname = entity.display_name.split(/\s+/).at(-1);
  if (surname) {
    const expression = new RegExp(
      `\\b${surname.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`,
      "i",
    );
    if (expression.test(originalQuestion)) {
      return originalQuestion.replace(expression, entity.display_name);
    }
  }
  return `${entity.display_name}: ${originalQuestion}`;
}
