"""Canonical position eligibility for every quarterback-specific publication."""

from __future__ import annotations

import polars as pl

from .errors import PipelineError

QB_POSITION = "QB"
QB_ELIGIBILITY_VERSION = "canonical-position-qb-v1"


def partition_canonical_qb_rows(
    frame: pl.DataFrame,
    players: pl.DataFrame,
    *,
    dataset: str,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return canonical-QB rows and explicit exclusions without changing source rows."""

    if "player_id" not in frame.columns:
        raise PipelineError(f"{dataset} lacks player_id for QB eligibility")
    required = {"player_id", "position"}
    missing = required - set(players.columns)
    if missing:
        raise PipelineError(f"players lack QB eligibility columns: {sorted(missing)}")
    if players.select("player_id").n_unique() != players.height:
        raise PipelineError("canonical players contain duplicate player_id values")

    original_columns = frame.columns
    joined = frame.join(
        players.select(
            "player_id",
            pl.col("position")
            .cast(pl.String)
            .str.strip_chars()
            .str.to_uppercase()
            .alias("canonical_position"),
        ),
        on="player_id",
        how="left",
        validate="m:1",
    )
    eligible = joined.filter(pl.col("canonical_position") == QB_POSITION).select(original_columns)
    excluded = joined.filter(
        pl.col("canonical_position").is_null() | (pl.col("canonical_position") != QB_POSITION)
    ).with_columns(
        pl.lit(dataset).alias("source_dataset"),
        pl.when(pl.col("canonical_position").is_null())
        .then(pl.lit("missing_canonical_position"))
        .otherwise(pl.lit("canonical_position_not_qb"))
        .alias("exclusion_reason"),
        pl.lit(QB_ELIGIBILITY_VERSION).alias("qb_eligibility_version"),
    )
    return eligible, excluded


def assert_canonical_qb_rows(
    frame: pl.DataFrame,
    players: pl.DataFrame,
    *,
    dataset: str,
) -> None:
    """Fail closed when a QB-specific frame contains a non-QB identity."""

    _, excluded = partition_canonical_qb_rows(frame, players, dataset=dataset)
    if excluded.height:
        sample_columns = [
            column
            for column in ("player_id", "canonical_position", "season", "team_id")
            if column in excluded.columns
        ]
        sample = excluded.select(sample_columns).head(5)
        raise PipelineError(
            f"{dataset} contains {excluded.height} non-QB rows; sample={sample.to_dicts()}"
        )
