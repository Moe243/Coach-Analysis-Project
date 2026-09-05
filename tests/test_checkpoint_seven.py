from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import psycopg
    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient
    from psycopg import sql
except ImportError:  # pragma: no cover
    psycopg = None

from nfl_coaching_impact.errors import PipelineError
from nfl_coaching_impact.serving import load_serving_database

ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(psycopg is not None and TEST_DATABASE_URL, "PostgreSQL test URL required")
class CheckpointSevenPostgreSQLTest(unittest.TestCase):
    @staticmethod
    def _copy_project_inputs(directory: str) -> Path:
        project_root = Path(directory)
        data_root = project_root / "data"
        data_root.mkdir(parents=True)
        shutil.copytree(ROOT / "data/manual", data_root / "manual")
        (data_root / "processed").symlink_to(ROOT / "data/processed", target_is_directory=True)
        return project_root

    @classmethod
    def _create_database(cls, database: str) -> str:
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        prefix, query = (
            TEST_DATABASE_URL.split("?", 1) if "?" in TEST_DATABASE_URL else (TEST_DATABASE_URL, "")
        )
        url = prefix.rsplit("/", 1)[0] + "/" + database + ("?" + query if query else "")
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url", url.replace("postgresql://", "postgresql+psycopg://", 1)
        )
        previous = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = url
        try:
            command.upgrade(config, "head")
        finally:
            if previous is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous
        return url

    @classmethod
    def _drop_database(cls, database: str) -> None:
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database,),
            )
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))

    @classmethod
    def setUpClass(cls) -> None:
        cls.database = f"nfl_c7_{secrets.token_hex(5)}"
        cls.url = cls._create_database(cls.database)
        config = Config(str(ROOT / "alembic.ini"))
        sqlalchemy_url = cls.url.replace("postgresql://", "postgresql+psycopg://", 1)
        config.set_main_option("sqlalchemy.url", sqlalchemy_url)
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        cls.first = load_serving_database(cls.url, ROOT)
        os.environ["DATABASE_URL"] = cls.url
        from nfl_coaching_impact.api import app

        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        os.environ.pop("DATABASE_URL", None)
        cls._drop_database(cls.database)

    def test_schema_migration_and_loader_are_repeatable(self) -> None:
        second = load_serving_database(self.url, ROOT)
        self.assertTrue(second.reused_existing)
        self.assertEqual(second.load_id, self.first.load_id)

    def test_supplemental_stats_completeness_and_environment_api(self) -> None:
        response = self.client.get("/qbs", params={"search": "Trent Edwards", "season": 2010})
        self.assertEqual(response.status_code, 200)
        rows = response.json()["items"]
        self.assertEqual({row["team_id"] for row in rows}, {"team_buf", "team_jax"})
        self.assertEqual(
            {row["team_id"]: row["passing_yards"] for row in rows},
            {"team_buf": 241, "team_jax": 280},
        )
        self.assertTrue(all(row["position"] == "QB" for row in rows))
        self.assertTrue(all("adjusted_net_yards_per_attempt" in row for row in rows))
        self.assertTrue(all("passing_touchdown_rate" in row for row in rows))
        self.assertTrue(all("interception_rate" in row for row in rows))
        team_stats = self.client.get(
            "/team-seasons", params={"team_id": "team_buf", "season": 2010}
        )
        self.assertEqual(team_stats.status_code, 200)
        self.assertEqual(team_stats.json()["total"], 1)
        self.assertEqual(team_stats.json()["items"][0]["team_games"], 16)
        self.assertIn("team_offensive_epa_per_play_rank", team_stats.json()["items"][0])
        completeness = self.client.get(
            "/coaching/completeness",
            params={"team_id": "team_hou", "season": 2020, "role": "play_caller"},
        )
        self.assertEqual(completeness.status_code, 200)
        self.assertEqual(completeness.json()["total"], 1)
        self.assertEqual(completeness.json()["items"][0]["review_status"], "manual_review")
        self.assertEqual(
            self.client.get("/coaching/completeness", params={"role": "invalid"}).status_code,
            422,
        )
        environment = self.client.get(
            "/environment", params={"team_id": "team_den", "season": 2024}
        )
        self.assertEqual(environment.status_code, 200)
        self.assertEqual(environment.json()["items"][0]["feature_source_max_season"], 2023)

        with psycopg.connect(self.url) as connection:
            load_id = connection.execute("SELECT load_id FROM serving_publication").fetchone()[0]
            with self.assertRaises(psycopg.Error), connection.transaction():
                connection.execute(
                    "UPDATE serving_inherited_environment "
                    "SET feature_source_max_season = season WHERE load_id = %s",
                    (load_id,),
                )

    def test_qb_endpoints_exclude_non_quarterback_positions(self) -> None:
        for name, player_id in (
            ("Terrelle Pryor", "00-0028825"),
            ("Taysom Hill", "00-0033357"),
            ("Derrick Henry", "00-0032764"),
        ):
            response = self.client.get("/qbs", params={"search": name})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["total"], 0)
            self.assertEqual(self.client.get(f"/qbs/{player_id}").status_code, 404)

        small_sample = self.client.get("/qbs", params={"search": "Kedon Slovis", "season": 2025})
        self.assertEqual(small_sample.status_code, 200)
        self.assertEqual(small_sample.json()["total"], 1)
        self.assertEqual(small_sample.json()["items"][0]["dropbacks"], 2)
        self.assertFalse(small_sample.json()["items"][0]["qualifies_default"])

        with psycopg.connect(self.url) as connection:
            for table in (
                "serving_qb_games",
                "serving_qb_seasons",
                "serving_qb_pae",
                "serving_qb_supplemental",
                "serving_coach_exposures",
            ):
                non_qbs = connection.execute(
                    f"SELECT count(*) FROM {table} facts "  # noqa: S608 - fixed table allowlist
                    "JOIN serving_players p ON p.load_id=facts.load_id "
                    "AND p.player_id=facts.player_id "
                    "WHERE upper(p.position) <> 'QB' OR p.position IS NULL"
                ).fetchone()[0]
                self.assertEqual(non_qbs, 0, table)

        with psycopg.connect(self.url) as connection:
            load_id = connection.execute("SELECT load_id FROM serving_publication").fetchone()[0]
            team_id = connection.execute(
                "SELECT team_id FROM serving_teams WHERE load_id = %s ORDER BY team_id LIMIT 1",
                (load_id,),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO serving_players VALUES "
                "(%s, 'not-a-qb', 'Position Fixture', 'WR', '{}')",
                (load_id,),
            )
            connection.execute(
                "INSERT INTO serving_qb_seasons VALUES "
                "(%s, 'not-a-qb', %s, 2025, 'analysis', 1, 0, 1, 0, NULL, 0, 0, "
                "false, 'test', '{}')",
                (load_id, team_id),
            )
        listing = self.client.get("/qbs", params={"search": "Position Fixture"})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["total"], 0)
        self.assertEqual(self.client.get("/qbs/not-a-qb").status_code, 404)
        self.assertEqual(self.client.get("/qbs/not-a-qb/pae").status_code, 404)
        with psycopg.connect(self.url) as connection:
            connection.execute(
                "DELETE FROM serving_qb_seasons WHERE load_id = %s AND player_id = 'not-a-qb'",
                (load_id,),
            )
            connection.execute(
                "DELETE FROM serving_players WHERE load_id = %s AND player_id = 'not-a-qb'",
                (load_id,),
            )

    def test_independent_clean_loads_have_identical_analytical_checksums(self) -> None:
        database = f"nfl_c7_clean_{secrets.token_hex(5)}"
        url = self._create_database(database)
        try:
            rebuilt = load_serving_database(url, ROOT)
            views = (
                "api_qb_statistics",
                "api_qb_pae",
                "api_coach_impact",
                "api_coach_comparisons",
                "api_coaching_assignments",
                "api_coaching_network_edges",
                "api_source_citations",
                "api_review_queue_summary",
                "api_coaching_completeness",
                "api_inherited_environment",
                "api_team_season_statistics",
            )
            checksums = []
            for connection_url in (self.url, url):
                with psycopg.connect(connection_url) as connection:
                    checksums.append(
                        [
                            connection.execute(
                                f"SELECT count(*), md5(string_agg(to_jsonb(v)::text, '' "
                                f"ORDER BY to_jsonb(v)::text)) FROM {view} v"
                            ).fetchone()
                            for view in views
                        ]
                    )
            self.assertEqual(rebuilt.load_id, self.first.load_id)
            self.assertEqual(checksums[0], checksums[1])
        finally:
            self._drop_database(database)

    def test_publication_has_complete_versions_and_manifests(self) -> None:
        with psycopg.connect(self.url) as connection:
            versions = connection.execute(
                "SELECT historical_data_version, expected_data_version, coach_data_version, "
                "enhancement_data_version "
                "FROM serving_loads"
            ).fetchone()
            manifest_count = connection.execute(
                "SELECT count(*) FROM serving_pipeline_manifests"
            ).fetchone()[0]
        self.assertEqual(
            versions,
            (
                "c3-f6c1aa118ff43b90",
                "c5-8fd5d1aba2598c59",
                "c6-400a5b474aa37a35",
                "enh-04254065cafd92ba",
            ),
        )
        self.assertEqual(manifest_count, 5)

    def test_invalid_lineage_duplicate_and_fraction_are_rejected(self) -> None:
        with psycopg.connect(self.url, autocommit=True) as connection:
            load_id = connection.execute("SELECT load_id FROM serving_publication").fetchone()[0]
            with self.assertRaises(psycopg.Error):
                with connection.transaction():
                    connection.execute(
                        "INSERT INTO serving_qb_games VALUES "
                        "(%s,'missing','missing','missing',2025,1,1,0,false,'{}')",
                        (load_id,),
                    )

    def test_every_exposure_assignment_lineage_field_is_enforced(self) -> None:
        mutations = (
            "coach_id = (SELECT coach_id FROM serving_coaches WHERE load_id = %s "
            "AND coach_id <> e.coach_id LIMIT 1)",
            "team_id = (SELECT team_id FROM serving_teams WHERE load_id = %s "
            "AND team_id <> e.team_id LIMIT 1)",
            "season = season + 1",
            "role = CASE WHEN role = 'head_coach' THEN 'play_caller' ELSE 'head_coach' END",
            "start_week = start_week + 1",
            "end_week = end_week - 1",
            "verification_status = CASE WHEN verification_status = 'verified' "
            "THEN 'provisional' ELSE 'verified' END",
            "confidence_level = CASE WHEN confidence_level = 'high' THEN 'medium' ELSE 'high' END",
            "interval_basis = CASE WHEN interval_basis = 'season_designation' "
            "THEN 'dated_source_weeks' ELSE 'season_designation' END",
            "is_shared = NOT is_shared",
        )
        with psycopg.connect(self.url) as connection:
            load_id = connection.execute("SELECT load_id FROM serving_publication").fetchone()[0]
            for mutation in mutations:
                params = (load_id, load_id) if "%s" in mutation else (load_id,)
                with self.subTest(mutation=mutation), self.assertRaises(psycopg.Error):
                    with connection.transaction():
                        connection.execute(
                            f"UPDATE serving_coach_exposures e SET {mutation} "
                            "WHERE load_id = %s AND assignment_key = "
                            "(SELECT assignment_key FROM serving_coach_exposures LIMIT 1)",
                            params,
                        )
                        connection.execute(
                            "SET CONSTRAINTS serving_exposure_lineage_guard IMMEDIATE"
                        )
            with self.assertRaises(psycopg.Error):
                with connection.transaction():
                    connection.execute(
                        "UPDATE serving_coach_exposures SET exposure_fraction = 0.5 "
                        "WHERE load_id = %s AND assignment_key = "
                        "(SELECT assignment_key FROM serving_coach_exposures LIMIT 1)",
                        (load_id,),
                    )

    def test_assignment_updates_revalidate_related_exposures(self) -> None:
        suffix = secrets.token_hex(5)
        team_id = f"lineage-team-{suffix}"
        alternate_team_id = f"lineage-team-alt-{suffix}"
        player_id = f"lineage-player-{suffix}"
        coach_id = f"lineage-coach-{suffix}"
        alternate_coach_id = f"lineage-coach-alt-{suffix}"
        assignment_key = f"lineage-assignment-{suffix}"
        with psycopg.connect(self.url, autocommit=True) as connection:
            load_id = connection.execute("SELECT load_id FROM serving_publication").fetchone()[0]
            with connection.transaction():
                connection.execute(
                    "INSERT INTO serving_teams VALUES "
                    "(%s,%s,'LIN','Lineage Team',NULL,'{}'),"
                    "(%s,%s,'LIA','Lineage Alternate',NULL,'{}')",
                    (load_id, team_id, load_id, alternate_team_id),
                )
                connection.execute(
                    "INSERT INTO serving_players VALUES (%s,%s,'Lineage QB','QB','{}')",
                    (load_id, player_id),
                )
                connection.execute(
                    "INSERT INTO serving_qb_seasons VALUES "
                    "(%s,%s,%s,2025,'analysis',1,1,40,.1,NULL,.5,.1,false,'test','{}')",
                    (load_id, player_id, team_id),
                )
                connection.execute(
                    "INSERT INTO serving_coaches VALUES "
                    "(%s,%s,'Lineage Coach',%s),(%s,%s,'Lineage Alternate Coach',%s)",
                    (
                        load_id,
                        coach_id,
                        coach_id,
                        load_id,
                        alternate_coach_id,
                        alternate_coach_id,
                    ),
                )
                connection.execute(
                    "INSERT INTO serving_coach_assignments VALUES "
                    "(%s,%s,%s,%s,2025,'head_coach',1,17,'season_designation',"
                    "'verified','high',false,false,false,'fixture','{}')",
                    (load_id, assignment_key, coach_id, team_id),
                )
                connection.execute(
                    "INSERT INTO serving_coach_citations VALUES "
                    "(%s,%s,'https://example.com/lineage','Fixture','test','2026-08-30',"
                    "'fixture','fixture')",
                    (load_id, assignment_key),
                )
                connection.execute(
                    "INSERT INTO serving_coach_exposures VALUES "
                    "(%s,%s,%s,%s,2025,%s,'head_coach','verified','high',"
                    "'season_designation',false,1,17,1,40,40,.1,NULL,'{}')",
                    (load_id, assignment_key, player_id, team_id, coach_id),
                )
                connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
            mutations = (
                ("coach_id = %s", alternate_coach_id),
                ("team_id = %s", alternate_team_id),
                ("season = %s", 2024),
                ("role = %s", "play_caller"),
                ("start_week = %s", 2),
                ("end_week = %s", 16),
                ("verification_status = %s", "provisional"),
                ("confidence_level = %s", "medium"),
                ("interval_basis = %s", "dated_source_weeks"),
                ("is_shared = %s", True),
            )
            try:
                for mutation, value in mutations:
                    with self.subTest(mutation=mutation), self.assertRaises(psycopg.Error):
                        with connection.transaction():
                            connection.execute(
                                f"UPDATE serving_coach_assignments SET {mutation} "
                                "WHERE load_id = %s AND assignment_key = %s",
                                (value, load_id, assignment_key),
                            )
                            connection.execute(
                                "SET CONSTRAINTS "
                                "serving_assignment_exposure_lineage_guard IMMEDIATE"
                            )
                with connection.transaction():
                    connection.execute(
                        "UPDATE serving_coach_assignments SET confidence_level = 'medium' "
                        "WHERE load_id = %s AND assignment_key = %s",
                        (load_id, assignment_key),
                    )
                    connection.execute(
                        "UPDATE serving_coach_exposures SET confidence_level = 'medium' "
                        "WHERE load_id = %s AND assignment_key = %s",
                        (load_id, assignment_key),
                    )
                    connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
                assignment_confidence, exposure_confidence = connection.execute(
                    "SELECT a.confidence_level::text, e.confidence_level::text "
                    "FROM serving_coach_assignments a JOIN serving_coach_exposures e "
                    "ON e.load_id=a.load_id AND e.assignment_key=a.assignment_key "
                    "WHERE a.load_id=%s AND a.assignment_key=%s",
                    (load_id, assignment_key),
                ).fetchone()
                self.assertEqual((assignment_confidence, exposure_confidence), ("medium", "medium"))
            finally:
                with connection.transaction():
                    connection.execute(
                        "DELETE FROM serving_coach_exposures "
                        "WHERE load_id=%s AND assignment_key=%s",
                        (load_id, assignment_key),
                    )
                    connection.execute(
                        "DELETE FROM serving_coach_citations "
                        "WHERE load_id=%s AND assignment_key=%s",
                        (load_id, assignment_key),
                    )
                    connection.execute(
                        "DELETE FROM serving_coach_assignments "
                        "WHERE load_id=%s AND assignment_key=%s",
                        (load_id, assignment_key),
                    )
                    connection.execute(
                        "DELETE FROM serving_qb_seasons WHERE load_id=%s AND player_id=%s",
                        (load_id, player_id),
                    )
                    connection.execute(
                        "DELETE FROM serving_players WHERE load_id=%s AND player_id=%s",
                        (load_id, player_id),
                    )
                    connection.execute(
                        "DELETE FROM serving_coaches WHERE load_id=%s AND coach_id IN (%s,%s)",
                        (load_id, coach_id, alternate_coach_id),
                    )
                    connection.execute(
                        "DELETE FROM serving_teams WHERE load_id=%s AND team_id IN (%s,%s)",
                        (load_id, team_id, alternate_team_id),
                    )

    def test_interval_basis_shared_duty_and_warmup_filter(self) -> None:
        with psycopg.connect(self.url) as connection:
            bases = connection.execute(
                "SELECT DISTINCT interval_basis::text FROM serving_coach_assignments"
            ).fetchall()
            shared = connection.execute(
                "SELECT count(*) FROM serving_coach_assignments WHERE is_shared"
            ).fetchone()[0]
            warmup = connection.execute(
                "SELECT count(*) FROM api_qb_statistics WHERE season < 2010"
            ).fetchone()[0]
        self.assertIn(("dated_source_weeks",), bases)
        self.assertGreater(shared, 0)
        self.assertEqual(warmup, 0)

    def test_out_of_sample_warmup_pae_is_not_published(self) -> None:
        with psycopg.connect(self.url) as connection:
            load_id = connection.execute("SELECT load_id FROM serving_publication").fetchone()[0]
            team_id = connection.execute(
                "SELECT team_id FROM serving_teams WHERE load_id = %s LIMIT 1", (load_id,)
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO serving_players VALUES (%s,'warmup-qb','Warmup QB','QB','{}')",
                (load_id,),
            )
            connection.execute(
                "INSERT INTO serving_qb_seasons VALUES "
                "(%s,'warmup-qb',%s,2009,'warmup',1,1,10,.1,NULL,.5,.1,false,'test','{}')",
                (load_id, team_id),
            )
            connection.execute(
                "INSERT INTO serving_qb_pae VALUES "
                "(%s,'warmup-qb',%s,2009,'test','test',0,.1,.1,NULL,NULL,"
                "'small_sample','low',true,'{}')",
                (load_id, team_id),
            )
            visible = connection.execute(
                "SELECT count(*) FROM api_qb_pae WHERE player_id = 'warmup-qb'"
            ).fetchone()[0]
            self.assertEqual(visible, 0)
            connection.rollback()

    def test_manual_input_change_creates_new_load_and_rebuilds(self) -> None:
        database = f"nfl_c7_manual_{secrets.token_hex(5)}"
        url = self._create_database(database)
        try:
            initial = load_serving_database(url, ROOT)
            from nfl_coaching_impact import serving

            with tempfile.TemporaryDirectory(prefix="c7-manual-") as directory:
                changed_root = self._copy_project_inputs(directory)
                coaches_path = changed_root / "data/manual/coaches.csv"
                coaches_path.write_text(
                    coaches_path.read_text(encoding="utf-8").replace(
                        "Aaron Glenn,aaron-glenn", "Aaron Glenn Snapshot,aaron-glenn", 1
                    ),
                    encoding="utf-8",
                )
                snapshot = serving._manual_snapshot(changed_root)
                rebuilt = load_serving_database(url, changed_root)
                self.assertNotEqual(initial.load_id, rebuilt.load_id)
                self.assertFalse(rebuilt.reused_existing)
                with psycopg.connect(url) as connection:
                    self.assertEqual(
                        connection.execute("SELECT count(*) FROM serving_loads").fetchone()[0], 2
                    )
                    digest, manifest_digest, canonical_name = connection.execute(
                        "SELECT l.manual_manifest_sha256, m.manifest->>'sha256', c.canonical_name "
                        "FROM serving_loads l JOIN serving_pipeline_manifests m "
                        "ON m.load_id=l.load_id AND m.pipeline_name='manual_inputs' "
                        "JOIN serving_coaches c ON c.load_id=l.load_id "
                        "WHERE l.load_id=%s AND c.coach_id='coach-aaron-glenn'",
                        (rebuilt.load_id,),
                    ).fetchone()
                    self.assertEqual((digest, manifest_digest), (snapshot.digest, snapshot.digest))
                    self.assertEqual(canonical_name, "Aaron Glenn Snapshot")
        finally:
            self._drop_database(database)

    def test_midload_manual_change_fails_closed_and_restarts_with_exact_bytes(self) -> None:
        database = f"nfl_c7_manual_race_{secrets.token_hex(5)}"
        url = self._create_database(database)
        try:
            initial = load_serving_database(url, ROOT)
            from nfl_coaching_impact import serving

            with tempfile.TemporaryDirectory(prefix="c7-manual-race-") as directory:
                changed_root = self._copy_project_inputs(directory)
                coaches_path = changed_root / "data/manual/coaches.csv"
                coaches_path.write_text(
                    coaches_path.read_text(encoding="utf-8").replace(
                        "Aaron Glenn,aaron-glenn", "Aaron Glenn Candidate,aaron-glenn", 1
                    ),
                    encoding="utf-8",
                )
                candidate_snapshot = serving._manual_snapshot(changed_root)
                versions, _, _ = serving._source_tables(changed_root)
                candidate_load_id = serving._serving_load_id(versions, candidate_snapshot.digest)
                original_insert = serving._insert_frames

                def mutate_then_insert(*args, **kwargs):
                    coaches_path.write_text(
                        coaches_path.read_text(encoding="utf-8").replace(
                            "Aaron Glenn Candidate,aaron-glenn",
                            "Aaron Glenn Restarted,aaron-glenn",
                            1,
                        ),
                        encoding="utf-8",
                    )
                    return original_insert(*args, **kwargs)

                with (
                    patch.object(serving, "_insert_frames", side_effect=mutate_then_insert),
                    self.assertRaises(PipelineError),
                ):
                    load_serving_database(url, changed_root)
                with psycopg.connect(url) as connection:
                    self.assertEqual(
                        str(
                            connection.execute(
                                "SELECT load_id FROM serving_publication"
                            ).fetchone()[0]
                        ),
                        initial.load_id,
                    )
                    self.assertEqual(
                        connection.execute(
                            "SELECT count(*) FROM serving_loads WHERE load_id=%s",
                            (candidate_load_id,),
                        ).fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        connection.execute(
                            "SELECT count(*) FROM serving_coaches WHERE load_id=%s",
                            (candidate_load_id,),
                        ).fetchone()[0],
                        0,
                    )
                restarted_snapshot = serving._manual_snapshot(changed_root)
                restarted = load_serving_database(url, changed_root)
                self.assertEqual(
                    restarted.load_id,
                    str(serving._serving_load_id(versions, restarted_snapshot.digest)),
                )
                with psycopg.connect(url) as connection:
                    digest, canonical_name = connection.execute(
                        "SELECT l.manual_manifest_sha256, c.canonical_name "
                        "FROM serving_loads l JOIN serving_coaches c ON c.load_id=l.load_id "
                        "WHERE l.load_id=%s AND c.coach_id='coach-aaron-glenn'",
                        (restarted.load_id,),
                    ).fetchone()
                    self.assertEqual(digest, restarted_snapshot.digest)
                    self.assertEqual(canonical_name, "Aaron Glenn Restarted")
        finally:
            self._drop_database(database)

    def test_revision_uses_immutable_snapshot(self) -> None:
        revision = (ROOT / "db/migrations/versions/0001_checkpoint7_schema.py").read_text()
        self.assertIn("0001_checkpoint7_schema.sql", revision)
        self.assertNotIn('parents[2] / "schema.sql"', revision)
        snapshot = ROOT / "db/migrations/versions/0001_checkpoint7_schema.sql"
        self.assertTrue(snapshot.is_file())
        self.assertEqual(
            hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            "73ed452bc55d7592756dd91e2b11bfd2c543bb7cd84de3a927c70967b1149c29",
        )
        integrity_revision = ROOT / "db/migrations/versions/0002_checkpoint7_integrity.py"
        integrity_sql = ROOT / "db/migrations/versions/0002_checkpoint7_integrity.sql"
        self.assertTrue(integrity_revision.is_file())
        self.assertTrue(integrity_sql.is_file())
        self.assertIn("0002_checkpoint7_integrity.sql", integrity_revision.read_text())

    def test_model_version_mismatch_fails_before_loading(self) -> None:
        from nfl_coaching_impact import serving

        versions, frames, _ = serving._source_tables(ROOT)
        altered = frames.copy()
        altered["coach_effects"] = (
            frames["coach_effects"]
            .with_columns(psycopg_model=frames["coach_effects"]["coach_model_version"])
            .drop("coach_model_version")
            .rename({"psycopg_model": "coach_model_version"})
        )
        altered["coach_effects"] = altered["coach_effects"].with_columns(
            coach_model_version=altered["coach_effects"]["coach_model_version"].replace(
                versions.coach_model, "wrong-model"
            )
        )
        with self.assertRaises(PipelineError):
            serving._validate_version_contracts(altered, versions)

    def test_failed_load_preserves_existing_publication(self) -> None:
        with psycopg.connect(self.url) as connection:
            old_load = connection.execute("SELECT load_id FROM serving_publication").fetchone()[0]
            old_team_count = connection.execute(
                "SELECT count(*) FROM serving_teams WHERE load_id = %s", (old_load,)
            ).fetchone()[0]
            old_load_count = connection.execute("SELECT count(*) FROM serving_loads").fetchone()[0]
        from nfl_coaching_impact import serving

        def insert_then_fail(connection, load_id, *_args):
            connection.execute(
                "INSERT INTO serving_teams VALUES (%s,'partial','PAR','Partial',NULL,'{}')",
                (load_id,),
            )
            raise RuntimeError("boom")

        with tempfile.TemporaryDirectory(prefix="c7-rollback-") as directory:
            changed_root = self._copy_project_inputs(directory)
            coaches_path = changed_root / "data/manual/coaches.csv"
            coaches_path.write_text(
                coaches_path.read_text(encoding="utf-8").replace(
                    "Aaron Glenn,aaron-glenn", "Aaron Glenn Rollback,aaron-glenn", 1
                ),
                encoding="utf-8",
            )
            snapshot = serving._manual_snapshot(changed_root)
            versions, _, _ = serving._source_tables(changed_root)
            failed_load = serving._serving_load_id(versions, snapshot.digest)
            with (
                patch.object(serving, "_insert_frames", side_effect=insert_then_fail),
                self.assertRaises(RuntimeError),
            ):
                load_serving_database(self.url, changed_root)
        with psycopg.connect(self.url) as connection:
            self.assertEqual(
                connection.execute("SELECT load_id FROM serving_publication").fetchone()[0],
                old_load,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT count(*) FROM serving_teams WHERE load_id = %s", (old_load,)
                ).fetchone()[0],
                old_team_count,
            )
            self.assertEqual(
                connection.execute("SELECT count(*) FROM serving_loads").fetchone()[0],
                old_load_count,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT count(*) FROM serving_teams WHERE load_id = %s", (failed_load,)
                ).fetchone()[0],
                0,
            )

    def test_citation_reassignment_cannot_orphan_verified_assignment(self) -> None:
        with psycopg.connect(self.url) as connection:
            source, target = connection.execute(
                "SELECT c.load_id, c.assignment_key, min(c.source_url) "
                "FROM serving_coach_citations c JOIN serving_coach_assignments a "
                "ON a.load_id=c.load_id AND a.assignment_key=c.assignment_key "
                "WHERE a.verification_status='verified' GROUP BY c.load_id,c.assignment_key "
                "HAVING count(*)=1 ORDER BY c.assignment_key LIMIT 2"
            ).fetchall()
            connection.commit()
            with self.assertRaises(psycopg.Error):
                with connection.transaction():
                    connection.execute(
                        "UPDATE serving_coach_citations SET assignment_key=%s "
                        "WHERE load_id=%s AND assignment_key=%s AND source_url=%s",
                        (target[1], source[0], source[1], source[2]),
                    )

    def test_health_and_versions(self) -> None:
        self.assertEqual(self.client.get("/health").status_code, 200)
        response = self.client.get("/versions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["api_contract_version"], "api-v1.4")

    def test_relationship_explorer_all_modes_use_the_active_publication(self) -> None:
        with psycopg.connect(self.url) as connection:
            load_id = str(
                connection.execute("SELECT load_id FROM serving_publication").fetchone()[0]
            )
            coach_id = connection.execute(
                "SELECT coach_id FROM api_coaching_assignments ORDER BY coach_id LIMIT 1"
            ).fetchone()[0]
            player_id = connection.execute(
                "SELECT player_id FROM api_qb_statistics ORDER BY player_id LIMIT 1"
            ).fetchone()[0]
            team_id = connection.execute(
                "SELECT team_id FROM api_qb_statistics ORDER BY team_id LIMIT 1"
            ).fetchone()[0]

        requests = (
            ("coach_journey", {"coach_id": coach_id}),
            ("qb_journey", {"player_id": player_id}),
            ("team_history", {"team_id": team_id}),
            ("full_network", {"team_id": team_id}),
            ("full_network", {}),
        )
        for mode, anchor in requests:
            with self.subTest(mode=mode):
                response = self.client.get(
                    "/relationships/explorer",
                    params={
                        "mode": mode,
                        **anchor,
                        "start_season": 2024,
                        "end_season": 2025,
                        "include_provisional": True,
                    },
                )
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["query"]["mode"], mode)
                self.assertEqual(body["versions"]["load_id"], load_id)
                self.assertEqual(body["versions"]["api_contract_version"], "api-v1.4")

    def test_relationship_explorer_requires_a_bounded_valid_scope(self) -> None:
        invalid = (
            {"mode": "coach_journey"},
            {"mode": "qb_journey"},
            {"mode": "team_history"},
            {
                "mode": "team_history",
                "team_id": "missing",
                "start_season": 2025,
                "end_season": 2024,
            },
            {
                "mode": "team_history",
                "team_id": "missing",
                "verification_status": "provisional",
            },
        )
        for params in invalid:
            with self.subTest(params=params):
                self.assertEqual(
                    self.client.get("/relationships/explorer", params=params).status_code,
                    422,
                )
        self.assertEqual(
            self.client.get(
                "/relationships/explorer",
                params={"mode": "team_history", "team_id": "missing", "role": "bad"},
            ).status_code,
            422,
        )
        empty = self.client.get(
            "/relationships/explorer",
            params={"mode": "team_history", "team_id": "missing"},
        )
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["nodes"], [])
        self.assertEqual(empty.json()["relationships"], [])

    def test_full_network_returns_complete_supported_range_without_truncation(self) -> None:
        with psycopg.connect(self.url) as connection:
            assignment_keys = {
                row[0]
                for row in connection.execute(
                    "SELECT assignment_key FROM api_coaching_assignments "
                    "WHERE season BETWEEN 2010 AND 2025"
                ).fetchall()
            }
            qb_keys = {
                (row[0], row[1], row[2])
                for row in connection.execute(
                    "SELECT player_id,team_id,season FROM api_qb_statistics "
                    "WHERE season BETWEEN 2010 AND 2025"
                ).fetchall()
            }
            coach_ids = {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT coach_id FROM api_coaching_assignments "
                    "WHERE season BETWEEN 2010 AND 2025"
                ).fetchall()
            }
            player_ids = {player_id for player_id, _, _ in qb_keys}
            team_seasons = {
                (row[0], row[1])
                for row in connection.execute(
                    "SELECT team_id,season FROM api_coaching_assignments "
                    "WHERE season BETWEEN 2010 AND 2025 UNION "
                    "SELECT team_id,season FROM api_qb_statistics "
                    "WHERE season BETWEEN 2010 AND 2025"
                ).fetchall()
            }
        response = self.client.get(
            "/relationships/explorer",
            params={
                "mode": "full_network",
                "start_season": 2010,
                "end_season": 2025,
                "include_provisional": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["query"]["mode"], "full_network")
        self.assertEqual(body["query"]["start_season"], 2010)
        self.assertEqual(body["query"]["end_season"], 2025)
        self.assertEqual(body["node_count"], len(body["nodes"]))
        self.assertEqual(body["relationship_count"], len(body["relationships"]))
        self.assertEqual(body["max_nodes"], 2_000)
        self.assertEqual(body["max_relationships"], 4_000)
        returned_assignments = {
            row["assignment_key"]
            for row in body["relationships"]
            if row["relationship_type"] == "coach_assignment"
        }
        returned_qbs = {
            (row["player_id"], row["team_id"], row["season"])
            for row in body["relationships"]
            if row["relationship_type"] == "qb_team_season"
        }
        self.assertEqual(returned_assignments, assignment_keys)
        self.assertEqual(returned_qbs, qb_keys)
        self.assertEqual(body["relationship_count"], len(assignment_keys) + len(qb_keys))
        self.assertEqual(body["node_count"], len(coach_ids) + len(player_ids) + len(team_seasons))

    def test_relationship_team_anchors_preserve_qbs_independent_of_coach_filters(
        self,
    ) -> None:
        with psycopg.connect(self.url) as connection:
            role_case = connection.execute(
                "SELECT qs.load_id::text, qs.team_id, qs.season, qs.player_id, "
                "pae.expected_epa_per_dropback, pae.actual_epa_per_dropback, "
                "pae.performance_above_expectation "
                "FROM api_qb_statistics qs JOIN api_qb_pae pae "
                "ON pae.load_id=qs.load_id AND pae.player_id=qs.player_id "
                "AND pae.team_id=qs.team_id AND pae.season=qs.season "
                "WHERE NOT EXISTS (SELECT 1 FROM api_coaching_assignments a "
                "WHERE a.team_id=qs.team_id AND a.season=qs.season "
                "AND a.role='play_caller') "
                "ORDER BY qs.season, qs.team_id, qs.player_id LIMIT 1"
            ).fetchone()
            provisional_case = connection.execute(
                "SELECT qs.team_id, qs.season, min(qs.player_id) "
                "FROM api_qb_statistics qs "
                "WHERE NOT EXISTS (SELECT 1 FROM api_coaching_assignments a "
                "WHERE a.team_id=qs.team_id AND a.season=qs.season "
                "AND a.verification_status='provisional') "
                "GROUP BY qs.team_id, qs.season "
                "ORDER BY qs.season, qs.team_id LIMIT 1"
            ).fetchone()
            filtered_case = connection.execute(
                "SELECT qs.team_id, qs.season FROM api_qb_statistics qs "
                "WHERE EXISTS (SELECT 1 FROM api_coaching_assignments a "
                "WHERE a.team_id=qs.team_id AND a.season=qs.season "
                "AND a.role='head_coach' AND a.verification_status='verified') "
                "ORDER BY qs.season, qs.team_id LIMIT 1"
            ).fetchone()

        load_id, team_id, season, player_id, expected, actual, pae = role_case
        for mode in ("team_history", "full_network"):
            with self.subTest(mode=mode):
                response = self.client.get(
                    "/relationships/explorer",
                    params={
                        "mode": mode,
                        "team_id": team_id,
                        "start_season": season,
                        "end_season": season,
                        "role": "play_caller",
                        "include_provisional": True,
                    },
                )
                self.assertEqual(response.status_code, 200)
                body = response.json()
                coach_edges = [
                    row
                    for row in body["relationships"]
                    if row["relationship_type"] == "coach_assignment"
                ]
                qb_edges = [
                    row
                    for row in body["relationships"]
                    if row["relationship_type"] == "qb_team_season"
                ]
                self.assertEqual(coach_edges, [])
                target = next(row for row in qb_edges if row["player_id"] == player_id)
                self.assertEqual(target["publication_version"], load_id)
                self.assertEqual((target["team_id"], target["season"]), (team_id, season))
                self.assertAlmostEqual(target["expected_epa_per_dropback"], expected)
                self.assertAlmostEqual(target["actual_epa_per_dropback"], actual)
                self.assertAlmostEqual(target["performance_above_expectation"], pae)

        provisional_team, provisional_season, provisional_player = provisional_case
        provisional = self.client.get(
            "/relationships/explorer",
            params={
                "mode": "team_history",
                "team_id": provisional_team,
                "start_season": provisional_season,
                "end_season": provisional_season,
                "verification_status": "provisional",
                "include_provisional": True,
            },
        )
        self.assertEqual(provisional.status_code, 200)
        provisional_relationships = provisional.json()["relationships"]
        self.assertFalse(
            any(row["relationship_type"] == "coach_assignment" for row in provisional_relationships)
        )
        self.assertTrue(
            any(
                row["relationship_type"] == "qb_team_season"
                and row["player_id"] == provisional_player
                for row in provisional_relationships
            )
        )

        filtered_team, filtered_season = filtered_case
        filtered = self.client.get(
            "/relationships/explorer",
            params={
                "mode": "team_history",
                "team_id": filtered_team,
                "start_season": filtered_season,
                "end_season": filtered_season,
                "role": "head_coach",
                "verification_status": "verified",
            },
        )
        self.assertEqual(filtered.status_code, 200)
        filtered_relationships = filtered.json()["relationships"]
        filtered_coaches = [
            row for row in filtered_relationships if row["relationship_type"] == "coach_assignment"
        ]
        self.assertGreater(len(filtered_coaches), 0)
        self.assertTrue(
            all(
                row["role"] == "head_coach" and row["verification_status"] == "verified"
                for row in filtered_coaches
            )
        )
        self.assertTrue(
            any(row["relationship_type"] == "qb_team_season" for row in filtered_relationships)
        )

    def test_relationship_explorer_rejects_node_and_relationship_cap_overflow(self) -> None:
        with psycopg.connect(self.url, autocommit=True) as connection:
            load_id = connection.execute("SELECT load_id FROM serving_publication").fetchone()[0]
            team_id, season = connection.execute(
                "SELECT team_id, season FROM api_qb_statistics ORDER BY season, team_id LIMIT 1"
            ).fetchone()
            for label, count in (("nodes", 1_001), ("relationships", 2_001)):
                prefix = f"relationship-cap-{label}-{secrets.token_hex(4)}"
                player_ids = [f"{prefix}-{index:04d}" for index in range(count)]
                try:
                    with connection.transaction():
                        with connection.cursor() as cursor:
                            cursor.executemany(
                                "INSERT INTO serving_players "
                                "(load_id,player_id,display_name,position,payload) "
                                "VALUES (%s,%s,%s,'QB','{}')",
                                [
                                    (load_id, player, f"Cap Fixture {index:04d}")
                                    for index, player in enumerate(player_ids)
                                ],
                            )
                            cursor.executemany(
                                "INSERT INTO serving_qb_seasons "
                                "(load_id,player_id,team_id,season,scope,games,starts,dropbacks,"
                                "epa_per_dropback,cpoe,success_rate,sack_rate,qualifies_default,"
                                "metric_version,payload) "
                                "VALUES (%s,%s,%s,%s,'analysis',1,0,1,.01,NULL,.5,.1,false,"
                                "'cap-fixture','{}')",
                                [(load_id, player, team_id, season) for player in player_ids],
                            )
                    response = self.client.get(
                        "/relationships/explorer",
                        params={
                            "mode": "team_history",
                            "team_id": team_id,
                            "start_season": season,
                            "end_season": season,
                        },
                    )
                    self.assertEqual(response.status_code, 413)
                    self.assertEqual(
                        response.json(),
                        {"detail": "Relationship scope is too large; narrow it"},
                    )
                    self.assertNotIn("nodes", response.json())
                    self.assertNotIn("relationships", response.json())
                finally:
                    with connection.transaction():
                        connection.execute(
                            "DELETE FROM serving_qb_seasons "
                            "WHERE load_id=%s AND player_id = ANY(%s)",
                            (load_id, player_ids),
                        )
                        connection.execute(
                            "DELETE FROM serving_players WHERE load_id=%s AND player_id = ANY(%s)",
                            (load_id, player_ids),
                        )

    def test_relationship_explorer_preserves_canonical_coach_and_qb_identity(self) -> None:
        with psycopg.connect(self.url) as connection:
            coach_id = connection.execute(
                "SELECT coach_id FROM api_coaching_assignments "
                "GROUP BY coach_id HAVING count(DISTINCT season) > 1 "
                "AND count(DISTINCT team_id) > 1 ORDER BY coach_id LIMIT 1"
            ).fetchone()[0]
            player_id = connection.execute(
                "SELECT player_id FROM api_qb_statistics GROUP BY player_id "
                "HAVING count(DISTINCT season) > 1 ORDER BY player_id LIMIT 1"
            ).fetchone()[0]

        coach = self.client.get(
            "/relationships/explorer",
            params={
                "mode": "coach_journey",
                "coach_id": coach_id,
                "include_provisional": True,
            },
        )
        self.assertEqual(coach.status_code, 200)
        coach_body = coach.json()
        coach_nodes = [row for row in coach_body["nodes"] if row["node_type"] == "coach"]
        assignments = [
            row
            for row in coach_body["relationships"]
            if row["relationship_type"] == "coach_assignment"
        ]
        self.assertEqual(
            sum(row["coach_id"] == coach_id for row in coach_nodes),
            1,
        )
        self.assertGreater(len(coach_nodes), 1)
        self.assertGreater(len({row["season"] for row in assignments}), 1)
        self.assertGreater(len({row["team_id"] for row in assignments}), 1)
        self.assertEqual(len({row["assignment_key"] for row in assignments}), len(assignments))
        selected_scopes = {
            (row["team_id"], row["season"]) for row in assignments if row["coach_id"] == coach_id
        }
        supporting_assignments = [row for row in assignments if row["coach_id"] != coach_id]
        self.assertTrue(supporting_assignments)
        self.assertTrue(
            all(
                (row["team_id"], row["season"]) in selected_scopes for row in supporting_assignments
            )
        )

        qb = self.client.get(
            "/relationships/explorer",
            params={"mode": "qb_journey", "player_id": player_id},
        )
        self.assertEqual(qb.status_code, 200)
        qb_body = qb.json()
        qb_nodes = [row for row in qb_body["nodes"] if row["node_type"] == "quarterback"]
        qb_edges = [
            row for row in qb_body["relationships"] if row["relationship_type"] == "qb_team_season"
        ]
        self.assertEqual([row["player_id"] for row in qb_nodes], [player_id])
        self.assertGreater(len({row["season"] for row in qb_edges}), 1)
        self.assertEqual(
            len({(row["player_id"], row["team_id"], row["season"]) for row in qb_edges}),
            len(qb_edges),
        )

    def test_relationship_explorer_attaches_multi_team_pae_by_complete_key(self) -> None:
        with psycopg.connect(self.url) as connection:
            player_id, season = connection.execute(
                "SELECT player_id, season FROM api_qb_pae GROUP BY player_id, season "
                "HAVING count(DISTINCT team_id) > 1 ORDER BY season, player_id LIMIT 1"
            ).fetchone()
            expected = {
                row[0]: row[1:]
                for row in connection.execute(
                    "SELECT team_id, expected_epa_per_dropback, actual_epa_per_dropback, "
                    "performance_above_expectation FROM api_qb_pae "
                    "WHERE player_id=%s AND season=%s ORDER BY team_id",
                    (player_id, season),
                ).fetchall()
            }
        response = self.client.get(
            "/relationships/explorer",
            params={
                "mode": "qb_journey",
                "player_id": player_id,
                "start_season": season,
                "end_season": season,
            },
        )
        self.assertEqual(response.status_code, 200)
        edges = [
            row
            for row in response.json()["relationships"]
            if row["relationship_type"] == "qb_team_season"
        ]
        self.assertEqual({row["team_id"] for row in edges}, set(expected))
        for row in edges:
            values = expected[row["team_id"]]
            self.assertAlmostEqual(row["expected_epa_per_dropback"], values[0])
            self.assertAlmostEqual(row["actual_epa_per_dropback"], values[1])
            self.assertAlmostEqual(row["performance_above_expectation"], values[2])
            self.assertEqual(
                row["relationship_id"],
                f"qb-team-season:{player_id}:{row['team_id']}:{season}",
            )

    def test_relationship_explorer_keeps_the_pae_triplet_internally_consistent(self) -> None:
        with psycopg.connect(self.url, autocommit=True) as connection:
            (
                load_id,
                player_id,
                team_id,
                season,
                original_expected,
                original_actual,
                original_pae,
            ) = connection.execute(
                "SELECT load_id, player_id, team_id, season, "
                "expected_epa_per_dropback, actual_epa_per_dropback, "
                "performance_above_expectation "
                "FROM serving_qb_pae ORDER BY season, player_id, team_id LIMIT 1"
            ).fetchone()
            expected = 0.125
            pae_actual = -0.075
            pae = pae_actual - expected
            try:
                with connection.transaction():
                    connection.execute(
                        "UPDATE serving_qb_pae SET expected_epa_per_dropback=%s, "
                        "actual_epa_per_dropback=%s, performance_above_expectation=%s "
                        "WHERE load_id=%s AND player_id=%s AND team_id=%s AND season=%s",
                        (expected, pae_actual, pae, load_id, player_id, team_id, season),
                    )
                response = self.client.get(
                    "/relationships/explorer",
                    params={
                        "mode": "qb_journey",
                        "player_id": player_id,
                        "start_season": season,
                        "end_season": season,
                    },
                )
                self.assertEqual(response.status_code, 200)
                edge = next(
                    row
                    for row in response.json()["relationships"]
                    if row["relationship_type"] == "qb_team_season" and row["team_id"] == team_id
                )
                self.assertAlmostEqual(edge["actual_epa_per_dropback"], pae_actual)
                self.assertAlmostEqual(edge["expected_epa_per_dropback"], expected)
                self.assertAlmostEqual(edge["performance_above_expectation"], pae)
                self.assertAlmostEqual(
                    edge["actual_epa_per_dropback"] - edge["expected_epa_per_dropback"],
                    edge["performance_above_expectation"],
                )
            finally:
                with connection.transaction():
                    connection.execute(
                        "UPDATE serving_qb_pae SET expected_epa_per_dropback=%s, "
                        "actual_epa_per_dropback=%s, performance_above_expectation=%s "
                        "WHERE load_id=%s "
                        "AND player_id=%s AND team_id=%s AND season=%s",
                        (
                            original_expected,
                            original_actual,
                            original_pae,
                            load_id,
                            player_id,
                            team_id,
                            season,
                        ),
                    )

    def test_relationship_explorer_preserves_interval_and_evidence_states(self) -> None:
        with psycopg.connect(self.url) as connection:
            oc_team, oc_season = connection.execute(
                "SELECT team_id, season FROM api_coaching_assignments "
                "WHERE role='offensive_coordinator' GROUP BY team_id, season "
                "HAVING count(*) > 1 "
                "ORDER BY season, team_id LIMIT 1"
            ).fetchone()
            interim_team, interim_season, interim_key = connection.execute(
                "SELECT team_id, season, assignment_key FROM api_coaching_assignments "
                "WHERE is_interim ORDER BY season, team_id, assignment_key LIMIT 1"
            ).fetchone()
            shared_team, shared_season, shared_key = connection.execute(
                "SELECT team_id, season, assignment_key FROM api_coaching_assignments "
                "WHERE is_shared ORDER BY season, team_id, assignment_key LIMIT 1"
            ).fetchone()
            mixed_team, mixed_season = connection.execute(
                "SELECT team_id, season FROM api_coaching_assignments "
                "GROUP BY team_id, season HAVING bool_or(verification_status='verified') "
                "AND bool_or(verification_status='provisional') "
                "ORDER BY season, team_id LIMIT 1"
            ).fetchone()

        def assignment_edges(team_id: str, season: int) -> dict[str, dict[str, object]]:
            response = self.client.get(
                "/relationships/explorer",
                params={
                    "mode": "team_history",
                    "team_id": team_id,
                    "start_season": season,
                    "end_season": season,
                    "include_provisional": True,
                },
            )
            self.assertEqual(response.status_code, 200)
            return {
                row["assignment_key"]: row
                for row in response.json()["relationships"]
                if row["relationship_type"] == "coach_assignment"
            }

        oc_edges = assignment_edges(oc_team, oc_season)
        self.assertGreater(
            len([row for row in oc_edges.values() if row["role"] == "offensive_coordinator"]),
            1,
        )
        self.assertGreater(
            len(
                {
                    (row["start_week"], row["end_week"])
                    for row in oc_edges.values()
                    if row["role"] == "offensive_coordinator"
                }
            ),
            1,
        )
        interim_edges = assignment_edges(interim_team, interim_season)
        self.assertTrue(interim_edges[interim_key]["is_interim"])
        shared_edges = assignment_edges(shared_team, shared_season)
        self.assertTrue(shared_edges[shared_key]["is_shared"])
        mixed_edges = assignment_edges(mixed_team, mixed_season)
        self.assertTrue(
            {"verified", "provisional"}
            <= {str(row["verification_status"]) for row in mixed_edges.values()}
        )
        self.assertTrue(
            all(row["relationship_id"] == row["assignment_key"] for row in mixed_edges.values())
        )
        self.assertTrue(
            all(
                row["citations"]
                for row in mixed_edges.values()
                if row["verification_status"] == "verified"
            )
        )

    def test_relationship_explorer_preserves_missing_pae_and_distinct_sample_labels(self) -> None:
        suffix = secrets.token_hex(5)
        player_id = f"relationship-missing-pae-{suffix}"
        with psycopg.connect(self.url, autocommit=True) as connection:
            load_id = connection.execute("SELECT load_id FROM serving_publication").fetchone()[0]
            team_id, season = connection.execute(
                "SELECT team_id, season FROM api_coaching_assignments "
                "ORDER BY season DESC, team_id LIMIT 1"
            ).fetchone()
            try:
                with connection.transaction():
                    connection.execute(
                        "INSERT INTO serving_players VALUES (%s,%s,'Missing PAE QB','QB','{}')",
                        (load_id, player_id),
                    )
                    connection.execute(
                        "INSERT INTO serving_qb_seasons VALUES "
                        "(%s,%s,%s,%s,'analysis',1,0,12,.025,NULL,.5,.1,false,'fixture','{}')",
                        (load_id, player_id, team_id, season),
                    )
                response = self.client.get(
                    "/relationships/explorer",
                    params={
                        "mode": "qb_journey",
                        "player_id": player_id,
                        "start_season": season,
                        "end_season": season,
                    },
                )
                self.assertEqual(response.status_code, 200)
                edge = next(
                    row
                    for row in response.json()["relationships"]
                    if row["relationship_type"] == "qb_team_season"
                )
                self.assertEqual(edge["actual_epa_per_dropback"], 0.025)
                self.assertIsNone(edge["expected_epa_per_dropback"])
                self.assertIsNone(edge["performance_above_expectation"])
                self.assertIsNone(edge["eligibility_status"])
                self.assertIsNone(edge["reliability"])
                self.assertFalse(edge["qualifies_default"])
            finally:
                with connection.transaction():
                    connection.execute(
                        "DELETE FROM serving_qb_seasons WHERE load_id=%s AND player_id=%s",
                        (load_id, player_id),
                    )
                    connection.execute(
                        "DELETE FROM serving_players WHERE load_id=%s AND player_id=%s",
                        (load_id, player_id),
                    )

    def test_relationship_explorer_is_deterministic_versioned_and_noncausal(self) -> None:
        with psycopg.connect(self.url) as connection:
            team_id = connection.execute(
                "SELECT team_id FROM api_coaching_assignments ORDER BY team_id LIMIT 1"
            ).fetchone()[0]
            load_id = str(
                connection.execute("SELECT load_id FROM serving_publication").fetchone()[0]
            )
        params = {
            "mode": "team_history",
            "team_id": team_id,
            "start_season": 2020,
            "end_season": 2025,
            "include_provisional": True,
        }
        first = self.client.get("/relationships/explorer", params=params)
        second = self.client.get("/relationships/explorer", params=params)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        body = first.json()
        self.assertFalse(body["semantics"]["exact_weekly_overlap"])
        self.assertIn("within the same season", body["semantics"]["coach_qb_context"])
        self.assertEqual(body["versions"]["load_id"], load_id)
        self.assertEqual(body["versions"]["api_contract_version"], "api-v1.4")
        node_ids = [row["node_id"] for row in body["nodes"]]
        relationship_ids = [row["relationship_id"] for row in body["relationships"]]
        self.assertEqual(len(node_ids), len(set(node_ids)))
        self.assertEqual(len(relationship_ids), len(set(relationship_ids)))
        self.assertTrue(all(row["publication_version"] == load_id for row in body["relationships"]))

    def test_qb_search_profile_pae_filters_and_sorting(self) -> None:
        page = self.client.get("/qbs", params={"search": "Brady", "limit": 2, "sort": "season"})
        self.assertEqual(page.status_code, 200)
        self.assertGreater(page.json()["total"], 0)
        player_id = page.json()["items"][0]["player_id"]
        self.assertEqual(self.client.get(f"/qbs/{player_id}").status_code, 200)
        self.assertEqual(self.client.get(f"/qbs/{player_id}/pae").status_code, 200)

    def test_coach_team_assignment_network_citation_and_review_endpoints(self) -> None:
        coaches = self.client.get("/coaches", params={"limit": 1}).json()
        coach_id = coaches["items"][0]["coach_id"]
        self.assertEqual(self.client.get(f"/coaches/{coach_id}").status_code, 200)
        for endpoint in (
            "/coach-impact",
            "/teams",
            "/assignments",
            "/network/nodes",
            "/network/edges",
            "/citations",
            "/review-queue/summary",
        ):
            response = self.client.get(endpoint, params={"limit": 1})
            self.assertEqual(response.status_code, 200, endpoint)
            self.assertIn("items", response.json())

    def test_pagination_validation_empty_and_not_found(self) -> None:
        first = self.client.get("/teams", params={"limit": 1, "offset": 0}).json()
        second = self.client.get("/teams", params={"limit": 1, "offset": 1}).json()
        self.assertNotEqual(first["items"], second["items"])
        self.assertEqual(self.client.get("/teams", params={"limit": 0}).status_code, 422)
        self.assertEqual(self.client.get("/qbs/not-a-player").status_code, 404)
        self.assertEqual(
            self.client.get("/qbs", params={"search": "zzzz-no-match"}).json()["items"], []
        )

    def test_total_ordering_prevents_cross_page_duplicates(self) -> None:
        cases = (
            (
                "/qbs",
                {"sort": "dropbacks"},
                lambda row: (row["player_id"], row["team_id"], row["season"]),
            ),
            (
                "/qbs",
                {"sort": "epa"},
                lambda row: (row["player_id"], row["team_id"], row["season"]),
            ),
            ("/coach-impact", {"sort": "effect"}, lambda row: (row["coach_id"], row["role"])),
            ("/assignments", {}, lambda row: row["assignment_key"]),
            ("/citations", {}, lambda row: (row["assignment_key"], row["source_url"])),
            (
                "/network/edges",
                {},
                lambda row: (row["source_assignment_key"], row["target_assignment_key"]),
            ),
        )
        for endpoint, params, key in cases:
            with self.subTest(endpoint=endpoint, params=params):
                first = self.client.get(
                    endpoint, params={**params, "limit": 25, "offset": 0}
                ).json()["items"]
                second = self.client.get(
                    endpoint, params={**params, "limit": 25, "offset": 25}
                ).json()["items"]
                repeat = self.client.get(
                    endpoint, params={**params, "limit": 25, "offset": 0}
                ).json()["items"]
                self.assertEqual(first, repeat)
                self.assertFalse(set(map(key, first)) & set(map(key, second)))

    def test_role_status_filters_validate_and_filter(self) -> None:
        valid_cases = (
            ("/coaches", {"role": "head_coach"}, "role", "head_coach"),
            ("/coach-impact", {"role": "head_coach"}, "role", "head_coach"),
            (
                "/assignments",
                {"verification_status": "verified"},
                "verification_status",
                "verified",
            ),
            (
                "/review-queue/summary",
                {"role": "play_caller", "status": "open"},
                "role",
                "play_caller",
            ),
        )
        for endpoint, params, field, expected in valid_cases:
            response = self.client.get(endpoint, params=params)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["items"])
            self.assertTrue(all(str(row[field]) == expected for row in response.json()["items"]))
        for endpoint in ("/coaches", "/coach-impact", "/assignments", "/review-queue/summary"):
            self.assertEqual(
                self.client.get(endpoint, params={"role": "not-a-role"}).status_code, 422
            )
        self.assertEqual(
            self.client.get(
                "/assignments", params={"verification_status": "not-a-status"}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.get("/review-queue/summary", params={"status": "not-a-status"}).status_code,
            422,
        )
        self.assertEqual(
            self.client.get(
                "/network/edges", params={"verification_status": "not-a-status"}
            ).status_code,
            422,
        )

    def test_network_edges_preserve_verification_and_interval_metadata(self) -> None:
        verified = self.client.get(
            "/network/edges", params={"verification_status": "verified", "limit": 20}
        )
        self.assertEqual(verified.status_code, 200)
        self.assertTrue(verified.json()["items"])
        required = {
            "source_verification_status",
            "target_verification_status",
            "source_confidence_level",
            "target_confidence_level",
            "source_start_week",
            "source_end_week",
            "target_start_week",
            "target_end_week",
            "overlap_start_week",
            "overlap_end_week",
            "source_is_shared",
            "target_is_shared",
            "source_is_provisional",
            "target_is_provisional",
        }
        for row in verified.json()["items"]:
            self.assertTrue(required <= row.keys())
            self.assertEqual(str(row["source_verification_status"]), "verified")
            self.assertEqual(str(row["target_verification_status"]), "verified")
        provisional = self.client.get(
            "/network/edges", params={"verification_status": "provisional", "limit": 20}
        ).json()["items"]
        self.assertTrue(provisional)
        self.assertTrue(
            all(
                row["source_is_provisional"] and row["target_is_provisional"] for row in provisional
            )
        )

    def test_exploratory_and_suppressed_labels_are_preserved(self) -> None:
        data = self.client.get("/coach-impact", params={"eligible": False, "limit": 200}).json()
        self.assertTrue(data["items"])
        self.assertTrue(all("identification_status" in row for row in data["items"]))
        self.assertTrue(all("ranking_status" in row for row in data["items"]))
