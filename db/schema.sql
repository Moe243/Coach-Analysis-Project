-- NFL Coaching Impact Engine
-- Checkpoint-one PostgreSQL contract. Alembic migrations begin when loading is implemented.

BEGIN;

CREATE EXTENSION IF NOT EXISTS btree_gist;

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

ALTER TABLE team_aliases
    ADD CONSTRAINT team_alias_date_ranges_do_not_overlap
    EXCLUDE USING gist (
        source_system WITH =,
        alias WITH =,
        (daterange(valid_from, COALESCE(valid_to, 'infinity'::date), '[]')) WITH &&
    )
    DEFERRABLE INITIALLY IMMEDIATE;

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
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (coach_id, team_id, season, role, start_week, end_week),
    CHECK (end_week >= start_week),
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);

-- Non-shared assignments for the same team, season, and role may not overlap.
ALTER TABLE coach_assignments
    ADD CONSTRAINT coach_assignment_nonshared_overlap
    EXCLUDE USING gist (
        team_id WITH =,
        season WITH =,
        role WITH =,
        (int4range(start_week::integer, end_week::integer, '[]')) WITH &&
    ) WHERE (is_shared = false)
    DEFERRABLE INITIALLY IMMEDIATE;

-- Shared assignments may overlap one another, but never a non-shared assignment.
ALTER TABLE coach_assignments
    ADD CONSTRAINT coach_assignment_mixed_overlap
    EXCLUDE USING gist (
        team_id WITH =,
        season WITH =,
        role WITH =,
        (int4range(start_week::integer, end_week::integer, '[]')) WITH &&,
        is_shared WITH <>
    )
    DEFERRABLE INITIALLY IMMEDIATE;

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
    career_starts integer,
    previous_dropbacks integer,
    previous_epa_per_dropback numeric,
    previous_cpoe numeric,
    changed_team boolean,
    new_coaching_environment boolean,
    feature_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    ingestion_run_id bigint NOT NULL REFERENCES ingestion_runs(ingestion_run_id),
    PRIMARY KEY (player_id, team_id, season, feature_version),
    CHECK (as_of_season < season),
    CHECK (nfl_experience IS NULL OR nfl_experience >= 0),
    CHECK (career_starts IS NULL OR career_starts >= 0),
    CHECK (previous_dropbacks IS NULL OR previous_dropbacks >= 0)
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
    is_out_of_sample boolean NOT NULL,
    warning_flags text[] NOT NULL DEFAULT '{}',
    PRIMARY KEY (model_run_id, qb_season_id)
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
