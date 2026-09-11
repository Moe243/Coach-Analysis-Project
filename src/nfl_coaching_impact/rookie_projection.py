"""C20 source-gated rookie research closeout; deliberately contains no fitted model.

The audited college source gate failed. Preserve the outcome-independent drafted-QB
universe and explicit missingness instead of fitting a survivor-only draft model.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import platform
import tempfile
from dataclasses import asdict
from datetime import date
from pathlib import Path

import polars as pl

from .predictive_foundation import (
    AS_OF_MONTH_DAY,
    FeatureDefinition,
    validate_feature_records,
    validate_feature_registry,
)

CONTRACT = "checkpoint-20-rookie-source-gate-v1"
STATUS = "NOT ESTIMABLE / DATA-LIMITED"
MIN_ROOKIE_DROPBACKS = 100
DRAFT_YEARS = tuple(range(1999, 2026))
VERSIONS = {
    "historical": "c3-f6c1aa118ff43b90",
    "enhancements": "enh-04254065cafd92ba",
    "predictive_foundation": "c13-5e3d7a34ea4d1af5",
}
COLLEGE_COUNTS = ("attempts", "completions", "passing_yards", "passing_td", "interceptions")
RATE_FORMULAS = {
    "completion_rate": "completions",
    "yards_per_attempt": "passing_yards",
    "td_rate": "passing_td",
    "interception_rate": "interceptions",
}
COLLEGE_FEATURES = (
    *COLLEGE_COUNTS,
    *RATE_FORMULAS,
    "rushing_attempts",
    "rushing_yards",
    "rushing_td",
    "sacks",
    "college_seasons",
    "college_starts",
    "air_yards",
)


def json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n"
    ).encode()


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def require_key(frame: pl.DataFrame, key: list[str]) -> None:
    if frame.select(pl.any_horizontal(pl.col(key).is_null()).any()).item():
        raise ValueError(f"null canonical key: {key}")
    if frame.select(key).n_unique() != frame.height:
        raise ValueError(f"duplicate canonical key: {key}")


def college_registry() -> tuple[FeatureDefinition, ...]:
    definitions = tuple(
        FeatureDefinition(
            name=f"college_{name}",
            entity_grain="QB",
            family="college_profile",
            description=f"Pre-NFL college {name}; unavailable in this source-gated build.",
            football_interpretation="Observed college production, not an NFL ability score.",
            source="unavailable_college_corpus",
            source_fields=name,
            earliest_supported_season=None,
            latest_supported_season=None,
            timing_class="HISTORICAL_PRIOR",
            minimum_sample_rule="verified pre-NFL history",
            derivation=(f"{RATE_FORMULAS[name]} / attempts" if name in RATE_FORMULAS else "source"),
            status="UNAVAILABLE",
            missing_data_behavior="SOURCE_NOT_AVAILABLE",
            predictive_permission="NO",
            research_readiness="DATA_LIMITED",
        )
        for name in sorted(COLLEGE_FEATURES)
    )
    validate_feature_registry(definitions)
    return definitions


def validate_college_records(records: pl.DataFrame) -> None:
    """Reuse C13 chronology and lineage; no independent timing implementation."""
    validate_feature_records(records, college_registry(), predictive_only=False)
    if records.filter(pl.col("source_available_date") > pl.col("as_of_date")).height:
        raise ValueError("post-cutoff college source")


def college_rates(counts: dict[str, float | None]) -> dict[str, float | None]:
    """Unfitted contract helper, tested on synthetic fixtures only; no imputation."""
    if set(counts) - set(COLLEGE_COUNTS):
        raise ValueError("unregistered college input (NFL outcomes/context are forbidden)")
    for name, value in counts.items():
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError(f"invalid college statistic: {name}")
    attempts = counts.get("attempts")
    for field in ("completions", "passing_td", "interceptions"):
        if attempts is not None and counts.get(field) is not None and counts[field] > attempts:
            raise ValueError(f"{field} exceeds attempts")
    return {
        feature: counts.get(numerator) / attempts
        if attempts and counts.get(numerator) is not None
        else None
        for feature, numerator in RATE_FORMULAS.items()
    }


def build_universe(players: pl.DataFrame) -> pl.DataFrame:
    """Draft facts define membership, never observed NFL participation or current status."""
    qbs = players.filter((pl.col("position") == "QB") | (pl.col("position_group") == "QB"))
    qbs = qbs.filter(pl.col("draft_year").is_in(DRAFT_YEARS)).select(
        pl.col("gsis_id").alias("player_id"),
        "display_name",
        "birth_date",
        "draft_year",
        "draft_round",
        "draft_pick",
        pl.col("rookie_season").alias("reported_rookie_season"),
    )
    require_key(qbs, ["player_id"])
    if qbs.filter(~pl.col("player_id").str.contains(r"^00-\d{7}$")).height:
        raise ValueError("unresolved GSIS QB identity")
    rows = []
    for row in qbs.sort("draft_year", "player_id").to_dicts():
        year = int(row["draft_year"])
        cutoff = date(year, *AS_OF_MONTH_DAY)
        birthday = date.fromisoformat(str(row["birth_date"])[:10]) if row["birth_date"] else None
        if birthday and birthday >= cutoff:
            raise ValueError("invalid birth date")
        for key in ("draft_round", "draft_pick"):
            if row[key] is not None and row[key] <= 0:
                raise ValueError(f"invalid {key}")
        row.update(
            target_season=year,
            as_of_date=cutoff.isoformat(),
            age_at_cutoff=(cutoff - birthday).days / 365.2425 if birthday else None,
            membership_basis="IMMUTABLE_DRAFT_FACT_CANONICAL_QB",
            rookie_timing_status=(
                "CONSISTENT"
                if row["reported_rookie_season"] == year
                else "ROOKIE_SEASON_UNRESOLVED"
            ),
        )
        rows.append(row)
    if not rows:
        raise ValueError("no historical drafted QBs")
    return pl.DataFrame(rows, infer_schema_length=None)


def attach_outcomes(universe: pl.DataFrame, outcomes: pl.DataFrame) -> pl.DataFrame:
    """Left join draft-year outcomes only; never advance a year to find a successful season."""
    require_key(outcomes, ["player_id", "team_id", "season"])
    eligible = outcomes.join(
        universe.select("player_id", pl.col("target_season").alias("season")),
        on=["player_id", "season"],
        how="inner",
        validate="m:1",
    ).sort("player_id", "season", "team_id")
    for row in eligible.to_dicts():
        if (
            row["dropbacks"] is None
            or row["dropbacks"] <= 0
            or row["total_qb_epa"] is None
            or not math.isfinite(row["total_qb_epa"])
        ):
            raise ValueError("invalid rookie NFL outcome")
        if row["positive_epa_dropbacks"] is None or not (
            0 <= row["positive_epa_dropbacks"] <= row["dropbacks"]
        ):
            raise ValueError("invalid success numerator")
        if row["cpoe_attempts"] is None or not 0 <= row["cpoe_attempts"] <= row["dropbacks"]:
            raise ValueError("invalid CPOE denominator")
        if row["cpoe_attempts"] > 0 and (
            row["total_cpoe"] is None or not math.isfinite(row["total_cpoe"])
        ):
            raise ValueError("invalid covered CPOE")
    totals = (
        eligible.group_by("player_id", "season", maintain_order=True)
        .agg(
            pl.col("team_id").sort().str.join("|").alias("outcome_team_ids"),
            pl.col("dropbacks").sum().alias("rookie_dropbacks"),
            pl.col("total_qb_epa").sum().alias("rookie_total_epa"),
            pl.col("positive_epa_dropbacks").sum().alias("rookie_successes"),
            pl.col("cpoe_attempts").sum().alias("rookie_cpoe_attempts"),
            pl.col("total_cpoe").sum().alias("rookie_total_cpoe"),
        )
        .rename({"season": "target_season"})
    )
    result = universe.join(totals, on=["player_id", "target_season"], how="left", validate="1:1")
    timing_ok = pl.col("rookie_timing_status") == "CONSISTENT"
    result = result.with_columns(
        pl.when(timing_ok)
        .then(pl.col("rookie_total_epa") / pl.col("rookie_dropbacks"))
        .otherwise(None)
        .alias("rookie_epa_per_dropback"),
        pl.when(timing_ok)
        .then(pl.col("rookie_successes") / pl.col("rookie_dropbacks"))
        .otherwise(None)
        .alias("rookie_success_rate"),
        pl.when(timing_ok & (pl.col("rookie_cpoe_attempts") > 0))
        .then(pl.col("rookie_total_cpoe") / pl.col("rookie_cpoe_attempts"))
        .otherwise(None)
        .alias("rookie_cpoe"),
        pl.when(~timing_ok)
        .then(pl.lit("ROOKIE_SEASON_UNRESOLVED"))
        .when(pl.col("rookie_dropbacks").is_null())
        .then(pl.lit("NO_RECORDED_DRAFT_YEAR_QB_OUTCOME"))
        .when(pl.col("rookie_dropbacks") < MIN_ROOKIE_DROPBACKS)
        .then(pl.lit("INSUFFICIENT_SAMPLE"))
        .otherwise(pl.lit("EVALUATION_ELIGIBLE"))
        .alias("outcome_status"),
        pl.lit(False).alias("model_eligible"),
        pl.lit("SOURCE_NOT_AVAILABLE").alias("college_missingness_reason"),
    )
    return result.sort("target_season", "player_id")


def planned_folds(cohort: pl.DataFrame) -> pl.DataFrame:
    """Chronological audit assignments, explicitly NOT executed model folds."""
    rows = []
    for year in sorted(set(cohort["target_season"])):
        for row in cohort.filter(pl.col("target_season") <= year).to_dicts():
            rows.append(
                {
                    "test_season": year,
                    "player_id": row["player_id"],
                    "row_season": row["target_season"],
                    "partition": "TEST" if row["target_season"] == year else "TRAIN_CANDIDATE",
                    "outcome_eligible": row["outcome_status"] == "EVALUATION_ELIGIBLE",
                    "model_eligible": False,
                    "status": "NOT_RUN_SOURCE_GATE",
                }
            )
    return pl.DataFrame(rows).sort("test_season", "row_season", "player_id")


def assemble_tables(players: pl.DataFrame, outcomes: pl.DataFrame, audit: dict) -> dict:
    if audit["gate"] != STATUS or audit["college_histories_ingested"]:
        raise ValueError("C20 gate-only contract cannot admit a college corpus or fit models")
    universe = build_universe(players)
    cohort = attach_outcomes(universe, outcomes)
    registry = pl.DataFrame([asdict(item) for item in college_registry()])
    crosswalk = universe.select("player_id", "display_name", "draft_year").with_columns(
        pl.lit(None, dtype=pl.String).alias("college_player_id"),
        pl.lit("NFL_ID_RESOLVED_COLLEGE_SOURCE_UNAVAILABLE").alias("mapping_status"),
        pl.lit("SOURCE_NOT_AVAILABLE").alias("missingness_reason"),
    )
    profiles = universe.select("player_id", "target_season", "as_of_date").with_columns(
        *[pl.lit(None, dtype=pl.Float64).alias(f"college_{f}") for f in sorted(COLLEGE_FEATURES)],
        pl.lit(None, dtype=pl.String).alias("college_school"),
        pl.lit(None, dtype=pl.String).alias("college_conference"),
        pl.lit(None, dtype=pl.Int64).alias("final_college_season"),
        pl.lit("SOURCE_NOT_AVAILABLE").alias("missingness_reason"),
    )
    coverage = (
        cohort.group_by("draft_year")
        .agg(
            pl.len().alias("drafted_canonical_qbs"),
            pl.col("rookie_dropbacks").is_not_null().sum().alias("draft_year_outcome_rows"),
            pl.col("rookie_epa_per_dropback").is_not_null().sum().alias("rookie_outcome_rows"),
            (pl.col("outcome_status") == "EVALUATION_ELIGIBLE")
            .sum()
            .alias("qualified_rookie_rows"),
            (pl.col("rookie_timing_status") != "CONSISTENT")
            .sum()
            .alias("rookie_timing_unresolved"),
            pl.col("draft_round").null_count().alias("draft_round_missing"),
            pl.col("draft_pick").null_count().alias("draft_pick_missing"),
            pl.col("age_at_cutoff").null_count().alias("age_missing"),
        )
        .with_columns(pl.lit(0).alias("college_matches"))
        .sort("draft_year")
    )
    comparisons = pl.DataFrame(
        [
            {
                "model": model,
                "feature_family": family,
                "status": "NOT_FIT_SOURCE_GATE",
                "n": 0,
                "rmse": None,
                "mae": None,
                "pearson": None,
                "spearman": None,
                "calibration_slope": None,
                "calibration_intercept": None,
            }
            for model, family in (
                ("B0", "rookie_mean"),
                ("B1", "draft_only"),
                ("B2", "college_only"),
                ("M1", "draft_and_college"),
                ("M2", "optional_challenger_not_attempted"),
            )
        ]
    )
    decision = {
        "status": STATUS,
        "checkpoint_status": "COMPLETE_DATA_GATE_CLOSEOUT",
        "selected_model": None,
        "prediction_count": 0,
        "rookie_state_created": False,
        "c19_rookie_support": "NOT_READY",
        "c18_status": "NOT_READY",
        "reason": "No approved accessible college corpus or verified college-to-GSIS crosswalk",
        "draft_years": [min(DRAFT_YEARS), max(DRAFT_YEARS)],
        "cohort_rows": cohort.height,
        "college_matches": 0,
        "rookie_outcomes": cohort["rookie_epa_per_dropback"].count(),
        "qualified_rookie_outcomes": cohort.filter(
            pl.col("outcome_status") == "EVALUATION_ELIGIBLE"
        ).height,
        "minimum_rookie_dropbacks": MIN_ROOKIE_DROPBACKS,
        "outcome_status_counts": dict(cohort.group_by("outcome_status").len().iter_rows()),
        "cohort_scope": (
            "canonical drafted NFL QBs in existing master, not an exhaustive draft ledger"
        ),
        "unresolved_rookie_years": cohort.filter(pl.col("rookie_timing_status") != "CONSISTENT")
        .select("player_id", "display_name", "draft_year", "reported_rookie_season")
        .to_dicts(),
    }
    return {
        "source_audit.json": audit,
        "source_audit.csv": pl.DataFrame(audit["sources"]),
        "player_identity_crosswalk.parquet": crosswalk,
        "rookie_state_universe.parquet": universe,
        "historical_rookie_cohort.parquet": cohort,
        "college_qb_profiles.parquet": profiles,
        "feature_registry.csv": registry,
        "fold_assignments.parquet": planned_folds(cohort),
        "baseline_comparisons.csv": comparisons.filter(pl.col("model").str.starts_with("B")),
        "model_comparisons.csv": comparisons,
        "missingness_coverage.csv": coverage,
        "out_of_sample_predictions.parquet": pl.DataFrame(
            schema={
                "player_id": pl.String,
                "target_season": pl.Int64,
                "model": pl.String,
                "prediction": pl.Float64,
                "status": pl.String,
            }
        ),
        "uncertainty_coverage.csv": pl.DataFrame(
            [
                {
                    "nominal_coverage": level,
                    "n": 0,
                    "empirical_coverage": None,
                    "method": "NOT_FIT_SOURCE_GATE",
                    "status": STATUS,
                }
                for level in (0.5, 0.8, 0.95)
            ]
        ),
        "subgroup_diagnostics.csv": cohort.with_columns(
            pl.when(pl.col("draft_round").is_null())
            .then(pl.lit("UNKNOWN_ROUND"))
            .when(pl.col("draft_round") <= 2)
            .then(pl.lit("EARLY_ROUND_1_2"))
            .otherwise(pl.lit("LATER_ROUND"))
            .alias("subgroup")
        )
        .group_by("subgroup")
        .agg(
            pl.len().alias("cohort_n"),
            (pl.col("outcome_status") == "EVALUATION_ELIGIBLE").sum().alias("outcome_eligible_n"),
        )
        .with_columns(pl.lit("NOT_FIT_SOURCE_GATE").alias("status"))
        .sort("subgroup"),
        "style_translation_results.csv": pl.DataFrame(
            [
                {"mapping": name, "n": 0, "estimate": None, "status": STATUS}
                for name in ("college_mobility_to_nfl_scramble", "college_depth_to_nfl_depth")
            ]
        ),
        "leakage_audit.csv": pl.DataFrame(
            [
                {"check": check, "status": "PASS", "details": detail}
                for check, detail in (
                    ("universe", "Immutable draft facts only; no participation-based inclusion"),
                    (
                        "outcomes",
                        "Left-joined draft-year targets only; no later-season substitution",
                    ),
                    ("rookie_year", "Conflicting entry metadata suppresses evaluation rates"),
                    (
                        "college_predictors",
                        "All null; no target NFL or future master fields admitted",
                    ),
                    (
                        "chronological_folds",
                        "Candidates earlier than test year; no fitted transformations",
                    ),
                    (
                        "models",
                        "No estimator, tuning, standardization or interval calibration executed",
                    ),
                    ("public_behavior", "No C19 rookie route or production behavior changed"),
                )
            ]
        ),
        "final_decision.json": decision,
    }


def build_checkpoint_twenty(project: Path, output: Path) -> Path:
    hashes = {}

    def capture(path: Path) -> bytes:
        content = path.read_bytes()
        hashes[str(path.relative_to(project))] = digest(content)
        return content

    def table(family: str, name: str) -> pl.DataFrame:
        root = project / "data/processed" / family / VERSIONS[family]
        manifest = json.loads(capture(root / "RUN_MANIFEST.json"))
        checksums = json.loads(capture(root / "OUTPUT_CHECKSUMS.json"))
        if manifest["data_version"] != VERSIONS[family]:
            raise ValueError("source version mismatch")
        content = capture(root / name)
        if digest(content) != checksums[name]["sha256"]:
            raise ValueError("source checksum mismatch")
        return pl.read_parquet(io.BytesIO(content))

    players = table("historical", "bronze/players/players.parquet")
    outcomes = table("enhancements", "canonical_qb_team_season_performance.parquet")
    c13 = project / "data/processed/predictive_foundation" / VERSIONS["predictive_foundation"]
    if (
        json.loads(capture(c13 / "MANIFEST.json"))["data_version"]
        != VERSIONS["predictive_foundation"]
    ):
        raise ValueError("C13 identity mismatch")
    audit = json.loads(capture(project / "research/rookie_projection/source_audit.json"))
    artifacts = assemble_tables(players, outcomes, audit)
    artifacts["source_lineage.json"] = {"versions": VERSIONS, "input_sha256": dict(hashes)}
    module_root = Path(__file__).parent
    identity = {
        "contract": CONTRACT,
        "inputs": hashes,
        "versions": VERSIONS,
        "source_code": {
            name: digest((module_root / name).read_bytes())
            for name in ("rookie_projection.py", "predictive_foundation.py", "constants.py")
        },
        "python": platform.python_version(),
        "polars": pl.__version__,
        "draft_years": DRAFT_YEARS,
        "minimum_dropbacks": MIN_ROOKIE_DROPBACKS,
        "serialization": "sorted-json-csv-empty-null-parquet-zstd-rowgroup10000-v1",
    }
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".c20-", dir=output) as temporary:
        stage = Path(temporary)
        for name, value in sorted(artifacts.items()):
            path = stage / name
            if name.endswith(".json"):
                path.write_bytes(json_bytes(value))
            elif name.endswith(".parquet"):
                value.write_parquet(path, compression="zstd", row_group_size=10000)
            else:
                value.write_csv(path, null_value="")
        checksums = {p.name: digest(p.read_bytes()) for p in sorted(stage.iterdir())}
        identity["artifact_sha256"] = checksums
        version = "c20-" + digest(json_bytes(identity))[:16]
        (stage / "MANIFEST.json").write_bytes(
            json_bytes(
                {
                    "data_version": version,
                    "identity": identity,
                    "output_checksums": checksums,
                    "status": STATUS,
                }
            )
        )
        destination = output / version
        if destination.exists():
            if sorted(p.name for p in destination.iterdir()) != sorted(
                p.name for p in stage.iterdir()
            ):
                raise ValueError("immutable C20 artifact inventory mismatch")
            for path in stage.iterdir():
                if (destination / path.name).read_bytes() != path.read_bytes():
                    raise ValueError("immutable C20 artifact mismatch")
        else:
            os.replace(stage, destination)
    with tempfile.NamedTemporaryFile(dir=output, prefix=".LATEST-", delete=False) as pointer:
        pointer.write((version + "\n").encode())
    os.replace(pointer.name, output / "LATEST")
    return destination
