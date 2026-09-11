"""C17: gated conditional destination associations, never a causal transfer model."""

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
from sklearn.linear_model import Ridge

from . import player_scheme_fit as fit
from . import predictive_foundation as foundation
from . import qb_projection as qp

BASELINE_SHA = "da75c03563db4b6e033b140783767d00fc7149e7"
BASE_VERSION = "c16r-8c8063c5954e2a22"
ORIGINAL_VERSION = "c16-c7cee27a36eb0445"
KEY = ["player_id", "team_id", "target_season"]
SCHEME = fit.CORE_SCHEME_FEATURES
INTERACTIONS = fit.INTERACTION_DEFINITIONS
STYLE = tuple(sorted({p for _, p, _, _ in INTERACTIONS}))
SCHEME_COLUMNS = tuple(f"scheme_{n}" for n in SCHEME)
MODELS = ("M0", "M1", "M2")
LABEL = "CONDITIONAL HISTORICAL ASSOCIATION — HYPOTHETICAL DESTINATION"


@dataclass(frozen=True)
class ScenarioConfig:
    specification: str = "c17-conditional-destination-ridge-v1"
    minimum_dropbacks: int = 50
    minimum_train: int = 120
    minimum_train_seasons: int = 3
    minimum_test: int = 20
    inner_train: int = 80
    inner_seasons: int = 2
    inner_test: int = 15
    minimum_feature: int = 10
    alphas: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0, 1000.0)
    default_alpha: float = 100.0
    development_end: int = 2018
    selection_folds: int = 3
    relative_gain: float = 0.02
    win_fraction: float = 0.60
    development_rmse_ratio: float = 1.01
    validation_n: int = 200
    validation_folds: int = 5
    changer_n: int = 50
    changer_qbs: int = 30
    changer_folds: int = 5
    interval_window: int = 5
    interval_n: int = 100
    interval_levels: tuple[float, ...] = (0.50, 0.80, 0.95)
    coverage_tolerance: float = 0.06
    slope_bounds: tuple[float, float] = (0.5, 1.5)
    intercept_bound: float = 0.05
    bootstrap_draws: int = 1000
    placebo_draws: int = 1000
    seed: int = 17026
    high_volume: int = 200
    support_distance_quantile: float = 0.95
    design_rank_tolerance: float = 1e-8


def _frame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


def _capture(directory: Path, files: tuple[str, ...], manifest_name="MANIFEST.json"):
    raw = (directory / manifest_name).read_bytes()
    manifest = json.loads(raw)
    hashes = {f"{directory.name}/{manifest_name}": qp._digest(raw)}
    frames = {}
    for name in files:
        content = (directory / name).read_bytes()
        digest = qp._digest(content)
        if digest != manifest["output_checksums"][name]:
            raise ValueError(f"frozen input checksum mismatch: {name}")
        hashes[f"{directory.name}/{name}"] = digest
        frames[name] = (
            pl.read_parquet(io.BytesIO(content))
            if name.endswith("parquet")
            else pl.read_csv(io.BytesIO(content))
        )
    return frames, hashes, manifest


def load_inputs(project: Path):
    """Hash and parse the same captured bytes, retaining frozen parent identities."""
    root = project / "data/processed"
    frames, hashes = qp.load_inputs(project)
    base, bh, bm = _capture(
        root / "qb_projection_refinement" / BASE_VERSION,
        (
            "calibrated_oos_predictions.parquet",
            "projections_2026.parquet",
            "candidate_predictors_2026.parquet",
        ),
    )
    if bm["data_version"] != BASE_VERSION or bm["original_version"] != ORIGINAL_VERSION:
        raise ValueError("C16 baseline version mismatch")
    if "c16r-" + qp._digest(qp._json_bytes(bm["identity"]))[:16] != BASE_VERSION:
        raise ValueError("C16 content identity mismatch")
    if bm["selected_base_models"]["epa"] != "B2" or bm["selected_calibrators"]["epa"] != "BIAS":
        raise ValueError("unapproved C16 baseline")
    source, sh, sm = _capture(
        root / "predictive_foundation" / qp.C13_VERSION,
        ("feature_registry.csv", "predictive_feature_records.csv"),
    )
    if sm["data_version"] != qp.C13_VERSION:
        raise ValueError("scheme identity mismatch")
    # Use the real C13 interface with captured bytes, not a second filesystem read.
    store = foundation.AsOfFeatureStore.__new__(foundation.AsOfFeatureStore)
    store.manifest = sm
    store.registry = {r["name"]: r for r in source["feature_registry.csv"].to_dicts()}
    store.records = source["predictive_feature_records.csv"]
    predictors, lineage = qp.build_predictors(
        frames["states"], frames["records"], frames["registry"]
    )
    frames.update(base)
    frames["predictors"] = predictors
    frames["player_lineage"] = lineage.filter(pl.col("feature_name").is_in(STYLE))
    hashes.update(bh)
    hashes.update(sh)
    return frames, store, hashes


def scheme_matrix(store: foundation.AsOfFeatureStore, years: tuple[int, ...]):
    selected = store.records.filter(pl.col("feature_name").is_in(SCHEME))
    registry = tuple(foundation.FeatureDefinition(**r) for r in store.registry.values())
    foundation.validate_feature_records(selected, registry)
    if selected.filter(
        pl.any_horizontal(pl.col("source_season", "source_available_date", "as_of_date").is_null())
        | (pl.col("source_season") >= pl.col("target_season"))
        | (pl.col("source_available_date") > pl.col("as_of_date"))
        | (pl.col("as_of_date") != pl.col("target_season").cast(pl.String) + "-08-31")
        | (pl.col("standardization_fit_end_season") >= pl.col("target_season"))
        | (pl.col("raw_value").is_not_null() & ~pl.col("raw_value").is_finite())
        | (pl.col("raw_value").is_null() & pl.col("missingness_reason").is_null())
    ).height:
        raise ValueError("scheme source/as-of/value leakage")
    matrices = []
    for year in years:
        store.target_matrix(target_season=year, feature_names=SCHEME)
        rows = selected.filter(pl.col("target_season") == year)
        raw = rows.select("entity_id", "feature_name", "raw_value").pivot(
            on="feature_name", index="entity_id", values="raw_value"
        )
        meta = rows.group_by("entity_id").agg(
            pl.col("source_season").max().alias("scheme_max_source_season"),
            pl.col("sample_size").min().alias("scheme_min_sample"),
        )
        raw = (
            raw.join(meta, on="entity_id", validate="1:1")
            .with_columns(
                pl.col("entity_id")
                .str.extract(r"^team:([^:]+):season:[0-9]+$", 1)
                .map_elements(fit._canonical_team, return_dtype=pl.String)
                .alias("team_id"),
                pl.lit(year).alias("target_season"),
            )
            .drop("entity_id")
            .rename({n: f"scheme_{n}" for n in SCHEME})
        )
        matrices.append(raw)
    result = pl.concat(matrices, how="vertical_relaxed").sort("target_season", "team_id")
    qp._assert_grain(result, ["team_id", "target_season"])
    return result, selected.sort("target_season", "entity_id", "feature_name")


def build_cohort(predictors, performance, baseline, scheme, config: ScenarioConfig):
    """Attach supplied condition separately; outcomes cannot create Player State."""
    qp._assert_grain(predictors, qp.KEY)
    if predictors.filter(
        (pl.col("maximum_source_season").is_null() & pl.any_horizontal(pl.col(STYLE).is_not_null()))
        | (pl.col("maximum_source_season") >= pl.col("target_season"))
        | (pl.col("as_of_date") != pl.col("target_season").cast(pl.String) + "-08-31")
    ).height:
        raise ValueError("player source/as-of leakage")
    base = baseline.filter((pl.col("outcome") == "epa") & (pl.col("model") == "BIAS"))
    qp._assert_grain(base, qp.KEY)
    if base.filter(
        (pl.col("base_model") != "B2")
        | (pl.col("train_end_season") >= pl.col("target_season"))
        | (pl.col("fit_end") >= pl.col("target_season"))
        | pl.col("prediction").is_null()
        | ~pl.col("prediction").is_finite()
    ).height:
        raise ValueError("C16 baseline lineage leakage")
    base = base.select(
        *qp.KEY, pl.col("prediction").alias("base_epa"), "train_end_season", "fit_end"
    )
    qp._assert_grain(performance, ["player_id", "team_id", "season"])
    if performance.filter(
        (pl.col("dropbacks") <= 0)
        | pl.col("total_qb_epa").is_null()
        | ~pl.col("total_qb_epa").is_finite()
    ).height:
        raise ValueError("invalid stint outcome")
    stints = (
        performance.filter(
            (pl.col("scope") == "analysis") & pl.col("season").is_between(2010, 2025)
        )
        .select(
            "player_id",
            "team_id",
            pl.col("season").alias("target_season"),
            "dropbacks",
            (pl.col("total_qb_epa") / pl.col("dropbacks")).alias("actual"),
        )
        .with_columns(pl.len().over(qp.KEY).alias("observed_team_count"))
    )
    prior = (
        performance.filter(pl.col("dropbacks") >= config.minimum_dropbacks)
        .group_by("player_id", "season")
        .agg(pl.col("team_id").sort().alias("prior_teams"))
        .with_columns((pl.col("season") + 1).alias("target_season"))
        .drop("season")
    )
    state = predictors.select(
        *qp.KEY,
        "as_of_date",
        "maximum_source_season",
        "state_version",
        "state_data_version",
        "preseason_ability_reliability",
        "preseason_ability_standard_error",
        *STYLE,
    ).with_columns(pl.lit(True).alias("state_matched"))
    result = (
        stints.join(prior, on=qp.KEY, how="left", validate="m:1")
        .join(state, on=qp.KEY, how="left", validate="m:1")
        .join(base, on=qp.KEY, how="left", validate="m:1")
        .join(scheme, on=["team_id", "target_season"], how="left", validate="m:1")
        .with_columns(
            pl.when(pl.col("prior_teams").is_not_null())
            .then(~pl.col("prior_teams").list.contains(pl.col("team_id")))
            .alias("team_change"),
            pl.lit("SUPPLIED_RETROSPECTIVE_CONDITION_NOT_PRESEASON_ASSIGNMENT").alias(
                "condition_basis"
            ),
            pl.lit(False).alias("preseason_assignment_claim"),
            pl.when(pl.col("state_matched").is_null())
            .then(pl.lit("NOT_IN_ASOF_STATE_UNIVERSE"))
            .when(pl.col("base_epa").is_null())
            .then(pl.lit("C16_OOS_BASELINE_UNAVAILABLE"))
            .when(pl.col("dropbacks") < config.minimum_dropbacks)
            .then(pl.lit("INSUFFICIENT_SAMPLE"))
            .when(pl.col("scheme_max_source_season").is_null())
            .then(pl.lit("SOURCE_NOT_AVAILABLE"))
            .otherwise(pl.lit(None, dtype=pl.String))
            .alias("exclusion_reason"),
        )
        .with_columns(
            pl.col("exclusion_reason").is_null().alias("eligible"),
            (pl.col("actual") - pl.col("base_epa")).alias("residual_target"),
        )
        .drop("prior_teams")
    )
    qp._assert_grain(result, KEY)
    return result.sort("target_season", "player_id", "team_id")


def validate_predictor_names(names):
    if not names or set(names) - set(SCHEME_COLUMNS + STYLE):
        raise ValueError("unregistered or forbidden scenario predictor")


@dataclass
class Design:
    """Train-centered main effects, orthogonalized interaction block; no outcome access."""

    scheme: fit.FoldPreprocessor
    player: fit.FoldPreprocessor | None
    center: np.ndarray
    interaction_projection: np.ndarray | None
    interaction_scale: np.ndarray | None
    interaction_names: tuple[str, ...]
    model: str

    @staticmethod
    def _products(frame, sx, sn, px, pn):
        columns, names = [], []
        for name, p, s, _ in INTERACTIONS:
            s = "scheme_" + s
            if p not in pn or s not in sn:
                continue
            observed = (frame[p].is_not_null() & frame[s].is_not_null()).to_numpy().astype(float)
            columns.extend((px[:, pn.index(p)] * sx[:, sn.index(s)] * observed, observed))
            names.extend((name, name + "__observed"))
        return np.column_stack(columns), tuple(names)

    @classmethod
    def fit(cls, train, year, model, config):
        if model not in ("M1", "M2"):
            raise ValueError("unknown environment model")
        validate_predictor_names(SCHEME_COLUMNS + STYLE)
        sp = fit.FoldPreprocessor.fit(
            train, SCHEME_COLUMNS, target_season=year, minimum_values=config.minimum_feature
        )
        sx, sn = sp.transform(train)
        center = sx.mean(axis=0)
        if model == "M1":
            return cls(sp, None, center, None, None, (), model)
        pp = fit.FoldPreprocessor.fit(
            train, STYLE, target_season=year, minimum_values=config.minimum_feature
        )
        px, pn = pp.transform(train)
        product, names = cls._products(train, sx, sn, px, pn)
        main = np.column_stack((np.ones(len(sx)), sx, px))
        # Compositional depth rates and their rounded source serializations produce
        # near-exact linear dependencies. Truncate numerical rank, not noisy data.
        projection = np.linalg.lstsq(main, product, rcond=config.design_rank_tolerance)[0]
        scale = (product - main @ projection).std(axis=0)
        scale = np.where(scale > 1e-10, scale, 1.0)
        return cls(sp, pp, center, projection, scale, names, model)

    def transform(self, frame):
        sx, sn = self.scheme.transform(frame)
        x = sx - self.center
        if self.model == "M1":
            return x, sn
        px, pn = self.player.transform(frame)
        product, names = self._products(frame, sx, sn, px, pn)
        if names != self.interaction_names:
            raise ValueError("interaction design changed")
        main = np.column_stack((np.ones(len(sx)), sx, px))
        z = (product - main @ self.interaction_projection) / self.interaction_scale
        return np.column_stack((x, z)), sn + names


def fit_adjustment(train, test, year, model, alpha, config):
    if train.filter(pl.col("target_season") >= year).height:
        raise ValueError("target/future training leakage")
    design = Design.fit(train, year, model, config)
    x, names = design.transform(train)
    xt, _ = design.transform(test)
    ridge = Ridge(alpha=alpha, fit_intercept=False, solver="svd")
    ridge.fit(x, train["residual_target"].to_numpy())
    return ridge.predict(xt), ridge, design, names


def tune_alpha(train, year, model, config):
    if train.filter(pl.col("target_season") >= year).height:
        raise ValueError("target/future tuning leakage")
    scores = {a: [] for a in config.alphas}
    audit = []
    for inner in sorted(train["target_season"].unique().to_list()):
        past = train.filter(pl.col("target_season") < inner)
        held = train.filter(pl.col("target_season") == inner)
        if (
            past.height < config.inner_train
            or past["target_season"].n_unique() < config.inner_seasons
            or held.height < config.inner_test
        ):
            continue
        # Learn transformations once per inner fold, never once for the outer dataset.
        d = Design.fit(past, inner, model, config)
        x, _ = d.transform(past)
        xt, _ = d.transform(held)
        for alpha in config.alphas:
            r = Ridge(alpha=alpha, fit_intercept=False, solver="svd").fit(
                x, past["residual_target"]
            )
            error = float(
                np.abs(
                    held["actual"].to_numpy() - held["base_epa"].to_numpy() - r.predict(xt)
                ).mean()
            )
            scores[alpha].append(error)
            audit.append(
                {
                    "target_season": year,
                    "model": model,
                    "inner_year": inner,
                    "fit_end": int(past["target_season"].max()),
                    "alpha": alpha,
                    "mae": error,
                }
            )
    candidates = [(float(np.mean(v)), -a, a) for a, v in scores.items() if v]
    return min(candidates)[2] if candidates else config.default_alpha, audit


def rolling_models(cohort, config):
    eligible = cohort.filter(pl.col("eligible"))
    rows, folds, coefficients, tuning = [], [], [], []
    intervals_cfg = qp.ProjectionConfig(
        calibration_window=config.interval_window,
        minimum_calibration=config.interval_n,
        interval_levels=config.interval_levels,
    )
    for year in sorted(eligible["target_season"].unique().to_list()):
        train = eligible.filter(pl.col("target_season") < year)
        test = eligible.filter(pl.col("target_season") == year)
        if (
            train.height < config.minimum_train
            or train["target_season"].n_unique() < config.minimum_train_seasons
            or test.height < config.minimum_test
        ):
            continue
        history = _frame(rows) if rows else pl.DataFrame()
        for model in MODELS:
            alpha = None
            adjustment = np.zeros(test.height)
            if model != "M0":
                alpha, audit = tune_alpha(train, year, model, config)
                tuning.extend(audit)
                adjustment, r, _, names = fit_adjustment(train, test, year, model, alpha, config)
                coefficients.extend(
                    {
                        "target_season": year,
                        "model": model,
                        "feature": n,
                        "standardized_coefficient": float(c),
                        "alpha": alpha,
                        "train_end": int(train["target_season"].max()),
                    }
                    for n, c in zip(names, r.coef_, strict=True)
                )
            radii = qp.residual_intervals(history, year, "epa", model, intervals_cfg)
            folds.append(
                {
                    "target_season": year,
                    "model": model,
                    "train_n": train.height,
                    "test_n": test.height,
                    "train_end": int(train["target_season"].max()),
                    "train_start": int(train["target_season"].min()),
                    "alpha": alpha,
                }
            )
            for row, delta in zip(test.to_dicts(), adjustment, strict=True):
                prediction = row["base_epa"] + float(delta)
                record = {
                    k: row[k]
                    for k in KEY
                    + [
                        "actual",
                        "base_epa",
                        "dropbacks",
                        "team_change",
                        "observed_team_count",
                        "preseason_ability_reliability",
                    ]
                }
                record.update(
                    {
                        "outcome": "epa",
                        "model": model,
                        "prediction": prediction,
                        "adjustment": float(delta),
                        **radii,
                    }
                )
                for p in config.interval_levels:
                    pct = round(100 * p)
                    radius = radii[f"radius_{pct}"]
                    record[f"lower_{pct}"] = prediction - radius if radius is not None else None
                    record[f"upper_{pct}"] = prediction + radius if radius is not None else None
                rows.append(record)
    if not rows:
        raise ValueError("NOT ESTIMABLE / DATA-LIMITED: no qualified rolling folds")
    return _frame(rows), _frame(folds), _frame(coefficients), _frame(tuning)


def summarize(predictions, config):
    rows = []
    for period, frame in (
        ("development", predictions.filter(pl.col("target_season") <= config.development_end)),
        ("validation", predictions.filter(pl.col("target_season") > config.development_end)),
        ("all_oos", predictions),
    ):
        for subset, part in (
            ("all", frame),
            ("team_changers", frame.filter(pl.col("team_change"))),
            ("team_stayers", frame.filter(~pl.col("team_change"))),
            ("single_team", frame.filter(pl.col("observed_team_count") == 1)),
            ("high_volume", frame.filter(pl.col("dropbacks") >= config.high_volume)),
            (
                "reliable_state",
                frame.filter(pl.col("preseason_ability_reliability").is_in(["HIGH", "MEDIUM"])),
            ),
        ):
            for model in MODELS:
                f = part.filter(pl.col("model") == model)
                if f.height:
                    rows.append(
                        {
                            "period": period,
                            "subset": subset,
                            "model": model,
                            "folds": f["target_season"].n_unique(),
                            "qbs": f["player_id"].n_unique(),
                            **fit._metrics(f["actual"].to_numpy(), f["prediction"].to_numpy(), 0.0),
                        }
                    )
    folds, coverage = [], []
    for (year, model), f in predictions.group_by("target_season", "model", maintain_order=True):
        for subset, part in (
            ("all", f),
            ("team_changers", f.filter(pl.col("team_change"))),
        ):
            if part.height:
                folds.append(
                    {
                        "target_season": year,
                        "model": model,
                        "subset": subset,
                        **fit._metrics(
                            part["actual"].to_numpy(), part["prediction"].to_numpy(), 0.0
                        ),
                    }
                )
    for model in MODELS:
        f = predictions.filter(
            (pl.col("model") == model) & (pl.col("target_season") > config.development_end)
        )
        for p in config.interval_levels:
            pct = round(100 * p)
            usable = f.filter(pl.col(f"lower_{pct}").is_not_null())
            coverage.append(
                {
                    "model": model,
                    "level": p,
                    "n": usable.height,
                    "missing_n": f.height - usable.height,
                    "coverage": float(
                        usable.select(
                            pl.col("actual")
                            .is_between(pl.col(f"lower_{pct}"), pl.col(f"upper_{pct}"))
                            .mean()
                        ).item()
                    )
                    if usable.height
                    else None,
                }
            )
    return _frame(rows), _frame(folds), _frame(coverage)


def paired(predictions, candidate, reference):
    a = predictions.filter(pl.col("model") == candidate)
    b = predictions.filter(pl.col("model") == reference)
    qp._assert_grain(a, KEY)
    qp._assert_grain(b, KEY)
    if a.height != b.height or a.join(b.select(KEY), on=KEY, how="anti").height:
        raise ValueError("unpaired comparison")
    return a.join(
        b.select(*KEY, pl.col("prediction").alias("reference_prediction")), on=KEY, validate="1:1"
    ).sort(KEY)


def resampling(predictions, config):
    """Paired fixed-OOS error uncertainty, NOT coefficient or causal uncertainty."""
    data = predictions.filter(pl.col("target_season") > config.development_end)
    rows, placebo = [], []
    for candidate, reference in (("M1", "M0"), ("M2", "M1")):
        all_pairs = paired(data, candidate, reference)
        for subset, f in (
            ("all", all_pairs),
            ("team_changers", all_pairs.filter(pl.col("team_change"))),
        ):
            if not f.height:
                continue
            for cluster in ("qb", "team_season"):
                keys = ["player_id"] if cluster == "qb" else ["team_id", "target_season"]
                groups = f.partition_by(keys, maintain_order=True)
                blocks = []
                for g in groups:
                    a = g["actual"].to_numpy()
                    e = a - g["prediction"].to_numpy()
                    r = a - g["reference_prediction"].to_numpy()
                    blocks.append(
                        [len(g), np.abs(r).sum(), np.abs(e).sum(), (r * r).sum(), (e * e).sum()]
                    )
                blocks = np.array(blocks)
                rng = np.random.default_rng(config.seed)
                draws = blocks[
                    rng.integers(0, len(blocks), (config.bootstrap_draws, len(blocks)))
                ].sum(axis=1)
                mae = (draws[:, 1] - draws[:, 2]) / draws[:, 0]
                rmse = np.sqrt(draws[:, 3] / draws[:, 0]) - np.sqrt(draws[:, 4] / draws[:, 0])
                rows.append(
                    {
                        "candidate": candidate,
                        "reference": reference,
                        "subset": subset,
                        "cluster": cluster,
                        "clusters": len(groups),
                        "n": f.height,
                        "successful_draws": config.bootstrap_draws,
                        "mae_gain_lower": float(np.quantile(mae, 0.025)),
                        "mae_gain_upper": float(np.quantile(mae, 0.975)),
                        "rmse_gain_lower": float(np.quantile(rmse, 0.025)),
                        "rmse_gain_upper": float(np.quantile(rmse, 0.975)),
                    }
                )
                if cluster == "qb":
                    gains = blocks[:, 1] - blocks[:, 2]
                    null = (
                        rng.choice([-1, 1], (config.placebo_draws, len(groups)))
                        @ gains
                        / blocks[:, 0].sum()
                    )
                    observed = float(gains.sum() / blocks[:, 0].sum())
                    placebo.append(
                        {
                            "candidate": candidate,
                            "reference": reference,
                            "subset": subset,
                            "method": "DESCRIPTIVE_PAIRED_QB_SIGN_FLIP_NOT_RANDOMIZED_ASSIGNMENT",
                            "draws": config.placebo_draws,
                            "observed_mae_gain": observed,
                            "one_sided_tail_fraction": float(
                                (1 + (null >= observed).sum()) / (1 + len(null))
                            ),
                        }
                    )
    return _frame(rows), _frame(placebo)


def decide(comparison, folds, coverage, bootstrap, config):
    def metric(model, period, subset="all"):
        f = comparison.filter(
            (pl.col("model") == model) & (pl.col("period") == period) & (pl.col("subset") == subset)
        )
        return f.row(0, named=True) if f.height else None

    rows = []
    for candidate, reference in (("M1", "M0"), ("M2", "M1")):
        gates = {}
        for period in ("development", "validation"):
            a, b = metric(candidate, period), metric(reference, period)
            fs = folds.filter(
                (pl.col("subset") == "all")
                & (
                    (pl.col("target_season") <= config.development_end)
                    if period == "development"
                    else (pl.col("target_season") > config.development_end)
                )
            )
            fa = fs.filter(pl.col("model") == candidate).sort("target_season")
            fb = fs.filter(pl.col("model") == reference).sort("target_season")
            if not a or not b or not fa.height:
                gates[period + "_sample"] = False
                continue
            gain = fb["mae"].to_numpy() - fa["mae"].to_numpy()
            if period == "development":
                se = (
                    float(np.std(gain, ddof=1) / math.sqrt(len(gain)))
                    if len(gain) > 1
                    else math.inf
                )
                gates["development_selection"] = bool(
                    len(gain) >= config.selection_folds
                    and gain.mean() > max(se, config.relative_gain * fb["mae"].mean())
                    and (gain > 0).mean() >= config.win_fraction
                    and fa["rmse"].mean() <= config.development_rmse_ratio * fb["rmse"].mean()
                )
            else:
                gates["validation_sample"] = (
                    a["n"] >= config.validation_n and a["folds"] >= config.validation_folds
                )
                gates["validation_accuracy"] = (
                    a["mae"] <= (1 - config.relative_gain) * b["mae"] and a["rmse"] <= b["rmse"]
                )
                gates["validation_fold_stability"] = bool((gain > 0).mean() >= config.win_fraction)
                gates["calibration"] = (
                    a["calibration_slope"] is not None
                    and config.slope_bounds[0] <= a["calibration_slope"] <= config.slope_bounds[1]
                    and abs(a["calibration_intercept"]) <= config.intercept_bound
                )
        intervals = coverage.filter(pl.col("model") == candidate)
        gates["intervals"] = intervals.height == len(config.interval_levels) and all(
            r["coverage"] is not None
            and r["missing_n"] == 0
            and abs(r["coverage"] - r["level"]) <= config.coverage_tolerance
            for r in intervals.to_dicts()
        )
        boot = bootstrap.filter((pl.col("candidate") == candidate) & (pl.col("subset") == "all"))
        gates["cluster_uncertainty"] = boot.height == 2 and bool((boot["mae_gain_lower"] > 0).all())
        for subset in ("single_team", "high_volume", "team_changers"):
            a, b = metric(candidate, "validation", subset), metric(reference, "validation", subset)
            gates[subset] = bool(a and b and a["mae"] < b["mae"] and a["rmse"] <= b["rmse"])
            if subset == "team_changers":
                gates["changer_sample"] = bool(
                    a
                    and a["n"] >= config.changer_n
                    and a["qbs"] >= config.changer_qbs
                    and a["folds"] >= config.changer_folds
                )
                cf = folds.filter(
                    (pl.col("subset") == subset)
                    & (pl.col("target_season") > config.development_end)
                )
                ca = cf.filter(pl.col("model") == candidate).sort("target_season")
                cb = cf.filter(pl.col("model") == reference).sort("target_season")
                gates["changer_stability"] = bool(
                    ca.height
                    and ((cb["mae"].to_numpy() - ca["mae"].to_numpy()) > 0).mean()
                    >= config.win_fraction
                )
        if candidate == "M2":
            gates["main_effect_model_approved"] = rows[0]["approved"]
        approved = all(gates.values())
        a, b = metric(candidate, "validation"), metric(reference, "validation")
        status = (
            "RESEARCH-READY WITH LIMITATIONS"
            if approved
            else (
                "EXPLORATORY ONLY"
                if a and b and a["mae"] < b["mae"] and a["rmse"] < b["rmse"]
                else "NOT SUPPORTED"
            )
        )
        rows.append(
            {
                "candidate": candidate,
                "reference": reference,
                "approved": approved,
                "status": status,
                "gates": json.dumps(gates, sort_keys=True),
                "failed_gates": ";".join(k for k, v in gates.items() if not v),
            }
        )
    return _frame(rows)


def forward_scenarios(candidates, base, scheme, train, predictions, decisions, config, version):
    approved = decisions.filter(pl.col("approved"))
    schema = {
        **{k: pl.String if k != "target_season" else pl.Int64 for k in KEY},
        "base_epa": pl.Float64,
        "adjustment": pl.Float64,
        "prediction": pl.Float64,
        "label": pl.String,
        "status": pl.String,
        "data_version": pl.String,
        **{
            f"{edge}_{round(100 * p)}": pl.Float64
            for p in config.interval_levels
            for edge in ("lower", "upper")
        },
    }
    if not approved.height:
        return pl.DataFrame(schema=schema)
    model = approved["candidate"][-1]
    if base.filter((pl.col("outcome") != "epa") | pl.col("active_roster_claim")).height:
        raise ValueError("only approved team-independent EPA candidates allowed")
    qp._assert_grain(candidates, qp.KEY)
    qp._assert_grain(base, qp.KEY)
    if candidates.filter(
        (pl.col("target_season") != 2026) | (pl.col("as_of_date") != "2026-08-31")
    ).height:
        raise ValueError("invalid forward as-of boundary")
    matrix = (
        candidates.select(*qp.KEY, *STYLE)
        .join(
            base.select(*qp.KEY, pl.col("prediction").alias("base_epa")), on=qp.KEY, validate="1:1"
        )
        .join(scheme.filter(pl.col("target_season") == 2026), on="target_season", how="inner")
    )
    if matrix.filter(pl.col("scheme_max_source_season") >= 2026).height:
        raise ValueError("forward scheme leakage")
    alpha, _ = tune_alpha(train, 2026, model, config)
    adjustments, _, design, _ = fit_adjustment(train, matrix, 2026, model, alpha, config)
    # Marginal range plus joint nearest-neighbor support. This is an extrapolation
    # guard, not proof of positivity or transportability.
    support_pp = fit.FoldPreprocessor.fit(train, SCHEME_COLUMNS + STYLE, target_season=2026)
    tx, _ = support_pp.transform(train)
    mx, _ = support_pp.transform(matrix)
    distance = ((tx[:, None, :] - tx[None, :, :]) ** 2).mean(axis=2)
    np.fill_diagonal(distance, np.inf)
    cutoff = np.quantile(distance.min(axis=1), config.support_distance_quantile)
    near = ((mx[:, None, :] - tx[None, :, :]) ** 2).mean(axis=2).min(axis=1) <= cutoff
    inside = ((mx >= tx.min(axis=0)) & (mx <= tx.max(axis=0))).all(axis=1)
    qc = qp.ProjectionConfig(
        calibration_window=config.interval_window,
        minimum_calibration=config.interval_n,
        interval_levels=config.interval_levels,
    )
    radii = qp.residual_intervals(predictions, 2026, "epa", model, qc)
    rows = []
    for i, row in enumerate(matrix.to_dicts()):
        available = bool(
            near[i]
            and inside[i]
            and all(radii[f"radius_{round(100 * p)}"] is not None for p in config.interval_levels)
        )
        p = row["base_epa"] + float(adjustments[i]) if available else None
        out = {k: row[k] for k in KEY + ["base_epa"]}
        out.update(
            {
                "adjustment": float(adjustments[i]) if available else None,
                "prediction": p,
                "label": LABEL,
                "status": "RESEARCH_ONLY" if available else "OUTSIDE_SUPPORTED_CONTEXT",
                "data_version": version,
            }
        )
        for level in config.interval_levels:
            pct = round(100 * level)
            out[f"lower_{pct}"] = p - radii[f"radius_{pct}"] if available else None
            out[f"upper_{pct}"] = p + radii[f"radius_{pct}"] if available else None
        rows.append(out)
    return _frame(rows)


def content_identity(hashes, config):
    _, identity = qp.content_identity(hashes, qp.ProjectionConfig())
    identity.update(
        {
            "baseline_sha": BASELINE_SHA,
            "anchor_version": BASE_VERSION,
            "scenario_config": asdict(config),
            "scenario_code": qp._digest(Path(__file__).read_bytes()),
            "scheme_features": SCHEME,
            "player_style": STYLE,
            "interaction_definitions": INTERACTIONS,
            "grain": KEY,
            "conditioning_contract": "SUPPLIED_NOT_PRESEASON_KNOWN",
            "targets": "EPA_STINT_ONLY_NO_PAE",
            "weighting": "EQUAL_STINT",
        }
    )
    identity = json.loads(qp._json_bytes(identity))
    return "c17-" + qp._digest(qp._json_bytes(identity))[:16], identity


def run_checkpoint_seventeen(project: Path, output_root: Path | None = None, config=None):
    config = config or ScenarioConfig()
    frames, store, hashes = load_inputs(project)
    version, identity = content_identity(hashes, config)
    root = output_root or project / "data/processed/qb_scenario"
    destination = root / version
    if destination.exists():
        manifest = json.loads((destination / "MANIFEST.json").read_bytes())
        if manifest["identity"] != identity:
            raise ValueError("scenario identity mismatch")
        for name, digest in manifest["output_checksums"].items():
            if qp._digest((destination / name).read_bytes()) != digest:
                raise ValueError("scenario output checksum mismatch")
        qp._publish_latest(root, version)
        return manifest
    scheme, lineage = scheme_matrix(store, tuple(range(2011, 2027)))
    cohort = build_cohort(
        frames["predictors"],
        frames["performance"],
        frames["calibrated_oos_predictions.parquet"],
        scheme,
        config,
    )
    predictions, folds, coefficients, tuning = rolling_models(cohort, config)
    comparison, fold_metrics, coverage = summarize(predictions, config)
    bootstrap, placebo = resampling(predictions, config)
    decisions = decide(comparison, fold_metrics, coverage, bootstrap, config)
    forward = forward_scenarios(
        frames["candidate_predictors_2026.parquet"],
        frames["projections_2026.parquet"],
        scheme,
        cohort.filter(pl.col("eligible")),
        predictions,
        decisions,
        config,
        version,
    )
    audit = _frame(
        [
            {
                "gate": "STATE_BEFORE_TARGET",
                "failures": cohort.filter(
                    pl.col("maximum_source_season") >= pl.col("target_season")
                ).height,
            },
            {
                "gate": "SCHEME_BEFORE_TARGET",
                "failures": cohort.filter(
                    pl.col("scheme_max_source_season") >= pl.col("target_season")
                ).height,
            },
            {
                "gate": "OUTER_FIT_BEFORE_TARGET",
                "failures": folds.filter(pl.col("train_end") >= pl.col("target_season")).height,
            },
            {
                "gate": "INNER_VALIDATION_BEFORE_OUTER",
                "failures": tuning.filter(
                    (pl.col("inner_year") >= pl.col("target_season"))
                    | (pl.col("fit_end") >= pl.col("inner_year"))
                ).height,
            },
            {
                "gate": "INTERVAL_HISTORY_BEFORE_TARGET",
                "failures": predictions.filter(
                    pl.col("calibration_end_season") >= pl.col("target_season")
                ).height,
            },
            {
                "gate": "NO_PRESEASON_ASSIGNMENT_CLAIM",
                "failures": cohort.filter(pl.col("preseason_assignment_claim")).height,
            },
        ]
    ).with_columns((pl.col("failures") == 0).alias("passed"))
    if not audit["passed"].all():
        raise ValueError("scenario leakage audit failed")
    registry = _frame(
        [
            {
                "feature": n,
                "family": "PLAYER_STYLE" if n in STYLE else "SCHEME",
                "permission": "HISTORICAL_ONLY",
                "normalization": "INNER_TRAIN_ONLY",
                "missingness": "RAW_NULL_TRAIN_MEDIAN_PLUS_INDICATOR",
            }
            for n in STYLE + SCHEME_COLUMNS
        ]
    )
    missingness = _frame(
        [
            {
                "feature": n,
                "cohort_n": cohort.filter(pl.col("eligible")).height,
                "missing_n": cohort.filter(pl.col("eligible"))[n].null_count(),
            }
            for n in STYLE + SCHEME_COLUMNS
        ]
    )
    artifacts = {
        "feature_registry.csv": registry,
        "modeling_cohort.parquet": cohort,
        "player_feature_lineage.parquet": frames["player_lineage"],
        "scheme_feature_lineage.parquet": lineage,
        "destination_scheme.parquet": scheme,
        "rolling_folds.csv": folds,
        "hyperparameter_audit.csv": tuning,
        "oos_predictions.parquet": predictions,
        "model_comparison.csv": comparison,
        "fold_metrics.csv": fold_metrics,
        "interaction_coefficients.csv": coefficients,
        "interval_coverage.csv": coverage,
        "cluster_bootstrap.csv": bootstrap,
        "placebo_results.csv": placebo,
        "scenario_decisions.csv": decisions,
        "missingness.csv": missingness,
        "leakage_audit.csv": audit,
        "hypothetical_scenarios_2026.parquet": forward,
        "interaction_definitions.csv": _frame(
            [{"name": n, "player": p, "scheme": s, "family": f} for n, p, s, f in INTERACTIONS]
        ),
    }
    approved = bool(decisions["approved"].any())
    status = (
        "RESEARCH-READY WITH LIMITATIONS"
        if approved
        else (
            "EXPLORATORY ONLY"
            if "EXPLORATORY ONLY" in decisions["status"].to_list()
            else "NOT SUPPORTED"
        )
    )
    manifest = {
        "data_version": version,
        "model_version": version.replace("c17-", "qb-scenario-"),
        "identity": identity,
        "checkpoint_status": "COMPLETE",
        "scenario_status": status,
        "checkpoint_18_readiness": "READY" if approved else "NOT READY",
        "counts": {
            "cohort": cohort.height,
            "eligible": cohort.filter(pl.col("eligible")).height,
            "oos_per_model": predictions.height // 3,
            "forward_rows": forward.height,
        },
        "decisions": decisions.to_dicts(),
        "output_checksums": {},
    }
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=root))
    try:
        for name, frame in artifacts.items():
            if name.endswith("parquet"):
                frame.write_parquet(
                    stage / name,
                    compression="zstd",
                    compression_level=3,
                    statistics=True,
                    row_group_size=10000,
                )
            else:
                frame.write_csv(stage / name, float_precision=15)
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
