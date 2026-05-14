"""GHG pillar — single-value indicators, sub-aggregates, and pillar
aggregates (Milestone 5a).

M5a covers CH₄ and VIIRS only. CO₂ context (ODIAC) is deferred to M5.5 —
the ODIAC asset isn't yet in the GEE catalogue and requires a personal
upload. GHG quality sub-scores are placeholders pending the IC_v5 §6.3
confidence-formula doc fix (same TODO chain as Air's confidence).

DONE(M5c): orchestrator needs to expose its accumulated payload to
  run_pillar (or compute borrowed sub-aggregates after each pillar) so
  GHG's combustion_proxy / fire_or_regional_transport_risk can read Air's
  values at runtime.

Layers (mirrors engine/air.py architecture):
1. Single-value indicators (IC_v4 §2.1 / Schema_v2 §3.1) — ch4, viirs.
   CO₂ stub: `compute_co2_snapshot` raises NotImplementedError.
2. GHG quality sub-scores (Schema_v2 §3.4) — temporal_coverage,
   spatial_resolution_suitability, retrieval_inventory_quality,
   nearby_source_isolation. All placeholders pending IC_v5 §6.3.
3. Sub-aggregates (IC_v4 §2.2 / Schema_v2 §3.2) — five computable in v1,
   three CO₂-dependent stubs that null-propagate.
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

TODOs deferred from this milestone:
- TODO(M5.5): wire CO₂ context once ODIAC asset is ingested. Activates
  three sub-aggregate stubs (ghg.co2_context, ghg.fossil_combustion_score,
  ghg.activity_adjusted_co2).
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
    CORE_GHG_AUDIT_SUPPORT_WEIGHTS,
    GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS,
    GHG_FOLLOWUP_WEIGHTS,
    NORMALISATION_K,
)
from engine.core import six_step
from engine.exceptions import IndicatorComputeError, PillarComputeError
from engine.ids import PILLAR_GHG, make_id


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


# IC_v4 §2.1 + Indicator_ID_Schema_v2.md §3.1 + GEE_Database_List §3.
GHG_INDICATOR_CONFIG: dict[str, GhgIndicatorConfig] = {
    "ch4": GhgIndicatorConfig(
        asset_id="COPERNICUS/S5P/OFFL/L3_CH4",
        band="CH4_column_volume_mixing_ratio_dry_air",
        scale_factor=1.0,
        scale_m=1113.2,
        display_unit="ppb",
    ),
    "viirs": GhgIndicatorConfig(
        asset_id="NASA/VIIRS/002/VNP46A2",
        band="Gap_Filled_DNB_BRDF_Corrected_NTL",
        scale_factor=1.0,
        scale_m=463.83,
        display_unit="nW/cm²/sr",
        # Schema_v2 §3.1 — VIIRS NTL emits a reduced measurement set.
        emitted_measurements=(
            "site", "anomaly", "trend", "confidence", "score",
        ),
    ),
    # TODO(M5.5): "co2": GhgIndicatorConfig(...) once ODIAC is ingested.
}


# Sub-aggregate weight dicts for the CO₂-dependent stubs. Both formulas
# null-propagate today (co2_context is None until M5.5 wires ODIAC).
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
    aoi: dict, time_range: tuple[str, str], mode: str, ee_client,
) -> dict:
    """CO₂ context snapshot — STUB in M5a, raises NotImplementedError.

    ODIAC is the canonical CO₂ inventory product but isn't in the public
    GEE catalogue; it requires a personal asset upload. Activates in M5.5.

    Note: this is the indicator-snapshot wrapper. The sub-aggregate
    `compute_co2_context(payload)` is a separate function that returns
    None until M5.5 makes `ghg.co2.score` available in the payload.
    """
    raise NotImplementedError(
        "CO₂ context deferred to M5.5 — ODIAC asset not yet ingested"
    )


# ---------------------------------------------------------------------------
# GHG quality sub-scores  (Schema_v2 §3.4 — placeholders)
# ---------------------------------------------------------------------------

def compute_temporal_coverage(payload: dict) -> dict:
    """Schema_v2 §3.4 — placeholder using ch4.confidence as a proxy.

    Real formula is `N_valid / N_total` of analysis-window observations;
    M2's confidence placeholder already encodes this for CH₄, so we
    re-use it here.

    TODO(IC_v5): replace placeholder with the real formula once §6.3 lands.
    """
    return {"ghg.temporal_coverage": payload.get("ghg.ch4.confidence")}


def compute_spatial_resolution_suitability(aoi: dict) -> dict:
    """Schema_v2 §3.4 — buffer-radius vs CH₄ native pixel scale.

    Larger buffer → better suitability. Saturates at 1.0 when the buffer
    radius covers at least one CH₄ on-ground pixel (~7 km, see
    `CH4_NATIVE_SCALE_M`).

    TODO(IC_v5): generalise per-indicator (CH₄ + CO₂ + VIIRS) once §6.3 lands.
    """
    radius_m = aoi["radius_km"] * 1000
    return {
        "ghg.spatial_resolution_suitability": min(1.0, radius_m / CH4_NATIVE_SCALE_M),
    }


def compute_retrieval_inventory_quality(payload: dict) -> dict:
    """Schema_v2 §3.4 — fixed 0.7 placeholder.

    Google's S5P L3 CH₄ product passes its own quality filters upstream,
    so the aggregate retrieval quality is decent but not best-in-class.
    Treating as constant for v1.

    TODO(M5.5): plumb real qa_value from TROPOMI CH₄ + ODIAC vintage flag.
    """
    return {"ghg.retrieval_inventory_quality": 0.7}


def compute_nearby_source_isolation(payload: dict) -> dict:
    """Schema_v2 §3.4 — fixed 1.0 placeholder.

    The real formula (IC_v4 §7.2) is the satellite-only proxy
    `0.5·isolation_from_no2 + 0.5·isolation_from_viirs`. Returning 1.0 in
    v1 over-states isolation in industrial corridors — acceptable v1 trade
    given Wind_Consistency is also deferred.

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

    STUB in M5a: `ghg.co2.score` isn't computed until M5.5 wires ODIAC, so
    this returns None and downstream sub-aggregates null-propagate.
    """
    return {"ghg.co2_context": payload.get("ghg.co2.score")}


def compute_fossil_combustion_score(payload: dict) -> dict:
    """IC_v4 §2.2 — `0.50·co2_context + 0.30·combustion_proxy + 0.20·activity_score`.

    STUB in M5a: co2_context is None until M5.5, so this returns None.
    """
    return {
        "ghg.fossil_combustion_score": _weighted_sum_strict(
            payload, _FOSSIL_COMBUSTION_WEIGHTS,
        ),
    }


def compute_activity_adjusted_co2(payload: dict) -> dict:
    """IC_v4 §2.2 — `0.70·co2_context + 0.30·activity_score`.

    STUB in M5a: co2_context is None until M5.5, so this returns None.
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

    `selected` restricts which terms contribute; weights renormalise over
    the surviving set. Without CO₂ in v1, the four-term formula
    renormalises naturally over the three non-CO₂ terms.
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
    payload: dict, mode: str,
) -> dict:
    """IC_v4 §2.3 — weighted sum per GHG_FOLLOWUP_WEIGHTS over the four
    pillar aggregates. Missing terms renormalised; same shape as Air's
    audit_followup_priority.

    `mode` is accepted for signature stability — mode-dependent behaviour
    lives upstream in `compute_ghg_trend`.
    """
    candidates: dict[str, float] = {}
    for term in GHG_FOLLOWUP_WEIGHTS:
        value = payload.get(_FOLLOWUP_TERM_TO_ID[term])
        if value is None:
            continue
        candidates[term] = value
    if not candidates:
        return {"ghg.audit_followup_priority": None}
    weights = _renormalise_weights(GHG_FOLLOWUP_WEIGHTS, set(candidates))
    score = sum(weights[t] * candidates[t] for t in candidates)
    return {"ghg.audit_followup_priority": score}


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

    for ind_key in sorted(indicator_keys):
        try:
            snapshot = compute_ghg_indicator_snapshot(
                aoi=aoi,
                indicator=ind_key,
                time_range=time_range,
                mode=mode,
                ee_client=ee_client,
            )
        except IndicatorComputeError as err:
            cfg = GHG_INDICATOR_CONFIG[ind_key]
            for measurement in cfg.emitted_measurements:
                payload[make_id(PILLAR_GHG, ind_key, measurement)] = None
            failures.append({
                "indicator":    ind_key,
                "indicator_id": err.indicator_id,
                "reason":       err.reason,
            })
        else:
            payload.update(snapshot)

    if indicator_keys and len(failures) == len(indicator_keys):
        affected = [
            make_id(PILLAR_GHG, ind, m)
            for ind in sorted(indicator_keys)
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

    # Quality sub-scores — placeholders pending IC_v5.
    payload.update(compute_temporal_coverage(payload))
    payload.update(compute_spatial_resolution_suitability(aoi))
    payload.update(compute_retrieval_inventory_quality(payload))
    payload.update(compute_nearby_source_isolation(payload))

    # Sub-aggregates — dependency order: Air-borrowed first (so dependents
    # downstream see them), then CH₄-side, then stubs.
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

    result[f"_provenance.ghg.{indicator}"] = {
        "asset_id":   cfg.asset_id,
        "time_range": time_range,
    }
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
