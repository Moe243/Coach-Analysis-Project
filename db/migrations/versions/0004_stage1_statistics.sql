ALTER TABLE serving_qb_supplemental
    ADD COLUMN completions integer,
    ADD COLUMN attempts integer,
    ADD COLUMN interceptions integer,
    ADD COLUMN sacks integer,
    ADD COLUMN yards_per_attempt double precision,
    ADD COLUMN adjusted_net_yards_per_attempt double precision,
    ADD COLUMN fumbles_lost integer;

CREATE TABLE serving_team_season_statistics (
    load_id uuid NOT NULL REFERENCES serving_loads(load_id) ON DELETE CASCADE,
    team_id text NOT NULL,
    season smallint NOT NULL,
    team_metric_version text NOT NULL,
    team_games smallint NOT NULL CHECK (team_games > 0),
    team_wins smallint NOT NULL CHECK (team_wins >= 0),
    team_losses smallint NOT NULL CHECK (team_losses >= 0),
    team_ties smallint NOT NULL CHECK (team_ties >= 0),
    team_win_percentage double precision NOT NULL CHECK (team_win_percentage BETWEEN 0 AND 1),
    team_points_scored integer NOT NULL,
    team_points_allowed integer NOT NULL,
    team_points_per_game double precision NOT NULL,
    team_total_offensive_yards integer,
    team_passing_yards integer,
    team_rushing_yards integer,
    team_offensive_touchdowns integer,
    team_turnovers integer,
    team_sacks_allowed integer,
    team_offensive_epa_per_play double precision,
    team_passing_epa_per_dropback double precision,
    team_offensive_success_rate double precision,
    team_points_per_game_rank smallint,
    team_offensive_epa_per_play_rank smallint,
    team_passing_epa_per_dropback_rank smallint,
    payload jsonb NOT NULL,
    PRIMARY KEY (load_id, team_id, season),
    FOREIGN KEY (load_id, team_id) REFERENCES serving_teams(load_id, team_id),
    CHECK (team_wins + team_losses + team_ties = team_games)
);

DROP VIEW api_qb_pae;
DROP VIEW api_qb_statistics;

CREATE VIEW api_qb_statistics AS
SELECT qs.*, p.display_name, p.position,
       (qs.payload->>'touchdown_rate')::double precision AS passing_touchdown_rate,
       (qs.payload->>'interception_rate')::double precision AS interception_rate,
       s.supplemental_metric_version,
       s.starter_wins, s.starter_losses, s.starter_ties, s.starter_decisions,
       s.team_points_scored, s.completion_percentage,
       s.completions, s.attempts, s.passing_yards, s.passing_touchdowns,
       s.interceptions, s.sacks, s.yards_per_attempt, s.adjusted_net_yards_per_attempt,
       s.rushing_yards, s.rushing_touchdowns, s.total_yards, s.total_touchdowns,
       s.fumbles, s.fumbles_lost,
       q.expected_epa_per_dropback, q.actual_epa_per_dropback,
       q.performance_above_expectation, q.eligibility_status AS pae_eligibility_status,
       q.reliability AS pae_reliability, q.model_version AS pae_model_version,
       ts.team_metric_version, ts.team_games, ts.team_wins, ts.team_losses, ts.team_ties,
       ts.team_win_percentage, ts.team_points_allowed, ts.team_points_per_game,
       ts.team_total_offensive_yards, ts.team_passing_yards, ts.team_rushing_yards,
       ts.team_offensive_touchdowns, ts.team_turnovers, ts.team_sacks_allowed,
       ts.team_offensive_epa_per_play, ts.team_passing_epa_per_dropback,
       ts.team_offensive_success_rate, ts.team_points_per_game_rank,
       ts.team_offensive_epa_per_play_rank, ts.team_passing_epa_per_dropback_rank,
       s.payload AS supplemental_payload, ts.payload AS team_statistics_payload
FROM serving_qb_seasons qs
JOIN serving_publication pub ON pub.load_id = qs.load_id
JOIN serving_players p ON p.load_id = qs.load_id AND p.player_id = qs.player_id
LEFT JOIN serving_qb_supplemental s
  ON s.load_id = qs.load_id AND s.player_id = qs.player_id
 AND s.team_id = qs.team_id AND s.season = qs.season
LEFT JOIN serving_qb_pae q
  ON q.load_id = qs.load_id AND q.player_id = qs.player_id
 AND q.team_id = qs.team_id AND q.season = qs.season AND q.is_out_of_sample
LEFT JOIN serving_team_season_statistics ts
  ON ts.load_id = qs.load_id AND ts.team_id = qs.team_id AND ts.season = qs.season
WHERE qs.scope = 'analysis' AND upper(p.position) = 'QB';

CREATE VIEW api_qb_pae AS
SELECT q.*, p.display_name
FROM serving_qb_pae q
JOIN serving_publication pub ON pub.load_id = q.load_id
JOIN serving_players p ON p.load_id = q.load_id AND p.player_id = q.player_id
JOIN serving_qb_seasons qs
  ON qs.load_id = q.load_id AND qs.player_id = q.player_id
 AND qs.team_id = q.team_id AND qs.season = q.season
WHERE q.is_out_of_sample AND qs.scope = 'analysis' AND upper(p.position) = 'QB';

CREATE VIEW api_team_season_statistics AS
SELECT ts.*, t.team_abbr, t.team_name
FROM serving_team_season_statistics ts
JOIN serving_publication pub ON pub.load_id = ts.load_id
JOIN serving_teams t ON t.load_id = ts.load_id AND t.team_id = ts.team_id;
