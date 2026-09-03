from __future__ import annotations

import re
import unittest
from pathlib import Path

import numpy as np
import polars as pl

from research.coach_effect import config
from research.coach_effect.phase_1_qb_effect.analysis import (
    add_pae,
    build_transitions,
    fit_expected_movement,
)
from research.coach_effect.phase_1_qb_effect.analysis import (
    formula_contract as phase_1_formulas,
)
from research.coach_effect.phase_2_play_calling.analysis import (
    ExpectedPlayModels,
    aggregate_pcae,
    attribute_play_callers,
    call_model_metrics,
    estimate_repeat_reliability,
    fit_expected_play_models,
    prepare_plays,
    score_expected_decisions,
    shrink_pcae,
)
from research.coach_effect.phase_2_play_calling.analysis import (
    formula_contract as phase_2_formulas,
)
from research.coach_effect.phase_3_environment.analysis import (
    compare_environment_models,
    leave_one_team_out,
    staged_environment_models,
)
from research.coach_effect.phase_4_coach_effect.analysis import (
    conceptual_framework,
    residualize_components,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _StaticCallModel:
    def predict_proba(self, values: np.ndarray) -> np.ndarray:
        probability = np.full(len(values), 0.6)
        return np.column_stack([1.0 - probability, probability])


class _StaticEpaModel:
    def __init__(self, value: float) -> None:
        self.value = value

    def predict(self, values: np.ndarray) -> np.ndarray:
        return np.full(len(values), self.value)


def _play_frame(epa: list[float]) -> pl.DataFrame:
    rows = []
    for index, actual_epa in enumerate(epa, start=1):
        row: dict[str, object] = {
            "game_id": "2025_01_X_Y",
            "play_id": index,
            "season": 2025,
            "season_type": "REG",
            "week": 1,
            "posteam": "X",
            "play_type": "pass" if index % 2 else "run",
            "epa": actual_epa,
        }
        row.update({feature: float(index) for feature in config.PLAY_CALL_FEATURES})
        rows.append(row)
    return pl.DataFrame(rows)


def _fitted_play_frame() -> pl.DataFrame:
    rows = []
    for season in (2022, 2023, 2024, 2025):
        for index in range(24):
            is_pass = index % 2 == 0
            row: dict[str, object] = {
                "game_id": f"{season}_01_X_Y",
                "play_id": index + 1,
                "season": season,
                "season_type": "REG",
                "week": 1,
                "posteam": "X",
                "play_type": "pass" if is_pass else "run",
                "epa": (0.08 if is_pass else 0.02) + index / 1_000,
            }
            row.update(
                {
                    feature: float(index + feature_index)
                    for feature_index, feature in enumerate(config.PLAY_CALL_FEATURES)
                }
            )
            rows.append(row)
    return pl.DataFrame(rows)


class CheckpointTenResearchTests(unittest.TestCase):
    def test_required_research_artifacts_exist(self) -> None:
        expected = [
            "research/coach_effect/config.py",
            "research/coach_effect/phase_1_qb_effect/analysis.py",
            "research/coach_effect/phase_1_qb_effect/qb_transition_analysis.sql",
            "research/coach_effect/phase_2_play_calling/analysis.py",
            "research/coach_effect/phase_3_environment/analysis.py",
            "research/coach_effect/phase_4_coach_effect/analysis.py",
            "docs/COACH_EFFECT_RESEARCH.md",
            "docs/COACH_EFFECT_METHODOLOGY.md",
            "docs/COACH_EFFECT_MODEL_CARD.md",
        ]
        self.assertEqual([], [path for path in expected if not (PROJECT_ROOT / path).is_file()])

    def test_formula_contracts_are_exact(self) -> None:
        self.assertEqual(
            "actual_epa_per_dropback - expected_epa_per_dropback",
            phase_1_formulas()["pae"],
        )
        self.assertEqual(
            "actual_qb_delta_pae - expected_qb_delta_pae",
            phase_1_formulas()["qb_development_signal"],
        )
        self.assertEqual(
            "expected_chosen_epa - expected_alternative_epa",
            phase_2_formulas()["call_value"],
        )
        self.assertEqual(
            "coach_average_call_value - league_average_call_value",
            phase_2_formulas()["pcae"],
        )

    def test_pae_arithmetic_and_eligibility_are_independent(self) -> None:
        source = pl.DataFrame(
            {
                "actual_epa_per_dropback": [0.20, -0.05],
                "expected_epa_per_dropback": [0.08, 0.02],
                "eligibility_status": ["eligible", "below_200_dropbacks"],
            }
        )
        result = add_pae(source)
        self.assertAlmostEqual(0.12, result["performance_above_expectation"][0])
        self.assertAlmostEqual(-0.07, result["performance_above_expectation"][1])
        self.assertEqual(
            source["eligibility_status"].to_list(), result["eligibility_status"].to_list()
        )

    def test_transition_grain_preserves_same_context_and_changed_oc(self) -> None:
        source = pl.DataFrame(
            {
                "player_id": ["qb-1", "qb-1"],
                "team_id": ["team-x", "team-x"],
                "season": [2023, 2024],
                "performance_above_expectation": [-0.04, 0.03],
                "offensive_coordinator_id": ["oc-a", "oc-b"],
                "head_coach_id": ["hc-a", "hc-a"],
            }
        )
        result = build_transitions(source).row(0, named=True)
        self.assertAlmostEqual(0.07, result["actual_qb_delta_pae"])
        self.assertTrue(result["same_team"])
        self.assertTrue(result["same_head_coach"])
        self.assertTrue(result["changed_offensive_coordinator"])

    def test_expected_movement_requires_strictly_earlier_training(self) -> None:
        training = pl.DataFrame(
            {
                "season": [2022, 2023],
                "prior_pae": [-0.10, 0.05],
                "actual_qb_delta_pae": [0.04, -0.02],
            }
        )
        scoring = pl.DataFrame(
            {"season": [2024], "prior_pae": [0.02], "actual_qb_delta_pae": [0.01]}
        )
        result, _ = fit_expected_movement(training, scoring)
        self.assertEqual(1, result.height)
        with self.assertRaisesRegex(ValueError, "earlier"):
            fit_expected_movement(training, training.tail(1))

    def test_call_value_never_uses_individual_actual_epa(self) -> None:
        models = ExpectedPlayModels(
            _StaticCallModel(),  # type: ignore[arg-type]
            _StaticEpaModel(0.10),  # type: ignore[arg-type]
            _StaticEpaModel(-0.04),  # type: ignore[arg-type]
        )
        first = score_expected_decisions(_play_frame([5.0, -4.0]), models)
        second = score_expected_decisions(_play_frame([-20.0, 30.0]), models)
        self.assertEqual(first["call_value"].to_list(), second["call_value"].to_list())
        self.assertEqual([0.14, -0.14], first["call_value"].to_list())

    def test_declared_play_models_fit_and_score_the_held_out_season(self) -> None:
        plays = prepare_plays(_fitted_play_frame())
        models = fit_expected_play_models(plays)
        scored = score_expected_decisions(plays, models)
        metrics = call_model_metrics(scored)
        self.assertEqual(2025, models.test_season)
        self.assertEqual((2022, 2023, 2024), models.train_seasons)
        self.assertEqual(24, scored.filter(pl.col("season") == 2025).height)
        self.assertTrue(0.0 <= metrics["brier"] <= 1.0)
        self.assertTrue(scored["call_value"].is_finite().all())

    def test_duplicate_play_keys_fail_before_modeling(self) -> None:
        duplicated = pl.concat([_play_frame([0.1]), _play_frame([0.2])])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            prepare_plays(duplicated)

    def test_null_play_identifiers_fail_instead_of_being_filtered(self) -> None:
        source = _play_frame([0.1]).with_columns(pl.lit(None).alias("game_id"))
        with self.assertRaisesRegex(ValueError, "missing identifiers"):
            prepare_plays(source)

    def test_play_caller_attribution_requires_explicit_interval_evidence(self) -> None:
        models = ExpectedPlayModels(
            _StaticCallModel(),  # type: ignore[arg-type]
            _StaticEpaModel(0.10),  # type: ignore[arg-type]
            _StaticEpaModel(-0.04),  # type: ignore[arg-type]
        )
        scored = score_expected_decisions(_play_frame([0.1, 0.2]), models)
        assignment = pl.DataFrame(
            {
                "assignment_key": ["2025-X-play-caller"],
                "season": [2025],
                "team_id": ["X"],
                "coach_id": ["coach-a"],
                "role": ["play_caller"],
                "start_week": [1],
                "end_week": [18],
                "verification_status": ["verified"],
                "confidence_level": ["high"],
                "interval_basis": ["dated_source_weeks"],
                "is_shared": [False],
                "primary_source_url": ["https://example.test/evidence"],
            }
        )
        attributed = attribute_play_callers(scored, assignment)
        self.assertEqual(2, attributed.height)
        self.assertEqual([1.0, 1.0], attributed["attribution_weight"].to_list())
        with self.assertRaisesRegex(ValueError, "explicit interval evidence"):
            attribute_play_callers(
                scored,
                assignment.with_columns(pl.lit("season_designation").alias("interval_basis")),
            )

    def test_pcae_is_league_centered(self) -> None:
        attributed = pl.DataFrame(
            {
                "season": [2025, 2025, 2025, 2025],
                "coach_id": ["a", "a", "b", "b"],
                "call_value": [0.10, 0.10, -0.10, -0.10],
                "attribution_weight": [1.0, 1.0, 1.0, 1.0],
            }
        )
        result = aggregate_pcae(attributed)
        self.assertEqual([0.10, -0.10], result["pcae"].to_list())

    def test_repeat_reliability_drives_declared_shrinkage(self) -> None:
        pcae = pl.DataFrame(
            {
                "coach_id": ["a", "a", "b", "b", "c", "c"],
                "season": [2024, 2025, 2024, 2025, 2024, 2025],
                "pcae": [0.10, 0.12, 0.00, 0.02, -0.10, -0.08],
            }
        )
        reliability = estimate_repeat_reliability(pcae)
        one_season = float(reliability["one_season_reliability"])
        self.assertAlmostEqual(0.9801980198019802, one_season)
        shrunk = shrink_pcae(pcae.head(1), one_season)
        self.assertAlmostEqual(0.10 * one_season, shrunk["shrunk_pcae"][0])

    def test_residual_components_are_orthogonal_to_the_removed_signal(self) -> None:
        source = pl.DataFrame(
            {
                "coach_id": [f"coach-{index}" for index in range(6)],
                "pae_signal": [-0.2, -0.1, 0.0, 0.1, 0.2, 0.3],
                "pcae": [-0.1, 0.03, -0.02, 0.11, 0.08, 0.24],
            }
        )
        result, diagnostics = residualize_components(source)
        self.assertEqual(source.height, result.height)
        self.assertAlmostEqual(0.0, diagnostics["pae_correlation_with_unique_pcae"], places=12)
        self.assertAlmostEqual(0.0, diagnostics["pcae_correlation_with_unique_pae"], places=12)

    def test_environment_comparison_and_leave_one_team_out_are_executable(self) -> None:
        rows = []
        for index in range(10):
            prior = -0.1 + index * 0.02
            expected = -0.05 + index * 0.01
            pcae = -0.02 + index * 0.004
            rows.append(
                {
                    "team_id": f"team-{index:02d}",
                    "actual_offensive_epa": 0.4 * prior + 0.6 * pcae + index % 2 * 0.001,
                    "prior_team_epa": prior,
                    "expected_qb_epa": expected,
                    "supporting_cast": float(index % 3),
                    "opponent_strength": float(index % 4) / 10,
                    "pcae": pcae,
                }
            )
        frame = pl.DataFrame(rows)
        environment, with_pcae = compare_environment_models(frame)
        staged = staged_environment_models(frame)
        scored, metrics = leave_one_team_out(frame, (*config.ENVIRONMENT_FEATURES, "pcae"))
        self.assertEqual("environment_only", environment.name)
        self.assertEqual("environment_plus_pcae", with_pcae.name)
        self.assertEqual(6, len(staged))
        self.assertEqual(frame.height, scored.height)
        self.assertTrue(np.isfinite(metrics["rmse"]))

    def test_no_numeric_final_component_weights_are_hardcoded(self) -> None:
        research_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((PROJECT_ROOT / "research" / "coach_effect").rglob("*"))
            if path.is_file() and path.suffix in {".py", ".md", ".sql"}
        )
        self.assertIsNone(re.search(r"\bw_[QPS]\s*=\s*[-+]?\d", research_text))
        framework = conceptual_framework()
        self.assertEqual(("w_Q", "w_P", "w_S"), framework["weight_names"])
        self.assertNotIn("score", framework)

    def test_research_is_not_imported_by_production(self) -> None:
        roots = ["src", "backend", "frontend", "alembic"]
        offenders = []
        for root in roots:
            directory = PROJECT_ROOT / root
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix in {".py", ".ts", ".tsx", ".sql"}:
                    if "research.coach_effect" in path.read_text(encoding="utf-8"):
                        offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual([], offenders)
        self.assertEqual(Path("research/coach_effect/outputs"), config.RESEARCH_OUTPUT_DIRECTORY)
        self.assertIn(
            "research/coach_effect/outputs/",
            (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8"),
        )

    def test_documentation_is_exploratory_noncausal_and_contains_release_gate(self) -> None:
        documents = [
            PROJECT_ROOT / "docs" / "COACH_EFFECT_RESEARCH.md",
            PROJECT_ROOT / "docs" / "COACH_EFFECT_METHODOLOGY.md",
            PROJECT_ROOT / "docs" / "COACH_EFFECT_MODEL_CARD.md",
        ]
        for path in documents:
            text = path.read_text(encoding="utf-8").casefold()
            self.assertIn("exploratory", text, path.name)
            self.assertIn("non-causal", text, path.name)
            self.assertIn("blocked", text, path.name)
            self.assertIn("play-caller", text, path.name)
            self.assertRegex(text, r"explicit\s+(?:source\s+)?evidence", path.name)
            self.assertRegex(text, r"weekly|in-season", path.name)

        combined = "\n".join(path.read_text(encoding="utf-8").casefold() for path in documents)
        self.assertIn("historical pcae expansion", combined)
        self.assertIn("confidence/uncertainty rules", combined)
        self.assertIn("suppression/evidence thresholds", combined)

    def test_historical_numbers_have_explicit_reproduction_status(self) -> None:
        narrative = (PROJECT_ROOT / "docs" / "COACH_EFFECT_RESEARCH.md").read_text(encoding="utf-8")
        for value in ("133,636", "32,813", "0.5717", "0.4491", "0.5926"):
            self.assertIn(value, narrative)
        self.assertIn("Exactly reproduced and explained", narrative)
        self.assertIn("Eligibility reproduced; attribution not reproduced", narrative)
        self.assertIn("134,138 rows; all 502 excluded rows are two-point conversions", narrative)


if __name__ == "__main__":
    unittest.main()
