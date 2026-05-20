"""Nature/Land pillar — single-value indicators, sub-aggregates, and pillar
aggregates (Milestone 5b).

M5b — Nature pillar with KBA proximity, Dynamic World, habitat conversion,
Hansen forest loss, NDVI, and recovery signal. EVI deferred per IC_v4 §7.4.
FIRMS active-fire deferred to v1.x. Sector-aware habitat weighting deferred
(uniform DW class buckets per `engine/constants.py`). JRC Global Surface
Water deferred per GEE_Database_List §4.3 — water exposure uses Dynamic
World water + flooded_vegetation classes instead.

Layers (mirrors engine/air.py and engine/ghg.py architecture):
1. Single-value indicators (IC_v4 §3.1 / Schema_v2 §4.1) — seven functions:
   compute_kba_proximity, compute_current_land_cover, compute_habitat_conversion,
   compute_forest_loss, compute_ndvi_condition, compute_water_exposure,
   compute_recovery_signal. KBA + DW + Hansen + JRC use their own direct EE
   computations (no six-step). NDVI uses IC §0.2 six-step.
2. Sub-aggregates (IC_v4 §3.2 / Schema_v2 §4.9) — three exposure-side scores
   that feed the pillar follow-up priority: biodiversity_exposure,
   habitat.conversion_score, vegetation_condition.
3. Pillar aggregates (IC_v4 §3.3 / Schema_v2 §4.10) — two aggregates:
   nature.quality_attribution (six confidence sub-scores) and
   nature.followup_priority (the headline pillar score).
4. `run_pillar` — orchestrator entry point. Cross-pillar dependencies: none
   in v1; `accumulated_payload` is accepted for signature parity only.

Quality notes (v1 baseline):
- EVI is dropped from Vegetation_Condition per IC_v4 §7.4. The v1 rescaled
  weights live in `engine.constants.VEGETATION_CONDITION_WEIGHTS`.
- FIRMS active-fire detection is deferred to v1.x; the fire-multiplier on
  Recovery_Signal stays at the IC §3.2 default of 0.20 (no escalation to
  0.40 when fires are confirmed).
- Sector-aware habitat weighting is deferred. Uniform DW class buckets are
  used per `engine.constants.DW_NATURAL_CLASSES` / `DW_NON_NATURAL_CLASSES`.
- Several Nature_Quality_Attribution sub-scores are placeholders pending
  IC_v5 §6.3 (same TODO chain as Air's confidence).

TODOs deferred from this milestone:
- TODO(v1.x): wire FIRMS once IC_v5 §7.3 confirms the active-fire multiplier.
- TODO(IC_v5): replace placeholder quality sub-scores with real formulas.
- TODO(v1.x): supplier_spatial_link and external_driver_screening per IC §7.5.
- TODO(v1.x): JRC GSW long-term water mask once IC docs specify the lookback.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import ee

from engine.constants import (
    BIODIVERSITY_EXPOSURE_WEIGHTS,
    CONVERSION_SATURATION_PCT,
    DW_EXCLUDED_CLASSES,
    DW_NATURAL_CLASSES,
    DW_NON_NATURAL_CLASSES,
    DW_WATER_CLASS,
    HABITAT_BASELINE_YEARS,
    HABITAT_CONVERSION_WEIGHTS,
    KBA_DISTANCE_DECAY_KM,
    NATURE_FOLLOWUP_WEIGHTS,
    NATURE_QUALITY_ATTRIBUTION_WEIGHTS,
    NDVI_NEGATIVE_TREND_THRESHOLD,
    NORMALISATION_K,
    VEGETATION_CONDITION_WEIGHTS,
    WATER_FLOODED_VEG_SATURATION_PCT,
)
from engine.core import (
    adaptive_scale_m,
    build_provenance,
    method_note_fragment,
    six_step,
)
from engine.core.buffers import site_buffer
from engine.exceptions import IndicatorComputeError, PillarComputeError
from engine.ids import DW_CLASS_TO_ID_SLUG, PILLAR_NATURE


# ---------------------------------------------------------------------------
# Constants / per-indicator configuration  (IC_v4 §3.1 / Schema_v2 §4.1)
# ---------------------------------------------------------------------------

# KBA asset — uploaded under the GSCO project per the M5b prompt. The
# `…/current` alias from GEE_Database_List §4.2 is a separate asset under
# `projects/ee-kbas-in-gee/assets/current` and is the v1.x default once
# access is generalised; for M5b we point at the uploaded snapshot.
KBA_ASSET_ID: str = (
    "projects/supply-chain-observatory/assets/KBAsGlobal_2026_March_01_POL"
)

# Dynamic World 90-day mode composite window — IC §3.1 specifies a 90-day
# composite for "current land cover composition", balancing freshness against
# DW's per-image classification noise.
DW_COMPOSITE_WINDOW_DAYS: int = 90


@dataclass(frozen=True)
class NatureIndicatorConfig:
    """Static config for one Nature single-value indicator.

    `emitted_keys` constrains which canonical IDs the indicator's compute
    function returns — KBA emits a tiny vector-derived set, DW emits per-class
    fractions, NDVI emits the standard six-step measurement set, etc.

    `data_type` / `data_source` feed the M5.6 canonical provenance schema —
    see docs/provenance_schema.md. Nature has the most varied set of data
    types of any pillar (reference vector data, ML-classified rasters,
    direct satellite NDVI), so each indicator overrides the default.
    """

    asset_id: str
    scale_m: float
    # Display unit for the headline raw value (when applicable). KBA, DW
    # composition, and recovery signal don't have a single "headline" unit
    # so they leave this empty.
    display_unit: str = ""
    direction: str = "higher_is_worse"
    # Canonical IDs this indicator emits in the result payload. Used by the
    # config-integrity tests in tests/test_nature.py and by run_pillar's
    # failure-path to mark every affected ID as None.
    emitted_keys: tuple[str, ...] = field(default_factory=tuple)
    # M5.6 — provenance metadata. Defaults are placeholders to surface
    # config gaps loudly: an indicator that forgot to override will emit
    # a misleading "satellite_observation" tag, which fails the new
    # TestProvenanceShape assertions in tests/test_nature.py.
    data_type: str = "satellite_observation"
    data_source: str = ""


# IC_v4 §3.1 + Indicator_ID_Schema_v2.md §4 + GEE_Database_List §4.
NATURE_INDICATOR_CONFIG: dict[str, NatureIndicatorConfig] = {
    "kba": NatureIndicatorConfig(
        asset_id=KBA_ASSET_ID,
        scale_m=0.0,                 # Vector asset — no raster scale.
        emitted_keys=(
            "nature.kba.dist_km",
            "nature.kba.overlap_ha",
            "nature.kba.overlap_pct",
            "nature.kba.proximity_score",
        ),
        data_type="reference_dataset",
        data_source="BirdLife International (Key Biodiversity Areas)",
    ),
    "dw": NatureIndicatorConfig(
        asset_id="GOOGLE/DYNAMICWORLD/V1",
        scale_m=10.0,
        emitted_keys=tuple(
            f"nature.dw.{slug}_{meas}"
            for slug in DW_CLASS_TO_ID_SLUG.values()
            for meas in ("pct", "ha")
        ) + (
            "nature.dw.dominant_class",
            "nature.dw.class_confidence",
            "nature.sensitive_land_cover_presence",
            "nature.water_or_flooded_veg_exposure",
        ),
        data_type="ml_classified_satellite",
        data_source="Google / WRI (Dynamic World V1)",
    ),
    "habitat": NatureIndicatorConfig(
        asset_id="GOOGLE/DYNAMICWORLD/V1",
        scale_m=10.0,
        emitted_keys=(
            "nature.habitat.natural_loss_ha",
            "nature.habitat.natural_loss_pct",
            "nature.habitat.nat_to_built_ha",
            "nature.habitat.nat_to_bare_ha",
            "nature.habitat.nat_to_crop_ha",
            "nature.habitat.built_expansion_ha",
            "nature.habitat.bare_expansion_ha",
            "nature.habitat.annualised_rate",
        ),
        # Habitat conversion is derived from two DW composites; the
        # underlying classification asset is what the data_source field
        # documents (the derivation itself lives in method_note).
        data_type="ml_classified_satellite",
        data_source="Google / WRI (Dynamic World V1)",
    ),
    "forest_loss": NatureIndicatorConfig(
        asset_id="UMD/hansen/global_forest_change_2023_v1_11",
        scale_m=30.92,                # Hansen native pixel
        emitted_keys=(
            "nature.forest_loss.ha",
            "nature.forest_loss.pct",
        ),
        data_type="ml_classified_satellite",
        data_source="UMD / Hansen Global Forest Change",
    ),
    "ndvi": NatureIndicatorConfig(
        asset_id="MODIS/061/MOD13Q1",
        scale_m=250.0,
        direction="lower_is_worse",   # Declining NDVI = worse.
        emitted_keys=(
            "nature.ndvi.mean",
            "nature.ndvi.anomaly",
            "nature.ndvi.z",
            "nature.ndvi.slope",
            "nature.ndvi.slope_p",
            "nature.ndvi.score",
            "nature.low_ndvi.ha",
            "nature.low_ndvi.pct",
        ),
        data_type="satellite_observation",
        data_source="NASA MODIS (MOD13Q1)",
    ),
    "water": NatureIndicatorConfig(
        asset_id="GOOGLE/DYNAMICWORLD/V1",  # Per GEE §4.3 — DW replaces JRC GSW for v1.
        scale_m=10.0,
        emitted_keys=(
            "nature.water.area_now_ha",
            "nature.flooded_veg.area_now_ha",
        ),
        data_type="ml_classified_satellite",
        data_source="Google / WRI (Dynamic World V1)",
    ),
    "recovery": NatureIndicatorConfig(
        asset_id="MODIS/061/MOD13Q1",       # NDVI-trend-derived.
        scale_m=250.0,
        emitted_keys=(
            "nature.recovery.ndvi_improvement_pct",
            "nature.recovery.natural_cover_gain_ha",
            "nature.recovery.bare_reduction_ha",
            "nature.recovery.score",
        ),
        data_type="satellite_observation",
        data_source="NASA MODIS (MOD13Q1)",
    ),
}


_SINGLE_VALUE_INDICATORS: tuple[str, ...] = tuple(NATURE_INDICATOR_CONFIG.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _buffer_area_ha(radius_km: float) -> float:
    """Geodesic-circle area in hectares. π·r² with r in metres ÷ 10 000."""
    radius_m = radius_km * 1000.0
    return math.pi * radius_m * radius_m / 10000.0


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _renormalise_weights(
    weights: dict[str, float],
    present_keys: set[str],
) -> dict[str, float]:
    """Subset `weights` to `present_keys` and rescale to sum to 1.0.

    Returns an empty dict when no keys overlap; callers should treat that
    as "no aggregate computable" (i.e. result is None, not 0.0). Sign of
    each weight is preserved (Vegetation_Condition's −0.10 recovery term).
    """
    relevant = {k: v for k, v in weights.items() if k in present_keys}
    total = sum(abs(v) for v in relevant.values())
    if total == 0:
        return {}
    return {k: v / total for k, v in relevant.items()}


def _weighted_sum_strict(
    payload: dict,
    weights: dict[str, float],
) -> float | None:
    """Weighted sum over `weights` keys. Missing/None → return None."""
    total = 0.0
    for key, weight in weights.items():
        value = payload.get(key)
        if value is None:
            return None
        total += weight * value
    return total


def _nature_keys_from_selected(selected: set[str]) -> set[str]:
    """Map canonical IDs back to NATURE_INDICATOR_CONFIG keys.

    Each `nature.<indicator>.*` ID is mapped to its top-level indicator key
    in NATURE_INDICATOR_CONFIG. We use ID prefix matching against the
    emitted_keys of each config so canonical IDs like
    `nature.kba.proximity_score`, `nature.dw.trees_pct`, `nature.ndvi.score`,
    `nature.water.area_now_ha`, etc. all resolve to the right indicator.

    Anything outside the known set is ignored (the orchestrator validates
    selection upstream).
    """
    indicators: set[str] = set()
    for ind_id in selected:
        if not ind_id.startswith(f"{PILLAR_NATURE}."):
            continue
        for cfg_key, cfg in NATURE_INDICATOR_CONFIG.items():
            if ind_id in cfg.emitted_keys:
                indicators.add(cfg_key)
                break
        else:
            # `nature.low_ndvi.*` and `nature.flooded_veg.*` IDs live in
            # other configs' emitted_keys; the loop covers them.
            # Fall back to prefix-style match so e.g. `nature.ndvi.score`
            # selection routes to "ndvi" indicator even when the user passed
            # a short form like `nature.ndvi` without a measurement suffix.
            parts = ind_id.split(".")
            if len(parts) >= 2 and parts[1] in NATURE_INDICATOR_CONFIG:
                indicators.add(parts[1])
    return indicators


# ---------------------------------------------------------------------------
# Single-value indicators  (IC_v4 §3.1 / Schema_v2 §4.1)
# ---------------------------------------------------------------------------

def compute_kba_proximity(
    aoi: dict,
    time_range: tuple[str, str] | None = None,
    ee_client=None,                                     # noqa: ARG001 — parity
) -> dict:
    """Vector-based KBA proximity / overlap (IC_v4 §3.1 / Schema_v2 §4.1).

    `time_range` is accepted for provenance consistency only — KBA is
    reference vector data and doesn't vary with time. None defaults to
    a static-snapshot sentinel; the dispatcher in run_pillar passes the
    user's request window through so the provenance block documents the
    request context.

    Computes:
    - `nature.kba.dist_km`         — distance from the AOI centre to the
      nearest KBA polygon edge. 0 when the centre is inside a KBA.
    - `nature.kba.overlap_ha`      — Site_Buffer ∩ all KBA polygons.
    - `nature.kba.overlap_pct`     — overlap_ha / buffer_area_ha × 100.
    - `nature.kba.proximity_score` — `max(overlap_pct/100, exp(-dist_km/10))`
      per IC §3.2 sub-formula table.

    Raises:
        IndicatorComputeError: KBA asset cannot be loaded.
    """
    centre = aoi["centre"]
    radius_km = aoi["radius_km"]
    point = ee.Geometry.Point([centre["lon"], centre["lat"]])
    site = site_buffer(centre, radius_km)

    try:
        kbas = ee.FeatureCollection(KBA_ASSET_ID)
    except Exception as exc:                                # noqa: BLE001
        raise IndicatorComputeError(
            indicator_id="nature.kba",
            reason=f"KBA asset {KBA_ASSET_ID!r} not loadable: {exc!s}",
        ) from exc

    # Distance to nearest KBA. Server-side computation: filter to nearby
    # features (bounded by the site buffer), then use geometry.distance().
    nearby = kbas.filterBounds(site.buffer(50_000))  # 50 km search radius.
    n_nearby = int(nearby.size().getInfo() or 0)

    if n_nearby == 0:
        # No KBAs within 50 km of the buffer → score collapses to 0.0.
        return _format_kba_result(
            dist_km=50.0, overlap_ha=0.0, overlap_pct=0.0,
            time_range=time_range,
        )

    # Distance from the AOI centre point to the union of nearby KBA polygons.
    union_geom = nearby.geometry()
    dist_m = float(point.distance(union_geom, maxError=10.0).getInfo() or 0.0)
    dist_km = dist_m / 1000.0

    # Overlap (intersection area between buffer and KBA polygons).
    intersection = site.intersection(union_geom, maxError=10.0)
    overlap_m2 = float(intersection.area(maxError=10.0).getInfo() or 0.0)
    overlap_ha = overlap_m2 / 10000.0
    buffer_ha = _buffer_area_ha(radius_km)
    overlap_pct = (overlap_ha / buffer_ha * 100.0) if buffer_ha > 0 else 0.0

    return _format_kba_result(
        dist_km=dist_km, overlap_ha=overlap_ha, overlap_pct=overlap_pct,
        time_range=time_range,
    )


# M5.6 — sentinel "no time range applies" for static reference data. KBA
# polygons don't vary with time, but the canonical provenance schema
# requires `time_range`; we surface the user's request window when present
# and this sentinel otherwise so reviewers see explicitly that the field
# isn't a real lookup window.
_STATIC_SNAPSHOT_TIME_RANGE: tuple[str, str] = ("static", "static")


def _format_kba_result(
    dist_km: float,
    overlap_ha: float,
    overlap_pct: float,
    time_range: tuple[str, str] | None = None,
) -> dict:
    """IC §3.2 sub-formula: `max(overlap_pct/100, exp(-dist_km/decay))`.

    Centralised so `compute_kba_proximity` and tests share one mapping.
    `time_range` is documented in provenance only; KBA is reference data.
    """
    score = max(
        overlap_pct / 100.0,
        math.exp(-dist_km / KBA_DISTANCE_DECAY_KM),
    )
    cfg = NATURE_INDICATOR_CONFIG["kba"]
    effective_time_range = time_range if time_range is not None else _STATIC_SNAPSHOT_TIME_RANGE
    return {
        "nature.kba.dist_km":         dist_km,
        "nature.kba.overlap_ha":      overlap_ha,
        "nature.kba.overlap_pct":     overlap_pct,
        "nature.kba.proximity_score": _clamp01(score),
        "_provenance.nature.kba": build_provenance(
            asset_id=cfg.asset_id,
            band=None,
            data_type=cfg.data_type,
            data_source=cfg.data_source,
            native_scale_m=cfg.scale_m,
            time_range=effective_time_range,
            method_note=(
                "vector distance + buffer intersection; "
                f"score = max(overlap_pct/100, exp(-dist_km/{KBA_DISTANCE_DECAY_KM}))"
            ),
            observations={"count": 1, "unit": "static_snapshot"},
            extra={"distance_decay_km": KBA_DISTANCE_DECAY_KM},
        ),
    }


def compute_current_land_cover(
    aoi: dict,
    time_range: tuple[str, str],
    ee_client,                                          # noqa: ARG001 — parity
) -> dict:
    """Dynamic World 90-day mode composite over Site_Buffer (IC §3.1 / §3.2).

    Emits per-class hectares + percentages for all nine DW classes plus:
    - `nature.dw.dominant_class`              — name of the highest-fraction class.
    - `nature.dw.class_confidence`            — placeholder (see TODO).
    - `nature.sensitive_land_cover_presence`  — fraction of buffer that is
      natural / semi-natural (DW_NATURAL_CLASSES sum, capped at 1.0).
    - `nature.water_or_flooded_veg_exposure`  — `min((water + flooded_veg)
      pct / WATER_FLOODED_VEG_SATURATION_PCT, 1.0)` per IC §3.2.

    Raises IndicatorComputeError if the buffer is empty (zero valid pixels).
    """
    cfg = NATURE_INDICATOR_CONFIG["dw"]
    centre = aoi["centre"]
    radius_km = aoi["radius_km"]
    geom = site_buffer(centre, radius_km)
    buffer_ha = _buffer_area_ha(radius_km)

    ic = (
        ee.ImageCollection(cfg.asset_id)
        .filterDate(time_range[0], time_range[1])
        .filterBounds(geom)
    )

    # M-ADAPTIVE-SCALE: pick reduction scale based on AOI size.
    scale_m = adaptive_scale_m(geom, cfg.scale_m)

    # `label` is the per-pixel mode class index (0-8). frequencyHistogram
    # returns {class_index_str: pixel_count} which we map to slugs below.
    histogram = (
        ic.select("label")
        .mode()
        .reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=geom,
            scale=scale_m,
            bestEffort=True,
            maxPixels=int(1e9),
        )
        .get("label")
        .getInfo()
    )

    if not histogram:
        raise IndicatorComputeError(
            indicator_id="nature.dw",
            reason="Dynamic World buffer has no valid pixels in time_range",
        )

    counts = _normalise_dw_histogram(histogram)
    total = sum(counts.values()) or 1
    # Pixel-area arithmetic uses the *effective* scale so the per-class
    # hectare estimates reflect the reduction the engine actually ran.
    pixel_area_ha = (scale_m ** 2) / 10000.0

    result: dict = {}
    pct_per_class: dict[str, float] = {}
    for class_label, slug in DW_CLASS_TO_ID_SLUG.items():
        count = counts.get(class_label, 0)
        pct = count / total * 100.0
        ha = count * pixel_area_ha
        pct_per_class[class_label] = pct
        result[f"nature.dw.{slug}_pct"] = pct
        result[f"nature.dw.{slug}_ha"] = ha

    # Exclude DW_EXCLUDED_CLASSES from the dominant-class pick.
    eligible = {
        k: v for k, v in pct_per_class.items() if k not in DW_EXCLUDED_CLASSES
    }
    dominant = max(eligible, key=eligible.get) if eligible else None

    result["nature.dw.dominant_class"] = dominant
    # TODO(IC_v5): class_confidence is `mean(prob_<dominant>)` over the
    # buffer. Placeholder uses the dominant class's pixel fraction in [0,1]
    # which is a defensible proxy until we wire the probability bands.
    result["nature.dw.class_confidence"] = (
        eligible[dominant] / 100.0 if dominant else None
    )

    # Sub-scores derived from the class fractions.
    natural_pct = sum(pct_per_class.get(c, 0.0) for c in DW_NATURAL_CLASSES)
    water_like_pct = pct_per_class.get(DW_WATER_CLASS, 0.0)
    water_like_pct += pct_per_class.get("flooded_vegetation", 0.0)

    result["nature.sensitive_land_cover_presence"] = _clamp01(natural_pct / 100.0)
    result["nature.water_or_flooded_veg_exposure"] = _clamp01(
        water_like_pct / WATER_FLOODED_VEG_SATURATION_PCT,
    )

    result["_provenance.nature.dw"] = build_provenance(
        asset_id=cfg.asset_id,
        band="label",
        data_type=cfg.data_type,
        data_source=cfg.data_source,
        native_scale_m=cfg.scale_m,
        time_range=time_range,
        method_note=(
            "DW 90-day mode composite; class fractions via frequencyHistogram; "
            f"{method_note_fragment(scale_m, cfg.scale_m)}"
        ),
        observations=None,  # TODO(v1.x): track DW image count from filterBounds().
        extra={"composite_window_days": DW_COMPOSITE_WINDOW_DAYS},
    )
    return result


def _normalise_dw_histogram(histogram: dict) -> dict[str, int]:
    """Convert {class_index_str: count} into {dw_class_label: count}.

    `histogram` keys come back from EE as stringified integers ("0".."8").
    The Dynamic World class order is documented in the asset: water=0,
    trees=1, grass=2, flooded_vegetation=3, crops=4, shrub_and_scrub=5,
    built=6, bare=7, snow_and_ice=8.
    """
    dw_index_to_label = (
        "water",
        "trees",
        "grass",
        "flooded_vegetation",
        "crops",
        "shrub_and_scrub",
        "built",
        "bare",
        "snow_and_ice",
    )
    out: dict[str, int] = {}
    for key, count in histogram.items():
        try:
            idx = int(key)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(dw_index_to_label):
            out[dw_index_to_label[idx]] = int(count or 0)
    return out


def compute_habitat_conversion(
    aoi: dict,
    time_range: tuple[str, str],
    ee_client,                                          # noqa: ARG001 — parity
) -> dict:
    """Habitat conversion: baseline vs current DW composition (IC §3.1 / §3.2).

    Baseline window is HABITAT_BASELINE_YEARS years before time_range[0]
    (Schema_v2 §4.3). Reports natural→non-natural transitions:
    `natural_loss_*`, `nat_to_built_*`, `nat_to_bare_*`, `nat_to_crop_*`,
    plus annualised rate.

    v1 approximation: rather than reducing per-pixel transitions (which is
    EE-expensive for global DW), we compare buffer-level natural / built /
    bare / crop fractions between the two windows and treat the *decrease*
    in natural-class fraction as the "natural loss" signal. Sub-totals
    (nat_to_built etc.) are apportioned by the *increase* in each
    non-natural class. This is a v1 demo-grade signal — full per-pixel
    transition mapping is a v1.x improvement.
    """
    cfg = NATURE_INDICATOR_CONFIG["habitat"]
    centre = aoi["centre"]
    radius_km = aoi["radius_km"]
    geom = site_buffer(centre, radius_km)
    buffer_ha = _buffer_area_ha(radius_km)

    start_year = int(time_range[0][:4])
    end_year = int(time_range[1][:4])
    # Baseline window mirrors the current window's day-of-year span exactly,
    # just shifted by HABITAT_BASELINE_YEARS — so a 90-day current window
    # compares against a 90-day baseline window five years earlier. Year
    # offset between the two endpoints is preserved so a Nov→Feb window
    # still maps to Nov→Feb in the baseline.
    baseline_start = f"{start_year - HABITAT_BASELINE_YEARS}-{time_range[0][5:]}"
    baseline_end = f"{end_year - HABITAT_BASELINE_YEARS}-{time_range[1][5:]}"

    # M-ADAPTIVE-SCALE: pick reduction scale based on AOI size. Both window
    # reductions reduce over the same geometry, so one helper call suffices.
    scale_m = adaptive_scale_m(geom, cfg.scale_m)

    current_hist = _dw_mode_histogram(
        cfg.asset_id, geom, time_range, scale_m=scale_m,
    )
    baseline_hist = _dw_mode_histogram(
        cfg.asset_id, geom, (baseline_start, baseline_end), scale_m=scale_m,
    )

    current_pct = _class_pct(current_hist)
    baseline_pct = _class_pct(baseline_hist)
    pixel_area_ha = (scale_m ** 2) / 10000.0  # noqa: F841 — parity with compute_current_land_cover.

    def _delta(class_label: str) -> float:
        return current_pct.get(class_label, 0.0) - baseline_pct.get(class_label, 0.0)

    current_natural = sum(current_pct.get(c, 0.0) for c in DW_NATURAL_CLASSES)
    baseline_natural = sum(baseline_pct.get(c, 0.0) for c in DW_NATURAL_CLASSES)
    natural_loss_pct = max(0.0, baseline_natural - current_natural)
    natural_loss_ha = natural_loss_pct / 100.0 * buffer_ha

    def _attribute(class_label: str) -> tuple[float, float]:
        increase_pct = max(0.0, _delta(class_label))
        ha = increase_pct / 100.0 * buffer_ha
        return ha, increase_pct

    nat_to_built_ha, _ = _attribute("built")
    nat_to_bare_ha, _ = _attribute("bare")
    nat_to_crop_ha, _ = _attribute("crops")

    built_expansion_ha = max(0.0, _delta("built")) / 100.0 * buffer_ha
    bare_expansion_ha = max(0.0, _delta("bare")) / 100.0 * buffer_ha

    annualised_rate_ha_per_yr = natural_loss_ha / HABITAT_BASELINE_YEARS

    return {
        "nature.habitat.natural_loss_ha":     natural_loss_ha,
        "nature.habitat.natural_loss_pct":    natural_loss_pct,
        "nature.habitat.nat_to_built_ha":     nat_to_built_ha,
        "nature.habitat.nat_to_bare_ha":      nat_to_bare_ha,
        "nature.habitat.nat_to_crop_ha":      nat_to_crop_ha,
        "nature.habitat.built_expansion_ha":  built_expansion_ha,
        "nature.habitat.bare_expansion_ha":   bare_expansion_ha,
        "nature.habitat.annualised_rate":     annualised_rate_ha_per_yr,
        "_provenance.nature.habitat": build_provenance(
            asset_id=cfg.asset_id,
            band="label",
            data_type=cfg.data_type,
            data_source=cfg.data_source,
            native_scale_m=cfg.scale_m,
            time_range=time_range,
            method_note=(
                f"DW mode composite (current vs baseline {HABITAT_BASELINE_YEARS}y "
                "earlier); class-fraction deltas → natural→non-natural attribution; "
                f"{method_note_fragment(scale_m, cfg.scale_m)}"
            ),
            observations=None,  # TODO(v1.x): track DW image count per window.
            extra={
                "baseline_time_range": (baseline_start, baseline_end),
                "baseline_years":      HABITAT_BASELINE_YEARS,
                "conversion_saturation_pct": CONVERSION_SATURATION_PCT,
            },
        ),
    }


def _dw_mode_histogram(
    asset_id: str,
    geom: ee.Geometry,
    time_range: tuple[str, str],
    scale_m: float,
) -> dict[str, int]:
    """Reduce a DW mode-composite to a {class_label: pixel_count} dict.

    Helper for compute_habitat_conversion (which needs two of these — one
    per window). Falls back to an empty dict when the window has no images.
    """
    ic = (
        ee.ImageCollection(asset_id)
        .filterDate(time_range[0], time_range[1])
        .filterBounds(geom)
    )
    if (ic.size().getInfo() or 0) == 0:
        return {}
    histogram = (
        ic.select("label")
        .mode()
        .reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=geom,
            scale=scale_m,
            bestEffort=True,
            maxPixels=int(1e9),
        )
        .get("label")
        .getInfo()
    )
    return _normalise_dw_histogram(histogram or {})


def _class_pct(hist: dict[str, int]) -> dict[str, float]:
    """Convert pixel-count histogram into class-fraction percentages."""
    total = sum(hist.values()) or 1
    return {k: v / total * 100.0 for k, v in hist.items()}


def compute_forest_loss(
    aoi: dict,
    time_range: tuple[str, str],
    ee_client,                                          # noqa: ARG001 — parity
) -> dict:
    """Hansen Global Forest Change loss within Site_Buffer (Schema_v2 §4.4).

    Returns hectares lost and percentage of buffer affected, restricted to
    Hansen lossyear values that fall in `time_range`. Hansen's lossyear band
    encodes year as years-since-2000 (so 23 = 2023).
    """
    cfg = NATURE_INDICATOR_CONFIG["forest_loss"]
    centre = aoi["centre"]
    radius_km = aoi["radius_km"]
    geom = site_buffer(centre, radius_km)
    buffer_ha = _buffer_area_ha(radius_km)

    start_yr_offset = int(time_range[0][:4]) - 2000
    end_yr_offset = int(time_range[1][:4]) - 2000

    image = ee.Image(cfg.asset_id).select("lossyear")
    loss_mask = image.gte(start_yr_offset).And(image.lte(end_yr_offset))

    # M-ADAPTIVE-SCALE: pick reduction scale based on AOI size.
    scale_m = adaptive_scale_m(geom, cfg.scale_m)

    area_image = loss_mask.multiply(ee.Image.pixelArea())
    area_m2 = (
        area_image.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geom,
            scale=scale_m,
            bestEffort=True,
            maxPixels=int(1e9),
        )
        .get("lossyear")
        .getInfo()
    )
    ha = float(area_m2 or 0.0) / 10000.0
    pct = (ha / buffer_ha * 100.0) if buffer_ha > 0 else 0.0
    return {
        "nature.forest_loss.ha":  ha,
        "nature.forest_loss.pct": pct,
        "_provenance.nature.forest_loss": build_provenance(
            asset_id=cfg.asset_id,
            band="lossyear",
            data_type=cfg.data_type,
            data_source=cfg.data_source,
            native_scale_m=cfg.scale_m,
            time_range=time_range,
            method_note=(
                "Hansen lossyear band; pixels with lossyear in time_range "
                "weighted by ee.Image.pixelArea(); "
                f"{method_note_fragment(scale_m, cfg.scale_m)}"
            ),
            observations={"count": 1, "unit": "annual_rasters"},
            extra={},
        ),
    }


def compute_ndvi_condition(
    aoi: dict,
    time_range: tuple[str, str],
    mode: str,                                          # noqa: ARG001 — parity
    ee_client,
) -> dict:
    """NDVI six-step pipeline on MOD13Q1 (IC §3.1, Schema_v2 §4.5).

    Direction is "lower_is_worse" — declining NDVI is bad. `to_score` inverts
    the sign so the result is still in [0, 1] with higher = worse.

    Also derives:
    - `nature.ndvi.inverted_anomaly` — clamp((bg − site) / (3·σ), 0, 1).
    - `nature.ndvi.negative_trend`   — clamp(−slope / threshold, 0, 1).
    - `nature.low_ndvi.pct`          — % pixels with NDVI < 0.3 (IC §3.1).
    - `nature.low_ndvi.pct_norm`     — clamp(pct / 100, 0, 1) for the
      vegetation_condition aggregate.
    """
    cfg = NATURE_INDICATOR_CONFIG["ndvi"]
    radius_km = aoi["radius_km"]
    if cfg.scale_m > radius_km * 1000:
        raise IndicatorComputeError(
            indicator_id="nature.ndvi",
            reason=(
                f"site buffer ({radius_km} km) smaller than NDVI "
                f"native pixel ({cfg.scale_m / 1000:.1f} km)"
            ),
        )

    # MOD13Q1 NDVI native scaling is ×10000. Bring it to physical NDVI
    # [-1, 1] before reducing so anomaly / z thresholds are interpretable.
    ic = (
        ee.ImageCollection(cfg.asset_id)
        .select("NDVI")
        .map(lambda img: (
            img.multiply(0.0001)
               .rename("NDVI")
               .copyProperties(img, ["system:time_start", "system:time_end"])
        ))
    )

    # M-ADAPTIVE-SCALE: pick reduction scale based on AOI size. MODIS NDVI
    # is already coarse (250 m) so adaptive only kicks in at region scale.
    geom_for_scale = site_buffer(aoi["centre"], radius_km)
    scale_m = adaptive_scale_m(geom_for_scale, cfg.scale_m)

    raw = six_step(
        aoi=aoi,
        image_collection=ic,
        band="NDVI",
        time_range=time_range,
        ee_client=ee_client,
        direction=cfg.direction,
        indicator_id="nature.ndvi",
        scale=scale_m,
    )

    inverted_anomaly = _ndvi_inverted_anomaly(raw)
    negative_trend = _ndvi_negative_trend(raw.get("trend"))
    low_ndvi_pct = _ndvi_low_area_pct(aoi, ic, time_range, scale_m)
    low_ndvi_ha = low_ndvi_pct / 100.0 * _buffer_area_ha(radius_km)
    low_ndvi_pct_norm = _clamp01(low_ndvi_pct / 100.0)

    return {
        "nature.ndvi.mean":             raw.get("site"),
        "nature.ndvi.anomaly":          raw.get("anomaly"),
        "nature.ndvi.z":                raw.get("z"),
        "nature.ndvi.slope":            raw.get("trend"),
        "nature.ndvi.slope_p":          raw.get("trend_p"),
        "nature.ndvi.score":            raw.get("score"),
        "nature.ndvi.inverted_anomaly": inverted_anomaly,
        "nature.ndvi.negative_trend":   negative_trend,
        "nature.low_ndvi.ha":           low_ndvi_ha,
        "nature.low_ndvi.pct":          low_ndvi_pct,
        "nature.low_ndvi.pct_norm":     low_ndvi_pct_norm,
        "_provenance.nature.ndvi": build_provenance(
            asset_id=cfg.asset_id,
            band="NDVI",
            data_type=cfg.data_type,
            data_source=cfg.data_source,
            native_scale_m=cfg.scale_m,
            time_range=time_range,
            method_note=(
                "MOD13Q1 NDVI ÷ 10000; IC §0.2 six-step pipeline with "
                f"direction={cfg.direction!r} (lower NDVI = worse); "
                f"{method_note_fragment(scale_m, cfg.scale_m)}"
            ),
            observations={"count": 1, "unit": "16day_composites"},
            extra={
                "ndvi_negative_trend_threshold": NDVI_NEGATIVE_TREND_THRESHOLD,
            },
        ),
    }


def _ndvi_inverted_anomaly(raw: dict) -> float | None:
    """IC §3.2 sub-formula: `clamp((NDVI_bg − NDVI_site) / (3·σ_bg), 0, 1)`.

    Inverted because lower NDVI is worse. Caps at 3·σ (≈ 99th percentile).
    The `score` from `six_step` already encodes this (direction='lower_is_worse'
    inverts the sign before clamping with k=NORMALISATION_K=3), so we surface
    it under the IC §3.2 name.
    """
    return raw.get("score")


def _ndvi_negative_trend(slope: float | None) -> float | None:
    """IC §3.2 sub-formula: `clamp(−slope / |threshold|, 0, 1)`.

    `NDVI_NEGATIVE_TREND_THRESHOLD = −0.01 NDVI/yr` is stored as a signed
    constant so its sign documents the direction (negative = decline). The
    sub-formula treats it as a magnitude, so we divide by `abs(threshold)`:
    a slope at −0.01 NDVI/yr saturates to 1.0; a positive slope (greening)
    clamps to 0. Returns None when slope is unavailable (M5+ trend wiring).
    """
    if slope is None:
        return None
    return _clamp01(-slope / abs(NDVI_NEGATIVE_TREND_THRESHOLD))


def _ndvi_low_area_pct(
    aoi: dict,
    ic: ee.ImageCollection,
    time_range: tuple[str, str],
    scale_m: float,
) -> float:
    """% of buffer pixels with mean NDVI below 0.3 (IC §3.1)."""
    geom = site_buffer(aoi["centre"], aoi["radius_km"])
    mean_image = ic.filterDate(time_range[0], time_range[1]).mean()
    low_mask = mean_image.lt(0.3)
    fractions = (
        low_mask.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=scale_m,
            bestEffort=True,
            maxPixels=int(1e9),
        )
        .get("NDVI")
        .getInfo()
    )
    return float(fractions or 0.0) * 100.0


def compute_water_exposure(
    aoi: dict,
    time_range: tuple[str, str],
    ee_client,                                          # noqa: ARG001 — parity
) -> dict:
    """Water + flooded-vegetation exposure from Dynamic World (Schema_v2 §4.6).

    Per GEE §4.3, JRC GSW is *not* live in GEE — v1 uses Dynamic World's
    `water` and `flooded_vegetation` classes for "current water exposure".
    The `nature.water_or_flooded_veg_exposure` sub-score is emitted by
    `compute_current_land_cover`; this function emits the raw areas only.
    """
    cfg = NATURE_INDICATOR_CONFIG["water"]
    centre = aoi["centre"]
    radius_km = aoi["radius_km"]
    geom = site_buffer(centre, radius_km)

    # M-ADAPTIVE-SCALE: pick reduction scale based on AOI size.
    scale_m = adaptive_scale_m(geom, cfg.scale_m)
    # Pixel-area arithmetic uses the *effective* scale so hectare estimates
    # reflect the reduction the engine actually ran.
    pixel_area_ha = (scale_m ** 2) / 10000.0

    ic = (
        ee.ImageCollection(cfg.asset_id)
        .filterDate(time_range[0], time_range[1])
        .filterBounds(geom)
    )
    histogram = (
        ic.select("label")
        .mode()
        .reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=geom,
            scale=scale_m,
            bestEffort=True,
            maxPixels=int(1e9),
        )
        .get("label")
        .getInfo()
    )
    counts = _normalise_dw_histogram(histogram or {})
    water_ha = counts.get(DW_WATER_CLASS, 0) * pixel_area_ha
    flooded_ha = counts.get("flooded_vegetation", 0) * pixel_area_ha
    return {
        "nature.water.area_now_ha":        water_ha,
        "nature.flooded_veg.area_now_ha":  flooded_ha,
        "_provenance.nature.water": build_provenance(
            asset_id=cfg.asset_id,
            band="label",
            data_type=cfg.data_type,
            data_source=cfg.data_source,
            native_scale_m=cfg.scale_m,
            time_range=time_range,
            method_note=(
                "DW water + flooded_vegetation pixel counts via "
                "frequencyHistogram (JRC GSW deferred per GEE §4.3); "
                f"{method_note_fragment(scale_m, cfg.scale_m)}"
            ),
            observations=None,  # TODO(v1.x): track DW image count.
            extra={},
        ),
    }


def compute_recovery_signal(
    aoi: dict,                                          # noqa: ARG001 — radius unused
    time_range: tuple[str, str],
    ee_client,                                          # noqa: ARG001 — parity
) -> dict:
    """Recovery signal (Schema_v2 §4.7 / IC §3.2 sub-formula).

    Two positive signals combined:
    1. Fraction of buffer with significant positive NDVI trend.
    2. Fraction transitioned non-natural → natural.

    Returned as the IC §3.2 sub-score `min(ndvi_improvement_pct/100 +
    natural_cover_gain_pct/100, 1.0)`. FIRMS-confirmed fires are deferred
    to v1.x — the 0.20 IC §3.2 fire-multiplier stays at its default.

    Implementation note: v1 returns `nature.recovery.score = 0.0` as the
    "no recovery detected" baseline so the Vegetation_Condition aggregate
    can still compute through the −0.10 weight on this term. Raw `_pct` /
    `_ha` fields are None until per-pixel trend mapping lands.
    """
    cfg = NATURE_INDICATOR_CONFIG["recovery"]
    return {
        "nature.recovery.ndvi_improvement_pct": None,
        "nature.recovery.natural_cover_gain_ha": None,
        "nature.recovery.bare_reduction_ha":     None,
        "nature.recovery.score":                 0.0,
        "_provenance.nature.recovery": build_provenance(
            asset_id=cfg.asset_id,
            band="NDVI",
            data_type=cfg.data_type,
            data_source=cfg.data_source,
            native_scale_m=cfg.scale_m,
            time_range=time_range,
            method_note=(
                "v1 placeholder — score=0.0 baseline; wires once "
                "engine/core/trend.py lands per-pixel NDVI improvement and "
                "natural-cover-gain attribution"
            ),
            observations=None,
            extra={"placeholder": True},
        ),
    }


# ---------------------------------------------------------------------------
# Habitat-conversion helper sub-scores  (IC §3.2 calibration)
# ---------------------------------------------------------------------------

def _conversion_pct_norm(payload: dict, *, ha_key: str, buffer_ha: float) -> float | None:
    """`clamp(loss_fraction / CONVERSION_SATURATION_PCT, 0, 1)` per IC §3.2.

    `loss_fraction` is the area in `ha_key` divided by the buffer area
    (`buffer_ha`). The pct_norm value treats CONVERSION_SATURATION_PCT
    fraction (10 % buffer conversion by default) as "fully concerning".
    """
    value = payload.get(ha_key)
    if value is None or buffer_ha <= 0:
        return None
    loss_fraction = value / buffer_ha
    return _clamp01(loss_fraction / CONVERSION_SATURATION_PCT)


def _augment_habitat_pct_norms(payload: dict, buffer_ha: float) -> dict:
    """Inject the four `*_pct_norm` keys consumed by HABITAT_CONVERSION_WEIGHTS.

    The pct_norm form is documented in IC §3.2's calibration note: pass each
    `_ha` term through `clamp(ha / buffer_ha / saturation, 0, 1)` before
    multiplying by its weight in `compute_habitat_conversion_score`.
    """
    return {
        "nature.habitat.natural_loss_pct_norm": _conversion_pct_norm(
            payload, ha_key="nature.habitat.natural_loss_ha", buffer_ha=buffer_ha,
        ),
        "nature.habitat.nat_to_built_pct_norm": _conversion_pct_norm(
            payload, ha_key="nature.habitat.nat_to_built_ha", buffer_ha=buffer_ha,
        ),
        "nature.habitat.nat_to_bare_pct_norm": _conversion_pct_norm(
            payload, ha_key="nature.habitat.nat_to_bare_ha", buffer_ha=buffer_ha,
        ),
        "nature.forest_loss.pct_norm": _conversion_pct_norm(
            payload, ha_key="nature.forest_loss.ha", buffer_ha=buffer_ha,
        ),
        # IC §3.2 — annualised_rate_score normalises the per-year loss to the
        # same saturation point: ha/yr → fraction/yr → /SATURATION.
        "nature.habitat.annualised_rate_score": (
            _clamp01(
                (payload["nature.habitat.annualised_rate"] / buffer_ha)
                / CONVERSION_SATURATION_PCT,
            )
            if payload.get("nature.habitat.annualised_rate") is not None
            and buffer_ha > 0
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Sub-aggregates  (IC_v4 §3.2 / Schema_v2 §4.9)
# ---------------------------------------------------------------------------

def compute_biodiversity_exposure(payload: dict) -> dict:
    """IC §3.2 — weighted sum of KBA + sensitive land cover + water exposure.

    Buffer_Sensitivity_v1 is 0 in v1 (no sector context); the surviving
    three weights are rescaled by 1/0.90 inside
    `engine.constants.BIODIVERSITY_EXPOSURE_WEIGHTS`. Strict null
    propagation: any missing dependency makes the aggregate None.
    """
    return {
        "nature.biodiversity_exposure": _weighted_sum_strict(
            payload, BIODIVERSITY_EXPOSURE_WEIGHTS,
        ),
    }


def compute_habitat_conversion_score(payload: dict) -> dict:
    """IC §3.2 — Habitat_Conversion weighted sum.

    Consumes the four `*_pct_norm` keys plus `annualised_rate_score` from
    `_augment_habitat_pct_norms`. Strict null propagation.
    """
    return {
        "nature.habitat.conversion_score": _weighted_sum_strict(
            payload, HABITAT_CONVERSION_WEIGHTS,
        ),
    }


def compute_vegetation_condition(payload: dict) -> dict:
    """IC §3.2 §7.4 — Vegetation_Condition_v1 (EVI removed, weights rescaled).

    `0.45·Inverted_NDVI_anomaly + 0.25·Negative_Vegetation_Trend
    + 0.20·Low_Vegetation_Area_pct − 0.10·Recovery_Signal`, clamped to [0, 1].

    Strict null propagation; clamps the final result so that an unusually
    large recovery signal can't drive the aggregate below 0.
    """
    raw = _weighted_sum_strict(payload, VEGETATION_CONDITION_WEIGHTS)
    if raw is None:
        return {"nature.vegetation_condition": None}
    return {"nature.vegetation_condition": _clamp01(raw)}


# ---------------------------------------------------------------------------
# Quality-attribution sub-scores  (IC §3.3 / Schema_v2 §4.8 — placeholders)
# ---------------------------------------------------------------------------

def compute_nature_quality_sub_scores(payload: dict, aoi: dict) -> dict:
    """The six IC §3.3 confidence-side sub-scores. v1 uses placeholders for
    five of the six (the sixth, `dw.class_confidence`, is already produced
    by `compute_current_land_cover`).

    TODO(IC_v5): replace placeholders with real formulas — Valid_Pixel_Coverage
    from masked count over total, Cloud_or_Observation_Quality from SCL,
    Seasonal_Comparability from month-offset, and §7.5 for the supplier link
    and external driver checks.
    """
    return {
        # Placeholder: fraction-of-expected-observations proxy. For now we
        # echo dw.class_confidence (it's our highest-fidelity confidence
        # signal until the real per-indicator coverage formula lands).
        "nature.valid_pixel_coverage":      payload.get("nature.dw.class_confidence"),
        # Cloud / SCL not wired in v1; fix to 0.8 as a defensible placeholder.
        "nature.cloud_observation_quality": 0.8,
        # `nature.dw.class_confidence` is already set by compute_current_land_cover.
        # We don't redefine it here so that the DW-emitted value flows through.
        # Seasonal_Comparability: 1.0 if user-selected window matches a 90-day
        # bracket cleanly; placeholder 1.0 until the month-offset calc lands.
        "nature.seasonal_comparability":    1.0,
        # §7.5 placeholders.
        "nature.supplier_spatial_link":     0.7,
        "nature.external_driver_screening": 1.0,
    }


# ---------------------------------------------------------------------------
# Pillar aggregates  (IC_v4 §3.3 / Schema_v2 §4.10)
# ---------------------------------------------------------------------------

def compute_nature_quality_attribution(payload: dict) -> dict:
    """IC §3.3 — weighted sum of the six confidence-side sub-scores.

    Missing terms renormalised. Returns None if every term is None.
    """
    candidates = {
        k: payload[k] for k in NATURE_QUALITY_ATTRIBUTION_WEIGHTS
        if payload.get(k) is not None
    }
    if not candidates:
        return {"nature.quality_attribution": None}
    weights = _renormalise_weights(
        NATURE_QUALITY_ATTRIBUTION_WEIGHTS, set(candidates),
    )
    score = sum(weights[k] * candidates[k] for k in candidates)
    return {"nature.quality_attribution": score}


# Maps NATURE_FOLLOWUP_WEIGHTS keys to canonical payload IDs.
_FOLLOWUP_TERM_TO_ID: dict[str, str] = {
    "biodiversity_exposure": "nature.biodiversity_exposure",
    "habitat_conversion":    "nature.habitat.conversion_score",
    "vegetation_condition":  "nature.vegetation_condition",
    "quality_attribution":   "nature.quality_attribution",
}


def compute_nature_followup_priority(
    payload: dict,
    mode: str,                                          # noqa: ARG001 — parity
) -> dict:
    """IC §3.3 — Nature_FollowUp_Priority weighted sum.

    Per `Engine_Module_Skeleton §3.2` Nature has no separate trend term
    (PLFS §10 H13), so the `mode` arg is accepted for signature parity but
    not used. Missing terms renormalised.
    """
    candidates: dict[str, float] = {}
    for term in NATURE_FOLLOWUP_WEIGHTS:
        value = payload.get(_FOLLOWUP_TERM_TO_ID[term])
        if value is None:
            continue
        candidates[term] = value
    if not candidates:
        return {"nature.followup_priority": None}
    weights = _renormalise_weights(NATURE_FOLLOWUP_WEIGHTS, set(candidates))
    score = sum(weights[t] * candidates[t] for t in candidates)
    return {"nature.followup_priority": score}


def compute_nature_spatiotemporal_anomaly(payload: dict) -> dict:
    """Schema_v2 §4.10 hint — mean of clamped z-scores across Nature
    indicators. In v1 only NDVI carries a z value (KBA, DW, Hansen don't).

    Not part of NATURE_FOLLOWUP_WEIGHTS, but exposed for downstream UI
    parity with Air's `air.spatiotemporal_anomaly_score`.
    """
    z = payload.get("nature.ndvi.z")
    if z is None:
        return {"nature.spatiotemporal_anomaly_score": None}
    return {
        "nature.spatiotemporal_anomaly_score": _clamp01(z / NORMALISATION_K),
    }


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
    accumulated_payload: dict | None = None,  # noqa: ARG001 — Nature has no cross-pillar borrows
) -> dict:
    """Compute every selected Nature indicator + sub-aggregates + pillar aggregates.

    `accumulated_payload` is accepted for orchestrator signature parity but
    unused — Nature is self-contained in v1.

    Logic:
    1. Resolve `selected_indicators` to a set of Nature indicator keys.
    2. For each indicator, call its `compute_*` function in dependency order
       (KBA → DW → habitat → forest_loss → NDVI → water → recovery).
       Per-indicator failures degrade gracefully — the affected IDs go to
       None in the payload and the failure is recorded in `_failures`.
    3. Augment habitat payload with `*_pct_norm` keys before aggregation.
    4. Compute the three sub-aggregates (strict null-propagation each).
    5. Compute placeholder quality sub-scores and the two pillar aggregates.
    6. Return the merged payload.

    Raises `PillarComputeError` if every selected Nature indicator fails.
    """
    indicator_keys = _nature_keys_from_selected(selected_indicators)
    payload: dict = {}
    failures: list[dict] = []

    # Sequential dispatch — the dict ordering here is the authoritative
    # compute order for Nature (KBA → DW → habitat → forest → NDVI → water → recovery).
    dispatch = {
        "kba":         lambda: compute_kba_proximity(aoi, time_range, ee_client),
        "dw":          lambda: compute_current_land_cover(aoi, time_range, ee_client),
        "habitat":     lambda: compute_habitat_conversion(aoi, time_range, ee_client),
        "forest_loss": lambda: compute_forest_loss(aoi, time_range, ee_client),
        "ndvi":        lambda: compute_ndvi_condition(aoi, time_range, mode, ee_client),
        "water":       lambda: compute_water_exposure(aoi, time_range, ee_client),
        "recovery":    lambda: compute_recovery_signal(aoi, time_range, ee_client),
    }

    for ind_key in [k for k in dispatch if k in indicator_keys]:
        try:
            payload.update(dispatch[ind_key]())
        except IndicatorComputeError as err:
            for emitted in NATURE_INDICATOR_CONFIG[ind_key].emitted_keys:
                payload[emitted] = None
            failures.append({
                "indicator":    ind_key,
                "indicator_id": err.indicator_id,
                "reason":       err.reason,
            })

    if indicator_keys and len(failures) == len(indicator_keys):
        affected = [
            key
            for ind in sorted(indicator_keys)
            for key in NATURE_INDICATOR_CONFIG[ind].emitted_keys
        ]
        raise PillarComputeError(
            pillar=PILLAR_NATURE,
            indicator_ids=affected,
            reason="all selected Nature indicators failed to compute",
        )

    # Augment habitat payload with the four pct_norm derived keys, plus
    # annualised_rate_score, that HABITAT_CONVERSION_WEIGHTS reads.
    buffer_ha = _buffer_area_ha(aoi["radius_km"])
    payload.update(_augment_habitat_pct_norms(payload, buffer_ha))

    # Sub-aggregates — all three exposure-side scores that feed the pillar.
    payload.update(compute_biodiversity_exposure(payload))
    payload.update(compute_habitat_conversion_score(payload))
    payload.update(compute_vegetation_condition(payload))

    # Quality sub-scores + pillar aggregates.
    payload.update(compute_nature_quality_sub_scores(payload, aoi))
    payload.update(compute_nature_quality_attribution(payload))
    payload.update(compute_nature_spatiotemporal_anomaly(payload))
    payload.update(compute_nature_followup_priority(payload, mode))

    if failures:
        payload["_failures"] = failures

    return payload
