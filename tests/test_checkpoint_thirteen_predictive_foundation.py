from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import polars as pl

from nfl_coaching_impact.predictive_foundation import (
    CORE_FEATURES,
    EXPECTED_PASS_MODEL_VERSION,
    EXPERIMENTAL_FEATURES,
    FEATURE_BUILD_VERSION,
    MISSINGNESS_REASONS,
    PERSONNEL_GROUPS,
    SUPPORTED_ENTITY_TYPES,
    AsOfFeatureStore,
    FeatureDefinition,
    HistoricalStandardizer,
    _content_identity,
    _registry_from_checkpoint_twelve,
    _write_csv,
    build_coach_scheme_associations,
    build_expected_pass_profiles,
    run_checkpoint_thirteen,
    validate_feature_records,
    validate_feature_registry,
)
from research.coach_effect.checkpoint_twelve_data_expansion import (
    build_ftn_profiles,
    build_participation_profiles,
    build_pbp_profiles,
    parse_offense_personnel,
)


def _availability_fixture() -> pl.DataFrame:
    rows = []
    features = {
        **{name: ("qb_usage", "nflverse_pbp", 2010, 2025) for name in CORE_FEATURES},
        **{
            f"personnel_{group}_rate": ("personnel_group", "nflverse_participation", 2016, 2025)
            for group in PERSONNEL_GROUPS
        },
        **{
            name: ("mechanic", "nflverse_ftn_charting", 2022, 2025)
            for name in EXPERIMENTAL_FEATURES
            if not name.startswith("q_")
        },
        "expected_pass_rate": ("tendency", "nflverse_pbp", 2010, 2025),
        "proe_mean": ("tendency", "nflverse_pbp", 2010, 2025),
        "designed_qb_run_rate": ("qb_usage", "none", None, None),
    }
    for name, (family, source, first, last) in features.items():
        rows.append(
            {
                "feature_name": name,
                "profile_family": family,
                "source_dataset": source,
                "source_fields": "explicit_fixture_field",
                "first_season": first,
                "last_season": last,
            }
        )
    return pl.DataFrame(rows)


def _registry() -> tuple[FeatureDefinition, ...]:
    return _registry_from_checkpoint_twelve(_availability_fixture())


def _record(registry: tuple[FeatureDefinition, ...], **updates: object) -> pl.DataFrame:
    definition = next(item for item in registry if item.name == "shotgun_rate")
    row = {
        "entity_type": "scheme-team-season",
        "entity_id": "team:ARI:season:2024",
        "feature_name": "shotgun_rate",
        "feature_value": 0.5,
        "raw_value": 0.7,
        "source_season": 2023,
        "target_season": 2024,
        "as_of_date": "2024-08-31",
        "source_available_date": "2024-08-31",
        "source_dataset": "nflverse_pbp",
        "source_version": "fixture-v1",
        "source_hash": "a" * 64,
        "intermediate_artifact": "fixture.csv",
        "intermediate_hash": "b" * 64,
        "feature_definition_version": definition.definition_version,
        "feature_build_version": FEATURE_BUILD_VERSION,
        "model_version": None,
        "sample_size": 100.0,
        "exposure": 100.0,
        "missingness_reason": None,
        "timing_class": definition.timing_class,
        "feature_status": definition.status,
        "predictive_permission": definition.predictive_permission,
        "standardization_method": "fixture",
        "standardization_fit_start_season": 2019,
        "standardization_fit_end_season": 2023,
        "standardization_mean": 0.5,
        "standardization_std": 0.1,
    }
    row.update(updates)
    return pl.DataFrame([row], infer_schema_length=None)


def _pbp_fixture() -> pl.DataFrame:
    rows = []
    for season in range(2005, 2012):
        for play_id in range(1, 9):
            rows.append(
                {
                    "season": season,
                    "season_type": "REG",
                    "posteam": "ARI",
                    "play_type": "pass" if play_id <= (5 if season < 2011 else 8) else "run",
                    "two_point_attempt": 0,
                    "qb_kneel": 0,
                    "down": 1 if play_id % 2 else 2,
                    "qtr": 1,
                    "ydstogo": 10,
                    "yardline_100": 50.0,
                    "score_differential": 0.0,
                }
            )
    return pl.DataFrame(rows)


def _scheme_pbp_fixture() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "game_id": "2022_01_ARI_ATL",
                "play_id": 1,
                "season": 2022,
                "season_type": "REG",
                "week": 1,
                "posteam": "ARI",
                "team_id": "ARI",
                "play_type": "pass",
                "two_point_attempt": 0,
                "epa": 1.0,
                "success": 1.0,
                "down": 1,
                "qtr": 1,
                "yardline_100": 50.0,
                "game_seconds_remaining": 3000.0,
                "score_differential": 0.0,
                "pass_attempt": 1,
                "rush_attempt": 0,
                "shotgun": 1,
                "no_huddle": 1,
                "qb_dropback": 1,
                "qb_kneel": 0,
                "qb_spike": 0,
                "qb_scramble": 0,
                "sack": 0,
                "rusher_player_id": None,
                "pass_length": "short",
                "pass_location": "left",
                "air_yards": 7.0,
                "xpass": 0.7,
                "pass_oe": 0.3,
            },
            {
                "game_id": "2022_01_ARI_ATL",
                "play_id": 2,
                "season": 2022,
                "season_type": "REG",
                "week": 1,
                "posteam": "ARI",
                "team_id": "ARI",
                "play_type": "run",
                "two_point_attempt": 0,
                "epa": -0.2,
                "success": 0.0,
                "down": 2,
                "qtr": 1,
                "yardline_100": 18.0,
                "game_seconds_remaining": 2900.0,
                "score_differential": 0.0,
                "pass_attempt": 0,
                "rush_attempt": 1,
                "shotgun": 0,
                "no_huddle": 0,
                "qb_dropback": 0,
                "qb_kneel": 0,
                "qb_spike": 0,
                "qb_scramble": 0,
                "sack": 0,
                "rusher_player_id": "00-0000001",
                "pass_length": None,
                "pass_location": None,
                "air_yards": None,
                "xpass": 0.4,
                "pass_oe": -0.4,
            },
        ]
    )


class FeatureRegistryTest(unittest.TestCase):
    def test_registry_contract_and_no_composite_coach_effect(self) -> None:
        registry = _registry()
        validate_feature_registry(registry)
        self.assertEqual(
            len({(item.name, item.definition_version) for item in registry}), len(registry)
        )
        self.assertTrue({item.entity_grain for item in registry} <= SUPPORTED_ENTITY_TYPES)
        self.assertEqual(
            {item.timing_class for item in registry},
            {"HISTORICAL_PRIOR", "PRESEASON_KNOWN", "TARGET_SEASON_FORBIDDEN"},
        )
        self.assertNotIn("coach_effect", {item.name for item in registry})
        self.assertEqual(
            next(
                item for item in registry if item.name == "pcae_verified_play_caller"
            ).research_readiness,
            "RESEARCH_READY",
        )

    def test_duplicate_registry_key_fails(self) -> None:
        registry = _registry()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_feature_registry((*registry, registry[0]))

    def test_invalid_entity_and_permission_fail(self) -> None:
        definition = _registry()[0]
        with self.assertRaisesRegex(ValueError, "unsupported entity"):
            validate_feature_registry((replace(definition, entity_grain="prospect"),))
        with self.assertRaisesRegex(ValueError, "predictive permission"):
            validate_feature_registry((replace(definition, predictive_permission="MAYBE"),))  # type: ignore[arg-type]


class LeakageFoundationTest(unittest.TestCase):
    def test_prior_record_passes_and_target_or_future_rows_fail(self) -> None:
        registry = _registry()
        validate_feature_records(_record(registry), registry)
        for source_season in (2024, 2025):
            with (
                self.subTest(source_season=source_season),
                self.assertRaisesRegex(ValueError, "leakage"),
            ):
                validate_feature_records(_record(registry, source_season=source_season), registry)
        with self.assertRaisesRegex(ValueError, "standardization fit"):
            validate_feature_records(
                _record(registry, standardization_fit_end_season=2024), registry
            )
        with self.assertRaisesRegex(ValueError, "outside the registered window"):
            validate_feature_records(
                _record(registry, source_season=2009, target_season=2010), registry
            )

    def test_unregistered_feature_fails(self) -> None:
        registry = _registry()
        with self.assertRaisesRegex(ValueError, "unregistered"):
            validate_feature_records(_record(registry, feature_name="secret_feature"), registry)

    def test_null_is_not_zero_and_requires_reason(self) -> None:
        registry = _registry()
        validate_feature_records(_record(registry, feature_value=0.0), registry)
        with self.assertRaisesRegex(ValueError, "null feature"):
            validate_feature_records(_record(registry, feature_value=None), registry)
        for reason in MISSINGNESS_REASONS:
            validate_feature_records(
                _record(registry, feature_value=None, missingness_reason=reason), registry
            )

    def test_standardizer_fits_history_only(self) -> None:
        history = pl.DataFrame({"season": [2021, 2022, 2023], "raw_value": [1.0, 2.0, 3.0]})
        standardizer = HistoricalStandardizer().fit(history, target_season=2024)
        self.assertEqual(standardizer.fit_end_season_, 2023)
        self.assertAlmostEqual(
            standardizer.transform(pl.DataFrame({"raw_value": [2.0]}))["standardized_value"].item(),
            0.0,
        )
        with self.assertRaisesRegex(ValueError, "leakage"):
            HistoricalStandardizer().fit(
                history.vstack(pl.DataFrame({"season": [2024], "raw_value": [99.0]})),
                target_season=2024,
            )

    def test_expected_pass_ignores_future_season(self) -> None:
        pbp = _pbp_fixture()
        hashes = {season: str(season) * 8 for season in range(2005, 2012)}
        complete = build_expected_pass_profiles(pbp, source_hashes=hashes, source_version="fixture")
        without_future = build_expected_pass_profiles(
            pbp.filter(pl.col("season") <= 2010),
            source_hashes={key: value for key, value in hashes.items() if key <= 2010},
            source_version="fixture",
        )
        left = complete.filter(pl.col("season") == 2010).select("feature_name", "raw_value")
        right = without_future.select("feature_name", "raw_value")
        self.assertTrue(left.equals(right))
        self.assertTrue((complete["model_fit_end_season"] < complete["season"]).all())
        self.assertEqual(
            complete["model_version"].unique().to_list(), [EXPECTED_PASS_MODEL_VERSION]
        )


class SourceSemanticsTest(unittest.TestCase):
    def test_personnel_groups_fullbacks_and_impossible_values(self) -> None:
        self.assertEqual(parse_offense_personnel("1 RB, 1 TE, 3 WR")["personnel_group"], "11")
        self.assertEqual(parse_offense_personnel("1 RB, 1 FB, 1 TE, 2 WR")["personnel_group"], "21")
        self.assertIsNone(parse_offense_personnel("5 RB, 5 TE, 5 WR")["personnel_group"])

    def test_personnel_zero_is_observed_and_missing_is_absent(self) -> None:
        participation = pl.DataFrame(
            {
                "nflverse_game_id": ["2022_01_ARI_ATL", "2022_01_ARI_ATL"],
                "play_id": [1, 2],
                "possession_team": ["ARI", "ARI"],
                "offense_formation": ["SHOTGUN", "UNDER CENTER"],
                "offense_personnel": ["1 RB, 1 TE, 3 WR", "1 RB, 2 TE, 2 WR"],
                "n_offense": [11, 11],
            }
        )
        personnel, families, formations, _ = build_participation_profiles(
            participation, _scheme_pbp_fixture(), "hash"
        )
        self.assertEqual(
            personnel.filter(pl.col("feature_name") == "personnel_11_rate")["raw_value"].item(),
            0.5,
        )
        self.assertEqual(
            families.filter(pl.col("feature_name") == "personnel_family_multiple_te_rate")[
                "raw_value"
            ].item(),
            0.5,
        )
        self.assertFalse(formations["feature_name"].str.contains("personnel").any())
        self.assertFalse(personnel.filter(pl.col("season") == 2015).height)

    def test_formation_and_ftn_use_explicit_fields_only(self) -> None:
        ftn = pl.DataFrame(
            {
                "nflverse_game_id": ["2022_01_ARI_ATL", "2022_01_ARI_ATL"],
                "nflverse_play_id": [1, 2],
                "season": [2022, 2022],
                "week": [1, 1],
                "qb_location": ["S", "P"],
                "is_motion": [True, False],
                "is_play_action": [False, True],
                "is_screen_pass": [True, False],
                "is_rpo": [False, True],
            }
        )
        mechanics, formation = build_ftn_profiles(ftn, _scheme_pbp_fixture(), "hash")
        self.assertEqual(
            set(mechanics["feature_name"]),
            {"motion_rate", "play_action_rate", "rpo_rate", "screen_rate"},
        )
        self.assertEqual(
            set(formation["feature_name"]),
            {"ftn_pistol_rate", "ftn_shotgun_rate", "ftn_under_center_rate"},
        )
        self.assertTrue((mechanics["season"] >= 2022).all())

    def test_tendencies_depth_air_yards_scramble_and_situations(self) -> None:
        pbp = _scheme_pbp_fixture()
        third_down = {**pbp.row(0, named=True), "play_id": 3, "down": 3}
        fourth_down = {
            **pbp.row(1, named=True),
            "play_id": 4,
            "down": 4,
            "play_type": "punt",
            "rush_attempt": 0,
        }
        pbp = pbp.vstack(pl.DataFrame([third_down, fourth_down], infer_schema_length=None))
        tendency, qb_usage, situation, outcome = build_pbp_profiles(pbp, {"fixture": "hash"})
        self.assertTrue(
            {"pass_rate", "no_huddle_rate", "shotgun_rate"} <= set(tendency["feature_name"])
        )
        self.assertTrue(
            {"target_depth_short_rate", "average_air_yards", "scramble_rate"}
            <= set(qb_usage["feature_name"])
        )
        self.assertTrue(
            {
                "early_down_pass_rate",
                "neutral_pass_rate",
                "red_zone_pass_rate",
                "third_down_pass_rate",
                "fourth_down_go_rate",
            }
            <= set(situation["feature_name"])
        )
        self.assertTrue(set(outcome["profile_family"]) == {"outcome"})

    def test_coach_association_preserves_assignment_grain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pl.DataFrame(
                [
                    {
                        "assignment_key": "a1",
                        "season": 2022,
                        "team_id": "ARI",
                        "coach_id": "coach-a",
                        "coach_canonical_name": "Coach A",
                        "role": "play_caller",
                        "start_week": 1,
                        "end_week": 8,
                        "start_date": "",
                        "end_date": "",
                        "is_interim": False,
                        "is_shared": False,
                        "is_retained": False,
                        "verification_status": "verified",
                        "confidence_level": "high",
                        "interval_basis": "source_verified_weeks",
                        "primary_source_url": "https://example.test",
                    },
                    {
                        "assignment_key": "a2",
                        "season": 2022,
                        "team_id": "ARI",
                        "coach_id": "coach-b",
                        "coach_canonical_name": "Coach B",
                        "role": "play_caller",
                        "start_week": 9,
                        "end_week": 18,
                        "start_date": "",
                        "end_date": "",
                        "is_interim": False,
                        "is_shared": False,
                        "is_retained": False,
                        "verification_status": "verified",
                        "confidence_level": "high",
                        "interval_basis": "source_verified_weeks",
                        "primary_source_url": "https://example.test",
                    },
                ]
            ).write_csv(root / "coach_role_scheme_associations.csv")
            scheme = pl.DataFrame(
                {
                    "team_id": ["ARI"],
                    "season": [2022],
                    "feature_name": ["shotgun_rate"],
                    "raw_value": [0.7],
                }
            )
            result = build_coach_scheme_associations(root, scheme)
            self.assertEqual(result.select("assignment_key", "feature_name").n_unique(), 2)
            self.assertEqual(result["assignment_week_exposure"].to_list(), [8, 10])
            self.assertFalse(result["exact_weekly_scheme_ownership"].any())


class DeterminismAndAccessTest(unittest.TestCase):
    def test_identity_and_csv_are_deterministic(self) -> None:
        registry = _registry()
        left, _ = _content_identity(inputs={"b": "2", "a": "1"}, registry=registry, code_hash="x")
        right, _ = _content_identity(inputs={"a": "1", "b": "2"}, registry=registry, code_hash="x")
        self.assertEqual(left, right)
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            frame = pl.DataFrame({"b": [2, 1], "a": [0.123456789012, 2.0]}).sort("b")
            _write_csv(frame, Path(first) / "artifact.csv")
            _write_csv(frame, Path(second) / "artifact.csv")
            self.assertEqual(
                (Path(first) / "artifact.csv").read_bytes(),
                (Path(second) / "artifact.csv").read_bytes(),
            )

    def test_asof_store_rejects_unregistered_and_reports_version_metadata(self) -> None:
        registry = _registry()
        records = _record(registry)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_csv(records, root / "predictive_feature_records.csv")
            pl.DataFrame([definition.__dict__ for definition in registry]).write_csv(
                root / "feature_registry.csv"
            )
            (root / "MANIFEST.json").write_text(
                json.dumps(
                    {"feature_set_version": FEATURE_BUILD_VERSION, "data_version": "c13-fixture"}
                ),
                encoding="utf-8",
            )
            store = AsOfFeatureStore(root)
            matrix = store.target_matrix(target_season=2024, feature_names=["shotgun_rate"])
            self.assertEqual(matrix.maximum_source_season, 2023)
            self.assertEqual(matrix.data_version, "c13-fixture")
            with self.assertRaisesRegex(ValueError, "unregistered"):
                store.target_matrix(target_season=2024, feature_names=["not_registered"])

    def test_two_independent_full_builds_are_byte_identical(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            left = run_checkpoint_thirteen(project_root, Path(first))
            right = run_checkpoint_thirteen(project_root, Path(second))
            self.assertEqual(left.data_version, right.data_version)
            left_files = sorted(
                path.relative_to(Path(first)) for path in Path(first).rglob("*") if path.is_file()
            )
            right_files = sorted(
                path.relative_to(Path(second)) for path in Path(second).rglob("*") if path.is_file()
            )
            self.assertEqual(left_files, right_files)
            for relative in left_files:
                self.assertEqual(
                    (Path(first) / relative).read_bytes(),
                    (Path(second) / relative).read_bytes(),
                    str(relative),
                )


if __name__ == "__main__":
    unittest.main()
