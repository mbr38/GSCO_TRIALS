"""Raw-to-score normalisation per docs/Indicators_Computation_v4.md §0.4.

The §0.4 clamp:

    X_score = clamp( (X_site − X_bg) / (k · σ_bg) , 0 , 1 )      higher = worse
    X_score = clamp( (X_bg − X_site) / (k · σ_bg) , 0 , 1 )      lower = worse

`k` defaults to NORMALISATION_K (= 3) — a 3σ exceedance saturates the score.
"""

from __future__ import annotations

from typing import Literal

from engine.constants import NORMALISATION_K

Direction = Literal["higher_is_worse", "lower_is_worse"]


def to_score(
    value: float,
    bg_median: float,
    bg_std: float,
    direction: Direction = "higher_is_worse",
    k: float = NORMALISATION_K,
) -> float | None:
    """Map a raw indicator value to a 0–1 score (IC_v4 §0.4).

    Returns None when `bg_std <= 0` — the background is uniform, so a
    normalised deviation is undefined. Callers can fall back to a default
    or surface the indicator as missing.
    """
    if bg_std <= 0:
        return None
    raw = (value - bg_median) if direction == "higher_is_worse" else (bg_median - value)
    score = raw / (k * bg_std)
    return max(0.0, min(1.0, score))
