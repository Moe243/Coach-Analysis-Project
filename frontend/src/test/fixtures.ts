import type {
  ApiPage,
  Citation,
  CoachAssignment,
  CoachImpact,
  CoachProfile,
  NetworkEdge,
  QbPae,
  QbProfile,
  QbSeason,
  Team,
  Versions,
} from "../api/contracts";

export const versions: Versions = {
  load_id: "test-load",
  schema_version: "checkpoint-7.2",
  loader_version: "serving-loader-v3",
  api_contract_version: "api-v1.1",
  historical_data_version: "c3-test",
  expected_data_version: "c5-test",
  expected_model_version: "expected-test",
  coach_data_version: "c6-test",
  coach_model_version: "coach-impact-test",
};

export const teams: Team[] = [
  {
    load_id: "test-load",
    team_id: "team_den",
    team_abbr: "DEN",
    team_name: "Denver Broncos",
    payload: {},
  },
  {
    load_id: "test-load",
    team_id: "team_hou",
    team_abbr: "HOU",
    team_name: "Houston Texans",
    payload: {},
  },
];

export const qbSeason: QbSeason = {
  load_id: "test-load",
  player_id: "qb-1",
  display_name: "Test Quarterback",
  team_id: "team_den",
  season: 2025,
  scope: "analysis",
  games: 17,
  starts: 17,
  dropbacks: 620,
  epa_per_dropback: 0.15,
  cpoe: 2.4,
  success_rate: 0.49,
  sack_rate: 0.05,
  qualifies_default: true,
  metric_version: "qb-dropback-v1",
  payload: { interception_rate: 0.02, touchdown_rate: 0.06 },
};

export const qbPae: QbPae = {
  load_id: "test-load",
  player_id: "qb-1",
  display_name: "Test Quarterback",
  team_id: "team_den",
  season: 2025,
  data_version: "c5-test",
  model_version: "expected-test",
  expected_epa_per_dropback: 0.08,
  actual_epa_per_dropback: 0.15,
  performance_above_expectation: 0.07,
  prediction_interval_low: -0.02,
  prediction_interval_high: 0.18,
  eligibility_status: "eligible",
  reliability: "high",
  is_out_of_sample: true,
  payload: { training_end_season: 2024 },
};

export const assignment: CoachAssignment = {
  load_id: "test-load",
  assignment_key: "den-2025-hc",
  coach_id: "coach-1",
  canonical_name: "Test Coach",
  team_id: "team_den",
  team_abbr: "DEN",
  team_name: "Denver Broncos",
  season: 2025,
  role: "head_coach",
  start_week: 1,
  end_week: 18,
  interval_basis: "observed_game_weeks",
  verification_status: "verified",
  confidence_level: "high",
  is_interim: false,
  is_shared: false,
  is_retained: true,
  notes: "Test-only fixture",
  payload: {},
};

export const coachImpact: CoachImpact = {
  load_id: "test-load",
  coach_id: "coach-1",
  canonical_name: "Test Coach",
  role: "head_coach",
  data_version: "c6-test",
  model_version: "coach-impact-test",
  estimated_effect: 0.01,
  confidence_low: -0.02,
  confidence_high: 0.03,
  bootstrap_replicates: 200,
  bootstrap_attempted_replicates: 200,
  bootstrap_interval_available: true,
  interval_estimand: "conditional_coach_appearance",
  identified_effect: false,
  identification_status: "exploratory_team_environment_confounding",
  rank_eligible: false,
  rank_exclusion_reason: "exploratory_team_environment_confounding",
  ranking_status: "suppressed_exploratory",
  preliminary_rank: null,
  verified_dropbacks: 620,
  qualifying_qb_seasons: 1,
  distinct_quarterbacks: 1,
  payload: {},
};

export const edge: NetworkEdge = {
  load_id: "test-load",
  source_assignment_key: "hou-hc",
  target_assignment_key: "hou-oc",
  source_coach_id: "coach-1",
  target_coach_id: "coach-2",
  team_id: "team_hou",
  season: 2020,
  source_role: "head_coach",
  target_role: "play_caller",
  source_verification_status: "verified",
  target_verification_status: "provisional",
  source_confidence_level: "high",
  target_confidence_level: "medium",
  source_start_week: 1,
  source_end_week: 4,
  target_start_week: 4,
  target_end_week: 17,
  overlap_start_week: 4,
  overlap_end_week: 4,
  source_is_shared: false,
  target_is_shared: true,
  source_is_provisional: false,
  target_is_provisional: true,
};

export const citation: Citation = {
  load_id: "test-load",
  assignment_key: "den-2025-hc",
  source_url: "https://example.com/source",
  source_title: "Test source",
  source_type: "team_source",
  source_accessed_at: "2026-08-30",
  evidence_locator: "page 1",
  evidence_note: "Test evidence",
  coach_id: "coach-1",
  team_id: "team_den",
  season: 2025,
  role: "head_coach",
};

export const qbProfile: QbProfile = {
  player: {
    player_id: "qb-1",
    display_name: "Test Quarterback",
    position: "QB",
    payload: {},
  },
  seasons: [qbSeason],
};

export const coachProfile: CoachProfile = {
  coach: { coach_id: "coach-1", canonical_name: "Test Coach" },
  role_history: [assignment],
};

export function page<T>(items: T[], offset = 0, limit = 200): ApiPage<T> {
  return {
    items: items.slice(offset, offset + limit),
    total: items.length,
    limit,
    offset,
  };
}

export function installApiFixture(
  overrides: Partial<Record<string, unknown>> = {},
) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://app.test");
    const path = url.pathname.replace(/^\/api/, "");
    const offset = Number(url.searchParams.get("offset") ?? 0);
    const limit = Number(url.searchParams.get("limit") ?? 200);
    const responses: Record<string, unknown> = {
      "/versions": versions,
      "/teams": page(teams, offset, limit),
      "/assignments": page([assignment], offset, limit),
      "/qbs": page([qbSeason], offset, limit),
      "/qbs/qb-1": qbProfile,
      "/qbs/qb-1/pae": page([qbPae], offset, limit),
      "/coaches/coach-1": coachProfile,
      "/coach-impact": page([coachImpact], offset, limit),
      "/citations": page([citation], offset, limit),
      "/network/edges": page([edge], offset, limit),
      ...overrides,
    };
    const body = responses[path];
    if (body instanceof Error) {
      return new Response(JSON.stringify({ detail: body.message }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (body === undefined) {
      return new Response(JSON.stringify({ detail: "Not found" }), {
        status: 404,
      });
    }
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
