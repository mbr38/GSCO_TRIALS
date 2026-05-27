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

from dataclasses import dataclass

import ee

from engine.constants import (
    ANOMALY_Z_THRESHOLD,
    CH4_NATIVE_SCALE_M,
    CO2_TO_C_RATIO,
    CORE_GHG_AUDIT_SUPPORT_WEIGHTS,
    GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS,
    GHG_FOLLOWUP_WEIGHTS,
    NORMALISATION_K,
)
from engine.core import (
    build_provenance,
    compute_anomaly_strength_term,
    compute_indicator_confidence,
    compute_n_valid_term,
    compute_qa_term,
    compute_spatial_context_term,
    six_step,
)
from engine.core.buffers import background_ring, site_buffer
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
        # Schema_v2 §3.1 — VIIRS NTL emits a reduced measurement set.
        # M-UI-A4: `.z` added so the C4b z-score-grammar severity tile can
        # read VIIRS's spatiotemporal anomaly magnitude. `z` was always
        # computed by six_step (z = anomaly / bg_std); it was previously
        # filtered out here. VIIRS still omits `.background`/`.hf`/`.trend_p`
        # — only the z used by the severity grammar is surfaced.
        emitted_measurements=(
            "site", "anomaly", "z", "trend", "confidence", "score",
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
    "anomaly":      "ghg.spatiotemporal_anomaly",
    "trend":        "ghg.trend",
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
    )

    return _format_result(indicator, cfg, raw, time_range)


def compute_ch4_snapshot(
    aoi: dict, time_range: tuple[str, str], mode: str, ee_client,
) -> dict:
    """CH₄ single-value snapshot — wrapper for explicit call sites."""
    return compute_ghg_indicator_snapshot(aoi, "ch4", time_range, mode, ee_client)


def compute_viirs_activity(
    aoi: dict, time_range: tuple[str, str], mode: str, ee_client,
) -> dict:
    """VIIRS NTL single-value snapshot — wrapper for explicit call sites."""
    return compute_ghg_indicator_snapshot(aoi, "viirs", time_range, mode, ee_client)


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
    # `n_months` is still read for the annualisation factor below and
    # surfaced in provenance. The historical "n_months == 0 → raise" guard
    # has been removed: run_pillar's M5.5c coverage_window check now skips
    # this function entirely for time ranges outside 2020-2023, so the
    # branch was dead code. If a future caller dispatches CO₂ outside its
    # coverage window without using run_pillar, the divide-by-zero in
    # `annualisation = 12.0 / n_months` will surface the bug loudly.
    n_months = int(ic.size().getInfo() or 0)

    site_geom = site_buffer(aoi["centre"], radius_km)
    # M-TIER-A3 Step B — background_ring returns a dict; extract geometry.
    ring_geom = background_ring(aoi["centre"], radius_km)["geometry"]

    # ODIAC b1 holds t C *per cell per month*; sum the cells inside the
    # buffer over time, divide by n_months and multiply by 12 to annualise,
    # then multiply by CO2_TO_C_RATIO to convert C → CO₂.
    # `ic.sum()` adds the months element-wise: sum_pixel = Σ_months tC.
    summed_image = ic.select(cfg.band).sum()

    # M-AIR-GHG-DEFENSIVE: materialise the reduceRegion dict first, then
    # use .get() with a None-aware fallback. The previous form
    # `reduceRegion(...).get(band).getInfo() or 0.0` relied on implicit
    # short-circuit when the band key was absent (empty buffer → None →
    # getInfo() returns None → falsy → 0.0); the explicit pattern below
    # is the same shape Nature uses (M-NATURE-DEFENSIVE) and crashes
    # loudly only on truly unexpected EE responses.
    site_sum_reduction = summed_image.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=site_geom,
        scale=cfg.scale_m,
        bestEffort=True,
        maxPixels=int(1e9),
    ).getInfo() or {}
    site_sum_t_c = float(site_sum_reduction.get(cfg.band) or 0.0)

    site_mean_reduction = summed_image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=site_geom,
        scale=cfg.scale_m,
        bestEffort=True,
        maxPixels=int(1e9),
    ).getInfo() or {}
    site_mean_t_c = float(site_mean_reduction.get(cfg.band) or 0.0)

    ring_mean_reduction = summed_image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=ring_geom,
        scale=cfg.scale_m,
        bestEffort=True,
        maxPixels=int(1e9),
    ).getInfo() or {}
    ring_mean_t_c = float(ring_mean_reduction.get(cfg.band) or 0.0)

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

_GHG_PER_INDICATOR_QA_KEYS: tuple[str, ...] = ("ch4", "co2", "viirs")


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
    """Schema_v2 §3.4 — fixed 1.0 placeholder.

    The real formula (IC_v4 §7.2) is the satellite-only proxy
    `0.5·isolation_from_no2 + 0.5·isolation_from_viirs`. Returning 1.0 in
    v1 over-states isolation in industrial corridors — acceptable v1 trade
    given Wind_Consistency is also deferred. Independent of A1 per spec §4.2.

    TODO(IC_v5): implement per §7.2 satellite-only proxy.
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
    return {
        "ghg.combustion_proxy": payload.get("air.industrial_combustion_proxy"),
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


def compute_ghg_spatiotemporal_anomaly(
    payload: dict, selected: set[str],
) -> dict:
    """IC_v4 §2.3 — mean of clamped z-scores across selected indicators.

    In v1 only CH₄ has a `.z` (VIIRS's reduced measurement set omits it).
    """
    contributions: list[float] = []
    for ind in _SINGLE_VALUE_INDICATORS:
        if make_id(PILLAR_GHG, ind, "score") not in selected:
            continue
        z = payload.get(make_id(PILLAR_GHG, ind, "z"))
        if z is None:
            continue
        contributions.append(min(max(z / NORMALISATION_K, 0.0), 1.0))
    if not contributions:
        return {"ghg.spatiotemporal_anomaly": None}
    return {
        "ghg.spatiotemporal_anomaly": sum(contributions) / len(contributions),
    }


def compute_ghg_trend(
    payload: dict, selected: set[str], mode: str,
) -> dict:
    """IC_v4 §2.3 — mean of per-indicator trend slopes.

    Zero in screening mode; computed in trend mode (None until M5+
    `engine/core/trend.py` lands).

    TODO(M5+): once trend.py exists, compute a meaningful mean in trend mode.
    """
    if mode == "screening":
        return {"ghg.trend": 0.0}
    trends: list[float] = []
    for ind in _SINGLE_VALUE_INDICATORS:
        if make_id(PILLAR_GHG, ind, "score") not in selected:
            continue
        trend = payload.get(make_id(PILLAR_GHG, ind, "trend"))
        if trend is None:
            continue
        trends.append(trend)
    if not trends:
        return {"ghg.trend": None}
    return {"ghg.trend": sum(trends) / len(trends)}

# Quality sub-scores aren't user-selectable — they're internal placeholders
# computed unconditionally by run_pillar. So we filter on presence, not on
# `selected`. Other pillar aggregates filter both.
def compute_ghg_data_quality_attribution(payload: dict) -> dict:
    """IC_v4 §2.3 — weighted sum per GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS
    over the four quality sub-scores. Missing terms renormalised."""
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

    `mode` is accepted for signature stability — mode-dependent
    behaviour lives upstream in ``compute_ghg_trend`` (0.0 in screening
    is a known v1 zero, not a missing value).

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

def run_pillar(
    aoi: dict,
    time_range: tuple[str, str],
    mode: str,
    selected_indicators: set[str],
    ee_client,
    *,
    accumulated_payload: dict | None = None,
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

    for ind_key in sorted(indicator_keys):
        cfg = GHG_INDICATOR_CONFIG[ind_key]

        # M-V1x-STANDING-WINDOW — a coverage_window marks a standing-exposure
        # indicator (ODIAC is the only one in v1). Such indicators read their
        # latest available year independent of the user's analysis window
        # (audit §9.3 / M5.5b standing-exposure intent), so present-day runs
        # surface the 2023 value rather than skipping. Live-window indicators
        # (CH₄, VIIRS) have no coverage_window → effective == user window.
        effective_time_range = (
            _latest_coverage_year_window(cfg.coverage_window)
            if cfg.coverage_window is not None
            else time_range
        )

        # M5.5c — skip silently when out of coverage. Retained as a safety
        # net for any future windowed indicator whose latest year still
        # can't satisfy the check; ODIAC's fixed latest-year window is always
        # in coverage, so it no longer hits this path. No `_failures` entry —
        # out-of-coverage is an expected case, not a failure.
        if not _time_range_in_coverage(effective_time_range, cfg.coverage_window):
            for measurement in cfg.emitted_measurements:
                payload[make_id(PILLAR_GHG, ind_key, measurement)] = None
            # M5.6 — canonical provenance even on the skip path. The
            # zero-count observations field tells reviewers explicitly
            # that no images were actually pulled. `observations.unit` is
            # ODIAC-specific today (it's the only indicator with a
            # coverage_window in v1); generalise when CH₄/VIIRS or other
            # indicators acquire windows.
            payload[f"_provenance.ghg.{ind_key}"] = build_provenance(
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
            continue

        attempted_keys.add(ind_key)

        try:
            # CO₂ has a bespoke ODIAC pipeline (inventory product, not a
            # column density), so it bypasses six_step. All other GHG
            # indicators flow through compute_ghg_indicator_snapshot.
            if ind_key == "co2":
                snapshot = compute_co2_snapshot(
                    aoi=aoi,
                    time_range=effective_time_range,    # fixed latest ODIAC year
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
                )
        # M-OCEAN-RING: silent-skip when the §0.2 ring lands over water /
        # outside asset coverage. CH₄ flows through six_step so it can
        # trip this; CO₂ uses its own ODIAC reduction (gated by
        # coverage_window) and won't. VIIRS goes through six_step too.
        except BackgroundRingNoDataError as err:
            payload.update(_emit_skipped_ghg_result(
                ind_key,
                time_range=time_range,
                skipped_reason="background_ring_no_data",
                reason_detail=err.reason,
            ))
        # M-AIR-GHG-DEFENSIVE: site buffer empty (e.g. Acre's deep-Amazon
        # AOI). Routed to the silent-skip payload with an asset-family
        # code (no_s5p_pixels for CH₄; no_viirs_pixels for VIIRS). Caught
        # before generic IndicatorComputeError because it's a subclass.
        except SiteBufferNoDataError as err:
            payload.update(_emit_skipped_ghg_result(
                ind_key,
                time_range=time_range,
                skipped_reason=cfg.skipped_reason_no_data,
                reason_detail=err.reason,
            ))
        except IndicatorComputeError as err:
            for measurement in cfg.emitted_measurements:
                payload[make_id(PILLAR_GHG, ind_key, measurement)] = None
            failures.append({
                "indicator":    ind_key,
                "indicator_id": err.indicator_id,
                "reason":       err.reason,
            })
        else:
            payload.update(snapshot)

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

    # Quality sub-scores — three derived from per-indicator A1 confidence
    # terms (in provenance.extra.confidence_terms); nearby_source_isolation
    # stays an independent §7.2 spatial proxy (placeholder pending wiring).
    payload.update(compute_temporal_coverage(payload))
    payload.update(compute_spatial_resolution_suitability(payload, aoi))
    payload.update(compute_retrieval_inventory_quality(payload))
    payload.update(compute_nearby_source_isolation(payload))

    # Sub-aggregates — dependency order: Air-borrowed first (so dependents
    # downstream see them), then CH₄-side, then the three CO₂-dependent
    # composites (activated in M5.5 once ODIAC is wired).
    payload.update(compute_combustion_proxy(payload))
    payload.update(compute_fire_or_regional_transport_risk(payload))
    payload.update(compute_ch4_hotspot_signal(payload))
    payload.update(compute_activity_score(payload))
    payload.update(compute_ch4_context_adjusted(payload))
    payload.update(compute_co2_context(payload))
    payload.update(compute_fossil_combustion_score(payload))
    payload.update(compute_activity_adjusted_co2(payload))

    # Pillar aggregates — augment `selected` so sub-aggregate IDs with
    # non-None values contribute to CORE_GHG_AUDIT_SUPPORT_WEIGHTS.
    augmented_selected: set[str] = set(selected_indicators)
    for sub_id in (
        "ghg.ch4_hotspot_signal",
        "ghg.combustion_proxy",
        "ghg.activity_score",
        "ghg.fire_or_regional_transport_risk",
        "ghg.ch4_context_adjusted",
        "ghg.co2_context",
        "ghg.fossil_combustion_score",
        "ghg.activity_adjusted_co2",
    ):
        if payload.get(sub_id) is not None:
            augmented_selected.add(sub_id)

    payload.update(compute_core_ghg_audit_support(payload, augmented_selected))
    payload.update(compute_ghg_spatiotemporal_anomaly(payload, augmented_selected))
    payload.update(compute_ghg_trend(payload, augmented_selected, mode))
    payload.update(compute_ghg_data_quality_attribution(payload))
    payload.update(compute_ghg_audit_followup_priority(payload, mode))

    # Strip the cross-pillar-injected keys — the orchestrator already has
    # Air's payload; GHG returns only its own pillar output.
    for key in injected_keys:
        payload.pop(key, None)

    if failures:
        payload["_failures"] = failures

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
