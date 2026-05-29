"""Per-indicator trend drill-down (M-TREND-A1).

Theil–Sen slope + Mann–Kendall significance computed on a **server-side
per-day site series** reduced **outside `six_step`**, invoked **on demand
after a screening** for a **single series indicator**. Trend is **never
aggregated** across indicators and **never enters
`composite.overall_screening`** (M-TREND_Decision_Log E1 / TR10).

Layering mirrors `repeatable_core`:

1. **Pure math** — `theil_sen_slope_per_year`, `mann_kendall_two_sided_p`,
   the severity / confidence / bucket / seasonal-flag helpers, and
   `assemble_trend_result`. No Earth Engine, no I/O; unit-tested on
   synthetic series.
2. **EE-touching** — `_server_side_day_means` (the per-day site-mean
   reducer following the `_server_side_hf` pattern) and the public
   `compute_trend` entry point.

`six_step` stays byte-identical and keeps `trend=None` in the screening
path (TR6). This module is the separate post-screening reducer the in-code
directive in `repeatable_core.py` (the "must provide a server-side reducer
following the same pattern as `_server_side_hf`" note) asked for.

Import-cycle note: `repeatable_core` imports this module at load time
(`from engine.core import trend as _trend`). To avoid a cycle, every
`repeatable_core` symbol this module needs is imported **lazily inside the
EE functions**, so the pure-math core (and `repeatable_core`'s own import
of it) never trips the partially-initialised module.

Anchored to:
- M-TREND_Decision_Log (29 May 2026) — the controlling design record.
- M-TREND-A1_spec.md §4 (output contract), §5 (severity), §6 (confidence),
  §7 (bucket + seasonal flag).
- docs/Indicators_Computation_v4.md §0.3 (Theil–Sen + Mann–Kendall),
  §0.4 (severity normalisation sibling).
"""

from __future__ import annotations

import math
from datetime import date as _date

from engine.constants import (
    BACKGROUND_RING_MAX_KM,
    BACKGROUND_RING_RADIUS_MULTIPLE,
    COLUMN_TO_SURFACE_MULTIPLIER,
    CLIMATOLOGY_FALLBACK_MULTIPLIER,
    SERVER_SIDE_HF_CHUNK_DAYS_DEFAULT,
    SERVER_SIDE_HF_CHUNK_DAYS_PER_INDICATOR,
    TEMPORAL_FALLBACK_MULTIPLIER,
    TREND_CONFIDENCE_SPAN_SATURATION_DAYS,
    TREND_CONFIDENCE_TERM_WEIGHTS,
    TREND_HARD_FLOOR_POINTS,
    TREND_SEASONAL_FLAG_MIN_DAYS,
    TREND_SERIES_INDICATOR_IDS,
    TREND_SEVERITY_K_SIGMA_PER_YEAR,
    TREND_SIGNIFICANT_P,
    TREND_SOFT_FLOOR_POINTS,
    TREND_WEAK_EMERGING_P,
)


def is_series_indicator(indicator_id: str | None) -> bool:
    """True when `indicator_id` has a real per-day series (UT7 eligibility).

    Accepts either a base ID (``"air.no2"``) or any measurement/select key
    that starts with one (``"air.no2.score"``, ``"air.no2.z"``). The "view
    trend" affordance and saved trend records are gated on this — non-series
    indicators (ODIAC CO₂, KBA, Dynamic World, Hansen) get no link and no
    substitute anywhere (decision-log U6).
    """
    if not indicator_id:
        return False
    return any(
        indicator_id == base or indicator_id.startswith(base + ".")
        for base in TREND_SERIES_INDICATOR_IDS
    )


def base_indicator_id(indicator_id: str) -> str:
    """Normalise a select/measurement key to its base ``pillar.slug`` form.

    ``"air.no2.score"`` → ``"air.no2"``; ``"nature.ndvi"`` → ``"nature.ndvi"``.
    Returns the input unchanged when it doesn't match a known series base.
    """
    for base in TREND_SERIES_INDICATOR_IDS:
        if indicator_id == base or indicator_id.startswith(base + "."):
            return base
    return indicator_id

_DAYS_PER_YEAR: float = 365.25
_MS_PER_UTC_DAY: int = 86_400_000


# ---------------------------------------------------------------------------
# Pure statistics (no EE) — IC_v4 §0.3
# ---------------------------------------------------------------------------

def theil_sen_slope_per_year(
    day_ordinals: list[int],
    values: list[float],
) -> float | None:
    """Theil–Sen slope in **raw units per year** (IC_v4 §0.3 / TR7).

    `day_ordinals` are proleptic-Gregorian ordinal days (one integer per
    observation); `values` the aligned per-day site means. The slope is the
    median of all pairwise slopes — robust to the outlier days that a
    cloudy / multi-swath series throws up, which is exactly why Theil–Sen
    is the house choice over OLS.

    Returns the slope rescaled to **per year** (x is divided by 365.25 so
    the slope is independent of window span — TR7). Returns None for fewer
    than two distinct x-values, where no slope is defined.
    """
    if len(day_ordinals) < 2 or len(set(day_ordinals)) < 2:
        return None
    # Lazy import — scipy is heavy and this module is imported at
    # repeatable_core load time; keep module import cheap.
    from scipy.stats import theilslopes

    x_years = [d / _DAYS_PER_YEAR for d in day_ordinals]
    result = theilslopes(values, x_years)
    return float(result[0])


def mann_kendall_two_sided_p(values: list[float]) -> float | None:
    """Two-sided Mann–Kendall p-value (IC_v4 §0.3 / TR9).

    `values` must already be in time order. Implements the standard
    normal-approximation MK test with the tie correction and the ±1
    continuity correction:

        S        = Σ_{i<j} sign(x_j − x_i)
        var(S)   = [n(n−1)(2n+5) − Σ_t t(t−1)(2t+5)] / 18   (t = tie-group sizes)
        z        = (S−1)/√var  if S>0 ; (S+1)/√var if S<0 ; 0 if S=0
        p        = 2·(1 − Φ(|z|))

    Standard MK assumes independent observations (TR14): a known limitation
    documented here rather than corrected — modified (Hamed–Rao / Yue–Pilon)
    MK is logged as a future calibration item, and the engine instead emits
    the per-day series + coverage descriptor so the UI can make
    autocorrelation legible. Returns None when fewer than 3 points or the
    variance is non-positive (all-tied series), where the test is undefined.
    """
    n = len(values)
    if n < 3:
        return None

    s = 0
    for i in range(n - 1):
        xi = values[i]
        for j in range(i + 1, n):
            diff = values[j] - xi
            if diff > 0:
                s += 1
            elif diff < 0:
                s -= 1

    # Tie correction: group equal values.
    tie_counts: dict[float, int] = {}
    for v in values:
        tie_counts[v] = tie_counts.get(v, 0) + 1
    tie_term = sum(t * (t - 1) * (2 * t + 5) for t in tie_counts.values() if t > 1)
    var_s = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if var_s <= 0:
        return None

    if s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0

    # Two-sided p via the standard normal CDF (math.erf — no scipy needed).
    p = 2.0 * (1.0 - _norm_cdf(abs(z)))
    return min(1.0, max(0.0, p))


def significance_bucket(p: float | None) -> str:
    """Map a MK p-value to a display bucket (TR9 / decision-log D2).

    Presentation-layer thresholds, **not a gate** — the raw slope + p are
    emitted regardless. `None` (below the hard floor) → ``"unavailable"``.
    """
    if p is None:
        return "unavailable"
    if p < TREND_SIGNIFICANT_P:
        return "significant"
    if p < TREND_WEAK_EMERGING_P:
        return "weak_emerging"
    return "none"


def seasonal_flag(span_days: int) -> bool:
    """Fire the (separate, categorical) seasonal flag (TR15).

    Orthogonal to confidence (decision-log C-ii): a short window risks
    reading phenology as trend, so the UI defaults the season-banded axis on
    when this fires. It does **not** modify `trend_confidence` or
    `trend_severity`.
    """
    return span_days < TREND_SEASONAL_FLAG_MIN_DAYS


def trend_severity(
    slope_per_year: float | None,
    bg_std: float | None,
    direction: str,
    k_trend: float = TREND_SEVERITY_K_SIGMA_PER_YEAR,
) -> float | None:
    """Slope → 0–1 display severity (TR12 / spec §5).

    Sibling of the IC §0.4 normalisation, in background-sigmas-per-year::

        slope_sigma_per_year = slope / bg_std
        higher_is_worse →  clamp( slope_sigma_per_year / k_trend, 0, 1)
        lower_is_worse  →  clamp(-slope_sigma_per_year / k_trend, 0, 1)

    Direction comes from the indicator's `direction` config (NDVI is
    ``lower_is_worse``, so a declining slope is the worrying one). Display
    only — never averaged, never an aggregate input (TR10/TR11). Returns
    None when the slope is unavailable or `bg_std` is degenerate.
    """
    if slope_per_year is None or bg_std is None or bg_std <= 0 or k_trend <= 0:
        return None
    slope_sigma_per_year = slope_per_year / bg_std
    if direction == "lower_is_worse":
        slope_sigma_per_year = -slope_sigma_per_year
    return _clamp01(slope_sigma_per_year / k_trend)


def coverage_descriptor(day_ordinals: list[int]) -> dict:
    """Coverage descriptor for the series (TR14 / spec §4).

    `n_valid_days` = distinct days; `span_days` = last − first; and
    `largest_gap_days` = the longest run between consecutive observations
    (the gap measure that distinguishes a dense series from a clustered one
    at equal count). Emitted as a first-class engine output so the UI can
    render clustering / sparse coverage to the eye.
    """
    if not day_ordinals:
        return {"n_valid_days": 0, "span_days": 0, "largest_gap_days": 0}
    ordered = sorted(day_ordinals)
    span = ordered[-1] - ordered[0]
    largest_gap = 0
    for prev, cur in zip(ordered, ordered[1:]):
        largest_gap = max(largest_gap, cur - prev)
    return {
        "n_valid_days": len(ordered),
        "span_days": span,
        "largest_gap_days": largest_gap,
    }


# ---------------------------------------------------------------------------
# Trend confidence — sibling of the M-TIER-A1 house formula (TR13 / spec §6)
# ---------------------------------------------------------------------------

def _length_term(n_valid_days: int) -> float:
    """0 at the hard floor, saturating to 1 at the soft floor.

    Length is the dominant base term because too-few-points is the primary
    trend-reliability risk (ties to the B4 floors).
    """
    denom = TREND_SOFT_FLOOR_POINTS - TREND_HARD_FLOOR_POINTS
    if denom <= 0:
        return 1.0
    return _clamp01((n_valid_days - TREND_HARD_FLOOR_POINTS) / denom)


def _span_term(span_days: int) -> float:
    """Penalise short windows (statistical-power sense; distinct from the
    seasonal flag). Saturates at a year of data."""
    if TREND_CONFIDENCE_SPAN_SATURATION_DAYS <= 0:
        return 1.0
    return _clamp01(span_days / TREND_CONFIDENCE_SPAN_SATURATION_DAYS)


def _coverage_term(span_days: int, largest_gap_days: int) -> float:
    """Penalise gappy / clustered distribution at equal count.

    ``1 − largest_gap/span``: an evenly spread series has a small largest
    gap → term near 1; a clustered series (one big gap) → term near 0.
    """
    if span_days <= 0:
        return 0.0
    return _clamp01(1.0 - largest_gap_days / span_days)


def trend_confidence(
    *,
    n_valid_days: int,
    span_days: int,
    largest_gap_days: int,
    column_to_surface_uncertainty: str,
    temporal_fallback_applied: bool = False,
    climatology_fallback_applied: bool = False,
    snapshot_confidence: float | None = None,
) -> float:
    """base(length + span + coverage) × column_to_surface × fallback chain.

    Matches the M-TIER-A1 confidence shape (additive base, then a
    multiplicative penalty chain) so trend confidence slots into the same
    `c_final` family (decision-log C-SHAPE). The multiplier chain reuses the
    indicator's `column_to_surface` term plus any SPPY (×0.60) / climatology
    (×0.75) multiplier that applied to the screening's background stats
    (TR13 / C-iii).

    C-iii invariant: **a trend can never display more confidently than the
    snapshot it is built on.** When `snapshot_confidence` is supplied the
    result is capped at it — the test in `test_trend.py` asserts the
    invariant holds.

    Raises:
        KeyError: `column_to_surface_uncertainty` not in the lookup —
                  strict by design, same as `compute_indicator_confidence`.
    """
    w = TREND_CONFIDENCE_TERM_WEIGHTS
    base = (
        w["length"]   * _length_term(n_valid_days)
        + w["span"]     * _span_term(span_days)
        + w["coverage"] * _coverage_term(span_days, largest_gap_days)
    )
    multiplier = COLUMN_TO_SURFACE_MULTIPLIER[column_to_surface_uncertainty]
    if temporal_fallback_applied:
        multiplier *= TEMPORAL_FALLBACK_MULTIPLIER
    if climatology_fallback_applied:
        multiplier *= CLIMATOLOGY_FALLBACK_MULTIPLIER
    confidence = _clamp01(base * multiplier)
    if snapshot_confidence is not None:
        confidence = min(confidence, snapshot_confidence)
    return confidence


# ---------------------------------------------------------------------------
# Assembly — pure, builds the full §4 output contract from a series
# ---------------------------------------------------------------------------

def assemble_trend_result(
    indicator_id: str,
    series: list[tuple[str, float]],
    *,
    bg_median: float | None,
    bg_std: float | None,
    direction: str,
    window: tuple[str, str],
    column_to_surface_uncertainty: str = "n_a",
    temporal_fallback_applied: bool = False,
    climatology_fallback_applied: bool = False,
    snapshot_confidence: float | None = None,
    bg_stats_source: str = "reused_from_screening",
    k_trend: float = TREND_SEVERITY_K_SIGMA_PER_YEAR,
) -> dict:
    """Build the M-TREND-A1 §4 output contract from a per-day series.

    Pure (no EE): the EE-touching `compute_trend` fetches `series` + the
    background stats, then defers all the maths and the floor logic here so
    the contract is exhaustively unit-testable on synthetic input.

    Floor behaviour (TR4):
    - `n_valid_days < hard_floor` → `trend/trend_p/trend_severity/
      trend_confidence = None`, `significance_bucket = "unavailable"`;
      `series` + `coverage` + `seasonal_flag` are still returned so the UI
      can show "too few observations" with the points it does have.
    - `hard_floor ≤ n_valid_days < soft_floor` → all values emitted;
      `trend_confidence` is driven toward zero by the length term.
    """
    # Sort by date and split into aligned arrays.
    ordered = sorted(series, key=lambda pair: pair[0])
    iso_dates = [iso for iso, _ in ordered]
    values = [float(v) for _, v in ordered]
    day_ordinals = [_date.fromisoformat(iso).toordinal() for iso in iso_dates]

    coverage = coverage_descriptor(day_ordinals)
    n_valid = coverage["n_valid_days"]
    span_days = coverage["span_days"]
    seasonal = seasonal_flag(span_days)
    series_payload = [[iso, v] for iso, v in zip(iso_dates, values)]

    provenance = {
        "algorithm": "theil_sen_slope + mann_kendall_two_sided",
        "window": list(window),
        "bg_median": bg_median,
        "bg_std": bg_std,
        "bg_stats_source": bg_stats_source,
        "k_trend_sigma_per_year": k_trend,
        "hard_floor_points": TREND_HARD_FLOOR_POINTS,
        "soft_floor_points": TREND_SOFT_FLOOR_POINTS,
        "significant_p": TREND_SIGNIFICANT_P,
        "weak_emerging_p": TREND_WEAK_EMERGING_P,
        "seasonal_flag_min_days": TREND_SEASONAL_FLAG_MIN_DAYS,
        "direction": direction,
        "column_to_surface_uncertainty": column_to_surface_uncertainty,
        "temporal_fallback_applied": temporal_fallback_applied,
        "climatology_fallback_applied": climatology_fallback_applied,
        "mk_limitation": (
            "standard Mann–Kendall assumes independent observations; "
            "autocorrelation is not corrected (modified MK deferred). The "
            "per-day series + coverage descriptor are emitted so the UI can "
            "make clustering / sparse coverage legible."
        ),
    }

    # --- Below the hard floor: no slope, but return what we have. ---
    if n_valid < TREND_HARD_FLOOR_POINTS:
        return {
            "indicator_id": indicator_id,
            "trend": None,
            "trend_p": None,
            "trend_severity": None,
            "trend_confidence": None,
            "significance_bucket": "unavailable",
            "seasonal_flag": seasonal,
            "series": series_payload,
            "coverage": coverage,
            "provenance": provenance,
        }

    slope = theil_sen_slope_per_year(day_ordinals, values)
    p_value = mann_kendall_two_sided_p(values)
    severity = trend_severity(slope, bg_std, direction, k_trend)
    confidence = trend_confidence(
        n_valid_days=n_valid,
        span_days=span_days,
        largest_gap_days=coverage["largest_gap_days"],
        column_to_surface_uncertainty=column_to_surface_uncertainty,
        temporal_fallback_applied=temporal_fallback_applied,
        climatology_fallback_applied=climatology_fallback_applied,
        snapshot_confidence=snapshot_confidence,
    )

    return {
        "indicator_id": indicator_id,
        "trend": slope,
        "trend_p": p_value,
        "trend_severity": severity,
        "trend_confidence": confidence,
        "significance_bucket": significance_bucket(p_value),
        "seasonal_flag": seasonal,
        "series": series_payload,
        "coverage": coverage,
        "provenance": provenance,
    }


# ---------------------------------------------------------------------------
# EE-touching — server-side per-day site-mean reducer (TR6 / B-ARCH)
# ---------------------------------------------------------------------------

def _server_side_day_means(
    aoi: dict,
    image_collection,
    band: str,
    scale: float | None,
    *,
    time_range: tuple[str, str],
    indicator_id: str | None = None,
) -> list[tuple[str, float]]:
    """Per-day site **means** over the buffer, reduced server-side.

    Follows the `_server_side_hf` pattern exactly (TR6 / decision-log
    B-DIRECTIVE): per-granule reduce → `day_bucket` tag → server-side
    grouped aggregate to one mean per UTC day → small payload. Reuses the
    same per-indicator chunking (90-day single chunk for low-cadence
    indicators, 10-day chunks for AOD/CH₄) so it inherits the EE
    timeout / 5000-element headroom the HF path was tuned for. The
    deprecated client-side `_per_date_site_series` is **not** revived.

    Cloudy / missing days are simply absent (TR3): no granule on a day → no
    `day_bucket` → that day is not in the result. No interpolation, no SPPY.

    A UTC day falls entirely within one date chunk (chunk boundaries are at
    UTC midnight), so per-chunk grouped means never need cross-chunk
    re-averaging — the same day-distinctness property `_server_side_hf`
    relies on. Returns ``[(iso_date, mean), …]`` sorted by date.

    `image_collection` must already be windowed + bounded (compute_trend
    does this once up front); the single-chunk fast path reduces it as-is,
    so it never touches the unfiltered global archive.
    """
    import ee  # lazy — keeps the pure core importable without EE installed

    from engine.core.buffers import site_buffer
    from engine.core.repeatable_core import (
        _date_chunks_iso,
        _day_bucket_to_iso,
        _window_days,
    )

    geom = site_buffer(aoi["centre"], aoi["radius_km"])
    mean_count_reducer = ee.Reducer.mean().combine(
        reducer2=ee.Reducer.count(), sharedInputs=True,
    )
    mean_key = f"{band}_mean"
    count_key = f"{band}_count"

    def per_image(image: "ee.Image") -> "ee.Feature":
        reduction = image.select(band).reduceRegion(
            reducer=mean_count_reducer,
            geometry=geom,
            scale=scale,
            bestEffort=True,
            maxPixels=int(1e9),
        )
        count = ee.Number(reduction.get(count_key, 0))
        is_valid = count.gt(0)
        site_mean = ee.Number(
            ee.Algorithms.If(is_valid, reduction.get(mean_key, 0.0), 0.0)
        )
        day_bucket = ee.Number(image.get("system:time_start")).divide(
            _MS_PER_UTC_DAY,
        ).floor()
        return ee.Feature(None, {
            "is_valid": is_valid,
            "site_mean": site_mean,
            "day_bucket": day_bucket,
        })

    # Chunk identically to _server_side_hf (per-indicator chunk days).
    chunk_days = SERVER_SIDE_HF_CHUNK_DAYS_PER_INDICATOR.get(
        indicator_id or "", SERVER_SIDE_HF_CHUNK_DAYS_DEFAULT,
    )
    win_days = _window_days(time_range)
    if win_days is None or chunk_days >= win_days:
        chunks: list[tuple[str, str] | None] = [None]
    else:
        chunks = list(_date_chunks_iso(time_range, chunk_days=chunk_days))

    selected = image_collection.select(band)
    day_means: dict[int, float] = {}
    for chunk in chunks:
        chunk_ic = selected if chunk is None else selected.filterDate(chunk[0], chunk[1])
        valid_fc = chunk_ic.map(per_image).filter(ee.Filter.eq("is_valid", 1))
        # Server-side group-by-day mean: one reduceColumns call per chunk.
        grouped = valid_fc.reduceColumns(
            selectors=["site_mean", "day_bucket"],
            reducer=ee.Reducer.mean().group(groupField=1, groupName="day_bucket"),
        ).getInfo() or {}
        for group in grouped.get("groups", []):
            day_bucket = group.get("day_bucket")
            mean = group.get("mean")
            if day_bucket is None or mean is None:
                continue
            day_means[int(day_bucket)] = float(mean)

    return [
        (_day_bucket_to_iso(day_bucket), mean)
        for day_bucket, mean in sorted(day_means.items())
    ]


def compute_trend(
    aoi: dict,
    image_collection,
    band: str,
    time_range: tuple[str, str],
    *,
    indicator_id: str,
    direction: str = "higher_is_worse",
    bg_median: float | None = None,
    bg_std: float | None = None,
    scale: float | None = None,
    seasonal: bool = True,
    column_to_surface_uncertainty: str = "n_a",
    temporal_fallback_applied: bool = False,
    climatology_fallback_applied: bool = False,
    snapshot_confidence: float | None = None,
) -> dict:
    """Public entry point — the §4 trend contract for one series indicator.

    On-demand, post-screening (decision-log B-ARCH): the caller passes the
    screening's AOI / band / scale / window and, when available, its
    `bg_median` / `bg_std` (TR5). When the background stats are not supplied
    (the screening result does not currently surface `bg_std` — Step A
    B-RECON), they are **recomputed** over the same window via
    `background_value`, anchored to the IC §0.5 reproducible window; the
    `bg_stats_source` provenance field records which path was taken.

    `six_step` is untouched and keeps `trend=None` in screening (TR6); this
    is the separate server-side reducer invoked only here.
    """
    # Window + bound the collection ONCE here, mirroring six_step's
    # construction, so neither the per-day reducer nor the background
    # recompute reduces over the unfiltered global archive (which times out).
    from engine.core.buffers import background_ring, site_buffer

    r_background_km = min(
        BACKGROUND_RING_RADIUS_MULTIPLE * aoi["radius_km"],
        BACKGROUND_RING_MAX_KM,
    )
    envelope = site_buffer(aoi["centre"], r_background_km)
    ic_window = (
        image_collection
        .filterDate(time_range[0], time_range[1])
        .filterBounds(envelope.bounds())
    )

    bg_stats_source = "reused_from_screening"
    if bg_median is None or bg_std is None:
        ring = background_ring(aoi["centre"], aoi["radius_km"])
        bg_median, bg_std = _recompute_background(
            aoi, ic_window, band, ring, seasonal=seasonal, scale=scale,
        )
        bg_stats_source = "recomputed"

    series = _server_side_day_means(
        aoi, ic_window, band, scale,
        time_range=time_range, indicator_id=indicator_id,
    )

    return assemble_trend_result(
        indicator_id,
        series,
        bg_median=bg_median,
        bg_std=bg_std,
        direction=direction,
        window=time_range,
        column_to_surface_uncertainty=column_to_surface_uncertainty,
        temporal_fallback_applied=temporal_fallback_applied,
        climatology_fallback_applied=climatology_fallback_applied,
        snapshot_confidence=snapshot_confidence,
        bg_stats_source=bg_stats_source,
    )


def _recompute_background(
    aoi: dict,
    ic_window,
    band: str,
    ring: dict,
    *,
    seasonal: bool,
    scale: float | None,
) -> tuple[float | None, float | None]:
    """Recompute `(bg_median, bg_std)` over the screening window (B-RECON).

    `ic_window` is the already windowed + bounded collection and `ring` the
    shared background ring (both built once in `compute_trend`, matching
    `six_step`'s construction). Returns ``(None, None)`` if the ring has no
    valid pixels — the caller still gets a series, but severity /
    normalisation degrade to None.
    """
    from engine.core.repeatable_core import background_value
    from engine.exceptions import BackgroundRingNoDataError

    try:
        return background_value(
            aoi, ic_window, band, seasonal=seasonal, scale=scale, ring=ring,
        )
    except BackgroundRingNoDataError:
        return None, None


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    """Standard normal CDF via the error function (stdlib only)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value
