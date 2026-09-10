"""C16 follow-up: frozen-family calibration and historical 2026 candidate states.

Original C16 artifacts and source module are never rewritten. Calibration methods
are chosen on development OOS folds only; final validation cannot change that choice.
"""

from __future__ import annotations

import io
import json
import math
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.linear_model import LinearRegression

from . import expected_performance as ep
from . import qb_player_state as state
from . import qb_projection as qp
from .predictive_foundation import FeatureDefinition, validate_feature_records

ORIGINAL_VERSION = "c16-c7cee27a36eb0445"
EXPECTED_VERSION = "c5-8fd5d1aba2598c59"
METHODS = ("NONE", "BIAS", "LINEAR")
LABEL = "TEAM-INDEPENDENT RESEARCH PROJECTIONS"


@dataclass(frozen=True)
class RefinementConfig:
    specification: str = "c16-prior-oos-calibration-candidate-state-v1"
    calibration_years: int = 5
    calibration_minimum_n: int = 100
    calibration_minimum_seasons: int = 3
    minimum_prediction_std: float = 1e-8
    development_end: int = 2018
    selection_minimum_folds: int = 3
    selection_relative_gain: float = 0.02
    selection_win_fraction: float = 0.60
    accuracy_maximum_ratio: float = 1.01
    forward_season: int = 2026
    candidate_history_season: int = 2025
    candidate_minimum_dropbacks: int = 50


def _read(path: Path, expected: str) -> tuple[pl.DataFrame, str]:
    content = path.read_bytes()
    digest = qp._digest(content)
    if digest != expected:
        raise ValueError(f"frozen input checksum mismatch: {path.name}")
    frame = (
        pl.read_parquet(io.BytesIO(content))
        if path.suffix == ".parquet"
        else pl.read_csv(io.BytesIO(content))
    )
    return frame, digest


def load_frozen_inputs(project: Path):
    root = project / "data/processed"
    original = root / "qb_projection" / ORIGINAL_VERSION
    raw = (original / "MANIFEST.json").read_bytes()
    manifest = json.loads(raw)
    if manifest["data_version"] != ORIGINAL_VERSION:
        raise ValueError("wrong original C16 version")
    if "c16-" + qp._digest(qp._json_bytes(manifest["identity"]))[:16] != ORIGINAL_VERSION:
        raise ValueError("original C16 content identity is invalid")
    frames, hashes = {}, {"original_manifest": qp._digest(raw)}
    for name, expected in manifest["output_checksums"].items():
        content = (original / name).read_bytes()
        if qp._digest(content) != expected:
            raise ValueError(f"original C16 output corrupted: {name}")
    for key, name in {
        "oos": "oos_predictions.parquet",
        "cohort": "projection_cohort.parquet",
        "comparison": "baseline_comparison.csv",
        "predictors": "state_predictors.parquet",
    }.items():
        frames[key], hashes[key] = _read(original / name, manifest["output_checksums"][name])
    c14 = root / "qb_player_state" / qp.C14_VERSION
    c14_bytes = (c14 / "MANIFEST.json").read_bytes()
    cm = json.loads(c14_bytes)
    hashes["c14_manifest"] = qp._digest(c14_bytes)
    for key, name in {
        "profiles": "qb_season_profiles.parquet",
        "registry": "qb_feature_registry.csv",
        "states": "player_states.parquet",
    }.items():
        frames[key], hashes[key] = _read(c14 / name, cm["output_checksums"][name])
    historical_version = frames["states"]["historical_source_version"].unique().to_list()
    if len(historical_version) != 1:
        raise ValueError("ambiguous historical lineage")
    frames["players"], hashes["players"] = _read(
        root / "historical" / historical_version[0] / "bronze/players/players.parquet",
        cm["identity"]["inputs"]["players"],
    )
    # Exact original C5 outcome history is required to extend its unchanged B2 formula.
    c5 = root / "expected_performance" / EXPECTED_VERSION
    checks_bytes = (c5 / "OUTPUT_CHECKSUMS.json").read_bytes()
    checks = json.loads(checks_bytes)
    hashes["c5_checksums"] = qp._digest(checks_bytes)
    expected = checks["preseason_features.parquet"]
    frames["c5"], hashes["c5"] = _read(c5 / "preseason_features.parquet", expected["sha256"])
    # C13 is audited, not joined to the candidate predictor matrix.
    c13 = root / "predictive_foundation" / qp.C13_VERSION
    m13_bytes = (c13 / "MANIFEST.json").read_bytes()
    hashes["c13_manifest"] = qp._digest(m13_bytes)
    name = "predictive_asof_snapshot_summary.csv"
    frames["snapshot"], hashes["snapshot"] = _read(
        c13 / name, json.loads(m13_bytes)["output_checksums"][name]
    )
    frames["performance"], hashes["performance"] = _read(
        root / "enhancements" / qp.ENH_VERSION / "canonical_qb_team_season_performance.parquet",
        cm["identity"]["inputs"]["qb_outcomes"],
    )
    return frames, hashes, manifest


def audit_original_selection(oos: pl.DataFrame, comparison: pl.DataFrame) -> pl.DataFrame:
    config = qp.ProjectionConfig()
    selected = qp.select_models(oos, comparison, config)
    if selected != {"epa": "B2", "pae": "M1"}:
        raise ValueError("frozen family selection failed its original rule")
    rows = []
    for outcome in qp.OUTCOMES:
        for model in ("B0", "B1", "M1"):
            f = comparison.filter(
                (pl.col("outcome") == outcome)
                & (pl.col("model") == model)
                & (pl.col("target_season") <= config.development_end)
            )
            gain = float(f["mae_improvement"].mean())
            se = float(f["mae_improvement"].std() / math.sqrt(f.height))
            rows.append(
                {
                    "outcome": outcome,
                    "candidate": model,
                    "selected": selected[outcome],
                    "development_start": int(f["target_season"].min()),
                    "development_end": config.development_end,
                    "validation_start": 2019,
                    "validation_end": 2025,
                    "folds": f.height,
                    "mean_fold_mae_gain": gain,
                    "gain_standard_error": se,
                    "required_gain": max(se, config.selection_relative_gain * f["b2_mae"].mean()),
                    "win_fraction": float((f["mae_improvement"] > 0).mean()),
                    "rmse_ratio": float(f["rmse"].mean() / f["b2_rmse"].mean()),
                    "validation_used_for_choice": False,
                }
            )
    return pl.DataFrame(rows).sort("outcome", "candidate")


def calibration_parameters(history: pl.DataFrame, year: int, method: str, config: RefinementConfig):
    if method not in METHODS:
        raise ValueError("unregistered calibration method")
    if history.height and history.filter(pl.col("target_season") >= year).height:
        raise ValueError("target/future OOS calibration leakage")
    h = history.filter(pl.col("target_season") >= year - config.calibration_years)
    n = h.height
    result = {
        "method": method,
        "bias": 0.0,
        "slope": 1.0,
        "fit_n": n,
        "fit_start": int(h["target_season"].min()) if n else None,
        "fit_end": int(h["target_season"].max()) if n else None,
        "calibrator_status": "NOT_APPLICABLE" if method == "NONE" else "INSUFFICIENT_OOS_HISTORY",
    }
    if (
        method == "NONE"
        or n < config.calibration_minimum_n
        or h["target_season"].n_unique() < config.calibration_minimum_seasons
    ):
        return result
    if not np.isfinite(h.select("actual", "prediction").to_numpy()).all():
        raise ValueError("nonfinite calibration data")
    if method == "BIAS":
        result["bias"] = float((h["actual"] - h["prediction"]).mean())
    elif float(h["prediction"].std(ddof=0)) >= config.minimum_prediction_std:
        fit = LinearRegression().fit(h.select("prediction").to_numpy(), h["actual"].to_numpy())
        result["bias"], result["slope"] = float(fit.intercept_), float(fit.coef_[0])
    else:
        result["calibrator_status"] = "INSUFFICIENT_PREDICTION_VARIATION"
        return result
    result["calibrator_status"] = "FITTED_PRIOR_OOS_ONLY"
    return result


def calibrate_oos(oos: pl.DataFrame, selected: dict, config: RefinementConfig):
    rows, params = [], []
    qc = qp.ProjectionConfig()
    for outcome, base_model in sorted(selected.items()):
        original = oos.filter(
            (pl.col("outcome") == outcome) & (pl.col("model") == base_model)
        ).sort("target_season", "player_id")
        qp._assert_grain(original, qp.KEY)
        for method in METHODS:
            past = []
            for year in sorted(original["target_season"].unique().to_list()):
                h = original.filter(pl.col("target_season") < year)
                fit = calibration_parameters(h, year, method, config)
                params.append(
                    {"outcome": outcome, "base_model": base_model, "target_season": year, **fit}
                )
                history = pl.DataFrame(past, infer_schema_length=None) if past else pl.DataFrame()
                intervals = qp.residual_intervals(history, year, outcome, method, qc)
                for row in original.filter(pl.col("target_season") == year).to_dicts():
                    p = fit["bias"] + fit["slope"] * row["prediction"]
                    result = {
                        **row,
                        "model": method,
                        "base_model": base_model,
                        "uncalibrated_prediction": row["prediction"],
                        "prediction": p,
                        **fit,
                        **intervals,
                    }
                    for level in qc.interval_levels:
                        pct = round(100 * level)
                        radius = intervals[f"radius_{pct}"]
                        result[f"lower_{pct}"] = p - radius if radius is not None else None
                        result[f"upper_{pct}"] = p + radius if radius is not None else None
                    # Only complete historical calibrated predictions calibrate later intervals.
                    rows.append(result)
                    past.append(result)
    return pl.DataFrame(rows, infer_schema_length=None).sort(
        "outcome", "model", "target_season", "player_id"
    ), pl.DataFrame(params, infer_schema_length=None).sort("outcome", "method", "target_season")


def select_calibrators(predictions: pl.DataFrame, config: RefinementConfig):
    selected, audit = {}, []
    for outcome in qp.OUTCOMES:
        candidates = []
        baseline = predictions.filter(
            (pl.col("outcome") == outcome) & (pl.col("model") == "NONE")
        ).select(*qp.KEY, pl.col("prediction").alias("base"))
        for method in METHODS[1:]:
            dev = predictions.filter(
                (pl.col("outcome") == outcome)
                & (pl.col("model") == method)
                & (pl.col("target_season") <= config.development_end)
                & (pl.col("calibrator_status") == "FITTED_PRIOR_OOS_ONLY")
            ).join(baseline, on=qp.KEY, validate="1:1")
            folds = []
            for (year,), f in dev.group_by("target_season", maintain_order=True):
                a, p, b = (f[k].to_numpy() for k in ("actual", "prediction", "base"))
                folds.append(
                    {
                        "year": year,
                        "mae": float(np.mean(abs(a - p))),
                        "gain": float(np.mean(abs(a - b) - abs(a - p))),
                        "base_mae": float(np.mean(abs(a - b))),
                        "rmse": float(np.sqrt(np.mean((a - p) ** 2))),
                        "base_rmse": float(np.sqrt(np.mean((a - b) ** 2))),
                    }
                )
            f = pl.DataFrame(folds)
            n = len(folds)
            gain = float(f["gain"].mean()) if n else None
            threshold = (
                max(
                    float(f["gain"].std() / math.sqrt(n)),
                    config.selection_relative_gain * f["base_mae"].mean(),
                )
                if n > 1
                else None
            )
            win = float((f["gain"] > 0).mean()) if n else None
            passed = bool(
                n >= config.selection_minimum_folds
                and gain > threshold
                and win >= config.selection_win_fraction
                and f["rmse"].mean() <= config.accuracy_maximum_ratio * f["base_rmse"].mean()
            )
            audit.append(
                {
                    "outcome": outcome,
                    "method": method,
                    "selection_end": config.development_end,
                    "qualified_folds": n,
                    "gain": gain,
                    "required_gain": threshold,
                    "win_fraction": win,
                    "selected_eligible": passed,
                }
            )
            if passed:
                candidates.append((float(f["mae"].mean()), METHODS.index(method), method))
        selected[outcome] = min(candidates)[2] if candidates else "NONE"
    return selected, pl.DataFrame(audit)


def assess_calibration(
    original: pl.DataFrame,
    calibrated: pl.DataFrame,
    selected_methods: dict,
    refinement_config: RefinementConfig,
):
    """Reuse every original acceptance threshold and add an accuracy-damage guard."""
    config = qp.ProjectionConfig()
    metrics, coverage, decisions = (
        qp.model_metrics(calibrated, config),
        qp.interval_coverage(calibrated, config),
        [],
    )
    fold_metrics = []
    for outcome in qp.OUTCOMES:
        orig = original.filter(pl.col("outcome") == outcome)
        base = calibrated.filter((pl.col("outcome") == outcome) & (pl.col("model") == "NONE"))
        for method in METHODS:
            rows = calibrated.filter(
                (pl.col("outcome") == outcome) & (pl.col("model") == method)
            ).with_columns(pl.lit("M1").alias("model"))
            # Reuse the accepted challenger slot, preserving original B0/B2 benchmarks.
            combined = pl.concat(
                [orig.filter(pl.col("model") != "M1"), rows.select(orig.columns)],
                how="vertical_relaxed",
            )
            comparisons = qp.paired_comparison(combined, config)
            d = qp.assess_models(
                qp.model_metrics(combined, config),
                qp.interval_coverage(combined, config),
                comparisons,
                {outcome: "M1"},
                config,
            )[0]
            before = (
                qp.model_metrics(base, config)
                .filter(pl.col("period") == "LOCKED_VALIDATION")
                .row(0, named=True)
            )
            after = metrics.filter(
                (pl.col("period") == "LOCKED_VALIDATION")
                & (pl.col("outcome") == outcome)
                & (pl.col("model") == method)
            ).row(0, named=True)
            accuracy = (
                after["mae"] <= refinement_config.accuracy_maximum_ratio * before["mae"]
                and after["rmse"] <= refinement_config.accuracy_maximum_ratio * before["rmse"]
            )
            if not accuracy:
                d["model_status"] = "NOT SUPPORTED"
                d["projection_intervals_supported"] = False
            decisions.append(
                {
                    **d,
                    "selected_model": base["base_model"][0] + "+" + method,
                    "method": method,
                    "base_model": base["base_model"][0],
                    "selected_method": selected_methods[outcome],
                    "is_selected": method == selected_methods[outcome],
                    "accuracy_guard_passed": accuracy,
                    "evaluation_status": (
                        "RETROSPECTIVE_CALIBRATION_REFINEMENT_NOT_NEW_UNTOUCHED_HOLDOUT"
                    ),
                }
            )
            for (year,), f in rows.group_by("target_season", maintain_order=True):
                fold_metrics.append(
                    {
                        "outcome": outcome,
                        "method": method,
                        "target_season": year,
                        **qp._metrics(f["actual"].to_numpy(), f["prediction"].to_numpy(), 0.0),
                    }
                )
    return (
        metrics,
        coverage,
        pl.DataFrame(decisions),
        pl.DataFrame(fold_metrics).sort("outcome", "method", "target_season"),
    )


def candidate_states(frames: dict, version: str, source_hash: str, config: RefinementConfig):
    """Qualified 2025 history, NOT inferred active roster, team, or 2026 outcomes."""
    target, last = config.forward_season, config.candidate_history_season
    if target != last + 1 or last > 2025:
        raise ValueError("candidate source history must end by 2025")
    profiles = frames["profiles"]
    if profiles.filter(pl.col("season") > last).height:
        raise ValueError("future/2026 outcome in candidate source")
    qp._assert_grain(profiles, ["player_id", "season", "feature_name"])
    members = (
        profiles.filter(
            (pl.col("season") == last)
            & (pl.col("feature_name") == "epa_per_dropback")
            & (pl.col("denominator") >= config.candidate_minimum_dropbacks)
        )
        .select("player_id")
        .sort("player_id")
    )
    master = (
        frames["players"]
        .filter((pl.col("position") == "QB") | (pl.col("position_group") == "QB"))
        .select(
            pl.col("gsis_id").alias("player_id"),
            "display_name",
            "birth_date",
            "draft_year",
            "rookie_season",
        )
        .drop_nulls("player_id")
    )
    qp._assert_grain(master, ["player_id"])
    if members.join(master, on="player_id", how="anti").height:
        raise ValueError("candidate lacks canonical QB metadata")
    universe = members.join(master, on="player_id", validate="1:1").with_columns(
        pl.lit(target).alias("target_season"),
        pl.lit(f"{target}-08-31").alias("as_of_date"),
        pl.lit("candidate-history-v1").alias("universe_version"),
        pl.lit(f"qualified_{last}_qb_history_only").alias("membership_basis"),
        pl.lit(f"{target}-08-31").alias("evidence_available_date"),
        pl.when(pl.col("draft_year") <= last).then(pl.col("draft_year")).alias("draft_year"),
        pl.when(pl.col("rookie_season") <= last)
        .then(pl.col("rookie_season"))
        .alias("rookie_season"),
    )
    registry = tuple(FeatureDefinition(**r) for r in frames["registry"].to_dicts())
    records = state.build_state_features(
        universe,
        profiles,
        registry,
        data_version=version,
        source_hash=source_hash,
        target_seasons=(target,),
    )
    history = frames["performance"]
    if history.filter(pl.col("season") > last).height:
        raise ValueError("future/2026 usage in candidate history")
    states = state.build_player_states(
        universe,
        records,
        version,
        history,
        feature_store_version=qp.C13_VERSION,
        source_versions={
            "historical": frames["states"]["historical_source_version"].unique().item(),
            "expected_performance": EXPECTED_VERSION,
            "enhancements": qp.ENH_VERSION,
        },
        total_state_features=len(registry),
    ).with_columns(
        pl.lit("HISTORICAL_INFORMATION_CANDIDATE_NOT_ACTIVE_ROSTER").alias("candidate_status"),
        pl.lit(last).alias("candidate_history_season"),
        pl.lit(False).alias("active_roster_claim"),
        pl.lit(qp.C14_VERSION).alias("historical_profile_version"),
    )
    selected = records.filter(pl.col("feature_name").is_in(qp.STATE_FEATURES))
    validate_feature_records(selected, registry)
    if selected.filter(pl.col("feature_status") != "PREDICTIVE_CORE").height:
        raise ValueError("non-core candidate feature cannot enter a projection")
    if states.filter(
        (pl.col("maximum_source_season") >= target) | (pl.col("as_of_date") != f"{target}-08-31")
    ).height:
        raise ValueError("candidate state chronology failed")
    matrix = states.select(
        *qp.KEY,
        "as_of_date",
        "preseason_ability_standard_error",
        "age_at_season_start",
        "seasons_since_rookie_year",
        "seasons_with_qb_activity",
        "prior_starts",
        "prior_dropbacks",
        "career_starts",
        "career_dropbacks",
    ).with_columns(
        *[
            pl.col(n).cast(pl.Float64).log1p().alias(n + "_log1p")
            for n in ("prior_starts", "prior_dropbacks", "career_starts", "career_dropbacks")
        ]
    )
    matrix = matrix.join(
        selected.select(*qp.KEY, "feature_name", "feature_value").pivot(
            on="feature_name", index=qp.KEY, values="feature_value"
        ),
        on=qp.KEY,
        how="left",
        validate="1:1",
    )
    for name in qp.MODEL_FEATURES:
        if name not in matrix.columns:
            matrix = matrix.with_columns(pl.lit(None, dtype=pl.Float64).alias(name))
    matrix = matrix.select(*qp.KEY, "as_of_date", *qp.MODEL_FEATURES).sort("player_id")
    return (
        universe.sort("player_id"),
        states.sort("player_id"),
        records.sort("player_id", "feature_name"),
        matrix,
    )


def b2_forward(history: pl.DataFrame, candidates: pl.DataFrame, target: int):
    if history.filter(pl.col("season") >= target).height:
        raise ValueError("future season in B2 history")
    qp._assert_grain(history, ["player_id", "team_id", "season"])
    league = ep._league_average(history.filter(pl.col("dropbacks") >= ep.TRAINING_MIN_DROPBACKS))
    career = history.group_by("player_id").agg(
        pl.col("dropbacks").sum().alias("career_dropbacks"),
        (pl.col("actual_epa_per_dropback") * pl.col("dropbacks")).sum().alias("total"),
    )
    career = career.with_columns(
        (pl.col("total") / pl.col("career_dropbacks")).alias("career_epa_per_dropback")
    )
    joined = candidates.select("player_id").join(career, on="player_id", how="left", validate="1:1")
    return np.asarray(
        [ep._baseline_prediction(row, league, "career_performance") for row in joined.to_dicts()]
    ), {
        "league": league,
        "career_shrinkage": ep.CAREER_SHRINKAGE_DROPBACKS,
        "history_end": int(history["season"].max()),
    }


def forward_projections(
    frames: dict,
    matrix: pl.DataFrame,
    calibrated: pl.DataFrame,
    decisions: pl.DataFrame,
    config: RefinementConfig,
    version: str,
):
    rows, parameters = [], []
    qc = qp.ProjectionConfig()
    for d in decisions.filter(pl.col("is_selected")).to_dicts():
        if not d["projection_intervals_supported"] or d["model_status"] not in {
            "VALIDATED FOR RESEARCH PROJECTION",
            "RESEARCH-READY WITH LIMITATIONS",
        }:
            continue
        outcome, base_model, method = d["outcome"], d["base_model"], d["method"]
        history = frames["oos"].filter(
            (pl.col("outcome") == outcome) & (pl.col("model") == base_model)
        )
        fit = calibration_parameters(history, config.forward_season, method, config)
        if method != "NONE" and fit["calibrator_status"] != "FITTED_PRIOR_OOS_ONLY":
            continue
        if base_model == "B2":
            predictions, model_meta = b2_forward(frames["c5"], matrix, config.forward_season)
            if outcome == "pae":
                predictions = np.zeros(matrix.height)
        elif base_model == "M1":
            training = (
                frames["cohort"]
                .filter(pl.col("eligible") & pl.col(f"outcome_{outcome}").is_not_null())
                .sort("target_season", "player_id")
            )
            alpha, inner, _ = qp.tune_alpha(training, outcome, config.forward_season, qc)
            predictions, model, prep, names = qp.fit_ridge(
                training, matrix, outcome, config.forward_season, alpha, qc
            )
            model_meta = {
                "alpha": alpha,
                "inner_validation_seasons": inner,
                "preprocessor": asdict(prep),
                "coefficients": dict(zip(names, model.coef_.tolist(), strict=True)),
                "intercept": float(model.intercept_),
            }
        else:
            raise ValueError("unsupported frozen base family")
        errors = calibrated.filter((pl.col("outcome") == outcome) & (pl.col("model") == method))
        intervals = qp.residual_intervals(errors, config.forward_season, outcome, method, qc)
        if any(intervals[f"radius_{round(100 * p)}"] is None for p in qc.interval_levels):
            continue
        parameters.append(
            {"outcome": outcome, "base_model": base_model, "calibrator": fit, "model": model_meta}
        )
        for member, raw in zip(matrix.to_dicts(), predictions, strict=True):
            p = fit["bias"] + fit["slope"] * float(raw)
            if not math.isfinite(p):
                raise ValueError("nonfinite forward projection")
            row = {
                "player_id": member["player_id"],
                "target_season": config.forward_season,
                "as_of_date": member["as_of_date"],
                "outcome": outcome,
                "prediction": p,
                "uncalibrated_prediction": float(raw),
                "base_model": base_model,
                "calibration_method": method,
                "label": LABEL,
                "active_roster_claim": False,
                "model_status": d["model_status"],
                "data_version": version,
                "model_version": version.replace("c16r-", "qb-calibrated-"),
                "candidate_state_version": version,
                **intervals,
            }
            for level in qc.interval_levels:
                pct = round(100 * level)
                row[f"lower_{pct}"] = p - intervals[f"radius_{pct}"]
                row[f"upper_{pct}"] = p + intervals[f"radius_{pct}"]
            rows.append(row)
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame(
        schema={
            "player_id": pl.String,
            "target_season": pl.Int64,
            "outcome": pl.String,
            "prediction": pl.Float64,
            "label": pl.String,
        }
    ), parameters


def run_refinement(
    project: Path, output_root: Path | None = None, config: RefinementConfig | None = None
):
    config = config or RefinementConfig()
    frames, hashes, original = load_frozen_inputs(project)
    original_spec = original["identity"]["config"]
    if json.loads(qp._json_bytes(asdict(qp.ProjectionConfig()))) != original_spec:
        raise ValueError("original acceptance/model thresholds changed")
    _, base_identity = qp.content_identity(hashes, qp.ProjectionConfig())
    identity = {
        "base_identity": base_identity,
        "config": asdict(config),
        "methods": METHODS,
        "source_code": {
            p.name: qp._digest(p.read_bytes())
            for p in (Path(__file__), Path(state.__file__), Path(ep.__file__))
        },
    }
    identity = json.loads(qp._json_bytes(identity))
    version = "c16r-" + qp._digest(qp._json_bytes(identity))[:16]
    root = output_root or project / "data/processed/qb_projection_refinement"
    destination = root / version
    if destination.exists():
        manifest = json.loads((destination / "MANIFEST.json").read_bytes())
        if manifest["identity"] != identity:
            raise ValueError("refinement identity mismatch")
        for name, digest in manifest["output_checksums"].items():
            if qp._digest((destination / name).read_bytes()) != digest:
                raise ValueError("refinement output checksum mismatch")
        qp._publish_latest(root, version)
        return manifest
    audit = audit_original_selection(frames["oos"], frames["comparison"])
    selected = original["counts"]["selected_models"]
    calibrated, parameters = calibrate_oos(frames["oos"], selected, config)
    methods, selection_audit = select_calibrators(calibrated, config)
    metrics, coverage, decisions, folds = assess_calibration(
        frames["oos"], calibrated, methods, config
    )
    universe, states, records, matrix = candidate_states(
        frames, version, hashes["profiles"], config
    )
    forward, forward_params = forward_projections(
        frames, matrix, calibrated, decisions, config, version
    )
    leakage = pl.DataFrame(
        [
            {
                "gate": "CALIBRATOR_FIT_BEFORE_TARGET",
                "failures": parameters.filter(pl.col("fit_end") >= pl.col("target_season")).height,
            },
            {
                "gate": "INTERVAL_CALIBRATION_BEFORE_TARGET",
                "failures": calibrated.filter(
                    pl.col("calibration_end_season") >= pl.col("target_season")
                ).height,
            },
            {
                "gate": "CANDIDATE_SOURCE_THROUGH_2025",
                "failures": records.filter(
                    (pl.col("source_season") > 2025)
                    | (pl.col("standardization_fit_end_season") > 2025)
                    | (pl.col("observation_end_season") > 2025)
                ).height,
            },
            {
                "gate": "CANDIDATE_PLAYER_ONLY_ALLOWLIST",
                "failures": len(
                    set(matrix.columns) - set(qp.KEY + ["as_of_date"] + list(qp.MODEL_FEATURES))
                ),
            },
            {
                "gate": "METHOD_SELECTION_BEFORE_VALIDATION",
                "failures": selection_audit.filter(pl.col("selection_end") >= 2019).height,
            },
        ]
    ).with_columns((pl.col("failures") == 0).alias("passed"))
    if not leakage["passed"].all():
        raise ValueError("refinement leakage gate failed")
    root_cause = {
        "classification": "A_DOCUMENTATION_REPORTING_ERROR_ONLY",
        "c13_forward_entity": "TEAM",
        "c13_2026_entities": int(
            frames["snapshot"].filter(pl.col("target_season") == 2026)["entities"][0]
        ),
        "c14_target_start": int(frames["states"]["target_season"].min()),
        "c14_target_end": int(frames["states"]["target_season"].max()),
        "c14_target_constant_end": max(state.TARGET_SEASONS),
        "reason": (
            "C13's 2026 snapshot is 32 teams, not Player State. C14 intentionally implemented "
            "historical targets 2010-2025. The claim an existing 2026 QB state existed was "
            "incorrect, not an active-roster blocker."
        ),
        "candidate_universe": (
            "Canonical 2025 QB participants with >=50 historical dropbacks; "
            "no claim of 2026 participation or team."
        ),
    }
    artifacts = {
        "leakage_audit.csv": leakage,
        "original_selection_audit.csv": audit,
        "calibration_selection_audit.csv": selection_audit,
        "calibration_parameters.csv": parameters,
        "calibrated_oos_predictions.parquet": calibrated,
        "model_comparison.csv": metrics,
        "interval_coverage.csv": coverage,
        "fold_metrics.csv": folds,
        "outcome_decisions.csv": decisions,
        "candidate_universe_2026.parquet": universe,
        "candidate_player_states_2026.parquet": states,
        "candidate_feature_records_2026.parquet": records,
        "candidate_predictors_2026.parquet": matrix,
        "projections_2026.parquet": forward,
    }
    manifest = {
        "data_version": version,
        "model_version": version.replace("c16r-", "qb-calibrated-"),
        "original_version": ORIGINAL_VERSION,
        "identity": identity,
        "selected_base_models": selected,
        "selected_calibrators": methods,
        "decisions": decisions.filter(pl.col("is_selected")).to_dicts(),
        "candidate_states": states.height,
        "forward_projection_rows": forward.height,
        "forward_qbs": forward["player_id"].n_unique(),
        "state_audit": root_cause,
        "checkpoint_status": "COMPLETE",
        "checkpoint_17_readiness": "NOT READY",
        "checkpoint_17_blocker": (
            "No validated historical target-environment/scenario contract or Player × Scheme "
            "response. A team-independent baseline cannot validate scenario simulation."
        ),
        "output_checksums": {},
    }
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=root))
    try:
        for name, frame in artifacts.items():
            if name.endswith(".parquet"):
                frame.write_parquet(
                    stage / name,
                    compression="zstd",
                    compression_level=3,
                    statistics=True,
                    row_group_size=10000,
                )
            else:
                frame.write_csv(stage / name, float_precision=15)
        (stage / "forward_model_parameters.json").write_bytes(qp._json_bytes(forward_params))
        (stage / "forward_state_audit.json").write_bytes(qp._json_bytes(root_cause))
        manifest["output_checksums"] = {
            p.name: qp._digest(p.read_bytes()) for p in sorted(stage.iterdir())
        }
        (stage / "MANIFEST.json").write_bytes(qp._json_bytes(manifest))
        os.replace(stage, destination)
        qp._publish_latest(root, version)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return manifest
