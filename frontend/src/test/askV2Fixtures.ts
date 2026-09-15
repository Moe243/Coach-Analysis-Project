import type { AskV2Response } from "../api/askV2";

export function askV2Response(
  overrides: Partial<AskV2Response> = {},
): AskV2Response {
  return {
    contract_version: "ask-v2",
    answerability: "SUPPORTED",
    answer_mode: "deterministic",
    reason_code: "SUPPORTED_ANALYTICAL_TASK",
    answer:
      "Josh Allen recorded 0.237 EPA/dropback for Buffalo in 2022 and outperformed his preseason expectation by 0.115.",
    entities: [{ kind: "qb", id: "00-0034857", display_name: "Josh Allen" }],
    clarification_candidates: [],
    evidence: [
      {
        rank: 1,
        evidence_id: "evidence_qb_2022",
        summary: "Josh Allen · Buffalo · 2022 · 651 dropbacks",
      },
    ],
    propositions: [
      {
        proposition_id: "prop_qb_2022",
        kind: "HISTORICAL_FACT",
        statement:
          "Josh Allen recorded 0.237 EPA/dropback for Buffalo in 2022 across 651 dropbacks.",
        evidence_ids: ["evidence_qb_2022"],
        permission_id: "permission_historical",
        uncertainty_id: "uncertainty_qb_2022",
        subject: "Josh Allen",
        predicate: "recorded",
        metric: "epa_per_dropback",
        value: 0.237,
        unit: "epa_per_dropback",
        season: 2022,
        qualifier: "651 dropbacks; high reliability",
        operation_id: null,
        importance: 90,
      },
    ],
    conclusion_permissions: [
      {
        permission_id: "permission_historical",
        kind: "HISTORICAL_FACT",
        decision: "ALLOWED",
        reason_code: "direct_source_evidence",
        explanation: "Direct historical claims may use approved evidence.",
        evidence_ids: ["evidence_qb_2022"],
        permitted_numeric_fields: ["epa_per_dropback"],
        comparison_winner_allowed: false,
      },
    ],
    uncertainty: [
      {
        uncertainty_id: "uncertainty_qb_2022",
        method: "observed_sample",
        standard_error: null,
        lower: -0.102,
        upper: 0.347,
        confidence_level: 0.95,
        reliability: "HIGH",
        explanation: "651 dropbacks; high reliability",
      },
    ],
    unsupported_portions: [],
    limitations: ["Observed performance is not proof of causation."],
    follow_ups: [
      { label: "View 2023", question: "How did Josh Allen perform in 2023?" },
    ],
    versions: {
      ask_contract_version: "ask-v2",
      contract_schema_sha256: "a".repeat(64),
      scientific_policy_version: "ask-policy-test",
      analytical_data_version: "c19-test",
      analytical_model_versions: ["expected-test"],
      evidence_reducer_version: "ask-v2-evidence-v1",
      deterministic_planner_version: "ask-v2-stage-c",
      planner_implementation_version: "ask-v2-stage-c",
      planner_model_version: null,
      synthesizer_implementation_version: "ask-v2-stage-c",
      synthesizer_model_version: null,
      answer_mode: "deterministic",
    },
    ...overrides,
  };
}

export function partialAlignmentResponse(): AskV2Response {
  return askV2Response({
    answerability: "PARTIALLY_SUPPORTED",
    answer:
      "Kyler Murray's measured tendencies can be compared with Minnesota's historical scheme.",
    entities: [
      { kind: "qb", id: "00-0035228", display_name: "Kyler Murray" },
      { kind: "team", id: "team_min", display_name: "Minnesota Vikings" },
    ],
    evidence: [
      {
        rank: 1,
        evidence_id: "evidence_alignment",
        summary: "Comparable scramble rates",
      },
    ],
    propositions: [
      {
        proposition_id: "prop_alignment",
        kind: "PLAYER_SCHEME_DESCRIPTIVE_ALIGNMENT",
        statement:
          "Murray's recent scramble rate was 6.5%; Minnesota's historical rate was 2.8%.",
        evidence_ids: ["evidence_alignment"],
        permission_id: "permission_alignment",
        uncertainty_id: null,
        subject: "Kyler Murray and Minnesota Vikings",
        predicate: "descriptive_alignment",
        metric: "scramble_rate",
        value: null,
        unit: "rate",
        season: null,
        qualifier: "Comparable measured tendencies only; not predictive fit.",
        operation_id: "operation_alignment",
        importance: 90,
      },
    ],
    conclusion_permissions: [
      {
        permission_id: "permission_alignment",
        kind: "PLAYER_SCHEME_DESCRIPTIVE_ALIGNMENT",
        decision: "ALLOWED_WITH_LIMITATIONS",
        reason_code: "registered_dimensions_only",
        explanation: "Only measured tendencies may be aligned descriptively.",
        evidence_ids: ["evidence_alignment"],
        permitted_numeric_fields: [],
        comparison_winner_allowed: false,
      },
    ],
    uncertainty: [],
    unsupported_portions: [
      {
        description: "Destination-team numerical performance or improvement",
        reason_code: "C17_SCENARIO_NOT_SUPPORTED",
        explanation:
          "C17 did not validate a Player × Scheme environment-response model.",
      },
    ],
    limitations: ["Descriptive alignment is not a prediction."],
    follow_ups: [],
  });
}

export function coachComparisonResponse(): AskV2Response {
  return askV2Response({
    answerability: "PARTIALLY_SUPPORTED",
    answer:
      "Andy Reid has clearer directly verified offensive/QB-role attribution in the available evidence; this is not proof of better QB development.",
    entities: [
      { kind: "coach", id: "coach-andy-reid", display_name: "Andy Reid" },
      { kind: "coach", id: "coach-mike-tomlin", display_name: "Mike Tomlin" },
    ],
    evidence: [
      {
        rank: 1,
        evidence_id: "evidence_reid_roles",
        summary: "Verified offensive-role coverage for Andy Reid.",
      },
      {
        rank: 2,
        evidence_id: "evidence_tomlin_roles",
        summary: "Verified head-coach coverage for Mike Tomlin.",
      },
    ],
    propositions: [
      {
        proposition_id: "prop_reid_roles",
        kind: "VERIFIED_ROLE_ATTRIBUTION",
        statement:
          "Andy Reid has directly verified offensive-role coverage in the comparison evidence.",
        evidence_ids: ["evidence_reid_roles"],
        permission_id: "permission_verified_roles",
        uncertainty_id: null,
        subject: "Andy Reid",
        predicate: "verified_role_coverage",
        metric: null,
        value: null,
        unit: null,
        season: null,
        qualifier: "Role attribution is not causal development evidence.",
        operation_id: null,
        importance: 90,
      },
      {
        proposition_id: "prop_tomlin_roles",
        kind: "VERIFIED_ROLE_ATTRIBUTION",
        statement:
          "Mike Tomlin has directly verified head-coach coverage in the comparison evidence.",
        evidence_ids: ["evidence_tomlin_roles"],
        permission_id: "permission_verified_roles",
        uncertainty_id: null,
        subject: "Mike Tomlin",
        predicate: "verified_role_coverage",
        metric: null,
        value: null,
        unit: null,
        season: null,
        qualifier: "Role attribution is not causal development evidence.",
        operation_id: null,
        importance: 80,
      },
    ],
    conclusion_permissions: [
      {
        permission_id: "permission_verified_roles",
        kind: "VERIFIED_ROLE_ATTRIBUTION",
        decision: "ALLOWED_WITH_LIMITATIONS",
        reason_code: "verified_assignment_evidence",
        explanation:
          "Verified role attribution may be described without a causal claim.",
        evidence_ids: ["evidence_reid_roles", "evidence_tomlin_roles"],
        permitted_numeric_fields: [],
        comparison_winner_allowed: false,
      },
    ],
    uncertainty: [],
    unsupported_portions: [
      {
        description: "Universal or causal QB-development winner",
        reason_code: "DEVELOPMENT_CONCLUSION_NOT_PERMITTED",
        explanation:
          "Verified roles and QB contexts do not identify causal development quality.",
      },
    ],
    limitations: [
      "Verified roles and QB contexts do not identify causal development quality.",
    ],
    follow_ups: [{ label: "Explain why", question: "Why?" }],
  });
}

export function counterfactualResponse(): AskV2Response {
  return askV2Response({
    answerability: "PARTIALLY_SUPPORTED",
    answer:
      "The project can compare Patrick Mahomes's actual history with Chicago's historical context.",
    entities: [
      { kind: "qb", id: "00-0033873", display_name: "Patrick Mahomes" },
      { kind: "team", id: "team_chi", display_name: "Chicago Bears" },
    ],
    evidence: [
      {
        rank: 1,
        evidence_id: "evidence_mahomes_history",
        summary: "Patrick Mahomes · Kansas City · observed NFL history",
      },
      {
        rank: 2,
        evidence_id: "evidence_chicago_context",
        summary: "Chicago · observed historical offensive context",
      },
    ],
    propositions: [
      {
        proposition_id: "prop_mahomes_history",
        kind: "HISTORICAL_FACT",
        statement:
          "Patrick Mahomes's actual NFL history is available as observed evidence.",
        evidence_ids: ["evidence_mahomes_history"],
        permission_id: "permission_historical_context",
        uncertainty_id: null,
        subject: "Patrick Mahomes",
        predicate: "observed_history_available",
        metric: null,
        value: null,
        unit: null,
        season: null,
        qualifier: "Actual history only; no alternate career is inferred.",
        operation_id: null,
        importance: 90,
      },
      {
        proposition_id: "prop_chicago_context",
        kind: "HISTORICAL_FACT",
        statement:
          "Chicago's observed historical offensive context is available for descriptive comparison.",
        evidence_ids: ["evidence_chicago_context"],
        permission_id: "permission_historical_context",
        uncertainty_id: null,
        subject: "Chicago Bears",
        predicate: "observed_context_available",
        metric: null,
        value: null,
        unit: null,
        season: null,
        qualifier: "Observed context is not an alternate-career estimate.",
        operation_id: null,
        importance: 80,
      },
    ],
    conclusion_permissions: [
      {
        permission_id: "permission_historical_context",
        kind: "HISTORICAL_FACT",
        decision: "ALLOWED_WITH_LIMITATIONS",
        reason_code: "observed_history_only",
        explanation:
          "Observed histories may be compared without simulating an alternate career.",
        evidence_ids: ["evidence_mahomes_history", "evidence_chicago_context"],
        permitted_numeric_fields: [],
        comparison_winner_allowed: false,
      },
    ],
    uncertainty: [],
    unsupported_portions: [
      {
        description: "Alternate-career numerical simulation",
        reason_code: "C18_COUNTERFACTUAL_NOT_IMPLEMENTED",
        explanation:
          "The project does not have a validated alternate-career model.",
      },
    ],
    limitations: [
      "Historical context cannot establish an alternate-career outcome.",
    ],
    follow_ups: [],
  });
}
