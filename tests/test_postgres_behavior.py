from __future__ import annotations

import os
import secrets
import unittest
from pathlib import Path

from nfl_coaching_impact.coaching_loader import load_coaching_data
from nfl_coaching_impact.constants import CANONICAL_TEAM_IDS

try:
    import psycopg
    from psycopg import sql
except ImportError:  # pragma: no cover - exercised only when optional integration deps are absent
    psycopg = None
    sql = None


ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(
    psycopg is not None and TEST_DATABASE_URL,
    "set TEST_DATABASE_URL and install psycopg to run PostgreSQL behavior tests",
)
class PostgreSQLBehaviorTest(unittest.TestCase):
    """Execute the schema and prove its cross-row rules against PostgreSQL."""

    connection: psycopg.Connection
    schema_name: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.schema_name = f"nfl_coaching_test_{secrets.token_hex(6)}"
        cls.connection = psycopg.connect(TEST_DATABASE_URL, autocommit=True)
        cls.connection.execute("CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public")
        cls.connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema_name)))
        cls.connection.execute(
            sql.SQL("SET search_path TO {}, public").format(sql.Identifier(cls.schema_name))
        )
        cls.connection.execute((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.execute("SET search_path TO public")
        cls.connection.execute(
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema_name))
        )
        cls.connection.close()

    def insert_team(self, team_id: str) -> None:
        self.connection.execute(
            "INSERT INTO teams (team_id, display_name, franchise_name) VALUES (%s, %s, %s)",
            (team_id, team_id, team_id),
        )

    def insert_coach(self, name: str) -> int:
        return self.connection.execute(
            """
            INSERT INTO coaches (canonical_name, normalized_name)
            VALUES (%s, %s)
            RETURNING coach_id
            """,
            (name, name.lower().replace(" ", "-")),
        ).fetchone()[0]

    def insert_ingestion_run(self, version: str) -> int:
        return self.connection.execute(
            """
            INSERT INTO ingestion_runs
                (data_version, code_version, started_at, finished_at, status)
            VALUES (%s, 'test', now(), now(), 'succeeded')
            RETURNING ingestion_run_id
            """,
            (version,),
        ).fetchone()[0]

    def test_team_alias_validity_ranges_cannot_overlap(self) -> None:
        self.insert_team("ALIAS")
        self.connection.execute(
            """
            INSERT INTO team_aliases (team_id, source_system, alias, valid_from, valid_to)
            VALUES ('ALIAS', 'test', 'OLD', DATE '2020-01-01', DATE '2020-06-30')
            """
        )

        with self.assertRaises(psycopg.Error):
            with self.connection.transaction():
                self.connection.execute(
                    """
                    INSERT INTO team_aliases
                        (team_id, source_system, alias, valid_from, valid_to)
                    VALUES ('ALIAS', 'test', 'OLD', DATE '2020-06-01', DATE '2020-12-31')
                    """
                )

        self.connection.execute(
            """
            INSERT INTO team_aliases (team_id, source_system, alias, valid_from, valid_to)
            VALUES ('ALIAS', 'test', 'OLD', DATE '2020-07-01', DATE '2020-12-31')
            """
        )

    def test_shared_assignments_may_overlap_only_other_shared_assignments(self) -> None:
        self.insert_team("SHARED")
        coaches = [self.insert_coach(f"Shared Coach {index}") for index in range(1, 4)]
        for coach_id, start_week, end_week in ((coaches[0], 1, 10), (coaches[1], 5, 12)):
            self.connection.execute(
                """
                INSERT INTO coach_assignments
                    (coach_id, team_id, season, role, start_week, end_week, is_shared)
                VALUES (%s, 'SHARED', 2025, 'play_caller', %s, %s, true)
                """,
                (coach_id, start_week, end_week),
            )

        with self.assertRaises(psycopg.Error):
            with self.connection.transaction():
                self.connection.execute(
                    """
                    INSERT INTO coach_assignments
                        (coach_id, team_id, season, role, start_week, end_week, is_shared)
                    VALUES (%s, 'SHARED', 2025, 'play_caller', 10, 18, false)
                    """,
                    (coaches[2],),
                )

        self.connection.execute(
            """
            INSERT INTO coach_assignments
                (coach_id, team_id, season, role, start_week, end_week, is_shared)
            VALUES (%s, 'SHARED', 2025, 'play_caller', 13, 18, false)
            """,
            (coaches[2],),
        )

    def test_assignment_interval_basis_is_persisted_and_constrained(self) -> None:
        self.insert_team("BASIS")
        coach_id = self.insert_coach("Interval Basis Coach")
        assignment_id = self.connection.execute(
            """
            INSERT INTO coach_assignments
                (coach_id, team_id, season, role, start_week, end_week, interval_basis)
            VALUES (%s, 'BASIS', 2025, 'offensive_coordinator', 1, 9,
                    'observed_game_weeks')
            RETURNING assignment_id
            """,
            (coach_id,),
        ).fetchone()[0]
        value = self.connection.execute(
            "SELECT interval_basis::text FROM coach_assignments WHERE assignment_id = %s",
            (assignment_id,),
        ).fetchone()[0]
        self.assertEqual(value, "observed_game_weeks")

        with self.assertRaises(psycopg.Error):
            with self.connection.transaction():
                self.connection.execute(
                    """
                    INSERT INTO coach_assignments
                        (coach_id, team_id, season, role, start_week, end_week, interval_basis)
                    VALUES (%s, 'BASIS', 2024, 'offensive_coordinator', 1, 18,
                            'unsupported_basis')
                    """,
                    (coach_id,),
                )

    def test_coaching_loader_preserves_interval_basis(self) -> None:
        for team_id in CANONICAL_TEAM_IDS:
            self.connection.execute(
                """
                INSERT INTO teams (team_id, display_name, franchise_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (team_id) DO NOTHING
                """,
                (team_id, team_id, team_id),
            )
        with self.connection.transaction():
            count = load_coaching_data(self.connection, ROOT)
        self.assertGreater(count, 1300)
        rows = self.connection.execute(
            """
            SELECT ca.role::text, ca.interval_basis::text
              FROM coach_assignments ca
              JOIN coaches c ON c.coach_id = ca.coach_id
             WHERE ca.team_id = 'HOU' AND ca.season = 2020
               AND c.canonical_name = 'Tim Kelly'
             ORDER BY ca.role, ca.start_week, c.canonical_name
            """
        ).fetchall()
        self.assertEqual(
            rows,
            [
                ("offensive_coordinator", "season_designation"),
                ("play_caller", "dated_source_weeks"),
                ("play_caller", "dated_source_weeks"),
                ("play_caller", "season_designation"),
                ("quarterbacks_coach", "season_designation"),
            ],
        )

    def test_reassigning_a_citation_cannot_orphan_a_verified_assignment(self) -> None:
        self.insert_team("SOURCE")
        coach_id = self.insert_coach("Citation Coach")
        data_source_id = self.connection.execute(
            """
            INSERT INTO data_sources
                (source_name, base_url, collection_method, last_reviewed_at)
            VALUES ('citation-test', 'https://example.com', 'test', DATE '2026-08-25')
            RETURNING data_source_id
            """
        ).fetchone()[0]

        with self.connection.transaction():
            verified_id = self.connection.execute(
                """
                INSERT INTO coach_assignments
                    (coach_id, team_id, season, role, start_week, end_week, verification_status)
                VALUES (%s, 'SOURCE', 2025, 'head_coach', 1, 18, 'verified')
                RETURNING assignment_id
                """,
                (coach_id,),
            ).fetchone()[0]
            self.connection.execute(
                """
                INSERT INTO coach_assignment_sources
                    (assignment_id, data_source_id, source_url, accessed_at)
                VALUES (%s, %s, 'https://example.com/verified', DATE '2026-08-25')
                """,
                (verified_id, data_source_id),
            )

        replacement_id = self.connection.execute(
            """
            INSERT INTO coach_assignments
                (coach_id, team_id, season, role, start_week, end_week, verification_status)
            VALUES (%s, 'SOURCE', 2024, 'head_coach', 1, 18, 'unverified')
            RETURNING assignment_id
            """,
            (coach_id,),
        ).fetchone()[0]

        with self.assertRaises(psycopg.Error):
            with self.connection.transaction():
                self.connection.execute(
                    """
                    UPDATE coach_assignment_sources
                       SET assignment_id = %s
                     WHERE assignment_id = %s
                    """,
                    (replacement_id, verified_id),
                )

        remaining_assignment = self.connection.execute(
            "SELECT assignment_id FROM coach_assignment_sources WHERE source_url = %s",
            ("https://example.com/verified",),
        ).fetchone()[0]
        self.assertEqual(remaining_assignment, verified_id)

    def test_environment_members_must_match_assignment_lineage(self) -> None:
        self.insert_team("ENV-A")
        self.insert_team("ENV-B")
        coach_a = self.insert_coach("Environment Coach A")
        coach_b = self.insert_coach("Environment Coach B")
        environment_id = self.connection.execute(
            """
            INSERT INTO coaching_environments
                (team_id, season, start_week, end_week, environment_key)
            VALUES ('ENV-A', 2025, 1, 18, 'ENV-A-2025')
            RETURNING environment_id
            """
        ).fetchone()[0]
        valid_assignment = self.connection.execute(
            """
            INSERT INTO coach_assignments
                (coach_id, team_id, season, role, start_week, end_week)
            VALUES (%s, 'ENV-A', 2025, 'head_coach', 1, 18)
            RETURNING assignment_id
            """,
            (coach_a,),
        ).fetchone()[0]
        self.connection.execute(
            """
            INSERT INTO coaching_environment_members
                (environment_id, role, coach_id, assignment_id)
            VALUES (%s, 'head_coach', %s, %s)
            """,
            (environment_id, coach_a, valid_assignment),
        )
        wrong_assignment = self.connection.execute(
            """
            INSERT INTO coach_assignments
                (coach_id, team_id, season, role, start_week, end_week)
            VALUES (%s, 'ENV-B', 2024, 'offensive_coordinator', 1, 18)
            RETURNING assignment_id
            """,
            (coach_b,),
        ).fetchone()[0]

        with self.assertRaises(psycopg.Error):
            with self.connection.transaction():
                self.connection.execute(
                    """
                    INSERT INTO coaching_environment_members
                        (environment_id, role, coach_id, assignment_id)
                    VALUES (%s, 'quarterbacks_coach', %s, %s)
                    """,
                    (environment_id, coach_b, wrong_assignment),
                )

        with self.assertRaises(psycopg.Error):
            with self.connection.transaction():
                self.connection.execute(
                    "UPDATE coach_assignments SET team_id = 'ENV-B' WHERE assignment_id = %s",
                    (valid_assignment,),
                )

    def test_qb_stints_must_match_qb_season_and_environment_lineage(self) -> None:
        self.insert_team("STINT-A")
        self.insert_team("STINT-B")
        ingestion_id = self.insert_ingestion_run("stint-data")
        self.connection.execute(
            """
            INSERT INTO players (player_id, display_name, position)
            VALUES ('stint-qb-a', 'Stint QB A', 'QB'), ('stint-qb-b', 'Stint QB B', 'QB')
            """
        )
        environment_id = self.connection.execute(
            """
            INSERT INTO coaching_environments
                (team_id, season, start_week, end_week, environment_key)
            VALUES ('STINT-A', 2025, 1, 18, 'STINT-A-2025')
            RETURNING environment_id
            """
        ).fetchone()[0]
        qb_season_ids = []
        for player_id, team_id in (("stint-qb-a", "STINT-A"), ("stint-qb-b", "STINT-B")):
            qb_season_ids.append(
                self.connection.execute(
                    """
                    INSERT INTO qb_seasons
                        (player_id, team_id, season, games, dropbacks, pass_attempts,
                         qualifies_default, metric_version, ingestion_run_id)
                    VALUES (%s, %s, 2025, 1, 10, 8, false, 'test', %s)
                    RETURNING qb_season_id
                    """,
                    (player_id, team_id, ingestion_id),
                ).fetchone()[0]
            )

        self.connection.execute(
            """
            INSERT INTO qb_environment_stints
                (qb_season_id, environment_id, start_week, end_week, dropbacks, metric_version)
            VALUES (%s, %s, 1, 18, 10, 'test')
            """,
            (qb_season_ids[0], environment_id),
        )

        with self.assertRaises(psycopg.Error):
            with self.connection.transaction():
                self.connection.execute(
                    """
                    INSERT INTO qb_environment_stints
                        (qb_season_id, environment_id, start_week, end_week,
                         dropbacks, metric_version)
                    VALUES (%s, %s, 1, 18, 10, 'test')
                    """,
                    (qb_season_ids[1], environment_id),
                )

        with self.assertRaises(psycopg.Error):
            with self.connection.transaction():
                self.connection.execute(
                    "UPDATE qb_seasons SET team_id = 'STINT-B' WHERE qb_season_id = %s",
                    (qb_season_ids[0],),
                )

    def test_rankings_exclude_ineligible_rows_before_dense_rank(self) -> None:
        self.insert_team("RANK")
        ingestion_id = self.insert_ingestion_run("ranking-data")
        self.connection.execute(
            """
            INSERT INTO players (player_id, display_name, position)
            VALUES
                ('rank-qb-a', 'Rank QB A', 'QB'),
                ('rank-qb-b', 'Rank QB B', 'QB'),
                ('rank-qb-x', 'Ineligible QB', 'QB')
            """
        )
        qb_season_ids: dict[str, int] = {}
        for player_id, qualifies in (
            ("rank-qb-a", True),
            ("rank-qb-b", True),
            ("rank-qb-x", False),
        ):
            qb_season_ids[player_id] = self.connection.execute(
                """
                INSERT INTO qb_seasons
                    (player_id, team_id, season, games, dropbacks, pass_attempts,
                     epa_per_dropback, qualifies_default, metric_version, ingestion_run_id)
                VALUES (%s, 'RANK', 2025, 17, 300, 280, 0.20, %s, 'test', %s)
                RETURNING qb_season_id
                """,
                (player_id, qualifies, ingestion_id),
            ).fetchone()[0]
        expected_model = self.connection.execute(
            """
            INSERT INTO model_runs
                (model_kind, model_name, model_version, data_version, metric_version,
                 training_end_season, code_version)
            VALUES
                ('expected_performance', 'rank-test', '1', 'ranking-data', 'test', 2024, 'test')
            RETURNING model_run_id
            """
        ).fetchone()[0]
        for player_id, pae in (("rank-qb-a", 0.20), ("rank-qb-b", 0.10), ("rank-qb-x", 0.90)):
            self.connection.execute(
                """
                INSERT INTO qb_predictions
                    (model_run_id, qb_season_id, prediction_as_of_season,
                     expected_epa_per_dropback, performance_above_expectation,
                     is_out_of_sample)
                VALUES (%s, %s, 2024, 0.0, %s, true)
                """,
                (expected_model, qb_season_ids[player_id], pae),
            )

        qb_ranks = dict(
            self.connection.execute(
                """
                SELECT qb_season_id, default_rank
                  FROM v_qb_rankings
                 WHERE model_run_id = %s
                """,
                (expected_model,),
            ).fetchall()
        )
        self.assertEqual(
            qb_ranks,
            {
                qb_season_ids["rank-qb-a"]: 1,
                qb_season_ids["rank-qb-b"]: 2,
                qb_season_ids["rank-qb-x"]: None,
            },
        )

        coaches = [self.insert_coach(f"Ranking Coach {index}") for index in range(1, 4)]
        coach_model = self.connection.execute(
            """
            INSERT INTO model_runs
                (model_kind, model_name, model_version, data_version, metric_version,
                 training_end_season, code_version)
            VALUES ('coach_role', 'coach-rank-test', '1', 'ranking-data', 'test', 2025, 'test')
            RETURNING model_run_id
            """
        ).fetchone()[0]
        for coach_id, impact, eligible in (
            (coaches[0], 0.20, True),
            (coaches[1], 0.10, True),
            (coaches[2], 0.90, False),
        ):
            self.connection.execute(
                """
                INSERT INTO coach_effect_estimates
                    (model_run_id, coach_id, role, adjusted_impact,
                     qualifying_qb_seasons, distinct_quarterbacks, total_dropbacks,
                     is_rank_eligible)
                VALUES (%s, %s, 'head_coach', %s, 3, 2, 900, %s)
                """,
                (coach_model, coach_id, impact, eligible),
            )

        coach_ranks = dict(
            self.connection.execute(
                """
                SELECT coach_id, default_rank
                  FROM v_coach_rankings
                 WHERE model_run_id = %s
                """,
                (coach_model,),
            ).fetchall()
        )
        self.assertEqual(
            coach_ranks,
            {coaches[0]: 1, coaches[1]: 2, coaches[2]: None},
        )

    def test_expected_performance_fields_enforce_timing_intervals_and_pae(self) -> None:
        self.insert_team("EXPECT")
        ingestion_id = self.insert_ingestion_run("expected-performance-data")
        self.connection.execute(
            "INSERT INTO players (player_id, display_name, position) "
            "VALUES ('expect-qb', 'Expected QB', 'QB')"
        )
        self.connection.execute(
            """
            INSERT INTO qb_preseason_features
                (player_id, team_id, season, feature_version, as_of_season,
                 career_dropbacks, previous_success_rate, previous_sack_rate,
                 is_rookie, missing_feature_count, ingestion_run_id)
            VALUES
                ('expect-qb', 'EXPECT', 2025, 'fixture', 2024,
                 500, 0.45, 0.07, false, 3, %s)
            """,
            (ingestion_id,),
        )
        with self.assertRaises(psycopg.Error):
            with self.connection.transaction():
                self.connection.execute(
                    """
                    INSERT INTO qb_preseason_features
                        (player_id, team_id, season, feature_version, as_of_season,
                         missing_feature_count, ingestion_run_id)
                    VALUES ('expect-qb', 'EXPECT', 2025, 'leaked', 2025, 0, %s)
                    """,
                    (ingestion_id,),
                )

        qb_season_id = self.connection.execute(
            """
            INSERT INTO qb_seasons
                (player_id, team_id, season, games, dropbacks, pass_attempts,
                 epa_per_dropback, qualifies_default, metric_version, ingestion_run_id)
            VALUES ('expect-qb', 'EXPECT', 2025, 17, 300, 280,
                    0.20, true, 'test', %s)
            RETURNING qb_season_id
            """,
            (ingestion_id,),
        ).fetchone()[0]
        model_run_id = self.connection.execute(
            """
            INSERT INTO model_runs
                (model_kind, model_name, model_version, data_version, feature_version,
                 metric_version, training_end_season, code_version)
            VALUES ('expected_performance', 'career-performance', 'fixture',
                    'expected-performance-data', 'fixture', 'test', 2024, 'test')
            RETURNING model_run_id
            """
        ).fetchone()[0]
        self.connection.execute(
            """
            INSERT INTO qb_predictions
                (model_run_id, qb_season_id, prediction_as_of_season,
                 expected_epa_per_dropback, actual_epa_per_dropback,
                 performance_above_expectation, prediction_std_error,
                 prediction_interval_low, prediction_interval_high,
                 eligibility_status, reliability, is_out_of_sample)
            VALUES (%s, %s, 2024, 0.10, 0.20, 0.10, 0.05,
                    0.00, 0.20, 'eligible', 'high', true)
            """,
            (model_run_id, qb_season_id),
        )
        values = self.connection.execute(
            """
            SELECT prediction_std_error, prediction_interval_low,
                   prediction_interval_high, reliability
              FROM qb_predictions
             WHERE model_run_id = %s AND qb_season_id = %s
            """,
            (model_run_id, qb_season_id),
        ).fetchone()
        self.assertEqual(tuple(map(str, values[:3])), ("0.05", "0.00", "0.20"))
        self.assertEqual(values[3], "high")

        with self.assertRaises(psycopg.Error):
            with self.connection.transaction():
                self.connection.execute(
                    """
                    UPDATE qb_predictions
                       SET prediction_interval_low = 0.30,
                           prediction_interval_high = 0.20
                     WHERE model_run_id = %s AND qb_season_id = %s
                    """,
                    (model_run_id, qb_season_id),
                )
        with self.assertRaises(psycopg.Error):
            with self.connection.transaction():
                self.connection.execute(
                    """
                    UPDATE qb_predictions
                       SET performance_above_expectation = 0.50
                     WHERE model_run_id = %s AND qb_season_id = %s
                    """,
                    (model_run_id, qb_season_id),
                )


if __name__ == "__main__":
    unittest.main()
