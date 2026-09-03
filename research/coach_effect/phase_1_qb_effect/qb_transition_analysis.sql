-- Research only: Phase 1 QB/coach-transition contract.
-- Materialize inputs as the two research views named below; never interpolate untrusted
-- relation names. Full-season transition tests deliberately exclude team-seasons
-- with multiple intervals for either focal role rather than collapsing them.

WITH role_seasons AS (
    SELECT
        a.season,
        a.team_id,
        a.role,
        MIN(a.coach_id) AS coach_id,
        COUNT(DISTINCT a.assignment_key) AS assignment_intervals,
        MIN(a.start_week) AS start_week,
        MAX(a.end_week) AS end_week
    FROM research_coaching_assignments AS a
    WHERE a.role IN ('head_coach', 'offensive_coordinator')
      AND a.verification_status IN ('verified', 'provisional')
    GROUP BY a.season, a.team_id, a.role
),
unambiguous AS (
    SELECT season, team_id, role, coach_id
    FROM role_seasons
    WHERE assignment_intervals = 1
      AND start_week = 1
),
qb_role_seasons AS (
    SELECT
        q.player_id,
        q.team_id,
        q.season,
        q.performance_above_expectation,
        oc.coach_id AS offensive_coordinator_id,
        hc.coach_id AS head_coach_id
    FROM research_qb_pae AS q
    JOIN unambiguous AS oc
      ON oc.season = q.season
     AND oc.team_id = q.team_id
     AND oc.role = 'offensive_coordinator'
    JOIN unambiguous AS hc
      ON hc.season = q.season
     AND hc.team_id = q.team_id
     AND hc.role = 'head_coach'
    WHERE q.is_out_of_sample
),
transitions AS (
    SELECT
        cur.*,
        prev.team_id AS prior_team_id,
        prev.performance_above_expectation AS prior_pae,
        prev.offensive_coordinator_id AS prior_offensive_coordinator_id,
        prev.head_coach_id AS prior_head_coach_id
    FROM qb_role_seasons AS cur
    JOIN qb_role_seasons AS prev
      ON prev.player_id = cur.player_id
     AND prev.season = cur.season - 1
)
SELECT
    *,
    performance_above_expectation - prior_pae AS actual_qb_delta_pae,
    team_id = prior_team_id AS same_team,
    head_coach_id = prior_head_coach_id AS same_head_coach,
    offensive_coordinator_id <> prior_offensive_coordinator_id
        AS changed_offensive_coordinator
FROM transitions
ORDER BY season, player_id, team_id;
