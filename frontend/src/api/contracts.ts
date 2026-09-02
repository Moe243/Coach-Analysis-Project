export type CoachRole =
  "head_coach" | "offensive_coordinator" | "play_caller" | "quarterbacks_coach";

export type VerificationStatus =
  "unverified" | "provisional" | "verified" | "conflicting";

export interface ApiPage<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Versions {
  load_id: string;
  schema_version: string;
  loader_version: string;
  api_contract_version: string;
  historical_data_version: string;
  expected_data_version: string;
  expected_model_version: string;
  coach_data_version: string;
  coach_model_version: string;
  enhancement_data_version: string;
}

export type Payload = Record<string, unknown>;

export interface QbSeason {
  load_id: string;
  player_id: string;
  display_name: string;
  position: "QB";
  team_id: string;
  season: number;
  scope: "analysis";
  games: number;
  starts: number | null;
  dropbacks: number;
  epa_per_dropback: number | null;
  cpoe: number | null;
  success_rate: number | null;
  sack_rate: number | null;
  qualifies_default: boolean;
  metric_version: string;
  payload: Payload;
  supplemental_metric_version?: string | null;
  starter_wins?: number | null;
  starter_losses?: number | null;
  starter_ties?: number | null;
  starter_decisions?: number | null;
  team_points_scored?: number | null;
  completion_percentage?: number | null;
  completions?: number | null;
  attempts?: number | null;
  passing_yards?: number | null;
  interceptions?: number | null;
  sacks?: number | null;
  yards_per_attempt?: number | null;
  adjusted_net_yards_per_attempt?: number | null;
  passing_touchdown_rate?: number | null;
  interception_rate?: number | null;
  rushing_yards?: number | null;
  total_yards?: number | null;
  passing_touchdowns?: number | null;
  rushing_touchdowns?: number | null;
  total_touchdowns?: number | null;
  fumbles?: number | null;
  fumbles_lost?: number | null;
  expected_epa_per_dropback?: number | null;
  actual_epa_per_dropback?: number | null;
  performance_above_expectation?: number | null;
  pae_eligibility_status?: string | null;
  pae_reliability?: string | null;
  pae_model_version?: string | null;
  team_metric_version?: string | null;
  team_games?: number | null;
  team_wins?: number | null;
  team_losses?: number | null;
  team_ties?: number | null;
  team_win_percentage?: number | null;
  team_points_allowed?: number | null;
  team_points_per_game?: number | null;
  team_total_offensive_yards?: number | null;
  team_passing_yards?: number | null;
  team_rushing_yards?: number | null;
  team_offensive_touchdowns?: number | null;
  team_turnovers?: number | null;
  team_sacks_allowed?: number | null;
  team_offensive_epa_per_play?: number | null;
  team_passing_epa_per_dropback?: number | null;
  team_offensive_success_rate?: number | null;
  team_points_per_game_rank?: number | null;
  team_offensive_epa_per_play_rank?: number | null;
  team_passing_epa_per_dropback_rank?: number | null;
  supplemental_payload?: Payload | null;
}

export interface TeamSeasonStatistics {
  load_id: string;
  team_id: string;
  team_abbr: string;
  team_name: string;
  season: number;
  team_metric_version: string;
  team_games: number;
  team_wins: number;
  team_losses: number;
  team_ties: number;
  team_win_percentage: number;
  team_points_scored: number;
  team_points_allowed: number;
  team_points_per_game: number;
  team_total_offensive_yards: number | null;
  team_passing_yards: number | null;
  team_rushing_yards: number | null;
  team_offensive_touchdowns: number | null;
  team_turnovers: number | null;
  team_sacks_allowed: number | null;
  team_offensive_epa_per_play: number | null;
  team_passing_epa_per_dropback: number | null;
  team_offensive_success_rate: number | null;
  team_points_per_game_rank: number | null;
  team_offensive_epa_per_play_rank: number | null;
  team_passing_epa_per_dropback_rank: number | null;
  payload: Payload;
}

export interface QbPae {
  load_id: string;
  player_id: string;
  display_name: string;
  team_id: string;
  season: number;
  data_version: string;
  model_version: string;
  expected_epa_per_dropback: number;
  actual_epa_per_dropback: number;
  performance_above_expectation: number;
  prediction_interval_low: number | null;
  prediction_interval_high: number | null;
  eligibility_status: string;
  reliability: string;
  is_out_of_sample: boolean;
  payload: Payload;
}

export interface Team {
  load_id: string;
  team_id: string;
  team_abbr: string;
  team_name: string;
  payload: Payload;
}

export interface CoachAssignment {
  load_id: string;
  assignment_key: string;
  coach_id: string;
  canonical_name: string;
  team_id: string;
  team_abbr: string;
  team_name: string;
  season: number;
  role: CoachRole;
  start_week: number;
  end_week: number;
  interval_basis: string;
  verification_status: VerificationStatus;
  confidence_level: "high" | "medium" | "low";
  is_interim: boolean;
  is_shared: boolean;
  is_retained: boolean;
  notes: string | null;
  payload: Payload;
}

export interface CoachSummary {
  load_id: string;
  coach_id: string;
  canonical_name: string;
  role: CoachRole;
}

export interface CoachImpact {
  load_id: string;
  coach_id: string;
  canonical_name: string;
  role: CoachRole;
  data_version: string;
  model_version: string;
  estimated_effect: number | null;
  confidence_low: number | null;
  confidence_high: number | null;
  bootstrap_replicates: number;
  bootstrap_attempted_replicates: number;
  bootstrap_interval_available: boolean;
  interval_estimand: string;
  identified_effect: boolean;
  identification_status: string;
  rank_eligible: boolean;
  rank_exclusion_reason: string | null;
  ranking_status: string;
  preliminary_rank: number | null;
  verified_dropbacks: number;
  qualifying_qb_seasons: number;
  distinct_quarterbacks: number;
  payload: Payload;
}

export interface NetworkEdge {
  load_id: string;
  source_assignment_key: string;
  target_assignment_key: string;
  source_coach_id: string;
  target_coach_id: string;
  team_id: string;
  season: number;
  source_role: CoachRole;
  target_role: CoachRole;
  source_verification_status: VerificationStatus;
  target_verification_status: VerificationStatus;
  source_confidence_level: string;
  target_confidence_level: string;
  source_start_week: number;
  source_end_week: number;
  target_start_week: number;
  target_end_week: number;
  overlap_start_week: number;
  overlap_end_week: number;
  source_is_shared: boolean;
  target_is_shared: boolean;
  source_is_provisional: boolean;
  target_is_provisional: boolean;
}

export interface Citation {
  load_id: string;
  assignment_key: string;
  source_url: string;
  source_title: string | null;
  source_type: string | null;
  source_accessed_at: string;
  evidence_locator: string | null;
  evidence_note: string | null;
  coach_id: string;
  team_id: string;
  season: number;
  role: CoachRole;
}

export interface QbProfile {
  player: {
    player_id: string;
    display_name: string;
    position: string;
    payload: Payload;
  };
  seasons: QbSeason[];
}

export interface CoachProfile {
  coach: { coach_id: string; canonical_name: string };
  role_history: CoachAssignment[];
}

export type RelationshipMode =
  "coach_journey" | "qb_journey" | "team_history" | "full_network";

export interface RelationshipCitation {
  source_url: string;
  source_title: string | null;
  source_type: string | null;
  source_accessed_at: string;
  evidence_locator: string | null;
  evidence_note: string | null;
}

export interface CoachRelationshipNode {
  node_id: string;
  node_type: "coach";
  coach_id: string;
  canonical_name: string;
}

export interface QuarterbackRelationshipNode {
  node_id: string;
  node_type: "quarterback";
  player_id: string;
  display_name: string;
}

export interface TeamSeasonRelationshipNode {
  node_id: string;
  node_type: "team_season";
  team_id: string;
  team_abbr: string;
  team_name: string;
  season: number;
}

export type RelationshipNode =
  | CoachRelationshipNode
  | QuarterbackRelationshipNode
  | TeamSeasonRelationshipNode;

export interface CoachAssignmentRelationship {
  relationship_id: string;
  relationship_type: "coach_assignment";
  source_node_id: string;
  target_node_id: string;
  assignment_key: string;
  coach_id: string;
  team_id: string;
  season: number;
  role: CoachRole;
  start_week: number;
  end_week: number;
  interval_basis: string;
  verification_status: VerificationStatus;
  confidence_level: "high" | "medium" | "low";
  is_shared: boolean;
  is_interim: boolean;
  is_retained: boolean;
  is_provisional: boolean;
  citations: RelationshipCitation[];
  publication_version: string;
}

export interface QbTeamSeasonRelationship {
  relationship_id: string;
  relationship_type: "qb_team_season";
  source_node_id: string;
  target_node_id: string;
  player_id: string;
  team_id: string;
  season: number;
  dropbacks: number;
  actual_epa_per_dropback: number | null;
  expected_epa_per_dropback: number | null;
  performance_above_expectation: number | null;
  qualifies_default: boolean;
  eligibility_status: string | null;
  reliability: string | null;
  is_out_of_sample: boolean | null;
  metric_version: string;
  model_version: string | null;
  historical_data_version: string;
  expected_data_version: string | null;
  publication_version: string;
}

export type Relationship =
  CoachAssignmentRelationship | QbTeamSeasonRelationship;

export interface RelationshipExplorerResponse {
  query: {
    mode: RelationshipMode;
    coach_id: string | null;
    player_id: string | null;
    team_id: string | null;
    start_season: number;
    end_season: number;
    role: CoachRole | null;
    verification_status: VerificationStatus | null;
    include_provisional: boolean;
  };
  versions: Versions;
  semantics: {
    coach_assignment: string;
    qb_team_season: string;
    coach_qb_context: string;
    exact_weekly_overlap: false;
  };
  nodes: RelationshipNode[];
  relationships: Relationship[];
  node_count: number;
  relationship_count: number;
  max_nodes: number;
  max_relationships: number;
}
