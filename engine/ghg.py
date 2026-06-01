"""GHG pillar — single-value indicators, sub-aggregates, and pillar
aggregates (Milestones 5a + 5c + 5.5 + 5.5b + 5.5c).

M5.5c — coverage_window + data_type honesty. `GhgIndicatorConfig` carries
two new optional fields: `coverage_window` (None for always-available
indicators, ("2020-01-01", "2023-12-31") for ODIAC) and `data_type`
("satellite_observation" for CH₄ / VIIRS, "emissions_inventory_allocation"
for ODIAC). run_pillar checks coverage_window before dispatching each
indicator's snapshot; out-of-coverage indicators are skipped silently
with None-filled measurement keys and a provenance block carrying
`skipped_reason="out_of_coverage"`. No `_failures` entry — skipping is
expected, not a failure. This stops a present-day screening run from
queueing four futile EE calls trying to read ODIAC for a date range
where it has no data. compute_co2_snapshot's provenance now spells out
that ODIAC is a modelled allocation, not a measured atmosphere.

M5.5b — ODIAC demoted from the live composite. ODIAC's 2+ year vintage
lag means it cannot drive present-day screening (e.g. a May 2026 run
against a 90-day window in 2026 has zero ODIAC coverage and was
previously failing the whole CO₂ branch). CO₂ snapshot still computes
when in ODIAC's coverage window (2020-2023); the values still display
(ghg.co2.mean / total / relative_intensity / score) and the three
CO₂-dependent sub-aggregates still compute (ghg.co2_context,
ghg.fossil_combustion_score, ghg.activity_adjusted_co2). These are
diagnostic / display only and no longer feed compute_core_ghg_audit_support.

The live CO₂ proxy is now CH₄ + Combustion_Proxy + Activity_Score
(rescaled in CORE_GHG_AUDIT_SUPPORT_WEIGHTS by 1/0.61 to preserve
relative proportions). Offline validation that this trio correlates
with ODIAC values is tracked as a v1 deliverable in v1x_followups.md.

M5.5 — CO₂ activated via the ODIAC personal asset
(projects/supply-chain-observatory/assets/odiac). Three single-value
indicators (CH₄, CO₂, VIIRS), the three CO₂-dependent sub-aggregates
(ghg.co2_context, ghg.fossil_combustion_score, ghg.activity_adjusted_co2),
and full pillar-aggregate computation are all live. GHG quality sub-scores
are still placeholders pending the IC_v5 §6.3 confidence-formula doc fix
(same TODO chain as Air's confidence).

Layers (mirrors engine/air.py architecture):
1. Single-value indicators (IC_v4 §2.1 / Schema_v2 §3.1) — ch4, co2, viirs.
   CO₂ uses a custom 7-key measurement set with `.relative_intensity` in
   place of `.anomaly` (M5.5 rename per v1x_followups.md: ODIAC is an
   emissions allocation, not an atmospheric measurement, so the
   six-step "anomaly" framing was misleading).
2. GHG quality sub-scores (Schema_v2 §3.4) — temporal_coverage,
   spatial_resolution_suitability, retrieval_inventory_quality,
   nearby_source_isolation. All placeholders pending IC_v5 §6.3.
3. Sub-aggregates (IC_v4 §2.2 / Schema_v2 §3.2) — eight, all activatable
   in v1: ch4_hotspot_signal, combustion_proxy, activity_score,
   fire_or_regional_transport_risk, ch4_context_adjusted, co2_context,
   fossil_combustion_score, activity_adjusted_co2.
4. Pillar aggregates (IC_v4 §2.3 / Schema_v2 §3.3) — five aggregate scores.
5. `run_pillar` — orchestrator entry point.

Cross-pillar dependency (resolved M5c):
- `compute_combustion_proxy` and `compute_fire_or_regional_transport_risk`
  read values from the Air pillar's payload (`air.industrial_combustion_proxy`
  and `air.smoke_dust_regional_transport`). The orchestrator's `_PILLARS`
  iterates air → ghg → nature; ScreeningRun threads its accumulated payload
  (post-Air) into GHG's `run_pillar` via the `accumulated_payload` kwarg.
  `run_pillar` merges those keys into its local payload before sub-aggregate
  computation so the borrow chain resolves, then strips them before return
  so only GHG-pillar keys are emitted.

TODOs still deferred:
- TODO(v1.x): CARMA-overlap flag — when ODIAC's Site_Buffer overlaps a
  CARMA point source the score should carry a `carma_overlap=True`
  provenance flag and the limiting-factor template should surface it.
- TODO(IC_v5): replace placeholder GHG quality sub-scores with real
  formulas once §6.3 lands.
- TODO(IC_v5): no wind, no sector match in v1 — Wind_Consistency,
  Sector_Match, High_GWP_Sector_Risk are reserved namespace per Schema_v2 §8.
"""

from __future__ import annotations

import concurrent.futures

# M-PERF-PARALLEL #3b: per-pillar EE concurrency budget. 3 GHG indicators
# (CH₄, CO₂, VIIRS) → max-workers=3 saturates them; the constant exists
# for parity with Air's _AIR_MAX_PARALLEL_WORKERS and easy tuning.
_GHG_MAX_PARALLEL_WORKERS: int = 3

from dataclasses import dataclass

import ee

from engine.constants import (
    ANOMALY_Z_THRESHOLD,
    CH4_NATIVE_SCALE_M,
    CO2_TO_C_RATIO,
    CORE_GHG_AUDIT_SUPPORT_WEIGHTS,
    GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS,
    GHG_FOLLOWUP_WEIGHTS,
    VIIRS_FLARING_ABS_THRESHOLD_NW,
    VIIRS_FLARING_SATURATION_FRAC,
    VIIRS_MIN_SITE_PIXELS,
)
from engine.core import (
    build_provenance,
    compute_anomaly_strength_term,
    compute_indicator_confidence,
    compute_n_valid_term,
    compute_qa_term,
    compute_spatial_context_term,
    per_image_site_ring_series,
    six_step,
)
from engine.core.attributability import compute_viirs_attributability
from engine.core.buffers import background_ring, site_buffer
from engine.core.fallback import FallbackContext
from engine.exceptions import (
    BackgroundRingNoDataError,
    IndicatorComputeError,
    PillarComputeError,
    SiteBufferNoDataError,
)
from engine.ids import PILLAR_GHG, make_id


# Math import for the log-based CO₂ score (kept local — no other GHG
# function needs it).
import math


# ---------------------------------------------------------------------------
# Per-indicator configuration  (IC_v4 §2.1 / Schema_v2 §3.1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GhgIndicatorConfig:
    """Static config for one GHG single-value indicator.

    `emitted_measurements` constrains which of the standard nine `six_step`
    output keys get returned. CH₄ uses the full set; VIIRS uses a reduced
    set per Schema_v2 §3.1. `six_step` always computes the full nine
    internally — this is purely a result-payload filter, not a computation
    cut.
    """

    asset_id: str
    band: str
    scale_factor: float
    scale_m: float
    display_unit: str
    direction: str = "higher_is_worse"
    score_cap: float | None = None
    emitted_measurements: tuple[str, ...] = (
        "site", "background", "anomaly", "z", "hf",
        "trend", "trend_p", "confidence", "score",
    )
    # M5.5c — optional (start_iso, end_iso) for indicators with finite
    # coverage. None means "always available" (Sentinel-5P CH₄ and VIIRS
    # NTL — both still actively updated). When set, run_pillar skips the
    # indicator silently if the user's time_range doesn't overlap the
    # coverage window. The skipped-indicator case populates None-filled
    # measurement keys and a provenance block with
    # `skipped_reason="out_of_coverage"`, but does NOT register an entry
    # in `_failures` — out-of-coverage is an expected case, not a failure.
    coverage_window: tuple[str, str] | None = None
    # M5.5c / M5.6 — honesty about what kind of data this indicator emits.
    # UI and offline validators surface this so users and auditors aren't
    # misled about whether a value was measured from space or modelled
    # from statistics. The full set of allowed values lives in
    # engine/core/provenance.py::_ALLOWED_DATA_TYPES (M5.6); v1 GHG uses
    # "satellite_observation" (CH₄, VIIRS) and
    # "emissions_inventory_allocation" (ODIAC).
    data_type: str = "satellite_observation"
    # M5.6 — human-readable data-source label that lands in provenance.
    # Default matches S5P TROPOMI; explicit overrides per-indicator.
    data_source: str = "Copernicus / ESA (Sentinel-5P TROPOMI)"
    # M-V1x-RECONCILE — temporal framing per audit §9.3. Default
    # `live_window` reflects the user's analysis window. Override to
    # `standing_exposure` for cumulative / fixed-vintage indicators (ODIAC
    # CO₂). The provenance lookup table in `engine.core.provenance` also
    # encodes this default — overriding here keeps the per-indicator
    # config self-describing.
    temporal_mode: str = "live_window"
    # M-AIR-GHG-DEFENSIVE — asset-family code emitted in provenance when
    # the site buffer reduces to no usable pixels. Defaults to S5P; VIIRS
    # overrides to no_viirs_pixels. CO₂/ODIAC has its own coverage_window
    # check and won't reach the SiteBufferNoDataError path in v1, but
    # carries no_odiac_pixels for future safety if ODIAC is ever dispatched
    # outside its coverage window.
    skipped_reason_no_data: str = "no_s5p_pixels"


# IC_v4 §2.1 + Indicator_ID_Schema_v2.md §3.1 + GEE_Database_List §3.
GHG_INDICATOR_CONFIG: dict[str, GhgIndicatorConfig] = {
    "ch4": GhgIndicatorConfig(
        asset_id="COPERNICUS/S5P/OFFL/L3_CH4",
        band="CH4_column_volume_mixing_ratio_dry_air",
        scale_factor=1.0,
        scale_m=1113.2,
        display_unit="ppb",
        # data_type / data_source default to S5P satellite_observation —
        # correct for CH₄; explicit here for clarity.
        data_source="Copernicus / ESA (Sentinel-5P TROPOMI)",
    ),
    "viirs": GhgIndicatorConfig(
        asset_id="NASA/VIIRS/002/VNP46A2",
        band="Gap_Filled_DNB_BRDF_Corrected_NTL",
        scale_factor=1.0,
        scale_m=463.83,
        display_unit="nW/cm²/sr",
        # M-VIIRS-REDESIGN-A1 — two outputs from one indicator. SEVERITY:
        # `.score` = flaring (fraction of site pixels above the absolute intense-
        # source anchor), still feeds the composite via ghg.activity_score and is
        # banded by the score-band grammar; `.flaring_frac` is the raw fraction;
        # `.site` is the headline brightness. ATTRIBUTABILITY (Pattern A, NOT in
        # composite): `.attributability_state` + `.lit_contrast_percentile` /
        # `.ring_lit_pixel_count` / `.site_brightness`. Retires the old
        # `.contrast` / `.persistence` (sustained-contrast grammar; M-VIIRS-DIAG-A1
        # showed it could not rank intensity).
        emitted_measurements=(
            "site", "score", "flaring_frac", "confidence",
            "lit_contrast_percentile", "ring_lit_pixel_count",
            "site_brightness", "attributability_state",
        ),
        data_source="NASA / NOAA (VIIRS VNP46A2)",
        skipped_reason_no_data="no_viirs_pixels",  # M-AIR-GHG-DEFENSIVE
    ),
    # M5.5 — ODIAC monthly grids, ingested as ImageCollection on the GSCO
    # GCP project. Band `b1` is the default ODIAC raster band name (not
    # renamed at ingestion). Each pixel value is t C (tonnes of carbon, not
    # CO₂) per cell per month. The C → CO₂ molecular conversion
    # (CO2_TO_C_RATIO = 44/12) and the monthly → annual scaling (×12) are
    # applied inside compute_co2_snapshot after the reduceRegion sum, not
    # via scale_factor on the collection — keeps raw arithmetic simple and
    # the conversion explicit / audit-traceable.
    "co2": GhgIndicatorConfig(
        asset_id="projects/supply-chain-observatory/assets/odiac",
        band="b1",
        scale_factor=1.0,
        scale_m=1000.0,                # ODIAC native pixel ≈ 1 km.
        display_unit="t CO₂/yr",
        # Schema_v2 §3.1 — CO₂ emits a custom 7-key measurement set
        # distinct from both CH₄ (9-key full) and VIIRS (5-key reduced).
        # `relative_intensity` replaces the original `anomaly` per M5.5
        # follow-ups: ODIAC is an emissions allocation, not an atmospheric
        # column observation, so "anomaly" was the wrong framing.
        emitted_measurements=(
            "mean", "total", "relative_intensity",
            "trend", "trend_p", "confidence", "score",
        ),
        # M5.5c — ODIAC publishes annual grids 2020-2023 (latest vintage
        # is ODIAC2024 covering through Dec 2023). run_pillar consults this
        # window before dispatching to compute_co2_snapshot; out-of-coverage
        # time ranges are skipped silently rather than burning EE calls
        # that we already know will return zero monthly grids.
        coverage_window=("2020-01-01", "2023-12-31"),
        data_type="emissions_inventory_allocation",
        data_source="ODIAC / NIES Japan",
        # M-V1x-RECONCILE per audit §9.3 — ODIAC is a 1-2 year-lagged
        # cumulative emissions allocation; treat as standing exposure
        # rather than live-window.
        temporal_mode="standing_exposure",
        # M-AIR-GHG-DEFENSIVE — in v1 the coverage_window check in
        # run_pillar means CO₂ never reaches the SiteBufferNoDataError
        # path; this code is a safety net for any future caller that
        # dispatches CO₂ outside its coverage window without going
        # through run_pillar.
        skipped_reason_no_data="no_odiac_pixels",
    ),
}


# Sub-aggregate weight dicts for the two CO₂-dependent composites. Both
# activate in M5.5 once ghg.co2.score is in the payload.
# IC_v4 §2.2
_FOSSIL_COMBUSTION_WEIGHTS: dict[str, float] = {
    "ghg.co2_context":      0.50,
    "ghg.combustion_proxy": 0.30,
    "ghg.activity_score":   0.20,
}
# IC_v4 §2.2
_ACTIVITY_ADJUSTED_CO2_WEIGHTS: dict[str, float] = {
    "ghg.co2_context":    0.70,
    "ghg.activity_score": 0.30,
}


# `_FOLLOWUP_TERM_TO_ID` maps the short keys in GHG_FOLLOWUP_WEIGHTS to
# the canonical pillar-aggregate IDs they reference.
_FOLLOWUP_TERM_TO_ID: dict[str, str] = {
    "core_support": "ghg.core_audit_support",
    # M-TREND-A1 (TR10): the "trend" term is removed — trend is drill-down-
    # only and never enters the follow-up priority. `ghg.trend` is no longer
    # emitted (see compute_ghg_trend removal below).
    # M-GHG-REDESIGN-A1 (GATE B): the "anomaly" term
    # (`ghg.spatiotemporal_anomaly`) is RETIRED — VIIRS is no longer an anomaly
    # detector and CH₄/CO₂ carry no `.z`, so the GHG pillar has no
    # spatiotemporal-anomaly source. See compute_ghg_spatiotemporal_anomaly
    # removal below and CORE_GHG_AUDIT_SUPPORT_WEIGHTS.
    "quality":      "ghg.data_quality_attribution",
}


_SINGLE_VALUE_INDICATORS: tuple[str, ...] = tuple(GHG_INDICATOR_CONFIG.keys())


# ---------------------------------------------------------------------------
# Public functions — single-value indicators
# ---------------------------------------------------------------------------

def compute_ghg_indicator_snapshot(
    aoi: dict,
    indicator: str,
    time_range: tuple[str, str],
    mode: str,
    ee_client,
    fallback: FallbackContext | None = None,
) -> dict:
    """Run the IC_v4 §0.2 six-step pipeline for one GHG single-value indicator.

    Mirrors `engine.air.compute_pollutant_snapshot` but namespaced to GHG.
    Looks up `indicator` in GHG_INDICATOR_CONFIG, builds the scaled
    ImageCollection, delegates to engine.core.six_step, applies any score
    cap, filters keys to the indicator's `emitted_measurements`, and
    returns a dict keyed by canonical IDs plus a `_provenance.ghg.<indicator>`
    block.

    `mode` is accepted for signature stability; the orchestrator owns
    mode-dependent time-range selection.

    Raises:
        KeyError: indicator not in `GHG_INDICATOR_CONFIG`.
        IndicatorComputeError: pixel-size guard fires, or six_step fails.
    """
    if indicator not in GHG_INDICATOR_CONFIG:
        raise KeyError(f"unknown ghg indicator: {indicator!r}")
    cfg = GHG_INDICATOR_CONFIG[indicator]

    radius_km = aoi["radius_km"]
    if cfg.scale_m > radius_km * 1000:
        raise IndicatorComputeError(
            indicator_id=make_id(PILLAR_GHG, indicator),
            reason=(
                f"site buffer ({radius_km} km) smaller than {indicator} "
                f"native pixel ({cfg.scale_m / 1000:.1f} km) — "
                f"increase radius or pick a finer-resolution indicator"
            ),
        )

    ic = _build_image_collection(cfg)

    raw = six_step(
        aoi=aoi,
        image_collection=ic,
        band=cfg.band,
        time_range=time_range,
        ee_client=ee_client,
        direction=cfg.direction,
        indicator_id=make_id(PILLAR_GHG, indicator),
        scale=cfg.scale_m,
        fallback=fallback,
    )

    return _format_result(indicator, cfg, raw, time_range)


def compute_ch4_snapshot(
    aoi: dict, time_range: tuple[str, str], mode: str, ee_client,
) -> dict:
    """CH₄ single-value snapshot — wrapper for explicit call sites."""
    return compute_ghg_indicator_snapshot(aoi, "ch4", time_range, mode, ee_client)


# ---------------------------------------------------------------------------
# VIIRS — persistence-weighted ring-relative sustained contrast
# (M-GHG-REDESIGN-A1)
# ---------------------------------------------------------------------------
#
# Reframe (spec §2.1): VIIRS night-lights are NOT an anomaly detector. The
# GHG-emissions signal is *sustained brightness of the site relative to its
# background ring* over the screening window. The old per-day z-score grammar
# (anomaly / σ_bg, via six_step) is dropped entirely for VIIRS. Consistency is
# not penalised as "anomaly" — consistency (persistence) is what makes the
# brightness a credible, attributable emissions signal.
#
# This grammar is INTENTIONALLY different from the Air pillar's denominator
# approach (spec §2.1 / §6): VIIRS asks "is this site a sustained activity
# stock?", the Air indicators ask "is there a transient anomalous event?".
# Cross-pillar normalisation consistency is explicitly NOT a requirement.
#
# Attributability invariant (spec §0.4): every quantity is the site measured
# against its OWN background ring, never against absolute regional brightness.
# A bright supplier inside an equally-bright industrial cluster scores low
# because its ring-relative contrast is ~0 — exactly the desired behaviour.


def flaring_score_from_fraction(
    frac_above_threshold: float | None,
    n_site_pixels: int,
) -> float | None:
    """Pure-math core of the M-VIIRS-REDESIGN-A1 flaring (severity) signal.

    `frac_above_threshold` is the fraction of site-buffer pixels whose window-mean
    radiance exceeds VIIRS_FLARING_ABS_THRESHOLD_NW (the "intense source" anchor).
    Score = `min(frac / VIIRS_FLARING_SATURATION_FRAC, 1)`, clamped to [0, 1].

    Absolute-anchored (NOT self-relative): a self-relative outlier could not
    separate intense sources from rural lights (Step A→B evidence — see
    docs/M-VIIRS-REDESIGN-A1_step_a_findings.md); an absolute brightness anchor
    does. Directional, not a precise intensity ranker — complements the Air
    NO₂/CO borrow which ranks intensity (ρ 0.85) but misses flares.

    Returns None (sparse — "no data, no claim") when the site has fewer than
    VIIRS_MIN_SITE_PIXELS valid pixels.
    """
    if frac_above_threshold is None or n_site_pixels < VIIRS_MIN_SITE_PIXELS:
        return None
    if VIIRS_FLARING_SATURATION_FRAC <= 0:
        return 1.0 if frac_above_threshold > 0 else 0.0
    return max(0.0, min(frac_above_threshold / VIIRS_FLARING_SATURATION_FRAC, 1.0))


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Linear-interpolation percentile over an ascending-sorted list.

    Matches numpy's default ('linear') method so the choice of statistic is
    reproducible and documented. `pct` in [0, 100].
    """
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return sorted_vals[lo]
    frac = rank - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def lit_contrast_percentile_from_counts(
    n_ring_below: float | None,
    n_ring_total: float | None,
) -> float | None:
    """Pure-math core of the lit-contrast (attributability) signal (VR2).

    Percentile of the site's brightness within the ring's all-pixel distribution
    = fraction of ring pixels dimmer than the site median. Returns None when the
    ring is empty (no comparison possible); the categorical `sparse` decision
    (ring below MIN_RING_LIT_PIXELS) is made by `compute_viirs_attributability`.
    """
    if n_ring_below is None or not n_ring_total:
        return None
    return max(0.0, min(n_ring_below / n_ring_total, 1.0))


def compute_viirs_two_output(
    aoi: dict, time_range: tuple[str, str], mode: str, ee_client,  # noqa: ARG001
) -> dict:
    """VIIRS two-output snapshot (M-VIIRS-REDESIGN-A1) — replaces the retired
    sustained-contrast grammar (which could not rank intensity; M-VIIRS-DIAG-A1).

    Two distinct outputs from one indicator (VR1):
      * **flaring** (severity → `ghg.viirs.score`, feeds composite via
        `ghg.activity_score`): fraction of site-buffer pixels whose window-mean
        radiance exceeds VIIRS_FLARING_ABS_THRESHOLD_NW, normalised. An absolute-
        anchored intense-source detector (VR3 refined to absolute anchor — a
        self-relative outlier could not separate intense sources from rural
        lights; Step A→B evidence). Complements the Air NO₂/CO borrow.
      * **lit-contrast** (attributability → `ghg.viirs.attributability_state`,
        Pattern A, NOT in composite): percentile of site median brightness within
        the ring's all-pixel (land-masked) distribution → categorical state.

    All reductions are server-side and batched into one ``getInfo`` round-trip.

    Raises:
        IndicatorComputeError: pixel-size guard fires (buffer < VIIRS pixel).
        SiteBufferNoDataError: no VNP46A2 imagery / no site pixels in the window.
    """
    cfg = GHG_INDICATOR_CONFIG["viirs"]
    radius_km = aoi["radius_km"]
    if cfg.scale_m > radius_km * 1000:
        raise IndicatorComputeError(
            indicator_id=make_id(PILLAR_GHG, "viirs"),
            reason=(
                f"site buffer ({radius_km} km) smaller than VIIRS native "
                f"pixel ({cfg.scale_m / 1000:.2f} km) — increase radius or "
                f"omit VIIRS from selection"
            ),
        )

    band, scale = cfg.band, cfg.scale_m
    site_geom = site_buffer(aoi["centre"], radius_km)
    ring = background_ring(aoi["centre"], radius_km)
    ring_geom, ring_mask = ring["geometry"], ring["mask"]
    ic = (
        ee.ImageCollection(cfg.asset_id).select(band)
        .filterDate(time_range[0], time_range[1])
        .filterBounds(site_geom.bounds())
    )
    mean_img = ic.mean()

    # Site: median brightness + valid pixel count (median feeds both the display
    # site value and the lit-contrast comparison threshold).
    site_red = mean_img.reduceRegion(
        reducer=ee.Reducer.median().combine(ee.Reducer.count(), sharedInputs=True),
        geometry=site_geom, scale=scale, bestEffort=True, maxPixels=int(1e9),
    )
    site_median = ee.Number(
        ee.Algorithms.If(site_red.get(f"{band}_median"), site_red.get(f"{band}_median"), 0)
    )
    # Flaring: fraction of site pixels brighter than the absolute anchor.
    frac_above = mean_img.gt(VIIRS_FLARING_ABS_THRESHOLD_NW).rename("f").reduceRegion(
        reducer=ee.Reducer.mean(), geometry=site_geom, scale=scale,
        bestEffort=True, maxPixels=int(1e9),
    ).get("f")
    # Lit-contrast: ring all-pixel (land-masked) distribution; fraction dimmer than site.
    ring_img = mean_img.updateMask(ring_mask) if ring_mask is not None else mean_img
    n_ring = ring_img.rename("r").reduceRegion(
        reducer=ee.Reducer.count(), geometry=ring_geom, scale=scale,
        bestEffort=True, maxPixels=int(1e9),
    ).get("r")
    n_below = ring_img.lt(site_median).rename("b").reduceRegion(
        reducer=ee.Reducer.sum(), geometry=ring_geom, scale=scale,
        bestEffort=True, maxPixels=int(1e9),
    ).get("b")

    bundle = ee.Dictionary({
        "site_median": site_median,
        "n_site": site_red.get(f"{band}_count"),
        "frac_above": frac_above,
        "n_ring": n_ring,
        "n_below": n_below,
        "n_images": ic.size(),
    }).getInfo()

    n_images = int(bundle.get("n_images") or 0)
    n_site = int(bundle.get("n_site") or 0)
    if n_images == 0 or n_site == 0:
        raise SiteBufferNoDataError(
            indicator_id=make_id(PILLAR_GHG, "viirs"),
            reason=(
                "VIIRS had no site-buffer coverage in "
                f"{time_range[0]}..{time_range[1]} "
                f"(buffer={radius_km}km centre={aoi['centre']})"
            ),
        )

    flaring = flaring_score_from_fraction(bundle.get("frac_above"), n_site)
    percentile = lit_contrast_percentile_from_counts(bundle.get("n_below"), bundle.get("n_ring"))
    state = compute_viirs_attributability(percentile, int(bundle.get("n_ring") or 0))

    return _format_viirs_result(
        cfg=cfg, aoi=aoi, time_range=time_range,
        flaring=flaring, frac_above=bundle.get("frac_above"),
        site_brightness=bundle.get("site_median"),
        lit_contrast_percentile=percentile,
        n_ring_lit_pixels=int(bundle.get("n_ring") or 0),
        attributability_state=state,
        n_images=n_images,
    )


def _viirs_window_days(time_range: tuple[str, str]) -> int | None:
    """Inclusive day count between two ISO dates; None on parse failure.

    Local mirror of engine.core.repeatable_core._window_days (private there)
    so the VIIRS confidence coverage term has its window denominator.
    """
    from datetime import date as _date
    try:
        start = _date.fromisoformat(time_range[0])
        end = _date.fromisoformat(time_range[1])
    except (TypeError, ValueError):
        return None
    return max(1, (end - start).days)


def _viirs_confidence_terms(
    aoi: dict,
    n_valid: int,
    flaring: float | None,
    time_range: tuple[str, str],
) -> dict:
    """Four A1 confidence inputs for the redesigned VIIRS flaring term.

      * ``qa``               = QA_PER_INDICATOR["ghg.viirs"] (0.85).
      * ``n_valid``          = coverage term over the window (number of valid
                               daily images vs. expected).
      * ``anomaly_strength`` = the flaring score — the redesign's signal-strength
                               term (replaces persistence; passed through the
                               grammar-agnostic HF-shaped helper, clamped [0, 1]).
                               NOT the lit-contrast/attributability value, which
                               must never feed confidence (M-ATTRIB-A1 invariant).
      * ``spatial_context``  = buffer-vs-pixel ratio (unchanged).
    """
    buffer_area = math.pi * (aoi["radius_km"] * 1000.0) ** 2
    return {
        "qa": compute_qa_term("ghg.viirs"),
        "n_valid": compute_n_valid_term(
            "ghg.viirs",
            n_observations=n_valid,
            window_days=_viirs_window_days(time_range),
        ),
        "anomaly_strength": compute_anomaly_strength_term(
            "ghg.viirs", hf=flaring,
        ),
        "spatial_context": compute_spatial_context_term(
            "ghg.viirs", buffer_area_m2=buffer_area,
        ),
    }


def _format_viirs_result(
    cfg: GhgIndicatorConfig,
    *,
    aoi: dict,
    time_range: tuple[str, str],
    flaring: float | None,
    frac_above: float | None,
    site_brightness: float | None,
    lit_contrast_percentile: float | None,
    n_ring_lit_pixels: int,
    attributability_state: str,
    n_images: int,
) -> dict:
    """Map the two VIIRS outputs onto canonical IDs + provenance (M-VIIRS-REDESIGN-A1).

    Severity: `ghg.viirs.score` = flaring (feeds the composite via
    `ghg.activity_score`). Attributability (Pattern A, NOT in composite):
    `ghg.viirs.attributability_state` + sibling metrics, under its own
    `_provenance.ghg.viirs_lit_contrast` block.
    """
    confidence_terms = _viirs_confidence_terms(aoi, n_images, flaring, time_range)
    confidence = compute_indicator_confidence(
        indicator_id="ghg.viirs",
        column_to_surface_uncertainty="n_a",
        **confidence_terms,
    )

    return {
        # --- severity (composite-feeding) ---
        make_id(PILLAR_GHG, "viirs", "site"):          site_brightness,
        make_id(PILLAR_GHG, "viirs", "score"):         flaring,
        make_id(PILLAR_GHG, "viirs", "flaring_frac"):  frac_above,
        make_id(PILLAR_GHG, "viirs", "confidence"):    confidence,
        # --- attributability (Pattern A; NOT in composite or confidence) ---
        make_id(PILLAR_GHG, "viirs", "lit_contrast_percentile"): lit_contrast_percentile,
        make_id(PILLAR_GHG, "viirs", "ring_lit_pixel_count"):    n_ring_lit_pixels,
        make_id(PILLAR_GHG, "viirs", "site_brightness"):         site_brightness,
        make_id(PILLAR_GHG, "viirs", "attributability_state"):   attributability_state,
        "_provenance.ghg.viirs": build_provenance(
            indicator_id="ghg.viirs",
            asset_id=cfg.asset_id,
            band=cfg.band,
            data_type=cfg.data_type,
            data_source=cfg.data_source,
            native_scale_m=cfg.scale_m,
            time_range=time_range,
            method_note=(
                "M-VIIRS-REDESIGN-A1 flaring (severity): fraction of site pixels "
                f"brighter than {VIIRS_FLARING_ABS_THRESHOLD_NW:.0f} nW/cm²/sr "
                "(absolute intense-source anchor), normalised by "
                f"{VIIRS_FLARING_SATURATION_FRAC}. Replaces the retired sustained-"
                "contrast grammar (could not rank intensity; M-VIIRS-DIAG-A1). "
                "Directional; complements the Air NO₂/CO borrow."
            ),
            coverage_window=cfg.coverage_window,
            observations={"count": n_images, "unit": "daily_images"},
            extra={
                "flaring_fraction": frac_above,
                "abs_threshold_nw": VIIRS_FLARING_ABS_THRESHOLD_NW,
                "n_images": n_images,
                "confidence_terms": {
                    **confidence_terms,
                    "column_to_surface_uncertainty": "n_a",
                },
            },
        ),
        "_provenance.ghg.viirs_lit_contrast": build_provenance(
            indicator_id="ghg.viirs_lit_contrast",
            asset_id=cfg.asset_id,
            band=cfg.band,
            data_type=cfg.data_type,
            data_source=cfg.data_source,
            native_scale_m=cfg.scale_m,
            time_range=time_range,
            method_note=(
                "M-VIIRS-REDESIGN-A1 lit-contrast (attributability, Pattern A): "
                "percentile of site median brightness within the background ring's "
                "all-pixel (land-masked) distribution → categorical "
                "attributability_state. Does NOT enter the composite or the "
                "measurement-quality aggregate (M-ATTRIB-A1 invariant)."
            ),
            coverage_window=cfg.coverage_window,
            observations={"count": n_images, "unit": "daily_images"},
            extra={
                "lit_contrast_percentile": lit_contrast_percentile,
                "ring_lit_pixel_count": n_ring_lit_pixels,
                "attributability_state": attributability_state,
            },
        ),
    }


def compute_co2_snapshot(
    aoi: dict, time_range: tuple[str, str], mode: str, ee_client,  # noqa: ARG001
) -> dict:
    """ODIAC fossil CO₂ context snapshot (IC_v4 §2.1 / Schema_v2 §3.1).

    IMPORTANT — ODIAC is an emissions INVENTORY, not a satellite
    observation. NIES Japan compiles ODIAC by allocating national-level
    fossil-fuel CO₂ statistics down to a 1 km grid using the CARMA
    point-source database (for large facilities) and VIIRS nightlights
    (for diffuse emissions). The values are *attributed* to grid cells,
    not *measured* at them.

    This distinction matters for reviewers and auditors: the per-cell
    numbers reflect a modelled allocation, not observed CO₂ enhancement.
    The provenance block on every snapshot carries
    `data_type="emissions_inventory_allocation"` so downstream UI and
    validation can be explicit about this.

    Coverage: 2020-2023 only. Vintage lag is 2+ years and growing —
    ODIAC is updated roughly every 1-2 years. M5.5b demoted ODIAC from
    the live composite for this reason. M5.5c added a coverage_window
    check in run_pillar so present-day runs skip ODIAC silently rather
    than queueing futile EE calls.

    The site-vs-background six-step pattern doesn't apply directly to
    this inventory data — instead we compute:

    - `mean`               — average annualised flux density across buffer
                             pixels, expressed in t CO₂/yr per pixel.
    - `total`              — sum of annualised emissions within Site_Buffer
                             (t CO₂/yr across the whole AOI).
    - `relative_intensity` — site mean ÷ background ring mean. Labelled
                             "relative_intensity" not "anomaly" because
                             ODIAC is an allocation product, not a measured
                             baseline (see docs/v1x_followups.md).
    - `score`              — log-scaled 0-1 form of relative_intensity:
                             1× regional → 0, 10× regional → 1.

    The C → CO₂ molecular conversion (CO2_TO_C_RATIO = 44/12) and the
    monthly → annual scaling (×12) are applied here, not in
    GHG_INDICATOR_CONFIG, so the conversion is explicit and traceable in
    the provenance block.

    Raises:
        IndicatorComputeError: pixel-size guard fires (buffer < ODIAC native pixel)
                               or ODIAC has no pixels in the buffer / time_range.
    """
    cfg = GHG_INDICATOR_CONFIG["co2"]
    radius_km = aoi["radius_km"]
    if cfg.scale_m > radius_km * 1000:
        raise IndicatorComputeError(
            indicator_id=make_id(PILLAR_GHG, "co2"),
            reason=(
                f"site buffer ({radius_km} km) smaller than ODIAC "
                f"native pixel ({cfg.scale_m / 1000:.1f} km) — "
                f"increase radius or omit CO₂ from selection"
            ),
        )

    ic = ee.ImageCollection(cfg.asset_id).filterDate(*time_range)

    site_geom = site_buffer(aoi["centre"], radius_km)
    # M-TIER-A3 Step B — background_ring returns a dict; extract geometry.
    ring_geom = background_ring(aoi["centre"], radius_km)["geometry"]

    # ODIAC b1 holds t C *per cell per month*; sum the cells inside the
    # buffer over time, divide by n_months and multiply by 12 to annualise,
    # then multiply by CO2_TO_C_RATIO to convert C → CO₂.
    # `ic.sum()` adds the months element-wise: sum_pixel = Σ_months tC.
    summed_image = ic.select(cfg.band).sum()

    # M-PERF-A1 — batch the four per-snapshot getInfo round-trips into
    # one. `n_months` (collection size) and the three reduceRegion
    # dictionaries all evaluate server-side; combining them into one
    # ee.Dictionary lets a single `getInfo()` materialise everything.
    # Pre-batching this function fired 4 getInfo round-trips per
    # screening — see docs/M-PERF-A1_step_a_findings.md §3.
    #
    # Defensive shape (M-AIR-GHG-DEFENSIVE): each unpacked reduction
    # dict still falls back to `{}` and the per-band lookup falls back
    # to `0.0` so an empty buffer (band absent) yields zeros rather
    # than crashing.
    combined = ee.Dictionary({
        "n_months": ic.size(),
        "site_sum": summed_image.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=site_geom,
            scale=cfg.scale_m,
            bestEffort=True,
            maxPixels=int(1e9),
        ),
        "site_mean": summed_image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=site_geom,
            scale=cfg.scale_m,
            bestEffort=True,
            maxPixels=int(1e9),
        ),
        "ring_mean": summed_image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=ring_geom,
            scale=cfg.scale_m,
            bestEffort=True,
            maxPixels=int(1e9),
        ),
    }).getInfo() or {}

    # `n_months` surfaced in provenance + drives annualisation. The
    # historical "n_months == 0 → raise" guard has been removed:
    # run_pillar's M5.5c coverage_window check now skips this function
    # entirely for time ranges outside 2020-2023, so the branch was
    # dead code. If a future caller dispatches CO₂ outside its coverage
    # window without using run_pillar, the divide-by-zero in
    # `annualisation = 12.0 / n_months` will surface the bug loudly.
    n_months = int(combined.get("n_months") or 0)
    site_sum_t_c  = float((combined.get("site_sum")  or {}).get(cfg.band) or 0.0)
    site_mean_t_c = float((combined.get("site_mean") or {}).get(cfg.band) or 0.0)
    ring_mean_t_c = float((combined.get("ring_mean") or {}).get(cfg.band) or 0.0)

    # Annualise: `summed_image` is Σ months over time_range, so the mean
    # per month is (Σ months) / n_months; the annualised value is ×12.
    annualisation = 12.0 / n_months
    site_total_t_co2 = site_sum_t_c * annualisation * CO2_TO_C_RATIO
    site_mean_t_co2 = site_mean_t_c * annualisation * CO2_TO_C_RATIO
    ring_mean_t_co2 = ring_mean_t_c * annualisation * CO2_TO_C_RATIO

    relative_intensity, score = _co2_relative_intensity_and_score(
        site_mean_t_co2, ring_mean_t_co2,
    )

    return _format_co2_result(
        cfg=cfg,
        aoi=aoi,
        total=site_total_t_co2,
        mean=site_mean_t_co2,
        relative_intensity=relative_intensity,
        score=score,
        n_months=n_months,
        time_range=time_range,
    )


# Cap on relative_intensity: values > 10× regional background almost always
# indicate the buffer overlaps a CARMA-listed point source (single mega-
# emitter pixel dominating the small buffer). v1 clamps; v1.x will flag
# explicitly via the deferred CARMA-overlap provenance flag — see
# docs/v1x_followups.md.
_CO2_RELATIVE_INTENSITY_CAP: float = 10.0


def _co2_relative_intensity_and_score(
    site_mean: float, ring_mean: float,
) -> tuple[float | None, float | None]:
    """Compute (relative_intensity, score) for the CO₂ snapshot.

    Score formula: `clamp(log10(max(rel_intensity, 1)) / log10(10), 0, 1)`.
    At 1× regional background → score 0; at 10× background → score 1.
    Saturates log-style rather than linear so a 2× site doesn't read as
    "moderately concerning" — emissions are heavy-tailed.

    TODO(v1.x): CARMA-overlap flag — when the buffer overlaps a CARMA
    power-plant point, set carma_overlap=True in provenance and surface in
    the limiting-factor template per docs/v1x_followups.md.
    """
    if ring_mean <= 0:
        return None, None
    rel = min(site_mean / ring_mean, _CO2_RELATIVE_INTENSITY_CAP)
    safe_rel = max(rel, 1.0)
    score = math.log10(safe_rel) / math.log10(_CO2_RELATIVE_INTENSITY_CAP)
    return rel, max(0.0, min(1.0, score))


def _format_co2_result(
    cfg: GhgIndicatorConfig,
    *,
    aoi: dict,
    total: float,
    mean: float,
    relative_intensity: float | None,
    score: float | None,
    n_months: int,
    time_range: tuple[str, str],
) -> dict:
    """Map computed values onto the canonical CO₂ measurement IDs.

    `trend` / `trend_p` are None pending the same M5+ trend.py wiring used
    by Air and CH₄. `confidence` is computed via the M-TIER-A1 universal
    formula treating ODIAC as a single-snapshot indicator (the helper
    bypasses the daily-revisit ratio because `ghg.co2` is in
    SINGLE_SNAPSHOT_INDICATORS — see engine.core.confidence).
    """
    confidence_terms = _co2_confidence_terms(aoi, n_months, score)
    confidence = compute_indicator_confidence(
        indicator_id="ghg.co2",
        column_to_surface_uncertainty="n_a",
        **confidence_terms,
    )

    return {
        make_id(PILLAR_GHG, "co2", "mean"):               mean,
        make_id(PILLAR_GHG, "co2", "total"):              total,
        make_id(PILLAR_GHG, "co2", "relative_intensity"): relative_intensity,
        make_id(PILLAR_GHG, "co2", "trend"):              None,
        make_id(PILLAR_GHG, "co2", "trend_p"):            None,
        make_id(PILLAR_GHG, "co2", "confidence"):         confidence,
        make_id(PILLAR_GHG, "co2", "score"):              score,
        # M5.6 — canonical provenance via build_provenance. ODIAC-specific
        # fields (c_to_co2_factor) go into `extra`; the M5.5b
        # `role_in_pillar` field is dropped — `data_type` carries the same
        # information more honestly, and "not in live composite" is
        # encoded in CORE_GHG_AUDIT_SUPPORT_WEIGHTS itself.
        # M-TIER-A1 — confidence_terms also lands in `extra` for
        # downstream consumers (the GHG_DQA sub-scores in particular
        # walk these terms back to compute pillar-level rollups).
        "_provenance.ghg.co2": build_provenance(
            indicator_id="ghg.co2",
            asset_id=cfg.asset_id,
            band=cfg.band,
            data_type=cfg.data_type,
            data_source=cfg.data_source,
            native_scale_m=cfg.scale_m,
            time_range=time_range,
            method_note=(
                "monthly t C → annual t CO₂ via ×(12/n_months)·(44/12); "
                "national totals × CARMA point sources + VIIRS "
                "nightlights → 1 km grid"
            ),
            coverage_window=cfg.coverage_window,
            observations={"count": n_months, "unit": "monthly_grids"},
            extra={
                "c_to_co2_factor": CO2_TO_C_RATIO,
                "confidence_terms": {
                    **confidence_terms,
                    "column_to_surface_uncertainty": "n_a",
                },
            },
        ),
    }


def _co2_confidence_terms(aoi: dict, n_months: int, score: float | None) -> dict:
    """Compute the four A1 confidence inputs for ODIAC.

    ODIAC is a single-snapshot indicator (annual inventory), so:
      * `qa` = QA_PER_INDICATOR["ghg.co2"] (1.00 — no per-pixel QA concept)
      * `n_valid` = 1.0 when the snapshot computed (n_months >= 1); 0.0 when skipped
      * `anomaly_strength` = 1.0 (no HF concept; reference-style data)
      * `spatial_context` = clamp(sqrt(buffer / 1km²) / 3, 0, 1)
    All four are None only when the snapshot failed entirely
    (score is None), in which case strict-None propagates.
    """
    buffer_area = math.pi * (aoi["radius_km"] * 1000.0) ** 2
    return {
        "qa": compute_qa_term("ghg.co2"),
        "n_valid": compute_n_valid_term(
            "ghg.co2", n_observations=n_months, window_days=None,
        ),
        "anomaly_strength": compute_anomaly_strength_term("ghg.co2", hf=None),
        "spatial_context": compute_spatial_context_term(
            "ghg.co2", buffer_area_m2=buffer_area,
        ),
    }


# ---------------------------------------------------------------------------
# GHG quality sub-scores  (IC_v4 §6.3.2; spec §4.2)
# ---------------------------------------------------------------------------

# Three of the four GHG_Data_Quality_Attribution sub-scores are derived
# directly from per-indicator A1 confidence inputs (stored in each GHG
# indicator's `_provenance.ghg.<ind>.extra.confidence_terms`). The fourth,
# `nearby_source_isolation`, is a spatial-context check (IC_v4 §7.2) that
# stays independent of per-indicator QA/N_valid/HF/spatial_context inputs.

# M-CH4-A1 (30 May 2026): "ch4" removed — CH₄ is reference data, so its
# per-indicator QA terms no longer feed the scored GHG quality aggregates.
# The CH₄ snapshot still computes its own confidence for the reference card.
_GHG_PER_INDICATOR_QA_KEYS: tuple[str, ...] = ("co2", "viirs")


def _ghg_confidence_term_for(payload: dict, indicator: str, term: str) -> float | None:
    """Read one A1 confidence input for a GHG indicator from provenance.extra.

    Returns None when the indicator's snapshot didn't run (skipped path or
    failure), so survivor-renormalise in the mean below skips it.
    """
    prov = payload.get(f"_provenance.ghg.{indicator}")
    if not prov:
        return None
    extra = prov.get("extra") or {}
    terms = extra.get("confidence_terms")
    if not terms:
        return None
    value = terms.get(term)
    return value if isinstance(value, (int, float)) else None


def _mean_over_ghg_indicators(payload: dict, term: str) -> float | None:
    survivors = [
        v for ind in _GHG_PER_INDICATOR_QA_KEYS
        if (v := _ghg_confidence_term_for(payload, ind, term)) is not None
    ]
    if not survivors:
        return None
    return sum(survivors) / len(survivors)


def compute_temporal_coverage(payload: dict) -> dict:
    """IC_v4 §6.3.2 / spec §4.2 — mean of per-indicator N_valid across GHG.

    Replaces the pre-A1 placeholder that echoed `ghg.ch4.confidence`. After
    A1 every GHG indicator emits its own N_valid term (TROPOMI CH₄ daily
    revisit fraction, VIIRS daily revisit fraction, ODIAC single-snapshot
    pass-through to 1.0), so this is now the audit-doc-aligned form.
    """
    return {"ghg.temporal_coverage": _mean_over_ghg_indicators(payload, "n_valid")}


def compute_spatial_resolution_suitability(payload: dict, aoi: dict | None = None) -> dict:
    """IC_v4 §6.3.2 / spec §4.2 — mean of per-indicator spatial_context across GHG.

    Replaces the pre-A1 placeholder which used a single CH₄-only ratio
    (`radius_m / CH4_NATIVE_SCALE_M`). The new form averages all GHG
    indicators' spatial_context terms — CH₄'s 7 km pixel, ODIAC's 1 km
    grid, VIIRS's 463 m DNB cell — so the sub-score reflects all three
    indicators' suitability for the chosen buffer.

    `aoi` is accepted for signature parity with the pre-A1 call shape but
    no longer used; the per-indicator spatial_context terms already
    incorporate aoi.radius_km via `compute_spatial_context_term`.
    """
    del aoi
    return {
        "ghg.spatial_resolution_suitability": _mean_over_ghg_indicators(
            payload, "spatial_context",
        ),
    }


def compute_retrieval_inventory_quality(payload: dict) -> dict:
    """IC_v4 §6.3.2 / spec §4.2 — mean of per-indicator QA across GHG.

    Replaces the pre-A1 fixed 0.7 placeholder. After A1 each GHG indicator
    carries its own static QA value from `QA_PER_INDICATOR`
    (ghg.ch4 = 0.85, ghg.co2 = 1.00, ghg.viirs = 0.85), so the mean is a
    real per-pillar QA aggregate.
    """
    return {
        "ghg.retrieval_inventory_quality": _mean_over_ghg_indicators(payload, "qa"),
    }


def compute_nearby_source_isolation(payload: dict) -> dict:
    """Schema_v2 §3.4 — fixed 1.0 placeholder. RESERVED for future use.

    M-ATTRIB-A1 (AT15): this is an *attributability* concept, not a
    measurement-quality term. As of M-ATTRIB-A1 it is removed from
    `GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS` (the data-quality aggregate) so
    the fixed 1.0 placeholder no longer inflates that score. The field is
    still emitted into the payload and provenance — reserved for a future
    GHG attributability surface (parallel to the M-WIND-A1 v2.0 / Nature
    `supplier_spatial_link` attributability work) — but it does NOT enter
    any aggregate in v1.x.

    The real formula (IC_v4 §7.2) is the satellite-only proxy
    `0.5·isolation_from_no2 + 0.5·isolation_from_viirs`. Independent of A1
    per spec §4.2.

    TODO(IC_v5 / future attributability milestone): implement per §7.2.
    """
    return {"ghg.nearby_source_isolation": 1.0}


# ---------------------------------------------------------------------------
# Sub-aggregates  (IC_v4 §2.2 / Schema_v2 §3.2)
# ---------------------------------------------------------------------------

def compute_ch4_hotspot_signal(payload: dict) -> dict:
    """IC_v4 §2.2 — `ch4.score` when CH₄ z exceeds ANOMALY_Z_THRESHOLD, else 0.0.

    Strict: if either ch4.score or ch4.z is missing/None, the signal is None.
    """
    score = payload.get("ghg.ch4.score")
    z = payload.get("ghg.ch4.z")
    if score is None or z is None:
        return {"ghg.ch4_hotspot_signal": None}
    return {
        "ghg.ch4_hotspot_signal": score if z >= ANOMALY_Z_THRESHOLD else 0.0,
    }


def compute_combustion_proxy(payload: dict) -> dict:
    """IC_v4 §2.2 — borrowed from Air pillar's `industrial_combustion_proxy`.

    Cross-pillar dependency (resolved M5c): reads
    `air.industrial_combustion_proxy` from the local payload. At runtime
    the orchestrator (ScreeningRun) passes its accumulated post-Air payload
    via the `accumulated_payload` kwarg to `run_pillar`; `run_pillar`
    merges those keys into its local payload before this function is
    called, so Air's value is visible here.

    If Air didn't run, that key was excluded from `accumulated_payload`, or
    Air's pillar-wide failure left it None, this returns None and
    downstream sub-aggregates null-propagate.
    """
    borrow = payload.get("air.industrial_combustion_proxy")
    w_borrow = CORE_GHG_AUDIT_SUPPORT_WEIGHTS.get("ghg.combustion_proxy")
    return {
        "ghg.combustion_proxy": borrow,
        # VR17 — make the Air NO₂/CO borrow visible at the GHG level (it carries
        # the larger composite weight post-redesign). No value change; surfacing only.
        "_provenance.ghg.combustion_proxy": {
            "indicator_id": "ghg.combustion_proxy",
            "data_type": "derived",
            "data_source": "air_pillar_borrow",
            "method_note": (
                "GHG combustion proxy = the Air pillar's industrial_combustion_proxy "
                "(weighted NO₂ + CO scores), borrowed by the GHG composite. Only the "
                "numerical score is borrowed; the Air-pillar wind-attributability flags "
                "for NO₂/CO are NOT propagated (see the Air NO₂ + CO provenance entries)."
            ),
            "extra": {
                "borrowed_from": ["air.no2", "air.co"],
                "air_no2_score": payload.get("air.no2.score"),
                "air_co_score": payload.get("air.co.score"),
                "borrow_weight_in_ghg": w_borrow,
                "borrow_contribution": (borrow * w_borrow) if borrow is not None and w_borrow is not None else None,
            },
        },
    }


def compute_activity_score(payload: dict) -> dict:
    """IC_v4 §2.2 — surfaces `ghg.viirs.score` as a sub-aggregate ID for
    downstream `compute_activity_adjusted_co2` (M5.5)."""
    return {"ghg.activity_score": payload.get("ghg.viirs.score")}


def compute_fire_or_regional_transport_risk(payload: dict) -> dict:
    """IC_v4 §2.2 / §1.2 — borrowed from Air pillar's
    `smoke_dust_regional_transport`.

    Cross-pillar dependency (resolved M5c): the orchestrator threads its
    accumulated post-Air payload into `run_pillar` via `accumulated_payload`;
    `run_pillar` merges those keys into the local payload before this
    function runs, so Air's value is visible here. See
    `compute_combustion_proxy` for the full mechanism.
    """
    return {
        "ghg.fire_or_regional_transport_risk":
            payload.get("air.smoke_dust_regional_transport"),
    }


def compute_ch4_context_adjusted(payload: dict) -> dict:
    """IC_v4 §2.2 — `ch4.score − 0.20·fire_or_regional_transport_risk`,
    clamped to [0, 1]."""
    score = payload.get("ghg.ch4.score")
    fire = payload.get("ghg.fire_or_regional_transport_risk")
    if score is None or fire is None:
        return {"ghg.ch4_context_adjusted": None}
    value = score - 0.20 * fire
    return {"ghg.ch4_context_adjusted": min(max(value, 0.0), 1.0)}


def compute_co2_context(payload: dict) -> dict:
    """IC_v4 §2.2 — alias of `ghg.co2.score`.

    Activated in M5.5; demoted to display-only in M5.5b — no longer feeds
    compute_core_ghg_audit_support, which is now driven by the three live
    signals (CH₄ + combustion + activity). This function still emits the
    value so the UI can render it as standing-exposure context, and so
    offline validation harnesses can compare it against the live trio.
    """
    return {"ghg.co2_context": payload.get("ghg.co2.score")}


def compute_fossil_combustion_score(payload: dict) -> dict:
    """IC_v4 §2.2 — `0.50·co2_context + 0.30·combustion_proxy + 0.20·activity_score`.

    Activated in M5.5; display-only in M5.5b. No longer drives the live
    composite; kept for offline validation and for UI "ODIAC says X"
    captions. Strict-null-propagates if any input is missing.
    """
    return {
        "ghg.fossil_combustion_score": _weighted_sum_strict(
            payload, _FOSSIL_COMBUSTION_WEIGHTS,
        ),
    }


def compute_activity_adjusted_co2(payload: dict) -> dict:
    """IC_v4 §2.2 — `0.70·co2_context + 0.30·activity_score`.

    Activated in M5.5; display-only in M5.5b. No longer drives the live
    composite; kept for offline validation. Strict-null-propagates if
    either input is missing.

    TODO(v1.x): per docs/v1x_followups.md this term arguably triple-counts
    VIIRS (which already feeds ghg.activity_score directly and ODIAC
    indirectly via the diffuse allocation branch). Now that ODIAC isn't
    in the live composite the urgency is lower, but the triple-counting
    concern remains for whatever validation work uses this term.
    """
    return {
        "ghg.activity_adjusted_co2": _weighted_sum_strict(
            payload, _ACTIVITY_ADJUSTED_CO2_WEIGHTS,
        ),
    }


# ---------------------------------------------------------------------------
# Pillar aggregates  (IC_v4 §2.3 / Schema_v2 §3.3)
# ---------------------------------------------------------------------------

def compute_core_ghg_audit_support(
    payload: dict, selected: set[str],
) -> dict:
    """IC_v4 §2.3 — weighted sum per CORE_GHG_AUDIT_SUPPORT_WEIGHTS.

    Post-M5.5b: CO₂ is no longer in this composite. The three live signals
    (CH₄ + combustion + activity) are rescaled to sum to 1.00 in
    CORE_GHG_AUDIT_SUPPORT_WEIGHTS (0.46 / 0.44 / 0.10). `selected`
    restricts which terms contribute; weights renormalise over the
    surviving set. If a present-day screening run includes CO₂ but ODIAC
    is unavailable (time range outside 2020-2023), this aggregate still
    computes from the surviving three terms — that's the whole point of
    the M5.5b demotion.
    """
    candidates = {
        k: payload[k] for k in CORE_GHG_AUDIT_SUPPORT_WEIGHTS
        if k in selected and payload.get(k) is not None
    }
    if not candidates:
        return {"ghg.core_audit_support": None}
    weights = _renormalise_weights(CORE_GHG_AUDIT_SUPPORT_WEIGHTS, set(candidates))
    score = sum(weights[k] * candidates[k] for k in candidates)
    return {"ghg.core_audit_support": score}


# M-GHG-REDESIGN-A1 (GATE B): `compute_ghg_spatiotemporal_anomaly` is REMOVED.
# It averaged clamped per-indicator z-scores, but after M-CH4-A1 (CH₄ → reference
# data) and M-GHG-REDESIGN-A1 (VIIRS → persistence-weighted sustained contrast,
# no z-score; CO₂/ODIAC never had a `.z`) the GHG pillar has no spatiotemporal-
# anomaly source. The aggregate is retired from the follow-up priority
# (GHG_FOLLOWUP_WEIGHTS) and no longer computed or emitted. `ghg.spatiotemporal_
# anomaly` is kept as a reserved (retired) canonical ID in engine/ids.py.


# M-TREND-A1 (TR10 / decision-log E3): `compute_ghg_trend` is removed — no
# cross-indicator aggregate trend exists (same rationale as Air). Trend is a
# per-indicator on-demand drill-down (`engine/core/trend.py::compute_trend`);
# `ghg.trend` is no longer emitted and `composite` never sees GHG trend.

# Quality sub-scores aren't user-selectable — they're internal placeholders
# computed unconditionally by run_pillar. So we filter on presence, not on
# `selected`. Other pillar aggregates filter both.
def compute_ghg_data_quality_attribution(payload: dict) -> dict:
    """IC_v4 §2.3 — weighted sum per GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS
    over the three measurement-quality sub-scores. Missing terms
    renormalised.

    M-ATTRIB-A1 (AT15): nearby_source_isolation was removed from the
    weights dict (attributability, not measurement quality), so this is now
    a three-term aggregate. compute_nearby_source_isolation still emits the
    field into the payload, but it is not a candidate here.
    """
    candidates = {
        k: payload[k] for k in GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS
        if payload.get(k) is not None
    }
    if not candidates:
        return {"ghg.data_quality_attribution": None}
    weights = _renormalise_weights(
        GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS, set(candidates),
    )
    score = sum(weights[k] * candidates[k] for k in candidates)
    return {"ghg.data_quality_attribution": score}


def compute_ghg_audit_followup_priority(
    payload: dict, mode: str,                            # noqa: ARG001 — parity
) -> dict:
    """IC_v4 §2.3 — weighted sum per GHG_FOLLOWUP_WEIGHTS over the four
    pillar aggregates.

    `mode` is accepted for signature stability (M-TREND-A1 removed the
    only mode-dependent term, the aggregate trend).

    M-FOLLOWUP-FALLBACK: strict-None propagation. Same shape as
    ``compute_air_audit_followup_priority`` — any None among the
    sub-aggregates means a real upstream failure and the priority is
    None.
    """
    values: list[float] = []
    for term in GHG_FOLLOWUP_WEIGHTS:
        v = payload.get(_FOLLOWUP_TERM_TO_ID[term])
        if v is None:
            return {"ghg.audit_followup_priority": None}
        values.append(GHG_FOLLOWUP_WEIGHTS[term] * v)
    return {"ghg.audit_followup_priority": sum(values)}


# ---------------------------------------------------------------------------
# Pillar entry point
# ---------------------------------------------------------------------------

def _compute_one_ghg_indicator_outcome(
    ind_key: str,
    aoi: dict,
    time_range: tuple[str, str],
    mode: str,
    ee_client,
    fallback: FallbackContext | None,
) -> tuple[dict, dict | None, bool]:
    """Compute one GHG indicator — coverage gate + snapshot + skip / failure.

    Returns ``(payload_chunk, failure_or_none, attempted_flag)``:
      - ``attempted_flag=False`` for out-of-coverage skips (the original
        loop's ``continue`` path — chunk carries None values + skipped
        provenance; the indicator does NOT count toward attempted_keys).
      - ``attempted_flag=True`` for everything else (success, soft-skip
        via Background/SiteBuffer NoData, or hard IndicatorComputeError).

    Stateless / thread-safe; mirrors `_compute_one_pollutant_outcome` in
    engine.air. Bundling the standing-window check into the helper keeps
    the per-indicator work fully independent so the dispatcher in
    run_pillar can parallelise without coordination.
    """
    cfg = GHG_INDICATOR_CONFIG[ind_key]

    # M-V1x-STANDING-WINDOW + M5.5c — coverage gate before snapshot.
    effective_time_range = (
        _latest_coverage_year_window(cfg.coverage_window)
        if cfg.coverage_window is not None
        else time_range
    )
    if not _time_range_in_coverage(effective_time_range, cfg.coverage_window):
        chunk: dict = {
            make_id(PILLAR_GHG, ind_key, m): None
            for m in cfg.emitted_measurements
        }
        chunk[f"_provenance.ghg.{ind_key}"] = build_provenance(
            indicator_id=f"ghg.{ind_key}",
            asset_id=cfg.asset_id,
            band=cfg.band,
            data_type=cfg.data_type,
            data_source=cfg.data_source,
            native_scale_m=cfg.scale_m,
            time_range=effective_time_range,
            coverage_window=cfg.coverage_window,
            skipped_reason="out_of_coverage",
            observations={"count": 0, "unit": "monthly_grids"},
            extra={},
        )
        return chunk, None, False  # not attempted (the prior loop's `continue`)

    try:
        if ind_key == "co2":
            snapshot = compute_co2_snapshot(
                aoi=aoi,
                time_range=effective_time_range,
                mode=mode,
                ee_client=ee_client,
            )
        elif ind_key == "viirs":
            # M-GHG-REDESIGN-A1 — VIIRS has its own per-timestep sustained-
            # contrast path, off six_step. It owns its empty-series → None
            # handling, so it doesn't take the six_step `fallback` machinery.
            snapshot = compute_viirs_two_output(
                aoi=aoi,
                time_range=time_range,
                mode=mode,
                ee_client=ee_client,
            )
        else:
            snapshot = compute_ghg_indicator_snapshot(
                aoi=aoi,
                indicator=ind_key,
                time_range=time_range,
                mode=mode,
                ee_client=ee_client,
                fallback=fallback,
            )
        return snapshot, None, True
    except BackgroundRingNoDataError as err:
        return _emit_skipped_ghg_result(
            ind_key,
            time_range=time_range,
            skipped_reason="background_ring_no_data",
            reason_detail=err.reason,
        ), None, True
    except SiteBufferNoDataError as err:
        return _emit_skipped_ghg_result(
            ind_key,
            time_range=time_range,
            skipped_reason=cfg.skipped_reason_no_data,
            reason_detail=err.reason,
        ), None, True
    except IndicatorComputeError as err:
        chunk = {
            make_id(PILLAR_GHG, ind_key, m): None
            for m in cfg.emitted_measurements
        }
        failure = {
            "indicator":    ind_key,
            "indicator_id": err.indicator_id,
            "reason":       err.reason,
        }
        return chunk, failure, True


def run_pillar(
    aoi: dict,
    time_range: tuple[str, str],
    mode: str,
    selected_indicators: set[str],
    ee_client,
    *,
    accumulated_payload: dict | None = None,
    fallback: FallbackContext | None = None,
) -> dict:
    """Compute every selected GHG indicator + sub-aggregates + pillar aggregates.

    Cross-pillar dependency (M5c wired): `compute_combustion_proxy` and
    `compute_fire_or_regional_transport_risk` read values from Air's payload
    (`air.industrial_combustion_proxy`, `air.smoke_dust_regional_transport`).
    The orchestrator passes its accumulated payload (post-Air) as
    `accumulated_payload`; we merge it into the local payload before
    sub-aggregate computation so the borrows resolve, then strip the
    injected keys before return so we only emit GHG-pillar output.

    Raises `PillarComputeError` if every selected GHG indicator failed.
    """
    indicator_keys = _ghg_indicator_keys_from_selected(selected_indicators)
    payload: dict = {}
    failures: list[dict] = []
    # M5.5c — `attempted_keys` is the subset of indicator_keys whose
    # coverage_window overlapped the user's time_range, i.e. the indicators
    # we actually tried to compute. The "all failed" PillarComputeError
    # check below uses this set so that out-of-coverage skips don't count
    # as failures (a present-day run with only CO₂ selected would otherwise
    # trip PillarComputeError because the single selected indicator was
    # skipped, not failed).
    attempted_keys: set[str] = set()

    # M-PERF-PARALLEL #3b: dispatch the (up to 3) GHG indicators concurrently
    # through a thread pool. Each is independent — coverage-gating + snapshot
    # + skip + failure logic is bundled in _compute_one_ghg_indicator_outcome
    # so workers are stateless. attempted_keys / payload / failures are merged
    # on the main thread in canonical sorted order so the final shape stays
    # byte-identical to the prior serial implementation.
    sorted_keys = sorted(indicator_keys)
    if sorted_keys:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(_GHG_MAX_PARALLEL_WORKERS, len(sorted_keys)),
            thread_name_prefix="gsco-ghg",
        ) as ex:
            outcomes = list(ex.map(
                lambda ik: _compute_one_ghg_indicator_outcome(
                    ik, aoi, time_range, mode, ee_client, fallback,
                ),
                sorted_keys,
            ))
        for ind_key, (chunk, failure, attempted) in zip(sorted_keys, outcomes):
            payload.update(chunk)
            if failure is not None:
                failures.append(failure)
            if attempted:
                attempted_keys.add(ind_key)

    if attempted_keys and len(failures) == len(attempted_keys):
        affected = [
            make_id(PILLAR_GHG, ind, m)
            for ind in sorted(attempted_keys)
            for m in GHG_INDICATOR_CONFIG[ind].emitted_measurements
        ]
        raise PillarComputeError(
            pillar=PILLAR_GHG,
            indicator_ids=affected,
            reason="all selected GHG indicators failed to compute",
        )

    # M5c cross-pillar merge: inject Air's payload so the borrow chain
    # (compute_combustion_proxy, compute_fire_or_regional_transport_risk)
    # sees Air's values. Track what we injected so we strip it before return.
    # Filter out any ghg.* keys so an upstream pillar can't shadow GHG's own
    # computations through the accumulated payload — defensive guard against
    # future cross-pillar namespace pollution.
    injected_keys: set[str] = set()
    if accumulated_payload is not None:
        for key, value in accumulated_payload.items():
            if key.startswith(f"{PILLAR_GHG}."):
                continue
            if key not in payload:
                payload[key] = value
                injected_keys.add(key)

    recompute_ghg_aggregates(payload, selected_indicators, mode, aoi)

    # Strip the cross-pillar-injected keys — the orchestrator already has
    # Air's payload; GHG returns only its own pillar output.
    for key in injected_keys:
        payload.pop(key, None)

    if failures:
        payload["_failures"] = failures

    return payload


def recompute_ghg_aggregates(
    payload: dict,
    selected_indicators: set[str],
    mode: str,
    aoi: dict,
) -> dict:
    """Recompute GHG's quality sub-scores, sub-aggregates, and pillar
    aggregates in place on `payload` (pure, no EE).

    Extracted from `run_pillar` so the M-FALLBACK-A1 patch path can refresh
    the aggregates after splicing a recomputed single indicator. The Air
    cross-pillar borrows (`air.industrial_combustion_proxy`,
    `air.smoke_dust_regional_transport`) must already be present in `payload`
    — in a full screening payload they always are (Air runs first).
    """
    # Quality sub-scores — three derived from per-indicator A1 confidence
    # terms (in provenance.extra.confidence_terms); nearby_source_isolation
    # stays an independent §7.2 spatial proxy (placeholder pending wiring).
    payload.update(compute_temporal_coverage(payload))
    payload.update(compute_spatial_resolution_suitability(payload, aoi))
    payload.update(compute_retrieval_inventory_quality(payload))
    payload.update(compute_nearby_source_isolation(payload))

    # Sub-aggregates — dependency order: Air-borrowed first (so dependents
    # downstream see them), then the three CO₂-dependent composites (activated
    # in M5.5 once ODIAC is wired).
    #
    # M-CH4-A1 (30 May 2026): the two CH₄ scored sub-aggregates
    # (compute_ch4_hotspot_signal, compute_ch4_context_adjusted) are no longer
    # computed — CH₄ is reference data, so nothing scored consumes it. The
    # snapshot still emits ghg.ch4.* (incl. .z) for the C5 reference card; only
    # its downstream scoring consumption is removed (docs/ghg_odiac_validation.md
    # §10). compute_fire_or_regional_transport_risk stays computed (Air-borrowed,
    # cheap) but is now unconsumed — reserved for a future attributability surface.
    payload.update(compute_combustion_proxy(payload))
    payload.update(compute_fire_or_regional_transport_risk(payload))
    payload.update(compute_activity_score(payload))
    payload.update(compute_co2_context(payload))
    payload.update(compute_fossil_combustion_score(payload))
    payload.update(compute_activity_adjusted_co2(payload))

    # Pillar aggregates — augment `selected` so sub-aggregate IDs with
    # non-None values contribute to CORE_GHG_AUDIT_SUPPORT_WEIGHTS.
    augmented_selected: set[str] = set(selected_indicators)
    for sub_id in (
        "ghg.combustion_proxy",
        "ghg.activity_score",
        "ghg.fire_or_regional_transport_risk",
        "ghg.co2_context",
        "ghg.fossil_combustion_score",
        "ghg.activity_adjusted_co2",
    ):
        if payload.get(sub_id) is not None:
            augmented_selected.add(sub_id)

    payload.update(compute_core_ghg_audit_support(payload, augmented_selected))
    # M-TREND-A1 (TR10): no aggregate trend term — trend is drill-down-only.
    # M-GHG-REDESIGN-A1 (GATE B): no spatiotemporal-anomaly term — retired
    # (GHG has no anomaly source after the VIIRS re-grammar; see above).
    payload.update(compute_ghg_data_quality_attribution(payload))
    payload.update(compute_ghg_audit_followup_priority(payload, mode))
    return payload


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_image_collection(cfg: GhgIndicatorConfig) -> ee.ImageCollection:
    """Construct the scaled ImageCollection for `cfg`. No preprocess in M5a —
    CH₄ uses Google's L3 product directly; VIIRS uses the gap-filled product."""
    ic = ee.ImageCollection(cfg.asset_id).select(cfg.band)
    if cfg.scale_factor != 1.0:
        scale = cfg.scale_factor
        band_name = cfg.band
        # `multiply` produces a fresh image with no properties, which would
        # make `filterDate` return zero results downstream. copyProperties
        # restores the timestamps so the time-window filter works.
        ic = ic.map(lambda img: (
            img.multiply(scale)
               .rename(band_name)
               .copyProperties(img, ["system:time_start", "system:time_end"])
        ))
    return ic


def _format_result(
    indicator: str,
    cfg: GhgIndicatorConfig,
    raw: dict,
    time_range: tuple[str, str],
) -> dict:
    """Apply score cap, remap `raw` to canonical IDs filtered by
    `cfg.emitted_measurements`, attach provenance."""
    score = raw.get("score")
    if cfg.score_cap is not None and score is not None:
        score = min(score, cfg.score_cap)

    result: dict = {}
    for measurement in cfg.emitted_measurements:
        value = score if measurement == "score" else raw.get(measurement)
        result[make_id(PILLAR_GHG, indicator, measurement)] = value

    # M-TIER-A1 — same shape as engine.air._format_result: surface the
    # four confidence-formula inputs in provenance.extra.
    extra: dict = {}
    confidence_terms = raw.get("confidence_terms")
    if confidence_terms is not None:
        extra["confidence_terms"] = confidence_terms
    # M-UI-A1-SURFACE engine-gap fix — same dates + granules surface as Air.
    n_valid_dates = raw.get("n_valid_dates")
    if n_valid_dates is not None:
        extra["n_valid_dates"] = n_valid_dates
    granule_count = raw.get("granule_count")
    if granule_count is not None:
        extra["granule_count"] = granule_count
    # M-TIER-A3 Step E — MOD44W land-mask provenance fields per spec §3.6.
    ring_land_fraction = raw.get("ring_land_fraction")
    if ring_land_fraction is not None:
        extra["ring_land_fraction"] = ring_land_fraction
    ring_land_mask_applied = raw.get("ring_land_mask_applied")
    if ring_land_mask_applied is not None:
        extra["land_mask_applied"] = ring_land_mask_applied
    ring_land_mask_asset = raw.get("ring_land_mask_asset")
    if ring_land_mask_asset is not None:
        extra["land_mask_asset"] = ring_land_mask_asset
    # M-FALLBACK-A1 §4.7 — merge the additive fallback fields (aoi_scale_class
    # always; temporal_/climatology_ pair when a fallback fired).
    fallback_extra = raw.get("fallback_extra")
    if fallback_extra is not None:
        extra.update(fallback_extra)
    # M-DIAG-A4 — merge the climatology-baseline denominator provenance. CH₄
    # still gets the new denominator (extraction unchanged per M-CH4-A1) even
    # though its severity is no longer surfaced; the fix applies uniformly.
    clim_denominator_extra = raw.get("clim_denominator_extra")
    if clim_denominator_extra is not None:
        extra.update(clim_denominator_extra)

    result[f"_provenance.ghg.{indicator}"] = build_provenance(
        indicator_id=f"ghg.{indicator}",
        asset_id=cfg.asset_id,
        band=cfg.band,
        data_type=cfg.data_type,
        data_source=cfg.data_source,
        native_scale_m=cfg.scale_m,
        time_range=time_range,
        method_note=None,
        coverage_window=cfg.coverage_window,
        # TODO(v1.x): track six_step's actual image count and surface as
        # observations={"count": n, "unit": "daily_images"}.
        observations=None,
        extra=extra,
    )
    return result


# M-OCEAN-RING
def _emit_skipped_ghg_result(
    indicator: str,
    *,
    time_range: tuple[str, str],
    skipped_reason: str,
    reason_detail: str,
) -> dict:
    """Canonical 'GHG indicator skipped' payload.

    Mirrors ``engine.air._emit_skipped_air_result`` and the M5.5c
    out-of-coverage pattern (every emitted measurement → None,
    provenance carries ``skipped_reason``). NOT routed into
    ``_failures`` — silent-skip is a coverage statement, not a compute
    failure.
    """
    cfg = GHG_INDICATOR_CONFIG[indicator]
    result: dict = {
        make_id(PILLAR_GHG, indicator, m): None
        for m in cfg.emitted_measurements
    }
    result[f"_provenance.ghg.{indicator}"] = build_provenance(
        indicator_id=f"ghg.{indicator}",
        asset_id=cfg.asset_id,
        band=cfg.band,
        data_type=cfg.data_type,
        data_source=cfg.data_source,
        native_scale_m=cfg.scale_m,
        time_range=time_range,
        method_note=f"IC §0.2 six-step pipeline; skipped ({reason_detail})",
        coverage_window=cfg.coverage_window,
        skipped_reason=skipped_reason,
        observations={"count": 0, "unit": "daily_images"},
        extra={},
    )
    return result


def _renormalise_weights(
    weights: dict[str, float],
    present_keys: set[str],
) -> dict[str, float]:
    """Subset `weights` to `present_keys` and rescale to sum to 1.0.

    Returns an empty dict when no keys overlap; callers should treat that
    as "no aggregate computable" (i.e. result is None, not 0.0).
    """
    relevant = {k: v for k, v in weights.items() if k in present_keys}
    total = sum(relevant.values())
    if total == 0:
        return {}
    return {k: v / total for k, v in relevant.items()}


def _weighted_sum_strict(
    payload: dict, weights: dict[str, float],
) -> float | None:
    """Weighted sum over `weights` keys. If any key is missing or None in
    `payload`, return None — sub-aggregates should not produce a misleading
    partial result from incomplete inputs.
    """
    total = 0.0
    for key, weight in weights.items():
        value = payload.get(key)
        if value is None:
            return None
        total += weight * value
    return total


def _time_range_in_coverage(
    time_range: tuple[str, str],
    coverage_window: tuple[str, str] | None,
) -> bool:
    """Return True iff `time_range` overlaps `coverage_window`.

    `coverage_window=None` means "always available" → returns True.
    ISO date strings are lexicographically sortable so we don't need
    full date parsing here: two ranges (a_s, a_e) and (b_s, b_e) overlap
    iff a_s <= b_e AND b_s <= a_e. Used by run_pillar to skip ODIAC
    silently when the user's time_range is outside 2020-2023.
    """
    if coverage_window is None:
        return True
    user_start, user_end = time_range
    cov_start, cov_end = coverage_window
    return user_start <= cov_end and cov_start <= user_end


def _latest_coverage_year_window(
    coverage_window: tuple[str, str],
) -> tuple[str, str]:
    """Full-year window for the latest year of a coverage window.

    M-V1x-STANDING-WINDOW. Standing-exposure indicators (ODIAC) read their
    latest available year regardless of the user's analysis window — the
    audit §9.3 / M5.5b standing-exposure intent. e.g.
    ``("2020-01-01", "2023-12-31")`` → ``("2023-01-01", "2023-12-31")``.
    """
    latest_year = int(coverage_window[1][:4])
    return (f"{latest_year}-01-01", f"{latest_year}-12-31")


def _ghg_indicator_keys_from_selected(selected: set[str]) -> set[str]:
    """Map canonical IDs back to GHG indicator keys in GHG_INDICATOR_CONFIG.

    Accepts both `"ghg.<indicator>"` and `"ghg.<indicator>.<measurement>"`
    forms. Anything that doesn't resolve to a known indicator is ignored —
    the orchestrator validates selection upstream.
    """
    indicators: set[str] = set()
    for ind_id in selected:
        parts = ind_id.split(".")
        if (
            len(parts) >= 2
            and parts[0] == PILLAR_GHG
            and parts[1] in GHG_INDICATOR_CONFIG
        ):
            indicators.add(parts[1])
    return indicators
