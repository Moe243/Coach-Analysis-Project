"""Residualization and unweighted conceptual Coach Effect components."""

from __future__ import annotations

import numpy as np
import polars as pl
from sklearn.linear_model import LinearRegression

from research.coach_effect.config import CONCEPTUAL_COMPONENTS, CONCEPTUAL_WEIGHT_NAMES


def _require(frame: pl.DataFrame, columns: set[str]) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"coach signal frame is missing required columns: {missing}")


def _zscore(values: np.ndarray) -> np.ndarray:
    scale = float(np.std(values, ddof=0))
    if scale == 0:
        raise ValueError("component variance is required for residualization")
    return (values - float(np.mean(values))) / scale


def residualize_components(
    frame: pl.DataFrame,
    *,
    qb_column: str = "pae_signal",
    play_call_column: str = "pcae",
) -> tuple[pl.DataFrame, dict[str, float]]:
    """Separate unique linear residuals and a shared standardized direction.

    `unique_qb_development_signal` is PAE residualized on PCAE; the play-calling component is
    PCAE residualized on PAE. The shared signal is an unweighted diagnostic average of their
    standardized inputs, not a production score or fitted causal factor.
    """

    _require(frame, {qb_column, play_call_column})
    qb = frame[qb_column].cast(pl.Float64).to_numpy()
    play = frame[play_call_column].cast(pl.Float64).to_numpy()
    if len(qb) < 3:
        raise ValueError("at least three paired coach signals are required")
    unique_qb = qb - LinearRegression().fit(play.reshape(-1, 1), qb).predict(play.reshape(-1, 1))
    unique_play = play - LinearRegression().fit(qb.reshape(-1, 1), play).predict(qb.reshape(-1, 1))
    shared = (_zscore(qb) + _zscore(play)) / 2.0
    correlation = float(np.corrcoef(qb, play)[0, 1])
    same_direction = float(np.mean((qb * play) > 0))
    result = frame.with_columns(
        pl.Series("unique_qb_development_signal", unique_qb),
        pl.Series("unique_play_calling_signal", unique_play),
        pl.Series("shared_coaching_signal", shared),
    )
    diagnostics = {
        "pae_pcae_correlation": correlation,
        "shared_variance": correlation**2,
        "same_direction_rate": same_direction,
        "pae_correlation_with_unique_pcae": float(np.corrcoef(qb, unique_play)[0, 1]),
        "pcae_correlation_with_unique_pae": float(np.corrcoef(play, unique_qb)[0, 1]),
    }
    return result, diagnostics


def conceptual_framework() -> dict[str, tuple[str, ...] | str]:
    """Return the deliberately unestimated Coach Effect contract."""

    return {
        "components": CONCEPTUAL_COMPONENTS,
        "weight_names": CONCEPTUAL_WEIGHT_NAMES,
        "expression": (
            "confidence_c * (w_Q * unique_qb_development_signal + "
            "w_P * unique_play_calling_signal + w_S * shared_coaching_signal)"
        ),
        "status": "exploratory_unweighted_noncausal",
    }
