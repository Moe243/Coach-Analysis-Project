ALTER TABLE serving_loads ADD COLUMN enhancement_data_version text;

CREATE TABLE serving_qb_supplemental (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    player_id text NOT NULL,
    team_id text NOT NULL,
    season smallint NOT NULL,
    supplemental_metric_version text NOT NULL,
    starter_wins smallint NOT NULL CHECK (starter_wins >= 0),
    starter_losses smallint NOT NULL CHECK (starter_losses >= 0),
    starter_ties smallint NOT NULL CHECK (starter_ties >= 0),
    starter_decisions smallint NOT NULL CHECK (starter_decisions >= 0),
    team_points_scored integer,
    completion_percentage double precision,
    passing_yards integer,
    rushing_yards integer,
    total_yards integer,
    passing_touchdowns integer,
    rushing_touchdowns integer,
    total_touchdowns integer,
    fumbles integer,
    payload jsonb NOT NULL,
    PRIMARY KEY (load_id, player_id, team_id, season),
    FOREIGN KEY (load_id, player_id, team_id, season)
        REFERENCES serving_qb_seasons(load_id, player_id, team_id, season),
    CHECK (starter_wins + starter_losses + starter_ties = starter_decisions),
    CHECK (completion_percentage IS NULL OR completion_percentage BETWEEN 0 AND 1)
);

CREATE TABLE serving_coaching_completeness (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    team_id text NOT NULL,
    season smallint NOT NULL,
    role coach_role NOT NULL,
    assignment_status text NOT NULL
        CHECK (assignment_status IN ('verified', 'provisional', 'conflicting', 'missing')),
    review_status text NOT NULL CHECK (review_status IN ('complete', 'manual_review')),
    requires_manual_review boolean NOT NULL,
    assignment_count smallint NOT NULL CHECK (assignment_count >= 0),
    verified_assignment_count smallint NOT NULL CHECK (verified_assignment_count >= 0),
    citation_count smallint NOT NULL CHECK (citation_count >= 0),
    has_in_season_change boolean NOT NULL,
    has_interim boolean NOT NULL,
    has_shared_duty boolean NOT NULL,
    has_unclear_interval boolean NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (load_id, team_id, season, role),
    FOREIGN KEY (load_id, team_id) REFERENCES serving_teams(load_id, team_id)
);

CREATE TABLE serving_inherited_environment (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    team_id text NOT NULL,
    season smallint NOT NULL,
    feature_version text NOT NULL,
    feature_source_max_season smallint NOT NULL,
    prior_pressure_rate double precision,
    prior_protection_score double precision,
    wr_quality_score double precision,
    te_quality_score double precision,
    receiving_quality_score double precision,
    run_quality_score double precision,
    sos_pass_defense_strength double precision,
    payload jsonb NOT NULL,
    PRIMARY KEY (load_id, team_id, season),
    FOREIGN KEY (load_id, team_id) REFERENCES serving_teams(load_id, team_id),
    CHECK (feature_source_max_season < season)
);

DROP VIEW api_qb_pae;
DROP VIEW api_qb_statistics;

CREATE VIEW api_qb_statistics AS
SELECT qs.*, p.display_name,
       s.supplemental_metric_version,
       s.starter_wins, s.starter_losses, s.starter_ties, s.starter_decisions,
       s.team_points_scored, s.completion_percentage,
       s.passing_yards, s.rushing_yards, s.total_yards,
       s.passing_touchdowns, s.rushing_touchdowns, s.total_touchdowns, s.fumbles,
       s.payload AS supplemental_payload
FROM serving_qb_seasons qs
JOIN serving_publication pub ON pub.load_id = qs.load_id
JOIN serving_players p ON p.load_id = qs.load_id AND p.player_id = qs.player_id
LEFT JOIN serving_qb_supplemental s
  ON s.load_id = qs.load_id AND s.player_id = qs.player_id
 AND s.team_id = qs.team_id AND s.season = qs.season
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

CREATE VIEW api_coaching_completeness AS
SELECT c.*, t.team_abbr, t.team_name
FROM serving_coaching_completeness c
JOIN serving_publication p ON p.load_id = c.load_id
JOIN serving_teams t ON t.load_id = c.load_id AND t.team_id = c.team_id;

CREATE VIEW api_inherited_environment AS
SELECT e.*, t.team_abbr, t.team_name
FROM serving_inherited_environment e
JOIN serving_publication p ON p.load_id = e.load_id
JOIN serving_teams t ON t.load_id = e.load_id AND t.team_id = e.team_id
WHERE e.season BETWEEN 2010 AND 2025;
