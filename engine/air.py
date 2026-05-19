"""Air Pollution pillar — single-value indicators, sub-aggregates, and
pillar aggregates (Milestone 3b).

Layers in this module:
1. Single-value indicators (IC_v4 §1.1 / Schema_v2 §2.1) — the nine pollutants
   no2, so2, co, hcho, o3, aai, pm25, pm10, aod. Each runs the IC_v4 §0.2
   six-step pipeline via engine.core.six_step, maps the result to canonical
   IDs (`air.<pollutant>.<measurement>`), applies any per-pollutant score cap
   (only O3 in v1, IC_v4 §1.3), and attaches a `_provenance.air.<pollutant>`
   block.
2. Sub-aggregates (IC_v4 §1.2 / Schema_v2 §2.2) — six derived 0-1 scores
   combining pollutant scores via fixed weights. `pm_or_aerosol` has a CAMS
   fallback per IC_v4 §1.2 E4; the other five are strict (any missing
   dependency → result is None).
3. Pillar aggregates (IC_v4 §1.3 / Schema_v2 §2.3) — five aggregate scores
   computed over selected pollutants, with weights renormalised when terms
   are missing.
4. `run_pillar` — single entry point the orchestrator (M4) will call.

Deferred to Milestone 4: run_pillar is wired up, but the orchestrator
(ScreeningRun, TrendRun) that calls it lives in M4.

Quality notes (v1 baseline):
- OFFL Sentinel-5P assets only; NRTI fallback for very recent dates is deferred to M4.
- AOD applies an AOD_QA bits-8-11 mask via `apply_aod_qa_mask` — the only pollutant
  needing a per-image preprocess in v1.
- The confidence value returned by `six_step` is still the
  (N_valid/N_total)·1.0 placeholder from M2 (engine/core/repeatable_core.
  _placeholder_confidence). Real QA-band integration into `mean_qa` is deferred
  until the IC §6.3 doc gap is fixed.
- TODO(M4+): apply per-pollutant `qa_value > 0.75` filter on Sentinel-5P bands
  where available (NO2, SO2, CO, HCHO, O3, AAI).
- TODO(M5+): trend values are still None from M2 (engine/core/trend.py not
  implemented), so in trend mode `compute_trend_score` returns None.

Mode handling:
- The `mode` parameter is accepted for signature stability with
  Engine_Module_Skeleton §2.1. For single-value indicators it has no effect.
  At the pillar-aggregate level, `compute_trend_score` returns 0.0 in
  screening mode (so the Trend term doesn't pull the follow-up score) and
  the actual trend mean in trend mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import ee

from engine.constants import (
    AIR_FOLLOWUP_WEIGHTS,
    AIR_POLLUTION_PROXY_WEIGHTS,
    AOD_QA_VALID_BIT_MASK,
    CAMS_MIN_VALID_PCT,
    HEAVY_INDUSTRY_WEIGHTS,
    INDUSTRIAL_BURDEN_WEIGHTS,
    INDUSTRIAL_COMBUSTION_PROXY_WEIGHTS,
    NORMALISATION_K,
    O3_SCORE_CAP,
    PM_OR_AEROSOL_WEIGHTS,
    SMOKE_DUST_TRANSPORT_WEIGHTS,
    VOC_PHOTOCHEMICAL_WEIGHTS,
)
from engine.core import build_provenance, six_step
from engine.exceptions import IndicatorComputeError, PillarComputeError
from engine.ids import AIR_SUB_AGGREGATES, PILLAR_AIR, make_id


# ---------------------------------------------------------------------------
# Per-pollutant configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PollutantConfig:
    """Static config for one of the nine air-pollution single-value indicators.

    `scale_factor` converts native physical units to the display unit;
    `scale_m` is the EE reduceRegion scale (metres), set per data source to
    match the asset's native pixel resolution.

    `data_type` / `data_source` feed the M5.6 canonical provenance schema —
    see docs/provenance_schema.md. Default values cover the seven S5P-style
    pollutants; CAMS PM and MODIS MAIAC override.
    """

    asset_id: str
    band: str
    scale_factor: float
    scale_m: float
    display_unit: str
    direction: str = "higher_is_worse"
    score_cap: float | None = None
    preprocess: Callable[[ee.Image], ee.Image] | None = None
    # M5.6 — provenance metadata. Defaults match S5P TROPOMI; explicit
    # overrides per-pollutant cover CAMS PM (gridded model) and MODIS AOD.
    data_type: str = "satellite_observation"
    data_source: str = "Copernicus / ESA (Sentinel-5P TROPOMI)"


def apply_aod_qa_mask(image: ee.Image) -> ee.Image:
    """Mask MODIS MAIAC AOD pixels where AOD_QA bits 8-11 are non-zero.

    Bits 8-11 of `AOD_QA` encode the per-pixel AOD retrieval QA. A value of 0
    means best quality; non-zero values mark progressively worse retrievals.
    See `engine.constants.AOD_QA_VALID_BIT_MASK` for the full bit layout.
    """
    qa = image.select("AOD_QA")
    masked_bits = qa.bitwiseAnd(AOD_QA_VALID_BIT_MASK)
    valid = masked_bits.eq(0)
    return image.updateMask(valid)


# IC_v4 §1.1 + Indicator_ID_Schema_v2.md §2.1 + GEE_Database_List §2.
# `scale_factor` converts each band from its native unit to the display unit
# used in the dashboard (see Indicator_ID_Schema §2.1 unit columns).
AIR_POLLUTANT_CONFIG: dict[str, PollutantConfig] = {
    "no2": PollutantConfig(
        asset_id="COPERNICUS/S5P/OFFL/L3_NO2",
        band="NO2_column_number_density",
        scale_factor=1e6,                 # mol/m² → µmol/m²
        scale_m=1113.2,                   # Sentinel-5P L3 grid
        display_unit="µmol/m²",
    ),
    "so2": PollutantConfig(
        asset_id="COPERNICUS/S5P/OFFL/L3_SO2",
        band="SO2_column_number_density",
        scale_factor=1e6,
        scale_m=1113.2,
        display_unit="µmol/m²",
    ),
    "co": PollutantConfig(
        asset_id="COPERNICUS/S5P/OFFL/L3_CO",
        band="CO_column_number_density",
        scale_factor=1e3,                 # mol/m² → mmol/m²
        scale_m=1113.2,
        display_unit="mmol/m²",
    ),
    "hcho": PollutantConfig(
        asset_id="COPERNICUS/S5P/OFFL/L3_HCHO",
        band="tropospheric_HCHO_column_number_density",
        scale_factor=1e6,
        scale_m=1113.2,
        display_unit="µmol/m²",
    ),
    "o3": PollutantConfig(
        asset_id="COPERNICUS/S5P/OFFL/L3_O3",
        band="O3_column_number_density",
        # 1 DU = 4.4615e-4 mol/m² → divide mol/m² by 4.4615e-4 to get DU.
        scale_factor=1.0 / 4.4615e-4,
        scale_m=1113.2,
        display_unit="DU",
        score_cap=O3_SCORE_CAP,           # IC_v4 §1.3 — context, not primary.
    ),
    "aai": PollutantConfig(
        asset_id="COPERNICUS/S5P/OFFL/L3_AER_AI",
        band="absorbing_aerosol_index",
        scale_factor=1.0,
        scale_m=1113.2,
        display_unit="dimensionless",
    ),
    "pm25": PollutantConfig(
        asset_id="ECMWF/CAMS/NRT",
        # M-CAMS-BAND-FIX (May 2026): CAMS renamed `particulate_matter_2.5um`
        # to the longer, more descriptive `particulate_matter_d_less_than_25_um_surface`.
        # The legacy name now returns "band pattern did not match" on
        # `reduce.mean(...)`. See docs/v1x_followups.md.
        band="particulate_matter_d_less_than_25_um_surface",
        scale_factor=1e9,                 # kg/m³ → µg/m³
        scale_m=44544.0,                  # CAMS NRT global grid
        display_unit="µg/m³",
        data_type="gridded_model_output",
        data_source="ECMWF CAMS reanalysis",
    ),
    "pm10": PollutantConfig(
        asset_id="ECMWF/CAMS/NRT",
        # M-CAMS-BAND-FIX (May 2026): same rename as PM₂.₅ above.
        band="particulate_matter_d_less_than_10_um_surface",
        scale_factor=1e9,
        scale_m=44544.0,
        display_unit="µg/m³",
        data_type="gridded_model_output",
        data_source="ECMWF CAMS reanalysis",
    ),
    "aod": PollutantConfig(
        asset_id="MODIS/061/MCD19A2_GRANULES",
        band="Optical_Depth_055",
        scale_factor=1.0,
        scale_m=1000.0,                   # MODIS MAIAC AOD native
        display_unit="dimensionless",
        preprocess=apply_aod_qa_mask,
        data_source="NASA MODIS MAIAC",
        # data_type defaults to satellite_observation — correct for MAIAC.
    ),
}


# The standard nine `six_step` keys that get re-mapped to canonical IDs.
# Order matches Indicator_ID_Schema_v2.md §1 measurement-suffix table.
_MEASUREMENT_KEYS: tuple[str, ...] = (
    "site", "background", "anomaly", "z", "hf",
    "trend", "trend_p", "confidence", "score",
)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def compute_pollutant_snapshot(
    aoi: dict,
    pollutant: str,
    time_range: tuple[str, str],
    mode: str,
    ee_client,
) -> dict:
    """Run the IC_v4 §0.2 six-step pipeline for one air-pollution single-value indicator.

    Looks up `pollutant` in `AIR_POLLUTANT_CONFIG`, builds the scaled
    (and optionally masked) ImageCollection, delegates to
    `engine.core.six_step`, applies any score cap (O3 only in v1), and
    returns a dict keyed by canonical IDs plus a `_provenance.air.<pollutant>`
    block.

    `mode` is accepted but not used here in v1 — the orchestrator (M4)
    selects the time_range based on mode.

    Raises:
        KeyError: pollutant not in `AIR_POLLUTANT_CONFIG`.
        IndicatorComputeError: site or background buffer has no valid pixels.
    """
    if pollutant not in AIR_POLLUTANT_CONFIG:
        raise KeyError(f"unknown air pollutant: {pollutant!r}")
    cfg = AIR_POLLUTANT_CONFIG[pollutant]

    radius_km = aoi["radius_km"]
    if cfg.scale_m > radius_km * 1000:
        # Catch CAMS-at-5km and similar BEFORE we hand to EE — the message
        # tells the caller exactly which radius would work.
        raise IndicatorComputeError(
            indicator_id=make_id(PILLAR_AIR, pollutant),
            reason=(
                f"site buffer ({radius_km} km) smaller than {pollutant} "
                f"native pixel ({cfg.scale_m / 1000:.1f} km) — "
                f"increase radius or pick a finer-resolution pollutant"
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
        indicator_id=make_id(PILLAR_AIR, pollutant),
        scale=cfg.scale_m,
    )

    return _format_result(pollutant, cfg, raw, time_range)


def compute_pm25_proxy(
    aoi: dict, time_range: tuple[str, str], mode: str, ee_client,
) -> dict:
    """PM2.5 single-value snapshot — thin wrapper for explicit call sites."""
    return compute_pollutant_snapshot(aoi, "pm25", time_range, mode, ee_client)


def compute_pm10_proxy(
    aoi: dict, time_range: tuple[str, str], mode: str, ee_client,
) -> dict:
    """PM10 single-value snapshot — thin wrapper for explicit call sites."""
    return compute_pollutant_snapshot(aoi, "pm10", time_range, mode, ee_client)


def compute_aod(
    aoi: dict, time_range: tuple[str, str], mode: str, ee_client,
) -> dict:
    """AOD single-value snapshot — thin wrapper for explicit call sites."""
    return compute_pollutant_snapshot(aoi, "aod", time_range, mode, ee_client)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_image_collection(cfg: PollutantConfig) -> ee.ImageCollection:
    """Construct the scaled (and optionally masked) ImageCollection for `cfg`.

    The preprocess callable runs *before* band selection so it has access to
    auxiliary QA bands (e.g. AOD's `AOD_QA`); the target band is selected and
    scaled afterwards.
    """
    ic = ee.ImageCollection(cfg.asset_id)
    if cfg.preprocess is not None:
        ic = ic.map(cfg.preprocess)
    ic = ic.select(cfg.band)
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
    pollutant: str,
    cfg: PollutantConfig,
    raw: dict,
    time_range: tuple[str, str],
) -> dict:
    """Apply score cap, remap `raw` to canonical IDs, attach provenance."""
    score = raw.get("score")
    if cfg.score_cap is not None and score is not None:
        score = min(score, cfg.score_cap)

    result: dict = {}
    for measurement in _MEASUREMENT_KEYS:
        value = score if measurement == "score" else raw.get(measurement)
        result[make_id(PILLAR_AIR, pollutant, measurement)] = value

    result[f"_provenance.air.{pollutant}"] = build_provenance(
        asset_id=cfg.asset_id,
        band=cfg.band,
        data_type=cfg.data_type,
        data_source=cfg.data_source,
        native_scale_m=cfg.scale_m,
        time_range=time_range,
        method_note=_air_method_note(pollutant),
        # TODO(v1.x): track six_step's actual image count and surface it
        # here as observations={"count": n, "unit": "daily_images"}. For
        # now compute_pollutant_snapshot doesn't track the count.
        observations=None,
        extra=_air_extra(pollutant),
    )
    return result


# M5.6 — provenance extras / method notes per pollutant. Centralised here
# rather than inlined into _format_result so the format function stays
# tight and the per-pollutant exceptions are auditable.

def _air_method_note(pollutant: str) -> str | None:
    """Pollutant-specific method note for canonical provenance.

    PM2.5 / PM10 flag CAMS as modelled, not measured — important context
    a reviewer needs without having to read the data_type field too.
    AOD documents the bit-mask. Others have no special note in v1.
    """
    if pollutant in ("pm25", "pm10"):
        return "CAMS reanalysis; PM2.5/PM10 are modelled, not measured"
    if pollutant == "aod":
        return "MODIS MAIAC; AOD_QA bits 8-11 mask non-best retrievals"
    return None


def _air_extra(pollutant: str) -> dict:
    """Pollutant-specific `extra` dict — only AOD and PM populate it in v1."""
    if pollutant == "aod":
        return {"aod_qa_bit_mask": f"0x{AOD_QA_VALID_BIT_MASK:X}"}
    if pollutant in ("pm25", "pm10"):
        return {"cams_min_valid_pct": CAMS_MIN_VALID_PCT}
    return {}


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _renormalise_weights(
    weights: dict[str, float],
    present_keys: set[str],
) -> dict[str, float]:
    """Subset `weights` to `present_keys` and rescale so values sum to 1.0.

    Returns an empty dict when no keys overlap; callers should treat that as
    "no aggregate computable" (i.e. result is None, not 0.0).
    """
    relevant = {k: v for k, v in weights.items() if k in present_keys}
    total = sum(relevant.values())
    if total == 0:
        return {}
    return {k: v / total for k, v in relevant.items()}


def _weighted_sum_strict(
    payload: dict,
    weights: dict[str, float],
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


def _pollutant_keys_from_selected(selected: set[str]) -> set[str]:
    """Map canonical IDs back to the pollutant keys in AIR_POLLUTANT_CONFIG.

    Accepts both `"air.<pollutant>"` and `"air.<pollutant>.<measurement>"`
    forms. Anything that doesn't resolve to a known pollutant is ignored —
    the orchestrator (M4) is responsible for validating selection upstream.
    """
    pollutants: set[str] = set()
    for ind_id in selected:
        parts = ind_id.split(".")
        if len(parts) >= 2 and parts[0] == PILLAR_AIR and parts[1] in AIR_POLLUTANT_CONFIG:
            pollutants.add(parts[1])
    return pollutants


# Per-pollutant ID prefixes are useful for the per-pollutant pillar aggregates
# (anomaly / confidence / trend) that iterate over the nine single-value
# pollutants and pick `.z`, `.confidence`, etc. out of the payload.
_SINGLE_VALUE_POLLUTANTS: tuple[str, ...] = tuple(AIR_POLLUTANT_CONFIG.keys())

# IC_v4 §1.3 — the four pillar-aggregate IDs that feed `audit_followup_priority`,
# in the same key order as AIR_FOLLOWUP_WEIGHTS.
_FOLLOWUP_TERM_TO_ID: dict[str, str] = {
    "proxy":      "air.pollution_proxy_score",
    "anomaly":    "air.spatiotemporal_anomaly_score",
    "trend":      "air.trend_score",
    "confidence": "air.attribution_confidence_score",
}


# ---------------------------------------------------------------------------
# Sub-aggregates  (IC_v4 §1.2 / Schema_v2 §2.2)
# ---------------------------------------------------------------------------

def compute_pm_or_aerosol(payload: dict) -> dict:
    """IC_v4 §1.2 — `0.60·pm25.score + 0.40·aai.score`, with the CAMS fallback.

    The CAMS fallback (E4 trigger) fires when `air.pm25.score` is None or the
    CAMS site value (`air.pm25.site`) is null — both indicate the CAMS reading
    is unusable. The fallback uses `1.00·aai.score`. Returns None if the
    fallback also has no AAI to use.

    Returns:
        {
          "air.pm_or_aerosol": float | None,
          "_provenance.air.pm_or_aerosol": {"formula": "primary" | "fallback_aai_only"},
        }
    """
    pm25_score = payload.get("air.pm25.score")
    pm25_site = payload.get("air.pm25.site")

    if pm25_score is None or pm25_site is None:
        return {
            "air.pm_or_aerosol": payload.get("air.aai.score"),
            "_provenance.air.pm_or_aerosol": {"formula": "fallback_aai_only"},
        }

    return {
        "air.pm_or_aerosol": _weighted_sum_strict(payload, PM_OR_AEROSOL_WEIGHTS),
        "_provenance.air.pm_or_aerosol": {"formula": "primary"},
    }


def compute_industrial_combustion_proxy(payload: dict) -> dict:
    """IC_v4 §1.2 — `0.60·no2.score + 0.40·co.score`.

    Also re-exported via the GHG pillar later (IC_v4 §2.2 borrows the same
    formula under `ghg.combustion_proxy`).
    """
    return {
        "air.industrial_combustion_proxy": _weighted_sum_strict(
            payload, INDUSTRIAL_COMBUSTION_PROXY_WEIGHTS,
        ),
    }


def compute_heavy_industry_score(payload: dict) -> dict:
    """IC_v4 §1.2 — `0.60·so2.score + 0.30·no2.score + 0.10·pm_or_aerosol`."""
    return {
        "air.heavy_industry_score": _weighted_sum_strict(
            payload, HEAVY_INDUSTRY_WEIGHTS,
        ),
    }


def compute_voc_photochemical(payload: dict) -> dict:
    """IC_v4 §1.2 — `0.50·hcho.score + 0.30·no2.score + 0.20·o3.score`."""
    return {
        "air.voc_photochemical": _weighted_sum_strict(
            payload, VOC_PHOTOCHEMICAL_WEIGHTS,
        ),
    }


def compute_smoke_dust_regional_transport(payload: dict) -> dict:
    """IC_v4 §1.2 — `0.40·co.score + 0.40·aai.score + 0.20·pm_or_aerosol`."""
    return {
        "air.smoke_dust_regional_transport": _weighted_sum_strict(
            payload, SMOKE_DUST_TRANSPORT_WEIGHTS,
        ),
    }


def compute_industrial_air_pollution_burden(payload: dict) -> dict:
    """IC_v4 §1.2 — `0.40·no2.score + 0.35·so2.score + 0.25·pm_or_aerosol`."""
    return {
        "air.industrial_air_pollution_burden": _weighted_sum_strict(
            payload, INDUSTRIAL_BURDEN_WEIGHTS,
        ),
    }


# ---------------------------------------------------------------------------
# Pillar aggregates  (IC_v4 §1.3 / Schema_v2 §2.3)
# ---------------------------------------------------------------------------

def compute_air_pollution_proxy_score(
    payload: dict,
    selected: set[str],
) -> dict:
    """IC_v4 §1.3 — weighted sum per AIR_POLLUTION_PROXY_WEIGHTS over the terms
    in `selected` that are present in `payload`. Weights renormalised over the
    surviving set.

    `selected` is expected to contain canonical IDs (atomic `.score` IDs and
    any sub-aggregate IDs the caller wants included). run_pillar augments the
    user-supplied set with the computed sub-aggregate IDs before calling this.
    """
    candidates = {
        k: payload[k] for k in AIR_POLLUTION_PROXY_WEIGHTS
        if k in selected and payload.get(k) is not None
    }
    if not candidates:
        return {"air.pollution_proxy_score": None}
    weights = _renormalise_weights(AIR_POLLUTION_PROXY_WEIGHTS, set(candidates.keys()))
    score = sum(weights[k] * candidates[k] for k in candidates)
    return {"air.pollution_proxy_score": score}


def compute_spatiotemporal_anomaly_score(
    payload: dict,
    selected: set[str],
) -> dict:
    """IC_v4 §1.3 — mean of per-pollutant z-scores, clamped to [0, 1] via
    `min(max(z / NORMALISATION_K, 0), 1)` (z can be negative when the site is
    below background, and saturates at k=3 per IC_v4 §0.4).

    Iterates over the nine single-value pollutants, including only those whose
    `.score` ID is in `selected` and whose `.z` value is present in `payload`.
    Returns None if no pollutants survive both filters.
    """
    contributions: list[float] = []
    for pol in _SINGLE_VALUE_POLLUTANTS:
        if make_id(PILLAR_AIR, pol, "score") not in selected:
            continue
        z = payload.get(make_id(PILLAR_AIR, pol, "z"))
        if z is None:
            continue
        contributions.append(min(max(z / NORMALISATION_K, 0.0), 1.0))
    if not contributions:
        return {"air.spatiotemporal_anomaly_score": None}
    return {
        "air.spatiotemporal_anomaly_score": sum(contributions) / len(contributions),
    }


def compute_trend_score(
    payload: dict,
    selected: set[str],
    mode: str,
) -> dict:
    """IC_v4 §1.3 — mean of per-pollutant trend slopes across `selected`.

    In screening mode, returns 0.0 so the Trend term in
    `compute_air_audit_followup_priority` doesn't drag the score in either
    direction. In trend mode, trend values are still None from M2 — the
    function returns None until `engine/core/trend.py` lands.

    TODO(M5+): once trend.py exists and `compute_pollutant_snapshot` returns
    real `.trend` floats, this will compute a meaningful mean in trend mode.
    """
    if mode == "screening":
        return {"air.trend_score": 0.0}

    trends: list[float] = []
    for pol in _SINGLE_VALUE_POLLUTANTS:
        if make_id(PILLAR_AIR, pol, "score") not in selected:
            continue
        trend = payload.get(make_id(PILLAR_AIR, pol, "trend"))
        if trend is None:
            continue
        trends.append(trend)
    if not trends:
        return {"air.trend_score": None}
    return {"air.trend_score": sum(trends) / len(trends)}


def compute_attribution_confidence_score(
    payload: dict,
    selected: set[str],
) -> dict:
    """IC_v4 §1.3 — mean of per-pollutant confidence across `selected`."""
    contributions: list[float] = []
    for pol in _SINGLE_VALUE_POLLUTANTS:
        if make_id(PILLAR_AIR, pol, "score") not in selected:
            continue
        conf = payload.get(make_id(PILLAR_AIR, pol, "confidence"))
        if conf is None:
            continue
        contributions.append(conf)
    if not contributions:
        return {"air.attribution_confidence_score": None}
    return {
        "air.attribution_confidence_score": sum(contributions) / len(contributions),
    }


def compute_air_audit_followup_priority(
    payload: dict,
    mode: str,
) -> dict:
    """IC_v4 §1.3 — weighted sum per AIR_FOLLOWUP_WEIGHTS over the four pillar
    aggregates. Missing terms are skipped and weights renormalised over the
    surviving set.

    `mode` is accepted for signature stability; mode-dependent behaviour
    lives upstream in `compute_trend_score` (which returns 0.0 in screening
    and the real trend mean in trend mode).
    """
    candidates: dict[str, float] = {}
    for term in AIR_FOLLOWUP_WEIGHTS:
        value = payload.get(_FOLLOWUP_TERM_TO_ID[term])
        if value is None:
            continue
        candidates[term] = value
    if not candidates:
        return {"air.audit_followup_priority": None}
    weights = _renormalise_weights(AIR_FOLLOWUP_WEIGHTS, set(candidates.keys()))
    score = sum(weights[term] * candidates[term] for term in candidates)
    return {"air.audit_followup_priority": score}


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
    accumulated_payload: dict | None = None,  # noqa: ARG001 — Air has no cross-pillar borrows
) -> dict:
    """Compute every selected Air indicator + sub-aggregates + pillar aggregates.

    `accumulated_payload` (M5c) is accepted for orchestrator signature parity
    but unused — Air doesn't borrow from any other pillar.


    Logic (Engine_Module_Skeleton §2.1):
    1. Resolve `selected_indicators` to a set of pollutant keys.
    2. For each pollutant, call `compute_pollutant_snapshot` and merge the
       result. Single-pollutant failures degrade gracefully — the affected
       IDs go to None in the payload and the failure is recorded in
       `_failures`.
    3. Compute the six sub-aggregates (each handles missing deps internally).
    4. Compute the five pillar aggregates over an augmented `selected` set
       (atomic IDs + the sub-aggregate IDs that successfully computed).
    5. Return the merged payload.

    Raises `PillarComputeError` if every selected pollutant fails to compute —
    the orchestrator (M4) catches this to render the P-05 S2_Partial UI state.
    """
    pollutant_keys = _pollutant_keys_from_selected(selected_indicators)
    payload: dict = {}
    failures: list[dict] = []

    for pol_key in sorted(pollutant_keys):
        try:
            snapshot = compute_pollutant_snapshot(
                aoi=aoi,
                pollutant=pol_key,
                time_range=time_range,
                mode=mode,
                ee_client=ee_client,
            )
        except IndicatorComputeError as err:
            for measurement in _MEASUREMENT_KEYS:
                payload[make_id(PILLAR_AIR, pol_key, measurement)] = None
            failures.append({
                "pollutant":    pol_key,
                "indicator_id": err.indicator_id,
                "reason":       err.reason,
            })
        else:
            payload.update(snapshot)

    if pollutant_keys and len(failures) == len(pollutant_keys):
        affected = [
            make_id(PILLAR_AIR, p, m)
            for p in sorted(pollutant_keys)
            for m in _MEASUREMENT_KEYS
        ]
        raise PillarComputeError(
            pillar=PILLAR_AIR,
            indicator_ids=affected,
            reason="all selected air pollutants failed to compute",
        )

    # Sub-aggregates — pm_or_aerosol first because three others depend on it.
    payload.update(compute_pm_or_aerosol(payload))
    payload.update(compute_industrial_combustion_proxy(payload))
    payload.update(compute_voc_photochemical(payload))
    payload.update(compute_heavy_industry_score(payload))
    payload.update(compute_smoke_dust_regional_transport(payload))
    payload.update(compute_industrial_air_pollution_burden(payload))

    # Pillar aggregates — augment `selected` so sub-aggregates with non-None
    # values can contribute to AIR_POLLUTION_PROXY_WEIGHTS.
    augmented_selected: set[str] = set(selected_indicators)
    for sub_id in AIR_SUB_AGGREGATES:
        if payload.get(sub_id) is not None:
            augmented_selected.add(sub_id)

    payload.update(compute_air_pollution_proxy_score(payload, augmented_selected))
    payload.update(compute_spatiotemporal_anomaly_score(payload, augmented_selected))
    payload.update(compute_trend_score(payload, augmented_selected, mode))
    payload.update(compute_attribution_confidence_score(payload, augmented_selected))
    payload.update(compute_air_audit_followup_priority(payload, mode))

    if failures:
        payload["_failures"] = failures

    return payload
