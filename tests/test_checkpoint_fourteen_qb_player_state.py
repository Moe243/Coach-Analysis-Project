from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import polars as pl

from nfl_coaching_impact.qb_player_state import (
    _content_identity,
    _fit_prior,
    _shrink,
    add_player_season_pae,
    aggregate_qb_season_profiles,
    build_evaluation_links,
    build_qb_team_season_profiles,
    build_stability_report,
    build_state_features,
    build_state_universe,
    initial_registry,
    resolve_feature_status,
    run_checkpoint_fourteen,
    validate_state_feature_contract,
)


def _players() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "gsis_id": ["00-0000001", "00-0000002", "00-0000003", "00-0000004"],
            "display_name": ["Veteran", "Drafted Rookie", "Future QB", "Undrafted Rookie"],
            "birth_date": ["1985-01-01", "1990-01-01", "1995-01-01", "1990-05-01"],
            "position": ["QB", "QB", "QB", "QB"],
            "position_group": ["QB", "QB", "QB", "QB"],
            "draft_year": [2005, 2011, 2015, None],
            "rookie_season": [2005, 2011, 2015, 2011],
        },
        schema_overrides={"draft_year": pl.Int32},
    )


def _history() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "player_id": ["00-0000001", "00-0000004"],
            "season": [2009, 2011],
            "feature_name": ["epa_per_dropback", "epa_per_dropback"],
        }
    )


def _plays() -> pl.DataFrame:
    rows = []
    for team, values in (("team_buf", [0.2, -0.1]), ("team_jax", [0.5])):
        for index, epa in enumerate(values):
            rows.append(
                {
                    "season": 2010,
                    "player_id": "00-0000001",
                    "team_id": team,
                    "qb_epa": epa,
                    "qb_scramble": 1 if index == 1 else 0,
                    "pass_attempt": 0 if index == 1 else 1,
                    "sack": 0,
                    "cpoe": None if index == 1 else 2.0,
                    "air_yards": None if index == 1 else (5.0 if team == "team_buf" else 25.0),
                    "pass_location": None if index == 1 else "left",
                    "shotgun": 1,
                    "down": 3 if index == 1 else 1,
                    "yardline_100": 15 if index == 1 else 50,
                }
            )
    return pl.DataFrame(rows, infer_schema_length=None)


class StateUniverseTest(unittest.TestCase):
    def test_universe_is_independent_of_target_outcomes(self) -> None:
        history = _history().filter(pl.col("player_id") != "00-0000004")
        before = build_state_universe(_players(), history)
        mutated = history.vstack(
            pl.DataFrame(
                {
                    "player_id": ["00-0000004"],
                    "season": [2011],
                    "feature_name": ["epa_per_dropback"],
                }
            )
        )
        after = build_state_universe(_players(), mutated)
        self.assertEqual(
            before.filter(pl.col("target_season") <= 2011).to_dicts(),
            after.filter(pl.col("target_season") <= 2011).to_dicts(),
        )
        self.assertEqual(
            after.filter(
                (pl.col("player_id") == "00-0000004") & (pl.col("target_season") == 2011)
            ).height,
            0,
        )

    def test_draft_and_dated_evidence_are_asof_bounded(self) -> None:
        dated = pl.DataFrame(
            {
                "player_id": ["00-0000004", "00-0000004"],
                "position": ["QB", "QB"],
                "available_date": ["2011-08-20T12:00:00Z", "2012-09-01T12:00:00Z"],
            }
        )
        universe = build_state_universe(_players(), _history(), dated)
        rookie = universe.filter(
            (pl.col("player_id") == "00-0000002") & (pl.col("target_season") == 2011)
        ).row(0, named=True)
        self.assertIn("draft_fact", rookie["membership_basis"])
        undrafted = universe.filter(
            (pl.col("player_id") == "00-0000004") & (pl.col("target_season") == 2011)
        ).row(0, named=True)
        self.assertIn("dated_preseason_depth_chart", undrafted["membership_basis"])
        self.assertEqual(undrafted["evidence_available_date"], "2011-08-20")
        without_dated_evidence = build_state_universe(_players(), _history())
        self.assertNotIn(
            "dated_preseason_depth_chart",
            without_dated_evidence.filter(
                (pl.col("player_id") == "00-0000004") & (pl.col("target_season") == 2011)
            )["membership_basis"].to_list(),
        )

    def test_evaluation_cannot_backfill_state_universe(self) -> None:
        universe = build_state_universe(_players(), _history())
        outcomes = pl.DataFrame(
            {
                "player_id": ["00-9999999"],
                "team_id": ["team_buf"],
                "season": [2010],
                "dropbacks": [300],
                "starts": [16],
            }
        )
        linked = build_evaluation_links(universe, outcomes).row(0, named=True)
        self.assertFalse(linked["state_universe_member"])
        self.assertEqual(linked["state_exclusion_reason"], "NOT_IN_ASOF_STATE_UNIVERSE")


class ProfileAndStateTest(unittest.TestCase):
    def test_stints_and_player_season_reconcile_from_additive_totals(self) -> None:
        stints = build_qb_team_season_profiles(_plays())
        epa = stints.filter(pl.col("feature_name") == "epa_per_dropback")
        self.assertEqual(epa.height, 2)
        canonical = aggregate_qb_season_profiles(stints)
        row = canonical.filter(pl.col("feature_name") == "epa_per_dropback").row(0, named=True)
        self.assertAlmostEqual(row["raw_value"], (0.2 - 0.1 + 0.5) / 3)
        self.assertEqual(row["team_ids"], "team_buf|team_jax")

    def test_depth_location_and_scramble_denominators(self) -> None:
        supplemental = pl.DataFrame(
            {
                "player_id": ["00-0000001", "00-0000001"],
                "team_id": ["team_buf", "team_jax"],
                "season": [2010, 2010],
                "rushing_yards": [20, 5],
                "rushing_touchdowns": [1, 0],
            }
        )
        stints = build_qb_team_season_profiles(_plays(), supplemental)
        buf = stints.filter(pl.col("team_id") == "team_buf")
        values = {r["feature_name"]: r for r in buf.to_dicts()}
        expected = {
            "epa_per_dropback": (0.1, 2),
            "success_rate": (1, 2),
            "cpoe": (2, 1),
            "sack_rate": (0, 1),
            "average_air_yards": (5, 1),
            "target_depth_short_rate": (1, 1),
            "target_depth_intermediate_rate": (0, 1),
            "target_depth_deep_rate": (0, 1),
            "target_depth_short_epa": (0.2, 1),
            "target_depth_intermediate_epa": (0, 0),
            "target_depth_deep_epa": (0, 0),
            "shotgun_rate": (2, 2),
            "shotgun_epa": (0.1, 2),
            "early_down_epa": (0.2, 1),
            "third_down_epa": (-0.1, 1),
            "red_zone_epa": (-0.1, 1),
            "pass_location_left_rate": (1, 1),
            "pass_location_middle_rate": (0, 1),
            "pass_location_right_rate": (0, 1),
            "pass_location_left_epa": (0.2, 1),
            "pass_location_middle_epa": (0, 0),
            "pass_location_right_epa": (0, 0),
            "scramble_rate": (1, 2),
            "scramble_epa": (-0.1, 1),
            "rushing_yards_per_dropback": (20, 2),
            "rushing_tds_per_dropback": (1, 2),
        }
        self.assertEqual(set(values), set(expected))
        for feature, (numerator, denominator) in expected.items():
            self.assertAlmostEqual(values[feature]["numerator"] or 0, numerator)
            self.assertEqual(values[feature]["denominator"], denominator)

    def test_multi_team_pae_requires_invariant_expectation(self) -> None:
        stints = build_qb_team_season_profiles(_plays())
        profiles = aggregate_qb_season_profiles(stints)
        pae = pl.DataFrame(
            {
                "player_id": ["00-0000001", "00-0000001"],
                "team_id": ["team_buf", "team_jax"],
                "season": [2010, 2010],
                "dropbacks": [2, 1],
                "actual_epa_per_dropback": [0.05, 0.5],
                "expected_epa_per_dropback": [0.1, 0.1],
                "prediction_std_error": [0.05, 0.05],
                "is_out_of_sample": [True, True],
            }
        )
        result = add_player_season_pae(profiles, pae, stints)
        row = result.filter(pl.col("feature_name") == "pae").row(0, named=True)
        self.assertAlmostEqual(row["raw_value"], (0.05 * 2 + 0.5) / 3 - 0.1)
        with self.assertRaisesRegex(ValueError, "contradictory"):
            add_player_season_pae(
                profiles,
                pae.with_columns(
                    pl.when(pl.col("team_id") == "team_jax")
                    .then(0.2)
                    .otherwise(pl.col("expected_epa_per_dropback"))
                    .alias("expected_epa_per_dropback")
                ),
                stints,
            )
        with self.assertRaisesRegex(ValueError, "absent from canonical profiles"):
            add_player_season_pae(
                profiles,
                pae.with_columns(
                    pl.when(pl.col("team_id") == "team_jax")
                    .then(pl.lit("team_hou"))
                    .otherwise(pl.col("team_id"))
                    .alias("team_id")
                ),
                stints,
            )

    def test_beta_binomial_shrinks_small_sample_more(self) -> None:
        history = pl.DataFrame(
            {
                "raw_value": [0.4, 0.6, 0.5],
                "numerator": [40.0, 60.0, 50.0],
                "denominator": [100.0, 100.0, 100.0],
                "qualified": [True, True, True],
                "sum_squares": [None, None, None],
                "sampling_variance": [None, None, None],
            }
        )
        prior = _fit_prior(history, "binary")
        small = _shrink({"raw_value": 0.8, "numerator": 8.0, "denominator": 10.0}, prior, "binary")
        large = _shrink(
            {"raw_value": 0.8, "numerator": 80.0, "denominator": 100.0}, prior, "binary"
        )
        self.assertLess(small["weight"], large["weight"])
        self.assertLess(small["estimate"], large["estimate"])

    def test_normal_normal_fixture_preserves_manual_posterior(self) -> None:
        prior = {"mean": 0.0, "variance": 0.04, "strength": 0.0}
        observed = {
            "raw_value": 0.2,
            "numerator": 20.0,
            "denominator": 100.0,
            "sum_squares": 8.96,
        }
        result = _shrink(observed, prior, "continuous")
        sample_variance = ((8.96 - 20.0**2 / 100.0) / 99.0) / 100.0
        expected_weight = 0.04 / (0.04 + sample_variance)
        self.assertAlmostEqual(result["weight"], expected_weight)
        self.assertAlmostEqual(result["estimate"], expected_weight * 0.2)

    def test_conditioned_feature_requires_stability_and_portability(self) -> None:
        definition = next(item for item in initial_registry() if item.name == "recent_shotgun_epa")
        self.assertEqual(
            resolve_feature_status(definition, stability_pass=False, portability_pass=True),
            "PREDICTIVE_CONDITIONAL",
        )
        self.assertEqual(
            resolve_feature_status(definition, stability_pass=True, portability_pass=False),
            "PREDICTIVE_CONDITIONAL",
        )
        self.assertEqual(
            resolve_feature_status(definition, stability_pass=True, portability_pass=True),
            "PREDICTIVE_CORE",
        )

    def test_stability_requires_positive_medium_and_high_volume_direction(self) -> None:
        rows = []
        for player in range(4):
            for season, value, volume in (
                (2020, float(player), 250),
                (2021, float(player), 250),
                (2022, float(3 - player), 450),
                (2023, float(player), 450),
            ):
                rows.append(
                    {
                        "player_id": f"qb-{player}",
                        "season": season,
                        "feature_name": "epa_per_dropback",
                        "raw_value": value,
                        "qualified": True,
                        "denominator": float(volume),
                    }
                )
        report = (
            build_stability_report(pl.DataFrame(rows))
            .filter(pl.col("feature_name") == "epa_per_dropback")
            .row(0, named=True)
        )
        self.assertGreater(report["medium_volume_correlation"], 0)
        self.assertLess(report["high_volume_correlation"], 0)
        self.assertFalse(report["direction_consistent"])

    def test_forbidden_state_sources_fail_closed(self) -> None:
        base = initial_registry()[0]
        forbidden = replace(base, source="production API coach_effect output")
        with self.assertRaisesRegex(ValueError, "forbidden Player State"):
            validate_state_feature_contract((forbidden,))

    def test_state_features_never_use_target_or_future_season(self) -> None:
        stints = build_qb_team_season_profiles(_plays())
        profiles = aggregate_qb_season_profiles(stints)
        universe = pl.DataFrame(
            {
                "player_id": ["00-0000001"],
                "target_season": [2011],
                "universe_version": ["test"],
                "as_of_date": ["2011-08-31"],
                "membership_basis": ["prior_qb_history"],
                "evidence_available_date": [None],
                "display_name": ["Veteran"],
                "birth_date": ["1985-01-01"],
                "draft_year": [2005],
                "rookie_season": [2005],
            }
        )
        records = build_state_features(
            universe,
            profiles,
            initial_registry(),
            data_version="test-data",
            source_hash="a" * 64,
        )
        self.assertEqual(records.filter(pl.col("source_season") >= 2011).height, 0)
        self.assertNotIn("recent_observed_pae", records["feature_name"].to_list())


class DeterminismTest(unittest.TestCase):
    def test_input_registry_and_code_hashes_change_identity(self) -> None:
        registry = initial_registry()
        first, _ = _content_identity({"input": "a" * 64}, "b" * 64, registry)
        changed_input, _ = _content_identity({"input": "c" * 64}, "b" * 64, registry)
        changed_code, _ = _content_identity({"input": "a" * 64}, "d" * 64, registry)
        changed_registry, _ = _content_identity(
            {"input": "a" * 64},
            "b" * 64,
            tuple(replace(item, definition_version="changed") for item in registry),
        )
        self.assertEqual(len({first, changed_input, changed_code, changed_registry}), 4)

    def test_parameter_change_changes_identity(self) -> None:
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as output:
            first = run_checkpoint_fourteen(project, Path(output))
            with patch("nfl_coaching_impact.qb_player_state.REFERENCE_WINDOW_SEASONS", 4):
                second = run_checkpoint_fourteen(project, Path(output))
            self.assertNotEqual(first.data_version, second.data_version)
            reused = run_checkpoint_fourteen(project, Path(output))
            self.assertTrue(reused.reused_existing)
            self.assertEqual((Path(output) / "LATEST").read_text().strip(), first.data_version)

    def test_two_clean_builds_are_byte_identical(self) -> None:
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            one = run_checkpoint_fourteen(project, Path(left))
            two = run_checkpoint_fourteen(project, Path(right))
            self.assertEqual(one.data_version, two.data_version)
            manifest_one = json.loads((one.output_path / "MANIFEST.json").read_text())
            manifest_two = json.loads((two.output_path / "MANIFEST.json").read_text())
            self.assertEqual(manifest_one, manifest_two)
            for name in manifest_one["output_checksums"]:
                self.assertEqual(
                    (one.output_path / name).read_bytes(), (two.output_path / name).read_bytes()
                )


if __name__ == "__main__":
    unittest.main()
