from __future__ import annotations

import os
import secrets
import shutil
import tempfile
import unittest
import uuid
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
from nfl_coaching_impact.serving import (
    API_CONTRACT_VERSION,
    LOADER_VERSION,
    PUBLICATION_NAMESPACE,
    SCHEMA_VERSION,
    load_serving_database,
)

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
                "api_coach_comparisons",
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
        self.assertEqual(manifest_count, 4)

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
                changed_root = Path(directory)
                shutil.copytree(ROOT / "data/manual", changed_root / "data/manual")
                coaches_path = changed_root / "data/manual/coaches.csv"
                coaches_path.write_text(
                    coaches_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
                )
                changed_digest, changed_records, changed_paths = serving._manual_manifest(
                    changed_root
                )
                with patch.object(
                    serving,
                    "_manual_manifest",
                    return_value=(changed_digest, changed_records, changed_paths),
                ):
                    rebuilt = load_serving_database(url, ROOT)
            self.assertNotEqual(initial.load_id, rebuilt.load_id)
            self.assertFalse(rebuilt.reused_existing)
            with psycopg.connect(url) as connection:
                self.assertEqual(
                    connection.execute("SELECT count(*) FROM serving_loads").fetchone()[0], 2
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT count(*) FROM serving_pipeline_manifests "
                        "WHERE pipeline_name = 'manual_inputs'"
                    ).fetchone()[0],
                    2,
                )
        finally:
            self._drop_database(database)

    def test_revision_uses_immutable_snapshot(self) -> None:
        revision = (ROOT / "db/migrations/versions/0001_checkpoint7_schema.py").read_text()
        self.assertIn("0001_checkpoint7_schema.sql", revision)
        self.assertNotIn('parents[2] / "schema.sql"', revision)
        self.assertTrue((ROOT / "db/migrations/versions/0001_checkpoint7_schema.sql").is_file())

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

        digest, records, paths = serving._manual_manifest(ROOT)
        failed_digest = "failed-" + digest
        identity = "|".join(
            (
                SCHEMA_VERSION,
                LOADER_VERSION,
                API_CONTRACT_VERSION,
                *self.first.versions.__dict__.values(),
                failed_digest,
            )
        )
        failed_load = uuid.uuid5(PUBLICATION_NAMESPACE, identity)

        def insert_then_fail(connection, load_id, *_args):
            connection.execute(
                "INSERT INTO serving_teams VALUES (%s,'partial','PAR','Partial',NULL,'{}')",
                (load_id,),
            )
            raise RuntimeError("boom")

        with (
            patch.object(serving, "_manual_manifest", return_value=(failed_digest, records, paths)),
            patch.object(serving, "_insert_frames", side_effect=insert_then_fail),
            self.assertRaises(RuntimeError),
        ):
            load_serving_database(self.url, ROOT)
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
        self.assertEqual(response.json()["api_contract_version"], "api-v1.1")

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
