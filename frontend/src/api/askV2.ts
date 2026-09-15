import { API_BASE_URL, ApiError } from "./client";

export type AskV2Answerability =
  | "SUPPORTED"
  | "PARTIALLY_SUPPORTED"
  | "NOT_SUPPORTED"
  | "CLARIFICATION_REQUIRED"
  | "DATA_UNAVAILABLE";

export type AskV2AnswerMode = "deterministic" | "grounded_ai";
export type AskV2EntityKind = "qb" | "coach" | "team";
export type AskV2Reliability = "HIGH" | "MEDIUM" | "LOW" | "UNAVAILABLE";
export type AskV2Scalar = string | number | boolean | null;

export interface AskV2ContextTurn {
  role: "user" | "assistant";
  content: string;
}

export interface AskV2CanonicalEntity {
  kind: AskV2EntityKind;
  id: string;
}

export interface AskV2ResolvedEntity extends AskV2CanonicalEntity {
  display_name: string;
}

export interface AskV2SeasonContext {
  start_season: number;
  end_season: number;
}

export interface AskV2ConversationContext {
  turns: AskV2ContextTurn[];
  entities: AskV2CanonicalEntity[];
  seasons?: AskV2SeasonContext | null;
}

export interface AskV2Request {
  question: string;
  context: AskV2ConversationContext;
}

export interface AskV2EvidencePoint {
  rank: number;
  evidence_id: string;
  summary: string;
}

export interface AskV2Proposition {
  proposition_id: string;
  kind:
    | "HISTORICAL_FACT"
    | "DESCRIPTIVE_COMPARISON"
    | "VERIFIED_ROLE_ATTRIBUTION"
    | "DEVELOPMENT_QUALITY"
    | "PLAYER_SCHEME_DESCRIPTIVE_ALIGNMENT"
    | "PREDICTIVE_FIT"
    | "CAUSAL"
    | "NUMERICAL_COMPARISON_WINNER";
  statement: string;
  evidence_ids: string[];
  permission_id: string;
  uncertainty_id: string | null;
  subject: string | null;
  predicate: string | null;
  metric: string | null;
  value: AskV2Scalar;
  unit: string | null;
  season: number | null;
  qualifier: string | null;
  operation_id: string | null;
  importance: number;
}

export interface AskV2ConclusionPermission {
  permission_id: string;
  kind: AskV2Proposition["kind"];
  decision: "ALLOWED" | "ALLOWED_WITH_LIMITATIONS" | "DENIED";
  reason_code: string;
  explanation: string;
  evidence_ids: string[];
  permitted_numeric_fields: string[];
  comparison_winner_allowed: boolean;
}

export interface AskV2Uncertainty {
  uncertainty_id: string;
  method: string;
  standard_error: number | null;
  lower: number | null;
  upper: number | null;
  confidence_level: number | null;
  reliability: AskV2Reliability;
  explanation: string;
}

export interface AskV2UnsupportedPortion {
  description: string;
  reason_code: string;
  explanation: string;
}

export interface AskV2FollowUp {
  label: string;
  question: string;
}

export interface AskV2Versions {
  ask_contract_version: "ask-v2";
  contract_schema_sha256: string;
  scientific_policy_version: string;
  analytical_data_version: string | null;
  analytical_model_versions: string[];
  evidence_reducer_version: string | null;
  deterministic_planner_version: string | null;
  planner_implementation_version: string;
  planner_model_version: string | null;
  synthesizer_implementation_version: string;
  synthesizer_model_version: string | null;
  answer_mode: AskV2AnswerMode;
}

export interface AskV2Response {
  contract_version: "ask-v2";
  answerability: AskV2Answerability;
  answer_mode: AskV2AnswerMode;
  reason_code: string | null;
  answer: string;
  entities: AskV2ResolvedEntity[];
  clarification_candidates: AskV2ResolvedEntity[];
  evidence: AskV2EvidencePoint[];
  propositions: AskV2Proposition[];
  conclusion_permissions: AskV2ConclusionPermission[];
  uncertainty: AskV2Uncertainty[];
  unsupported_portions: AskV2UnsupportedPortion[];
  limitations: string[];
  follow_ups: AskV2FollowUp[];
  versions: AskV2Versions;
}

export async function askQuestionV2(
  request: AskV2Request,
  signal?: AbortSignal,
): Promise<AskV2Response> {
  const response = await fetch(`${API_BASE_URL}/ask/v2`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Preserve the status-based message for non-JSON failures.
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as AskV2Response;
}
