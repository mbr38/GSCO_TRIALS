"""Per-indicator confidence formula and pillar-level rollup (Tier A1).

Replaces the legacy `_placeholder_confidence` in repeatable_core (which
produced `(n_valid / n_total) · mean_qa` with mean_qa hardcoded to 1.0)
with the audit §1.1 / IC_v4 §6.3 canonical form:

    c_raw = 0.30·QA + 0.30·N_valid + 0.25·anomaly_strength + 0.15·spatial_context
    c_final = c_raw · COLUMN_TO_SURFACE_MULTIPLIER[uncertainty_tag]

Strict-None at the indicator level: any missing term → None. Pillars
apply survivor-renormalise via the existing `_renormalise_weights`
helpers when assembling their pillar-level confidence rollups.

The four canonical terms are computed via per-indicator helpers below.
Pillar modules call them with whatever ingredients are already at hand
(HF from six_step, n_observations from the EE pipeline, buffer area
from the AOI radius) and pass the resulting term values into
`compute_indicator_confidence` together with the indicator_id.

Anchored to:
- audit §1.1 (why confidence had to become real)
- audit §1.5 + Schema_v2 §6.1 (column_to_surface_uncertainty lookup —
  the same table that drives provenance)
- M-TIER-A1 spec §3
"""

from __future__ import annotations

import math

from engine.constants import (
    COLUMN_TO_SURFACE_MULTIPLIER,
    CONFIDENCE_FORMULA_WEIGHTS,
    EXPECTED_N_PER_WINDOW_DAY,
    NATIVE_PIXEL_AREA_M2,
    QA_PER_INDICATOR,
    SINGLE_SNAPSHOT_INDICATORS,
    SPATIAL_CONTEXT_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Per-term helpers
# ---------------------------------------------------------------------------

def compute_qa_term(indicator_id: str) -> float | None:
    """Per-indicator static QA default from `QA_PER_INDICATOR`.

    v1.x A1 ships per-indicator static QA values reflecting
    retrieval-quality consensus for each asset family. Plumbing real
    per-image qa_value pass-rates into the EE pipeline is logged as a
    Layer B follow-up (sensitivity-analysis target in Tier B1).

    Returns None when the indicator_id isn't in the table — caller
    surfaces this as strict-None at the indicator level.
    """
    return QA_PER_INDICATOR.get(indicator_id)


def compute_n_valid_term(
    indicator_id: str,
    *,
    n_observations: int | None,
    window_days: int | None,
) -> float | None:
    """Temporal-coverage term: clamp(n_obs / expected_n, 0, 1).

    Single-snapshot indicators (DW composites, Hansen / ODIAC annual
    rasters, KBA vector data) bypass the ratio and pass through 1.0
    when the snapshot was produced (n_observations >= 1) or 0.0 when
    skipped. Here 0.0 is the right semantic — the snapshot was
    *attempted and failed*, which is a real piece of information.

    Live-revisit indicators (TROPOMI, CAMS, MAIAC, VIIRS, MODIS NDVI)
    use `EXPECTED_N_PER_WINDOW_DAY[indicator_id] · window_days` as the
    denominator. Returns None when either input is missing or
    `window_days <= 0`.

    Step 8 design lock (22 May 2026): for live-revisit indicators,
    n_observations=0 returns None (no information about coverage), not
    0.0 (perfect-bad coverage). Zero observations means we have no
    data on the indicator's actual revisit behaviour over this AOI/
    window — structurally different from "we sampled and got 0 valid
    pixels per attempt." The None then strict-Nones the whole
    indicator's confidence (compute_indicator_confidence) and the
    pillar rollup drops it via survivor-renormalise. See also the
    matching strict-None pattern in compute_anomaly_strength_term.

    The SINGLE_SNAPSHOT_INDICATORS branch keeps 0.0 on n=0 because
    "snapshot was attempted and produced nothing" IS information — it
    means the composite/raster build failed end-to-end, which is a
    real signal to surface in the confidence rather than hide.
    """
    if indicator_id in SINGLE_SNAPSHOT_INDICATORS:
        if n_observations is None:
            return None
        return 1.0 if n_observations >= 1 else 0.0

    if n_observations is None or window_days is None or window_days <= 0:
        return None
    # Step 8 design lock: n_observations == 0 → None (no information),
    # NOT 0.0 (perfect-bad coverage). See class docstring above.
    if n_observations == 0:
        return None
    per_day = EXPECTED_N_PER_WINDOW_DAY.get(indicator_id)
    if per_day is None or per_day <= 0:
        return None
    expected = per_day * window_days
    if expected <= 0:
        return None
    return _clamp01(n_observations / expected)


def compute_anomaly_strength_term(
    indicator_id: str,
    *,
    hf: float | None,
) -> float:
    """HF-based per spec Q3=B. Already in [0, 1] by definition.

    For indicators that don't produce an HF value (KBA vector,
    DW composition, Hansen forest_loss, ODIAC inventory, etc.),
    returns 1.0 — "no anomaly concept applies → not a confidence
    drag". This is unconditional (never None) because absence of an
    HF concept is a structural property, not a missing input.

    Step 8 design lock (22 May 2026): when n_valid=0 (zero observations
    in the window), HF is necessarily None, and this function returns
    None. The downstream compute_indicator_confidence then strict-Nones
    the whole indicator's confidence. Survivor-renormalise at the pillar
    level drops the indicator from the rollup. This is "no data, no
    claim" — the indicator emits None rather than a low-confidence
    zero-floor value. Revisit in Tier B1 if user feedback indicates
    silent dropouts confuse the UI rendering.
    """
    if hf is not None:
        return _clamp01(hf)
    # Indicators with no HF concept (single-snapshot / vector / reference data):
    if indicator_id in SINGLE_SNAPSHOT_INDICATORS:
        return 1.0
    # Live-revisit indicator that returned HF=None means the formula could
    # not be computed (bg_std = 0, empty series, etc.) — surface as None
    # so the indicator's confidence becomes None at the strict-None step.
    return None  # type: ignore[return-value]


def compute_spatial_context_term(
    indicator_id: str,
    *,
    buffer_area_m2: float | None,
) -> float | None:
    """Pixel-buffer ratio: clamp(sqrt(buffer / pixel) / SPATIAL_CONTEXT_THRESHOLD, 0, 1).

    Saturates at 1.0 when the buffer covers ≥SPATIAL_CONTEXT_THRESHOLD
    native pixels in each linear dimension. Returns 1.0 for vector /
    non-raster indicators (native_pixel_area_m2 == 0).

    Returns None only when buffer_area_m2 is missing or the indicator
    isn't in NATIVE_PIXEL_AREA_M2.
    """
    if buffer_area_m2 is None or buffer_area_m2 <= 0:
        return None
    pixel_area = NATIVE_PIXEL_AREA_M2.get(indicator_id)
    if pixel_area is None:
        return None
    if pixel_area <= 0:
        # Vector / non-raster — concept doesn't apply, no penalty.
        return 1.0
    linear_pixels = math.sqrt(buffer_area_m2 / pixel_area)
    return _clamp01(linear_pixels / SPATIAL_CONTEXT_THRESHOLD)


# ---------------------------------------------------------------------------
# Main constructor + pillar rollup
# ---------------------------------------------------------------------------

def compute_indicator_confidence(
    *,
    indicator_id: str,
    qa: float | None,
    n_valid: float | None,
    anomaly_strength: float | None,
    spatial_context: float | None,
    column_to_surface_uncertainty: str,
) -> float | None:
    """Universal 4-term additive formula × column-to-surface multiplier.

    Strict-None at the indicator level — any None term collapses the
    indicator's confidence to None. The pillar rollup
    (`compute_pillar_confidence`) then survives the dropout via
    weight renormalisation.

    Raises:
        KeyError: `column_to_surface_uncertainty` not in
                  COLUMN_TO_SURFACE_MULTIPLIER. Strict by design —
                  audit §1.5 fixes the enum, so a typo here means
                  the caller passed an out-of-band value.
    """
    if any(v is None for v in (qa, n_valid, anomaly_strength, spatial_context)):
        return None
    if column_to_surface_uncertainty not in COLUMN_TO_SURFACE_MULTIPLIER:
        raise KeyError(
            f"unknown column_to_surface_uncertainty "
            f"{column_to_surface_uncertainty!r} for {indicator_id!r}; "
            f"expected one of {sorted(COLUMN_TO_SURFACE_MULTIPLIER)}"
        )
    w = CONFIDENCE_FORMULA_WEIGHTS
    c_raw = (
        w["qa"]               * qa
        + w["n_valid"]          * n_valid
        + w["anomaly_strength"] * anomaly_strength
        + w["spatial_context"]  * spatial_context
    )
    multiplier = COLUMN_TO_SURFACE_MULTIPLIER[column_to_surface_uncertainty]
    return _clamp01(c_raw * multiplier)


def compute_pillar_confidence(
    per_indicator_confidences: dict[str, float | None],
    *,
    weights: dict[str, float] | None = None,
) -> float | None:
    """Survivor-renormalise rollup.

    `per_indicator_confidences` maps indicator_id → c_i (or None when
    the indicator failed strict-None). If `weights` is None, the rollup
    is a uniform mean over the survivors (Air-style). Otherwise it's a
    weight-renormalised sum (GHG / Nature style — see audit-doc dicts
    in engine/constants.py).

    Returns None only when every input is None.
    """
    survivors = {k: v for k, v in per_indicator_confidences.items() if v is not None}
    if not survivors:
        return None
    if weights is None:
        return sum(survivors.values()) / len(survivors)
    relevant = {k: weights[k] for k in survivors if k in weights}
    if not relevant:
        return None
    total = sum(relevant.values())
    if total <= 0:
        return None
    return sum(survivors[k] * relevant[k] / total for k in relevant)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value
