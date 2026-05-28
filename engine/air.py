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
- The confidence value returned by `six_step` is the M-TIER-A1 universal
  4-term formula (QA + N_valid + anomaly_strength + spatial_context)
  × column-to-surface multiplier — see IC_v4.2 §8 and
  engine/core/confidence.py. QA is currently a per-indicator static
  default from `engine.constants.QA_PER_INDICATOR`; Layer B work
  (plumbing real `qa_value > 0.75` filter pass-rates into the EE
  pipeline) is logged for Tier B1 sensitivity-analysis follow-up.
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

import concurrent.futures
from dataclasses import dataclass
from typing import Callable

import ee


# M-PERF-PARALLEL #3b: cap concurrent EE requests per pillar to avoid
# overwhelming the project's per-second quota. 4 workers is a defensive
# default that comfortably saturates EE's parallelism budget for one
# project without tripping HTTP 429s; tune via this constant.
_AIR_MAX_PARALLEL_WORKERS: int = 4

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
from engine.core.fallback import FallbackContext
from engine.exceptions import (
    BackgroundRingNoDataError,
    IndicatorComputeError,
    PillarComputeError,
    SiteBufferNoDataError,
)
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
    # M-AIR-GHG-DEFENSIVE — asset-family code emitted in provenance when
    # the site buffer reduces to no usable pixels. Defaults to the S5P
    # family; CAMS PM and MAIAC AOD override. Surfaces in C9 / C4b via
    # the prose translation in _SKIPPED_REASON_TRANSLATIONS.
    skipped_reason_no_data: str = "no_s5p_pixels"


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
        skipped_reason_no_data="no_cams_pixels",  # M-AIR-GHG-DEFENSIVE
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
        skipped_reason_no_data="no_cams_pixels",  # M-AIR-GHG-DEFENSIVE
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
        skipped_reason_no_data="no_maiac_pixels",  # M-AIR-GHG-DEFENSIVE
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
    fallback: FallbackContext | None = None,
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
        fallback=fallback,
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

    # M-TIER-A1 — surface the four confidence formula inputs in
    # provenance.extra so the GHG/Nature pillar quality sub-scores and
    # auditors can read the per-indicator contributions back without
    # recomputing them. six_step attaches the dict to its output; if a
    # caller bypasses six_step the field is absent and downstream readers
    # treat the indicator as a non-contributor to pillar QA sub-scores.
    extra = dict(_air_extra(pollutant))
    confidence_terms = raw.get("confidence_terms")
    if confidence_terms is not None:
        extra["confidence_terms"] = confidence_terms
    # M-UI-A1-SURFACE engine-gap fix — surface the raw date and granule
    # counts (informational, never enters score arithmetic). Both keys
    # are absent for non-six_step paths; consumers must handle absence.
    n_valid_dates = raw.get("n_valid_dates")
    if n_valid_dates is not None:
        extra["n_valid_dates"] = n_valid_dates
    granule_count = raw.get("granule_count")
    if granule_count is not None:
        extra["granule_count"] = granule_count
    # M-TIER-A3 Step E — three MOD44W land-mask provenance fields per
    # spec §3.6. Absent for non-six_step paths (matches the existing
    # n_valid_dates / granule_count convention).
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
    # always present; the temporal_/climatology_ pair set when a fallback
    # fired). Absent for non-six_step paths; consumers handle absence.
    fallback_extra = raw.get("fallback_extra")
    if fallback_extra is not None:
        extra.update(fallback_extra)
    # M-WIND-A1 v2.0 §5.4 — merge the additive wind attributability fields
    # (wind_attributability_state always present for the five in-scope
    # indicators; metric fields populated when state != "sparse"). None for
    # out-of-scope pollutants (co, o3, pm25, pm10) so the merge no-ops.
    wind_extra = raw.get("wind_extra")
    if wind_extra is not None:
        extra.update(wind_extra)

    result[f"_provenance.air.{pollutant}"] = build_provenance(
        indicator_id=f"air.{pollutant}",
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
        extra=extra,
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


# M-OCEAN-RING
def _emit_skipped_air_result(
    pollutant: str,
    *,
    time_range: tuple[str, str],
    skipped_reason: str,
    reason_detail: str,
) -> dict:
    """Build the canonical 'pollutant skipped' payload.

    Mirrors the M5.5c ODIAC out-of-coverage and M-NATURE-DEFENSIVE
    no_dw_pixels patterns: every emitted measurement is set to None and
    the provenance block carries the machine-readable ``skipped_reason``
    so C9 (partial banner) and C4b (failed tile) can render the cause.

    Pollutant snapshots aren't appended to ``_failures`` — silent-skip is
    a coverage statement ("no data here"), not a compute failure.
    """
    cfg = AIR_POLLUTANT_CONFIG[pollutant]
    result: dict = {
        make_id(PILLAR_AIR, pollutant, m): None for m in _MEASUREMENT_KEYS
    }
    base_note = _air_method_note(pollutant) or "IC §0.2 six-step pipeline"
    method_note = f"{base_note}; skipped ({reason_detail})"
    result[f"_provenance.air.{pollutant}"] = build_provenance(
        indicator_id=f"air.{pollutant}",
        asset_id=cfg.asset_id,
        band=cfg.band,
        data_type=cfg.data_type,
        data_source=cfg.data_source,
        native_scale_m=cfg.scale_m,
        time_range=time_range,
        method_note=method_note,
        skipped_reason=skipped_reason,
        observations={"count": 0, "unit": "daily_images"},
        extra=_air_extra(pollutant),
    )
    return result


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
    # M-ATTRIB-A1 (AT16): points at the renamed measurement-quality ID.
    "confidence": "air.measurement_quality_score",
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


def compute_measurement_quality_score(
    payload: dict,
    selected: set[str],
) -> dict:
    """IC_v4 §1.3 — mean of per-pollutant confidence across `selected`.

    M-ATTRIB-A1 (AT16): renamed from `compute_attribution_confidence_score`.
    This computes *measurement quality* — the mean per-pollutant M-TIER-A1
    confidence — not attributability. The old name conflated the two; the
    new name is honest. Attributability (wind asymmetry per M-WIND-A1 v2.0)
    is a separate categorical surface that does NOT enter this value.

    Dual-emit (AT16 / Q-AT-3, 1-milestone window): emits the new canonical
    ID `air.measurement_quality_score` AND the legacy
    `air.attribution_confidence_score` with the identical value, so any
    out-of-repo consumer still reading the old key keeps working for one
    milestone. Remove the legacy key (and the module alias below) next
    milestone — see M-ATTRIB-A1 spec §4.6.
    """
    contributions: list[float] = []
    for pol in _SINGLE_VALUE_POLLUTANTS:
        if make_id(PILLAR_AIR, pol, "score") not in selected:
            continue
        conf = payload.get(make_id(PILLAR_AIR, pol, "confidence"))
        if conf is None:
            continue
        contributions.append(conf)
    value = sum(contributions) / len(contributions) if contributions else None
    return {
        "air.measurement_quality_score": value,
        # M-ATTRIB-A1 deprecation shim — legacy alias, remove next milestone.
        "air.attribution_confidence_score": value,
    }


# M-ATTRIB-A1 — legacy function-name alias for the deprecation window.
# Importers of the old name (e.g. test_formula_keys_match_engine) keep
# working; remove alongside the legacy ID emit next milestone.
compute_attribution_confidence_score = compute_measurement_quality_score


def compute_air_audit_followup_priority(
    payload: dict,
    mode: str,                                          # noqa: ARG001 — parity
) -> dict:
    """IC_v4 §1.3 — weighted sum per AIR_FOLLOWUP_WEIGHTS over the four
    pillar aggregates.

    `mode` is accepted for signature stability; mode-dependent behaviour
    lives upstream in `compute_trend_score` (which returns 0.0 in
    screening — a known v1 zero, not a missing value).

    M-FOLLOWUP-FALLBACK: strict-None propagation. If any sub-aggregate
    is None, the priority is None. The prior renormalise-over-survivors
    pattern produced misleading "high priority" headlines from a single
    surviving input when the rest had silently failed (e.g. coastal
    AOIs where every pollutant tripped the background-ring skip).
    """
    values: list[float] = []
    for term in AIR_FOLLOWUP_WEIGHTS:
        v = payload.get(_FOLLOWUP_TERM_TO_ID[term])
        if v is None:
            return {"air.audit_followup_priority": None}
        values.append(AIR_FOLLOWUP_WEIGHTS[term] * v)
    return {"air.audit_followup_priority": sum(values)}


# ---------------------------------------------------------------------------
# Pillar entry point
# ---------------------------------------------------------------------------

def _compute_one_pollutant_outcome(
    pol_key: str,
    aoi: dict,
    time_range: tuple[str, str],
    mode: str,
    ee_client,
    fallback: FallbackContext | None,
) -> tuple[dict, dict | None]:
    """Compute one pollutant's snapshot OR its skip / failure payload.

    Returns ``(payload_chunk, failure_or_none)`` so the parallel dispatcher
    in ``run_pillar`` can merge results deterministically on the main
    thread. Stateless — every input is passed in; nothing mutates any
    shared structure. Safe to run in a worker thread.

    Exception handling mirrors the prior inline loop body in run_pillar:
    BackgroundRingNoDataError + SiteBufferNoDataError become silent-skip
    payloads (no _failures entry); only IndicatorComputeError becomes a
    failure record (the indicator's keys are set to None).
    """
    try:
        snapshot = compute_pollutant_snapshot(
            aoi=aoi,
            pollutant=pol_key,
            time_range=time_range,
            mode=mode,
            ee_client=ee_client,
            fallback=fallback,
        )
        return snapshot, None
    except BackgroundRingNoDataError as err:
        return _emit_skipped_air_result(
            pol_key,
            time_range=time_range,
            skipped_reason="background_ring_no_data",
            reason_detail=err.reason,
        ), None
    except SiteBufferNoDataError as err:
        cfg = AIR_POLLUTANT_CONFIG[pol_key]
        return _emit_skipped_air_result(
            pol_key,
            time_range=time_range,
            skipped_reason=cfg.skipped_reason_no_data,
            reason_detail=err.reason,
        ), None
    except IndicatorComputeError as err:
        chunk = {
            make_id(PILLAR_AIR, pol_key, m): None for m in _MEASUREMENT_KEYS
        }
        failure = {
            "pollutant":    pol_key,
            "indicator_id": err.indicator_id,
            "reason":       err.reason,
        }
        return chunk, failure


def run_pillar(
    aoi: dict,
    time_range: tuple[str, str],
    mode: str,
    selected_indicators: set[str],
    ee_client,
    *,
    accumulated_payload: dict | None = None,  # noqa: ARG001 — Air has no cross-pillar borrows
    fallback: FallbackContext | None = None,
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

    # See _compute_one_pollutant_outcome below — the per-pollutant try/except
    # used to live inline here; extracting it into a stateless helper makes
    # the loop body suitable for concurrent dispatch.

    # M-PERF-PARALLEL #3b: the 9 pollutants are fully independent (each
    # reduces its own asset against the same AOI + window; no cross-pollutant
    # dependencies). Dispatching them through a thread pool overlaps the
    # blocking .getInfo() round-trips, dropping Air wall-time ~3-4×.
    # ThreadPoolExecutor.map preserves input order, so merging the per-
    # pollutant payload chunks in sorted(pollutant_keys) order keeps the
    # final payload byte-identical to the prior serial implementation.
    sorted_keys = sorted(pollutant_keys)
    if sorted_keys:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(_AIR_MAX_PARALLEL_WORKERS, len(sorted_keys)),
            thread_name_prefix="gsco-air",
        ) as ex:
            outcomes = list(ex.map(
                lambda pk: _compute_one_pollutant_outcome(
                    pk, aoi, time_range, mode, ee_client, fallback,
                ),
                sorted_keys,
            ))
        for chunk, failure in outcomes:
            payload.update(chunk)
            if failure is not None:
                failures.append(failure)

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

    recompute_air_aggregates(payload, selected_indicators, mode)

    if failures:
        payload["_failures"] = failures

    return payload


def recompute_air_aggregates(
    payload: dict,
    selected_indicators: set[str],
    mode: str,
) -> dict:
    """Recompute Air's sub-aggregates + pillar aggregates in place on `payload`.

    Pure function of the payload (no EE) — extracted from `run_pillar` so the
    M-FALLBACK-A1 patch path (`engine.orchestrator.patch_indicators`) can
    refresh the aggregates after splicing a recomputed single indicator,
    without re-fetching the other indicators.
    """
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
    payload.update(compute_measurement_quality_score(payload, augmented_selected))
    payload.update(compute_air_audit_followup_priority(payload, mode))
    return payload
