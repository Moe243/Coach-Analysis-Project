from __future__ import annotations

import os
import secrets
import unittest
from pathlib import Path

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

    def test_independent_clean_loads_have_identical_analytical_checksums(self) -> None:
        database = f"nfl_c7_clean_{secrets.token_hex(5)}"
        url = self._create_database(database)
        try:
            rebuilt = load_serving_database(url, ROOT)
            views = (
                "api_qb_statistics",
                "api_qb_pae",
                "api_coach_impact",
                "api_coaching_assignments",
                "api_coaching_network_edges",
                "api_source_citations",
                "api_review_queue_summary",
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
                "SELECT historical_data_version, expected_data_version, coach_data_version "
                "FROM serving_loads"
            ).fetchone()
            manifest_count = connection.execute(
                "SELECT count(*) FROM serving_pipeline_manifests"
            ).fetchone()[0]
        self.assertEqual(
            versions, ("c3-f6c1aa118ff43b90", "c5-8fd5d1aba2598c59", "c6-400a5b474aa37a35")
        )
        self.assertEqual(manifest_count, 3)

    def test_invalid_lineage_duplicate_and_fraction_are_rejected(self) -> None:
        with psycopg.connect(self.url) as connection:
            load_id = connection.execute("SELECT load_id FROM serving_publication").fetchone()[0]
            with self.assertRaises(psycopg.Error):
                with connection.transaction():
                    connection.execute(
                        "INSERT INTO serving_qb_games VALUES "
                        "(%s,'missing','missing','missing',2025,1,1,0,false,'{}')",
                        (load_id,),
                    )
            with self.assertRaises(psycopg.Error):
                with connection.transaction():
                    connection.execute(
                        "UPDATE serving_coach_exposures SET exposure_fraction = 0.5 "
                        "WHERE load_id = %s AND assignment_key = "
                        "(SELECT assignment_key FROM serving_coach_exposures LIMIT 1)",
                        (load_id,),
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

    def test_failed_load_rolls_back_without_publication(self) -> None:
        from unittest.mock import patch

        with psycopg.connect(self.url) as connection:
            connection.execute("DELETE FROM serving_publication")
            connection.execute("DELETE FROM serving_loads")
            connection.commit()
        with patch("nfl_coaching_impact.serving._insert_frames", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                load_serving_database(self.url, ROOT)
        with psycopg.connect(self.url) as connection:
            self.assertEqual(
                connection.execute("SELECT count(*) FROM serving_loads").fetchone()[0], 0
            )
            self.assertEqual(
                connection.execute("SELECT count(*) FROM serving_publication").fetchone()[0], 0
            )
        self.__class__.first = load_serving_database(self.url, ROOT)

    def test_health_and_versions(self) -> None:
        self.assertEqual(self.client.get("/health").status_code, 200)
        response = self.client.get("/versions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["api_contract_version"], "api-v1")

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

    def test_exploratory_and_suppressed_labels_are_preserved(self) -> None:
        data = self.client.get("/coach-impact", params={"eligible": False, "limit": 200}).json()
        self.assertTrue(data["items"])
        self.assertTrue(all("identification_status" in row for row in data["items"]))
        self.assertTrue(all("ranking_status" in row for row in data["items"]))
