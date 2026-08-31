-- NFL Coaching Impact Engine
-- PostgreSQL contract evolved through checkpoint five. Alembic begins with the application phase.

BEGIN;

CREATE TYPE coach_role AS ENUM (
    'head_coach',
    'offensive_coordinator',
    'play_caller',
    'quarterbacks_coach'
);

CREATE TYPE verification_status AS ENUM (
    'unverified',
    'provisional',
    'verified',
    'conflicting'
);

CREATE TYPE assignment_confidence AS ENUM ('low', 'medium', 'high');

CREATE TYPE assignment_interval_basis AS ENUM (
    'observed_game_weeks',
    'season_designation',
    'dated_source_weeks'
);

CREATE TYPE model_kind AS ENUM (
    'expected_performance',
    'coach_role',
    'coach_joint_sensitivity'
);

CREATE TYPE feature_timing AS ENUM (
    'preseason',
    'retrospective'
);

CREATE TABLE teams (
    team_id text PRIMARY KEY,
    display_name text NOT NULL,
    franchise_name text NOT NULL,
    first_season smallint,
    last_season smallint,
    CHECK (first_season IS NULL OR first_season >= 1920),
    CHECK (last_season IS NULL OR first_season IS NULL OR last_season >= first_season)
);

CREATE TABLE team_aliases (
    team_alias_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    team_id text NOT NULL REFERENCES teams(team_id),
    source_system text NOT NULL,
    alias text NOT NULL,
    valid_from date NOT NULL,
    valid_to date,
    UNIQUE (source_system, alias, valid_from),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE FUNCTION reject_overlapping_team_alias() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM team_aliases a
        WHERE a.source_system = NEW.source_system AND a.alias = NEW.alias
          AND a.team_alias_id <> COALESCE(NEW.team_alias_id, 0)
          AND daterange(a.valid_from, COALESCE(a.valid_to, 'infinity'::date), '[]')
              && daterange(NEW.valid_from, COALESCE(NEW.valid_to, 'infinity'::date), '[]')
    ) THEN RAISE EXCEPTION 'overlapping team alias interval'; END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER team_alias_date_ranges_do_not_overlap
BEFORE INSERT OR UPDATE ON team_aliases FOR EACH ROW EXECUTE FUNCTION reject_overlapping_team_alias();

CREATE INDEX team_alias_lookup_idx ON team_aliases (source_system, alias, valid_from, valid_to);

CREATE TABLE players (
    player_id text PRIMARY KEY,
    display_name text NOT NULL,
    birth_date date,
    position text,
    college text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE player_external_ids (
    player_id text NOT NULL REFERENCES players(player_id),
    external_system text NOT NULL,
    external_id text NOT NULL,
    PRIMARY KEY (external_system, external_id),
    UNIQUE (player_id, external_system)
);

CREATE TABLE coaches (
    coach_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    canonical_name text NOT NULL,
    normalized_name text NOT NULL,
    birth_date date,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (normalized_name, birth_date)
);

CREATE TABLE coach_aliases (
    coach_alias_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    coach_id bigint NOT NULL REFERENCES coaches(coach_id),
    alias text NOT NULL,
    source_system text NOT NULL,
    UNIQUE (coach_id, alias, source_system)
);

CREATE TABLE data_sources (
    data_source_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name text NOT NULL UNIQUE,
    base_url text NOT NULL,
    collection_method text NOT NULL,
    seasons_covered text,
    usage_concerns text,
    known_limitations text,
    last_reviewed_at date NOT NULL
);

CREATE TABLE ingestion_runs (
    ingestion_run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    data_version text NOT NULL UNIQUE,
    code_version text NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text,
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE TABLE source_assets (
    source_asset_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    data_source_id bigint NOT NULL REFERENCES data_sources(data_source_id),
    ingestion_run_id bigint REFERENCES ingestion_runs(ingestion_run_id),
    asset_url text NOT NULL,
    retrieved_at timestamptz NOT NULL,
    season smallint,
    sha256 text,
    byte_size bigint,
    row_count bigint,
    observed_schema jsonb,
    UNIQUE (asset_url, retrieved_at),
    CHECK (season IS NULL OR season BETWEEN 1920 AND 2100),
    CHECK (byte_size IS NULL OR byte_size >= 0),
    CHECK (row_count IS NULL OR row_count >= 0)
);

CREATE TABLE coach_assignments (
    assignment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    coach_id bigint NOT NULL REFERENCES coaches(coach_id),
    team_id text NOT NULL REFERENCES teams(team_id),
    season smallint NOT NULL CHECK (season BETWEEN 1920 AND 2100),
    role coach_role NOT NULL,
    start_week smallint NOT NULL DEFAULT 1 CHECK (start_week BETWEEN 1 AND 25),
    end_week smallint NOT NULL CHECK (end_week BETWEEN 1 AND 25),
    start_date date,
    end_date date,
    is_interim boolean NOT NULL DEFAULT false,
    is_shared boolean NOT NULL DEFAULT false,
    is_retained boolean,
    verification_status verification_status NOT NULL DEFAULT 'unverified',
    confidence_level assignment_confidence NOT NULL DEFAULT 'low',
    interval_basis assignment_interval_basis NOT NULL DEFAULT 'season_designation',
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (coach_id, team_id, season, role, start_week, end_week),
    CHECK (end_week >= start_week),
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);

CREATE FUNCTION reject_invalid_coach_assignment_overlap() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM coach_assignments a
        WHERE a.team_id = NEW.team_id AND a.season = NEW.season AND a.role = NEW.role
          AND a.assignment_id <> COALESCE(NEW.assignment_id, 0)
          AND int4range(a.start_week, a.end_week, '[]')
              && int4range(NEW.start_week, NEW.end_week, '[]')
          AND (NOT a.is_shared OR NOT NEW.is_shared)
    ) THEN RAISE EXCEPTION 'invalid overlapping coach assignment'; END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER coach_assignment_nonshared_overlap
BEFORE INSERT OR UPDATE ON coach_assignments
FOR EACH ROW EXECUTE FUNCTION reject_invalid_coach_assignment_overlap();

CREATE TABLE coach_assignment_sources (
    assignment_source_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    assignment_id bigint NOT NULL REFERENCES coach_assignments(assignment_id) ON DELETE CASCADE,
    data_source_id bigint REFERENCES data_sources(data_source_id),
    source_url text NOT NULL,
    source_title text,
    accessed_at date NOT NULL,
    evidence_note text,
    UNIQUE (assignment_id, source_url)
);

CREATE OR REPLACE FUNCTION enforce_verified_assignment_has_source()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    target_assignment_id bigint;
    target_assignment_ids bigint[];
    target_status verification_status;
BEGIN
    IF TG_TABLE_NAME = 'coach_assignments' THEN
        target_assignment_ids := ARRAY[NEW.assignment_id];
    ELSIF TG_OP = 'DELETE' THEN
        target_assignment_ids := ARRAY[OLD.assignment_id];
    ELSIF TG_OP = 'UPDATE' THEN
        target_assignment_ids := ARRAY[OLD.assignment_id, NEW.assignment_id];
    ELSE
        target_assignment_ids := ARRAY[NEW.assignment_id];
    END IF;

    FOREACH target_assignment_id IN ARRAY target_assignment_ids LOOP
        SELECT verification_status
          INTO target_status
          FROM coach_assignments
         WHERE assignment_id = target_assignment_id;

        IF target_status = 'verified'
           AND NOT EXISTS (
               SELECT 1
                 FROM coach_assignment_sources
                WHERE assignment_id = target_assignment_id
           ) THEN
            RAISE EXCEPTION 'verified assignment % must have at least one source', target_assignment_id;
        END IF;
    END LOOP;
    RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE CONSTRAINT TRIGGER verified_assignment_requires_source
AFTER INSERT OR UPDATE OF verification_status ON coach_assignments
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION enforce_verified_assignment_has_source();

CREATE CONSTRAINT TRIGGER verified_assignment_source_delete_guard
AFTER DELETE OR UPDATE OF assignment_id ON coach_assignment_sources
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION enforce_verified_assignment_has_source();

CREATE TABLE coaching_environments (
    environment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    team_id text NOT NULL REFERENCES teams(team_id),
    season smallint NOT NULL CHECK (season BETWEEN 1920 AND 2100),
    start_week smallint NOT NULL CHECK (start_week BETWEEN 1 AND 25),
    end_week smallint NOT NULL CHECK (end_week BETWEEN 1 AND 25),
    start_date date,
    end_date date,
    environment_key text NOT NULL UNIQUE,
    CHECK (end_week >= start_week),
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date),
    UNIQUE (team_id, season, start_week, end_week)
);

CREATE TABLE coaching_environment_members (
    environment_id bigint NOT NULL REFERENCES coaching_environments(environment_id) ON DELETE CASCADE,
    role coach_role NOT NULL,
    coach_id bigint NOT NULL REFERENCES coaches(coach_id),
    assignment_id bigint NOT NULL REFERENCES coach_assignments(assignment_id),
    is_shared boolean NOT NULL DEFAULT false,
    PRIMARY KEY (environment_id, role, coach_id)
);

CREATE OR REPLACE FUNCTION enforce_environment_member_lineage()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    invalid_member record;
BEGIN
    IF TG_TABLE_NAME = 'coaching_environment_members' THEN
        SELECT m.environment_id, m.assignment_id
          INTO invalid_member
          FROM coaching_environment_members m
          JOIN coaching_environments e ON e.environment_id = m.environment_id
          JOIN coach_assignments a ON a.assignment_id = m.assignment_id
         WHERE m.environment_id = NEW.environment_id
           AND m.role = NEW.role
           AND m.coach_id = NEW.coach_id
           AND (
               a.team_id <> e.team_id
               OR a.season <> e.season
               OR a.role <> m.role
               OR a.coach_id <> m.coach_id
               OR a.start_week > e.start_week
               OR a.end_week < e.end_week
               OR a.is_shared <> m.is_shared
           )
         LIMIT 1;
    ELSIF TG_TABLE_NAME = 'coach_assignments' THEN
        SELECT m.environment_id, m.assignment_id
          INTO invalid_member
          FROM coaching_environment_members m
          JOIN coaching_environments e ON e.environment_id = m.environment_id
         WHERE m.assignment_id = NEW.assignment_id
           AND (
               NEW.team_id <> e.team_id
               OR NEW.season <> e.season
               OR NEW.role <> m.role
               OR NEW.coach_id <> m.coach_id
               OR NEW.start_week > e.start_week
               OR NEW.end_week < e.end_week
               OR NEW.is_shared <> m.is_shared
           )
         LIMIT 1;
    ELSE
        SELECT m.environment_id, m.assignment_id
          INTO invalid_member
          FROM coaching_environment_members m
          JOIN coach_assignments a ON a.assignment_id = m.assignment_id
         WHERE m.environment_id = NEW.environment_id
           AND (
               a.team_id <> NEW.team_id
               OR a.season <> NEW.season
               OR a.role <> m.role
               OR a.coach_id <> m.coach_id
               OR a.start_week > NEW.start_week
               OR a.end_week < NEW.end_week
               OR a.is_shared <> m.is_shared
           )
         LIMIT 1;
    END IF;

    IF FOUND THEN
        RAISE EXCEPTION
            'coaching environment member % must match assignment % lineage',
            invalid_member.environment_id,
            invalid_member.assignment_id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE CONSTRAINT TRIGGER environment_member_lineage_guard
AFTER INSERT OR UPDATE ON coaching_environment_members
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION enforce_environment_member_lineage();

CREATE CONSTRAINT TRIGGER assignment_member_lineage_guard
AFTER UPDATE OF coach_id, team_id, season, role, start_week, end_week, is_shared ON coach_assignments
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION enforce_environment_member_lineage();

CREATE CONSTRAINT TRIGGER environment_member_parent_lineage_guard
AFTER UPDATE OF team_id, season, start_week, end_week ON coaching_environments
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION enforce_environment_member_lineage();

CREATE TABLE games (
    game_id text PRIMARY KEY,
    season smallint NOT NULL CHECK (season BETWEEN 1920 AND 2100),
    week smallint NOT NULL CHECK (week BETWEEN 1 AND 25),
    game_type text NOT NULL CHECK (game_type IN ('REG', 'WC', 'DIV', 'CON', 'SB')),
    game_date date NOT NULL,
    home_team_id text NOT NULL REFERENCES teams(team_id),
    away_team_id text NOT NULL REFERENCES teams(team_id),
    home_score smallint,
    away_score smallint,
    playoff_round text,
    CHECK (home_team_id <> away_team_id),
    CHECK (home_score IS NULL OR home_score >= 0),
    CHECK (away_score IS NULL OR away_score >= 0)
);

CREATE INDEX games_season_week_idx ON games (season, week, game_type);

CREATE TABLE qb_game_performance (
    game_id text NOT NULL REFERENCES games(game_id),
    player_id text NOT NULL REFERENCES players(player_id),
    team_id text NOT NULL REFERENCES teams(team_id),
    opponent_team_id text NOT NULL REFERENCES teams(team_id),
    is_start boolean,
    dropbacks integer NOT NULL CHECK (dropbacks >= 0),
    pass_attempts integer NOT NULL CHECK (pass_attempts >= 0),
    completions integer NOT NULL CHECK (completions >= 0),
    passing_tds integer NOT NULL CHECK (passing_tds >= 0),
    interceptions integer NOT NULL CHECK (interceptions >= 0),
    sacks integer NOT NULL CHECK (sacks >= 0),
    explosive_completions integer NOT NULL CHECK (explosive_completions >= 0),
    passing_first_downs integer NOT NULL CHECK (passing_first_downs >= 0),
    passing_air_yards numeric,
    total_qb_epa numeric,
    total_qb_wpa numeric,
    cpoe_sum numeric,
    cpoe_plays integer CHECK (cpoe_plays IS NULL OR cpoe_plays >= 0),
    success_plays integer CHECK (success_plays IS NULL OR success_plays >= 0),
    epa_per_dropback numeric,
    cpoe numeric,
    success_rate numeric CHECK (success_rate IS NULL OR success_rate BETWEEN 0 AND 1),
    explosive_pass_rate numeric CHECK (explosive_pass_rate IS NULL OR explosive_pass_rate BETWEEN 0 AND 1),
    interception_rate numeric CHECK (interception_rate IS NULL OR interception_rate BETWEEN 0 AND 1),
    touchdown_rate numeric CHECK (touchdown_rate IS NULL OR touchdown_rate BETWEEN 0 AND 1),
    sack_rate numeric CHECK (sack_rate IS NULL OR sack_rate BETWEEN 0 AND 1),
    air_yards_per_attempt numeric,
    first_down_rate numeric CHECK (first_down_rate IS NULL OR first_down_rate BETWEEN 0 AND 1),
    wpa_per_dropback numeric,
    metric_version text NOT NULL,
    ingestion_run_id bigint NOT NULL REFERENCES ingestion_runs(ingestion_run_id),
    PRIMARY KEY (game_id, player_id, team_id),
    CHECK (completions <= pass_attempts),
    CHECK (interceptions <= pass_attempts),
    CHECK (passing_tds <= pass_attempts)
);

CREATE TABLE qb_seasons (
    qb_season_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id text NOT NULL REFERENCES players(player_id),
    team_id text NOT NULL REFERENCES teams(team_id),
    season smallint NOT NULL CHECK (season BETWEEN 1920 AND 2100),
    games integer NOT NULL CHECK (games >= 0),
    starts integer CHECK (starts IS NULL OR starts >= 0),
    dropbacks integer NOT NULL CHECK (dropbacks >= 0),
    pass_attempts integer NOT NULL CHECK (pass_attempts >= 0),
    epa_per_dropback numeric,
    cpoe numeric,
    success_rate numeric CHECK (success_rate IS NULL OR success_rate BETWEEN 0 AND 1),
    explosive_pass_rate numeric CHECK (explosive_pass_rate IS NULL OR explosive_pass_rate BETWEEN 0 AND 1),
    interception_rate numeric CHECK (interception_rate IS NULL OR interception_rate BETWEEN 0 AND 1),
    touchdown_rate numeric CHECK (touchdown_rate IS NULL OR touchdown_rate BETWEEN 0 AND 1),
    sack_rate numeric CHECK (sack_rate IS NULL OR sack_rate BETWEEN 0 AND 1),
    air_yards_per_attempt numeric,
    first_down_rate numeric CHECK (first_down_rate IS NULL OR first_down_rate BETWEEN 0 AND 1),
    wpa_per_dropback numeric,
    previous_epa_change numeric,
    qualifies_default boolean NOT NULL,
    metric_version text NOT NULL,
    ingestion_run_id bigint NOT NULL REFERENCES ingestion_runs(ingestion_run_id),
    UNIQUE (player_id, team_id, season)
);

CREATE INDEX qb_seasons_ranking_idx ON qb_seasons (season, qualifies_default, epa_per_dropback DESC);

CREATE TABLE qb_environment_stints (
    qb_stint_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    qb_season_id bigint NOT NULL REFERENCES qb_seasons(qb_season_id) ON DELETE CASCADE,
    environment_id bigint NOT NULL REFERENCES coaching_environments(environment_id),
    start_week smallint NOT NULL CHECK (start_week BETWEEN 1 AND 25),
    end_week smallint NOT NULL CHECK (end_week BETWEEN 1 AND 25),
    starts integer CHECK (starts IS NULL OR starts >= 0),
    dropbacks integer NOT NULL CHECK (dropbacks >= 0),
    epa_per_dropback numeric,
    cpoe numeric,
    success_rate numeric CHECK (success_rate IS NULL OR success_rate BETWEEN 0 AND 1),
    metric_version text NOT NULL,
    UNIQUE (qb_season_id, environment_id),
    CHECK (end_week >= start_week)
);

CREATE OR REPLACE FUNCTION enforce_qb_stint_environment_lineage()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    invalid_stint record;
BEGIN
    IF TG_TABLE_NAME = 'qb_environment_stints' THEN
        SELECT s.qb_stint_id, s.qb_season_id, s.environment_id
          INTO invalid_stint
          FROM qb_environment_stints s
          JOIN qb_seasons qs ON qs.qb_season_id = s.qb_season_id
          JOIN coaching_environments e ON e.environment_id = s.environment_id
         WHERE s.qb_stint_id = NEW.qb_stint_id
           AND (
               qs.team_id <> e.team_id
               OR qs.season <> e.season
               OR s.start_week < e.start_week
               OR s.end_week > e.end_week
           )
         LIMIT 1;
    ELSIF TG_TABLE_NAME = 'qb_seasons' THEN
        SELECT s.qb_stint_id, s.qb_season_id, s.environment_id
          INTO invalid_stint
          FROM qb_environment_stints s
          JOIN coaching_environments e ON e.environment_id = s.environment_id
         WHERE s.qb_season_id = NEW.qb_season_id
           AND (
               NEW.team_id <> e.team_id
               OR NEW.season <> e.season
               OR s.start_week < e.start_week
               OR s.end_week > e.end_week
           )
         LIMIT 1;
    ELSE
        SELECT s.qb_stint_id, s.qb_season_id, s.environment_id
          INTO invalid_stint
          FROM qb_environment_stints s
          JOIN qb_seasons qs ON qs.qb_season_id = s.qb_season_id
         WHERE s.environment_id = NEW.environment_id
           AND (
               qs.team_id <> NEW.team_id
               OR qs.season <> NEW.season
               OR s.start_week < NEW.start_week
               OR s.end_week > NEW.end_week
           )
         LIMIT 1;
    END IF;

    IF FOUND THEN
        RAISE EXCEPTION
            'QB stint % must match QB season % and environment % lineage',
            invalid_stint.qb_stint_id,
            invalid_stint.qb_season_id,
            invalid_stint.environment_id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE CONSTRAINT TRIGGER qb_stint_environment_lineage_guard
AFTER INSERT OR UPDATE ON qb_environment_stints
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION enforce_qb_stint_environment_lineage();

CREATE CONSTRAINT TRIGGER qb_season_stint_lineage_guard
AFTER UPDATE OF team_id, season ON qb_seasons
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION enforce_qb_stint_environment_lineage();

CREATE CONSTRAINT TRIGGER environment_qb_stint_lineage_guard
AFTER UPDATE OF team_id, season, start_week, end_week ON coaching_environments
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION enforce_qb_stint_environment_lineage();

CREATE TABLE team_season_features (
    team_id text NOT NULL REFERENCES teams(team_id),
    season smallint NOT NULL CHECK (season BETWEEN 1920 AND 2100),
    feature_version text NOT NULL,
    timing feature_timing NOT NULL,
    as_of_season smallint,
    protection_proxy numeric,
    receiving_quality numeric,
    rushing_efficiency numeric,
    defensive_efficiency numeric,
    injury_burden numeric,
    schedule_strength numeric,
    offensive_coaching_continuity numeric,
    feature_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    ingestion_run_id bigint NOT NULL REFERENCES ingestion_runs(ingestion_run_id),
    PRIMARY KEY (team_id, season, feature_version, timing),
    CHECK (timing = 'retrospective' OR as_of_season IS NOT NULL),
    CHECK (timing <> 'preseason' OR as_of_season < season)
);

CREATE TABLE qb_preseason_features (
    player_id text NOT NULL REFERENCES players(player_id),
    team_id text NOT NULL REFERENCES teams(team_id),
    season smallint NOT NULL CHECK (season BETWEEN 1920 AND 2100),
    feature_version text NOT NULL,
    as_of_season smallint NOT NULL,
    age numeric,
    nfl_experience integer,
    prior_qb_seasons integer,
    no_prior_qb_performance boolean,
    experience_group text,
    performance_history_group text,
    career_starts integer,
    career_dropbacks integer,
    career_epa_per_dropback numeric,
    previous_dropbacks integer,
    previous_epa_per_dropback numeric,
    previous_cpoe numeric,
    previous_success_rate numeric,
    previous_sack_rate numeric,
    previous_interception_rate numeric,
    previous_touchdown_rate numeric,
    changed_team boolean,
    changed_team_missing boolean,
    preseason_team_id text REFERENCES teams(team_id),
    preseason_team_status text,
    is_rookie boolean,
    prior_injury_report_weeks integer,
    prior_injury_out_weeks integer,
    draft_position integer,
    draft_round integer,
    missing_feature_count integer NOT NULL DEFAULT 0,
    new_coaching_environment boolean,
    feature_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    ingestion_run_id bigint NOT NULL REFERENCES ingestion_runs(ingestion_run_id),
    PRIMARY KEY (player_id, team_id, season, feature_version),
    CHECK (as_of_season < season),
    CHECK (nfl_experience IS NULL OR nfl_experience >= 0),
    CHECK (prior_qb_seasons IS NULL OR prior_qb_seasons >= 0),
    CHECK (
        experience_group IS NULL
        OR experience_group IN ('rookie', 'one_prior_nfl_season', 'veteran', 'experience_unknown')
    ),
    CHECK (
        performance_history_group IS NULL
        OR performance_history_group IN (
            'no_prior_qb_performance',
            'one_prior_qb_season',
            'multiple_prior_qb_seasons'
        )
    ),
    CHECK (
        preseason_team_status IS NULL
        OR preseason_team_status IN (
            'available',
            'unavailable_ambiguous',
            'unavailable_no_week_1_snapshot'
        )
    ),
    CHECK (changed_team_missing IS DISTINCT FROM false OR changed_team IS NOT NULL),
    CHECK (is_rookie IS DISTINCT FROM true OR nfl_experience IN (0)),
    CHECK (
        no_prior_qb_performance IS NULL
        OR (no_prior_qb_performance AND prior_qb_seasons = 0)
        OR (NOT no_prior_qb_performance AND prior_qb_seasons > 0)
    ),
    CHECK (
        preseason_team_status IS DISTINCT FROM 'available'
        OR preseason_team_id IS NOT NULL
    ),
    CHECK (career_starts IS NULL OR career_starts >= 0),
    CHECK (career_dropbacks IS NULL OR career_dropbacks >= 0),
    CHECK (previous_dropbacks IS NULL OR previous_dropbacks >= 0),
    CHECK (previous_success_rate IS NULL OR previous_success_rate BETWEEN 0 AND 1),
    CHECK (previous_sack_rate IS NULL OR previous_sack_rate BETWEEN 0 AND 1),
    CHECK (previous_interception_rate IS NULL OR previous_interception_rate BETWEEN 0 AND 1),
    CHECK (previous_touchdown_rate IS NULL OR previous_touchdown_rate BETWEEN 0 AND 1),
    CHECK (prior_injury_report_weeks IS NULL OR prior_injury_report_weeks >= 0),
    CHECK (prior_injury_out_weeks IS NULL OR prior_injury_out_weeks >= 0),
    CHECK (draft_position IS NULL OR draft_position > 0),
    CHECK (draft_round IS NULL OR draft_round > 0),
    CHECK (missing_feature_count >= 0)
);

CREATE TABLE qb_season_star_teammates (
    qb_season_id bigint NOT NULL REFERENCES qb_seasons(qb_season_id) ON DELETE CASCADE,
    teammate_player_id text NOT NULL REFERENCES players(player_id),
    rule_version text NOT NULL,
    teammate_position text NOT NULL,
    prior_season smallint NOT NULL,
    standardized_value numeric NOT NULL,
    position_percentile numeric NOT NULL CHECK (position_percentile BETWEEN 0 AND 1),
    PRIMARY KEY (qb_season_id, teammate_player_id, rule_version)
);

CREATE TABLE model_runs (
    model_run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_kind model_kind NOT NULL,
    model_name text NOT NULL,
    model_version text NOT NULL,
    data_version text NOT NULL REFERENCES ingestion_runs(data_version),
    feature_version text,
    metric_version text NOT NULL,
    training_end_season smallint NOT NULL,
    evaluation_start_season smallint,
    evaluation_end_season smallint,
    code_version text NOT NULL,
    hyperparameters jsonb NOT NULL DEFAULT '{}'::jsonb,
    evaluation_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    diagnostics jsonb NOT NULL DEFAULT '{}'::jsonb,
    artifact_uri text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (model_kind, model_name, model_version, data_version, training_end_season),
    CHECK (evaluation_end_season IS NULL OR evaluation_start_season IS NULL OR evaluation_end_season >= evaluation_start_season)
);

CREATE TABLE qb_predictions (
    model_run_id bigint NOT NULL REFERENCES model_runs(model_run_id),
    qb_season_id bigint NOT NULL REFERENCES qb_seasons(qb_season_id),
    prediction_as_of_season smallint NOT NULL,
    expected_epa_per_dropback numeric NOT NULL,
    actual_epa_per_dropback numeric,
    performance_above_expectation numeric,
    prediction_std_error numeric CHECK (prediction_std_error IS NULL OR prediction_std_error >= 0),
    prediction_interval_low numeric,
    prediction_interval_high numeric,
    eligibility_status text,
    reliability text CHECK (reliability IS NULL OR reliability IN ('low', 'medium', 'high')),
    is_out_of_sample boolean NOT NULL,
    warning_flags text[] NOT NULL DEFAULT '{}',
    PRIMARY KEY (model_run_id, qb_season_id),
    CHECK (
        prediction_interval_high IS NULL
        OR prediction_interval_low IS NULL
        OR prediction_interval_high >= prediction_interval_low
    ),
    CHECK (
        performance_above_expectation IS NULL
        OR actual_epa_per_dropback IS NULL
        OR performance_above_expectation =
            actual_epa_per_dropback - expected_epa_per_dropback
    )
);

CREATE TABLE coach_effect_estimates (
    model_run_id bigint NOT NULL REFERENCES model_runs(model_run_id),
    coach_id bigint NOT NULL REFERENCES coaches(coach_id),
    role coach_role NOT NULL,
    adjusted_impact numeric NOT NULL,
    confidence_low numeric,
    confidence_high numeric,
    qualifying_qb_seasons integer NOT NULL CHECK (qualifying_qb_seasons >= 0),
    distinct_quarterbacks integer NOT NULL CHECK (distinct_quarterbacks >= 0),
    total_dropbacks integer NOT NULL CHECK (total_dropbacks >= 0),
    average_qb_pae numeric,
    average_offensive_performance numeric,
    continuity_rate numeric CHECK (continuity_rate IS NULL OR continuity_rate BETWEEN 0 AND 1),
    is_rank_eligible boolean NOT NULL,
    warning_flags text[] NOT NULL DEFAULT '{}',
    PRIMARY KEY (model_run_id, coach_id, role),
    CHECK (confidence_high IS NULL OR confidence_low IS NULL OR confidence_high >= confidence_low)
);

-- PostgreSQL CHECK constraints cannot contain subqueries, so timing is enforced with a trigger.
CREATE OR REPLACE FUNCTION enforce_prediction_precedes_season()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    target_season smallint;
BEGIN
    SELECT season INTO target_season FROM qb_seasons WHERE qb_season_id = NEW.qb_season_id;
    IF NEW.prediction_as_of_season >= target_season THEN
        RAISE EXCEPTION 'prediction as-of season % must precede target season %', NEW.prediction_as_of_season, target_season;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER qb_prediction_timing_guard
BEFORE INSERT OR UPDATE ON qb_predictions
FOR EACH ROW
EXECUTE FUNCTION enforce_prediction_precedes_season();

CREATE VIEW v_qb_rankings AS
WITH ranking_base AS (
    SELECT
        qs.qb_season_id,
        qs.player_id,
        p.display_name AS quarterback,
        qs.season,
        qs.team_id,
        qs.starts,
        qs.dropbacks,
        qp.expected_epa_per_dropback,
        qs.epa_per_dropback AS actual_epa_per_dropback,
        qp.performance_above_expectation,
        qs.cpoe,
        qs.success_rate,
        qs.sack_rate,
        qs.interception_rate,
        qs.explosive_pass_rate,
        qs.previous_epa_change,
        qs.qualifies_default,
        qp.is_out_of_sample,
        qp.model_run_id,
        qp.warning_flags
    FROM qb_seasons qs
    JOIN players p ON p.player_id = qs.player_id
    LEFT JOIN qb_predictions qp ON qp.qb_season_id = qs.qb_season_id
), eligible_ranks AS (
    SELECT
        qb_season_id,
        model_run_id,
        dense_rank() OVER (
            PARTITION BY season, model_run_id
            ORDER BY performance_above_expectation DESC NULLS LAST
        ) AS default_rank
    FROM ranking_base
    WHERE qualifies_default AND is_out_of_sample
)
SELECT
    rb.qb_season_id,
    rb.player_id,
    rb.quarterback,
    rb.season,
    rb.team_id,
    rb.starts,
    rb.dropbacks,
    rb.expected_epa_per_dropback,
    rb.actual_epa_per_dropback,
    rb.performance_above_expectation,
    rb.cpoe,
    rb.success_rate,
    rb.sack_rate,
    rb.interception_rate,
    rb.explosive_pass_rate,
    rb.previous_epa_change,
    rb.qualifies_default,
    er.default_rank,
    rb.model_run_id,
    rb.warning_flags
FROM ranking_base rb
LEFT JOIN eligible_ranks er
  ON er.qb_season_id = rb.qb_season_id
 AND er.model_run_id = rb.model_run_id;

CREATE VIEW v_coach_rankings AS
WITH eligible_ranks AS (
    SELECT
        model_run_id,
        coach_id,
        role,
        dense_rank() OVER (
            PARTITION BY model_run_id, role
            ORDER BY adjusted_impact DESC
        ) AS default_rank
    FROM coach_effect_estimates
    WHERE is_rank_eligible
)
SELECT
    ce.model_run_id,
    ce.coach_id,
    c.canonical_name AS coach,
    ce.role,
    ce.adjusted_impact,
    ce.confidence_low,
    ce.confidence_high,
    ce.qualifying_qb_seasons,
    ce.distinct_quarterbacks,
    ce.total_dropbacks,
    ce.average_qb_pae,
    ce.average_offensive_performance,
    ce.continuity_rate,
    ce.is_rank_eligible,
    er.default_rank,
    ce.warning_flags
FROM coach_effect_estimates ce
JOIN coaches c ON c.coach_id = ce.coach_id
LEFT JOIN eligible_ranks er
  ON er.model_run_id = ce.model_run_id
 AND er.coach_id = ce.coach_id
 AND er.role = ce.role;

CREATE VIEW v_team_seasons AS
WITH team_games AS (
    SELECT
        season,
        game_type,
        home_team_id AS team_id,
        home_score AS points_for,
        away_score AS points_against
    FROM games
    UNION ALL
    SELECT
        season,
        game_type,
        away_team_id AS team_id,
        away_score AS points_for,
        home_score AS points_against
    FROM games
)
SELECT
    season,
    team_id,
    count(*) FILTER (WHERE game_type = 'REG') AS regular_season_games,
    count(*) FILTER (WHERE game_type = 'REG' AND points_for > points_against) AS wins,
    count(*) FILTER (WHERE game_type = 'REG' AND points_for < points_against) AS losses,
    count(*) FILTER (WHERE game_type = 'REG' AND points_for = points_against) AS ties,
    sum(points_for) FILTER (WHERE game_type = 'REG') AS points_for,
    sum(points_against) FILTER (WHERE game_type = 'REG') AS points_against,
    count(*) FILTER (WHERE game_type <> 'REG') AS playoff_games,
    count(*) FILTER (WHERE game_type <> 'REG' AND points_for > points_against) AS playoff_wins
FROM team_games
GROUP BY season, team_id;

COMMENT ON VIEW v_team_seasons IS
'Checkpoint-one serving contract for regular-season records and playoff context.';

COMMIT;

-- Checkpoint seven serving layer. These tables preserve immutable analytical
-- versions while `serving_publication` atomically selects the API-visible load.
BEGIN;

CREATE TABLE serving_loads (
    load_id uuid PRIMARY KEY,
    schema_version text NOT NULL,
    loader_version text NOT NULL,
    api_contract_version text NOT NULL,
    historical_data_version text NOT NULL,
    expected_data_version text NOT NULL,
    expected_model_version text NOT NULL,
    coach_data_version text NOT NULL,
    coach_model_version text NOT NULL,
    manifest_sha256 text NOT NULL,
    manual_manifest_sha256 text NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (
        schema_version, loader_version, api_contract_version,
        historical_data_version, expected_data_version, expected_model_version,
        coach_data_version, coach_model_version, manifest_sha256, manual_manifest_sha256
    )
);

CREATE TABLE serving_publication (
    publication_id smallint PRIMARY KEY DEFAULT 1 CHECK (publication_id = 1),
    load_id uuid NOT NULL REFERENCES serving_loads(load_id),
    published_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE serving_teams (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    team_id text NOT NULL,
    team_abbr text NOT NULL,
    team_name text NOT NULL,
    nflverse_team_id text,
    payload jsonb NOT NULL,
    PRIMARY KEY (load_id, team_id)
);

CREATE TABLE serving_team_aliases (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    source_system text NOT NULL,
    alias text NOT NULL,
    team_id text NOT NULL,
    first_observed_season smallint,
    last_observed_season smallint,
    payload jsonb NOT NULL,
    PRIMARY KEY (load_id, source_system, alias),
    FOREIGN KEY (load_id, team_id) REFERENCES serving_teams(load_id, team_id),
    CHECK (last_observed_season IS NULL OR first_observed_season IS NULL
           OR last_observed_season >= first_observed_season)
);

CREATE TABLE serving_players (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    player_id text NOT NULL,
    display_name text NOT NULL,
    position text,
    payload jsonb NOT NULL,
    PRIMARY KEY (load_id, player_id)
);

CREATE TABLE serving_player_external_ids (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    player_id text NOT NULL,
    external_system text NOT NULL,
    external_id text NOT NULL,
    PRIMARY KEY (load_id, external_system, external_id),
    FOREIGN KEY (load_id, player_id) REFERENCES serving_players(load_id, player_id)
);

CREATE TABLE serving_games (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    game_id text NOT NULL,
    season smallint NOT NULL,
    week smallint NOT NULL,
    game_type text NOT NULL,
    game_date date NOT NULL,
    home_team_id text NOT NULL,
    away_team_id text NOT NULL,
    scope text NOT NULL CHECK (scope IN ('warmup', 'analysis')),
    payload jsonb NOT NULL,
    PRIMARY KEY (load_id, game_id),
    FOREIGN KEY (load_id, home_team_id) REFERENCES serving_teams(load_id, team_id),
    FOREIGN KEY (load_id, away_team_id) REFERENCES serving_teams(load_id, team_id),
    CHECK (season BETWEEN 1999 AND 2100),
    CHECK (week BETWEEN 1 AND 25),
    CHECK (home_team_id <> away_team_id)
);

CREATE TABLE serving_qb_games (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    game_id text NOT NULL,
    player_id text NOT NULL,
    team_id text NOT NULL,
    season smallint NOT NULL,
    week smallint NOT NULL,
    dropbacks integer NOT NULL CHECK (dropbacks >= 0),
    epa_per_dropback double precision,
    starter boolean,
    payload jsonb NOT NULL,
    PRIMARY KEY (load_id, game_id, player_id, team_id),
    FOREIGN KEY (load_id, game_id) REFERENCES serving_games(load_id, game_id),
    FOREIGN KEY (load_id, player_id) REFERENCES serving_players(load_id, player_id),
    FOREIGN KEY (load_id, team_id) REFERENCES serving_teams(load_id, team_id)
);

CREATE TABLE serving_qb_seasons (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    player_id text NOT NULL,
    team_id text NOT NULL,
    season smallint NOT NULL,
    scope text NOT NULL CHECK (scope IN ('warmup', 'analysis')),
    games integer NOT NULL CHECK (games >= 0),
    starts integer,
    dropbacks integer NOT NULL CHECK (dropbacks >= 0),
    epa_per_dropback double precision,
    cpoe double precision,
    success_rate double precision,
    sack_rate double precision,
    qualifies_default boolean NOT NULL,
    metric_version text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (load_id, player_id, team_id, season),
    FOREIGN KEY (load_id, player_id) REFERENCES serving_players(load_id, player_id),
    FOREIGN KEY (load_id, team_id) REFERENCES serving_teams(load_id, team_id)
);

CREATE TABLE serving_qb_pae (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    player_id text NOT NULL,
    team_id text NOT NULL,
    season smallint NOT NULL,
    data_version text NOT NULL,
    model_version text NOT NULL,
    expected_epa_per_dropback double precision NOT NULL,
    actual_epa_per_dropback double precision NOT NULL,
    performance_above_expectation double precision NOT NULL,
    prediction_interval_low double precision,
    prediction_interval_high double precision,
    eligibility_status text NOT NULL,
    reliability text NOT NULL,
    is_out_of_sample boolean NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (load_id, player_id, team_id, season),
    FOREIGN KEY (load_id, player_id, team_id, season)
        REFERENCES serving_qb_seasons(load_id, player_id, team_id, season),
    CHECK (performance_above_expectation = actual_epa_per_dropback - expected_epa_per_dropback),
    CHECK (prediction_interval_high IS NULL OR prediction_interval_low IS NULL
           OR prediction_interval_high >= prediction_interval_low)
);

CREATE TABLE serving_coaches (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    coach_id text NOT NULL,
    canonical_name text NOT NULL,
    normalized_name text NOT NULL,
    PRIMARY KEY (load_id, coach_id),
    UNIQUE (load_id, normalized_name)
);

CREATE TABLE serving_coach_assignments (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    assignment_key text NOT NULL,
    coach_id text NOT NULL,
    team_id text NOT NULL,
    season smallint NOT NULL,
    role coach_role NOT NULL,
    start_week smallint NOT NULL,
    end_week smallint NOT NULL,
    interval_basis assignment_interval_basis NOT NULL,
    verification_status verification_status NOT NULL,
    confidence_level assignment_confidence NOT NULL,
    is_interim boolean NOT NULL,
    is_shared boolean NOT NULL,
    is_retained boolean NOT NULL,
    notes text,
    payload jsonb NOT NULL,
    PRIMARY KEY (load_id, assignment_key),
    FOREIGN KEY (load_id, coach_id) REFERENCES serving_coaches(load_id, coach_id),
    FOREIGN KEY (load_id, team_id) REFERENCES serving_teams(load_id, team_id),
    CHECK (start_week BETWEEN 1 AND 25 AND end_week BETWEEN start_week AND 25)
);

CREATE FUNCTION reject_invalid_serving_assignment_overlap() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM serving_coach_assignments a
        WHERE a.load_id = NEW.load_id AND a.team_id = NEW.team_id
          AND a.season = NEW.season AND a.role = NEW.role
          AND a.assignment_key <> NEW.assignment_key
          AND int4range(a.start_week, a.end_week, '[]')
              && int4range(NEW.start_week, NEW.end_week, '[]')
          AND (NOT a.is_shared OR NOT NEW.is_shared)
    ) THEN RAISE EXCEPTION 'invalid overlapping serving coach assignment'; END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER serving_assignment_nonshared_overlap
BEFORE INSERT OR UPDATE ON serving_coach_assignments
FOR EACH ROW EXECUTE FUNCTION reject_invalid_serving_assignment_overlap();

CREATE TABLE serving_coach_citations (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    assignment_key text NOT NULL,
    source_url text NOT NULL,
    source_title text,
    source_type text,
    source_accessed_at date NOT NULL,
    evidence_locator text,
    evidence_note text,
    PRIMARY KEY (load_id, assignment_key, source_url),
    FOREIGN KEY (load_id, assignment_key)
        REFERENCES serving_coach_assignments(load_id, assignment_key) ON DELETE CASCADE,
    CHECK (source_url LIKE 'https://%')
);

CREATE FUNCTION enforce_serving_verified_assignment_source()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_key text; target_load uuid; target_status verification_status;
        keys text[]; loads uuid[]; position integer;
BEGIN
    IF TG_TABLE_NAME = 'serving_coach_assignments' THEN
        keys := ARRAY[NEW.assignment_key]; loads := ARRAY[NEW.load_id];
    ELSIF TG_OP = 'UPDATE' THEN
        keys := ARRAY[OLD.assignment_key, NEW.assignment_key];
        loads := ARRAY[OLD.load_id, NEW.load_id];
    ELSE
        keys := ARRAY[OLD.assignment_key]; loads := ARRAY[OLD.load_id];
    END IF;
    FOR position IN 1..array_length(keys, 1) LOOP
        target_key := keys[position]; target_load := loads[position];
        SELECT verification_status INTO target_status
          FROM serving_coach_assignments
         WHERE load_id = target_load AND assignment_key = target_key;
        IF target_status = 'verified' AND NOT EXISTS (
            SELECT 1 FROM serving_coach_citations
             WHERE load_id = target_load AND assignment_key = target_key
        ) THEN RAISE EXCEPTION 'verified serving assignment must have a citation'; END IF;
    END LOOP;
    RETURN COALESCE(NEW, OLD);
END;
$$;
CREATE CONSTRAINT TRIGGER serving_verified_assignment_requires_source
AFTER INSERT OR UPDATE OF verification_status ON serving_coach_assignments
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION enforce_serving_verified_assignment_source();
CREATE CONSTRAINT TRIGGER serving_verified_source_delete_guard
AFTER DELETE OR UPDATE OF load_id, assignment_key ON serving_coach_citations
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION enforce_serving_verified_assignment_source();

CREATE TABLE serving_review_queue (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    review_key text NOT NULL,
    team_id text NOT NULL,
    season smallint NOT NULL,
    role coach_role NOT NULL,
    review_status text NOT NULL,
    issue_type text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (load_id, review_key),
    FOREIGN KEY (load_id, team_id) REFERENCES serving_teams(load_id, team_id)
);

CREATE TABLE serving_coach_exposures (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    assignment_key text NOT NULL,
    player_id text NOT NULL,
    team_id text NOT NULL,
    season smallint NOT NULL,
    coach_id text NOT NULL,
    role coach_role NOT NULL,
    verification_status verification_status NOT NULL,
    confidence_level assignment_confidence NOT NULL,
    interval_basis assignment_interval_basis NOT NULL,
    is_shared boolean NOT NULL,
    start_week smallint NOT NULL,
    end_week smallint NOT NULL,
    exposure_fraction double precision NOT NULL,
    observed_dropbacks integer NOT NULL,
    exposure_dropbacks double precision NOT NULL,
    coach_interval_pae double precision,
    exclusion_reason text,
    payload jsonb NOT NULL,
    PRIMARY KEY (load_id, assignment_key, player_id, team_id, season),
    FOREIGN KEY (load_id, assignment_key)
        REFERENCES serving_coach_assignments(load_id, assignment_key),
    FOREIGN KEY (load_id, player_id, team_id, season)
        REFERENCES serving_qb_seasons(load_id, player_id, team_id, season),
    FOREIGN KEY (load_id, coach_id) REFERENCES serving_coaches(load_id, coach_id),
    CHECK (exposure_fraction > 0 AND exposure_fraction <= 1),
    CHECK (exposure_dropbacks >= 0),
    CHECK (abs(exposure_dropbacks - observed_dropbacks * exposure_fraction) < 0.000001)
);

CREATE FUNCTION enforce_serving_exposure_lineage()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE assignment serving_coach_assignments%ROWTYPE;
BEGIN
    SELECT * INTO assignment
      FROM serving_coach_assignments
     WHERE load_id = NEW.load_id AND assignment_key = NEW.assignment_key;
    IF NOT FOUND OR assignment.coach_id <> NEW.coach_id
       OR assignment.team_id <> NEW.team_id OR assignment.season <> NEW.season
       OR assignment.role <> NEW.role OR assignment.start_week <> NEW.start_week
       OR assignment.end_week <> NEW.end_week
       OR assignment.verification_status <> NEW.verification_status
       OR assignment.confidence_level <> NEW.confidence_level
       OR assignment.interval_basis <> NEW.interval_basis
       OR assignment.is_shared <> NEW.is_shared THEN
        RAISE EXCEPTION 'coach exposure must match assignment lineage';
    END IF;
    RETURN NEW;
END;
$$;
CREATE CONSTRAINT TRIGGER serving_exposure_lineage_guard
AFTER INSERT OR UPDATE ON serving_coach_exposures
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION enforce_serving_exposure_lineage();

CREATE TABLE serving_coach_effects (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    coach_id text NOT NULL,
    role coach_role NOT NULL,
    data_version text NOT NULL,
    model_version text NOT NULL,
    estimated_effect double precision,
    confidence_low double precision,
    confidence_high double precision,
    bootstrap_replicates integer NOT NULL,
    bootstrap_attempted_replicates integer NOT NULL,
    bootstrap_interval_available boolean NOT NULL,
    interval_estimand text NOT NULL,
    identified_effect boolean NOT NULL,
    identification_status text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (load_id, coach_id, role),
    FOREIGN KEY (load_id, coach_id) REFERENCES serving_coaches(load_id, coach_id),
    CHECK (confidence_high IS NULL OR confidence_low IS NULL OR confidence_high >= confidence_low)
);

CREATE TABLE serving_coach_rankings (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    coach_id text NOT NULL,
    role coach_role NOT NULL,
    rank_eligible boolean NOT NULL,
    rank_exclusion_reason text,
    ranking_status text NOT NULL,
    preliminary_rank integer,
    verified_dropbacks double precision NOT NULL,
    qualifying_qb_seasons integer NOT NULL,
    distinct_quarterbacks integer NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (load_id, coach_id, role),
    FOREIGN KEY (load_id, coach_id, role)
        REFERENCES serving_coach_effects(load_id, coach_id, role),
    CHECK (rank_eligible OR preliminary_rank IS NULL)
);

CREATE TABLE serving_source_manifests (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    asset_key text NOT NULL,
    dataset text NOT NULL,
    season smallint,
    source_url text NOT NULL,
    sha256 text NOT NULL,
    validation_status text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (load_id, asset_key)
);

CREATE TABLE serving_pipeline_manifests (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    pipeline_name text NOT NULL,
    data_version text NOT NULL,
    model_version text,
    manifest jsonb NOT NULL,
    PRIMARY KEY (load_id, pipeline_name)
);

CREATE VIEW api_qb_statistics AS
SELECT qs.*, p.display_name
FROM serving_qb_seasons qs
JOIN serving_publication pub ON pub.load_id = qs.load_id
JOIN serving_players p ON p.load_id = qs.load_id AND p.player_id = qs.player_id
WHERE qs.scope = 'analysis';

CREATE VIEW api_qb_pae AS
SELECT q.*, p.display_name
FROM serving_qb_pae q
JOIN serving_publication pub ON pub.load_id = q.load_id
JOIN serving_players p ON p.load_id = q.load_id AND p.player_id = q.player_id
JOIN serving_qb_seasons qs
  ON qs.load_id = q.load_id AND qs.player_id = q.player_id
 AND qs.team_id = q.team_id AND qs.season = q.season
WHERE q.is_out_of_sample AND qs.scope = 'analysis';

CREATE VIEW api_coach_impact AS
SELECT e.*, c.canonical_name, r.rank_eligible, r.rank_exclusion_reason,
       r.ranking_status, r.preliminary_rank, r.verified_dropbacks,
       r.qualifying_qb_seasons, r.distinct_quarterbacks
FROM serving_coach_effects e
JOIN serving_publication pub ON pub.load_id = e.load_id
JOIN serving_coaches c ON c.load_id = e.load_id AND c.coach_id = e.coach_id
JOIN serving_coach_rankings r
  ON r.load_id = e.load_id AND r.coach_id = e.coach_id AND r.role = e.role;

CREATE VIEW api_coach_comparisons AS SELECT * FROM api_coach_impact;

CREATE VIEW api_coaching_assignments AS
SELECT a.*, c.canonical_name, t.team_abbr, t.team_name
FROM serving_coach_assignments a
JOIN serving_publication pub ON pub.load_id = a.load_id
JOIN serving_coaches c ON c.load_id = a.load_id AND c.coach_id = a.coach_id
JOIN serving_teams t ON t.load_id = a.load_id AND t.team_id = a.team_id;

CREATE VIEW api_coaching_network_edges AS
SELECT DISTINCT a.load_id,
       a.assignment_key AS source_assignment_key,
       b.assignment_key AS target_assignment_key,
       a.coach_id AS source_coach_id, b.coach_id AS target_coach_id,
       a.team_id, a.season, a.role AS source_role, b.role AS target_role,
       a.verification_status AS source_verification_status,
       b.verification_status AS target_verification_status,
       a.confidence_level AS source_confidence_level,
       b.confidence_level AS target_confidence_level,
       a.start_week AS source_start_week, a.end_week AS source_end_week,
       b.start_week AS target_start_week, b.end_week AS target_end_week,
       greatest(a.start_week, b.start_week) AS overlap_start_week,
       least(a.end_week, b.end_week) AS overlap_end_week,
       a.is_shared AS source_is_shared, b.is_shared AS target_is_shared,
       (a.verification_status = 'provisional') AS source_is_provisional,
       (b.verification_status = 'provisional') AS target_is_provisional
FROM serving_coach_assignments a
JOIN serving_publication pub ON pub.load_id = a.load_id
JOIN serving_coach_assignments b
  ON b.load_id = a.load_id AND b.team_id = a.team_id AND b.season = a.season
 AND b.coach_id > a.coach_id
 AND int4range(b.start_week, b.end_week, '[]') && int4range(a.start_week, a.end_week, '[]');

CREATE VIEW api_source_citations AS
SELECT s.*, a.coach_id, a.team_id, a.season, a.role
FROM serving_coach_citations s
JOIN serving_publication pub ON pub.load_id = s.load_id
JOIN serving_coach_assignments a
  ON a.load_id = s.load_id AND a.assignment_key = s.assignment_key;

CREATE VIEW api_review_queue_summary AS
SELECT q.load_id, q.review_status, q.role, q.issue_type, count(*)::integer AS review_count
FROM serving_review_queue q
JOIN serving_publication pub ON pub.load_id = q.load_id
GROUP BY q.load_id, q.review_status, q.role, q.issue_type;

COMMIT;
