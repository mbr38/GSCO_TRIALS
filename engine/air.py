"""Air Pollution pillar — single-value indicators (Milestone 3a).

Implements the nine single-value air-pollution indicators per IC_v4 §1.1 and
Indicator_ID_Schema_v2.md §2.1: no2, so2, co, hcho, o3, aai, pm25, pm10, aod.
Each indicator runs the IC_v4 §0.2 six-step pipeline via engine.core.six_step,
maps the result to canonical IDs (`air.<pollutant>.<measurement>`), applies
any per-pollutant score cap (only O3 in v1, IC_v4 §1.3), and attaches a
`_provenance.air.<pollutant>` block.

Deferred to Milestone 3b:
- Sub-aggregates (`air.pm_or_aerosol`, `air.industrial_combustion_proxy`, etc.).
- Pillar aggregates (`air.pollution_proxy_score`, `air.audit_followup_priority`, …).
- `run_pillar` entry point for the orchestrator.

Quality notes (v1 baseline):
- OFFL Sentinel-5P assets only; NRTI fallback for very recent dates is deferred to M4.
- AOD applies an AOD_QA bits-8-11 mask via `apply_aod_qa_mask` — the only pollutant
  needing a per-image preprocess in v1.
- The confidence value returned by `six_step` is still the
  (N_valid/N_total)·1.0 placeholder from M2 (engine/core/repeatable_core.
  _placeholder_confidence). Real QA-band integration into `mean_qa` is deferred
  until the IC §6.3 doc gap is fixed.
- TODO(M3b): apply per-pollutant `qa_value > 0.75` filter on Sentinel-5P bands
  where available (NO2, SO2, CO, HCHO, O3, AAI).

Mode handling:
- The `mode` parameter is accepted for signature stability with
  Engine_Module_Skeleton §2.1 but does NOT change single-value computation
  in v1. The orchestrator (M4) picks the time_range based on mode; here we
  just compute with whatever time_range we're handed. Mode-dependent zeroing
  of `Trend_Score` happens at the pillar-aggregate level (M3b), not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import ee

from engine.constants import AOD_QA_VALID_BIT_MASK, O3_SCORE_CAP
from engine.core import six_step
from engine.exceptions import IndicatorComputeError
from engine.ids import PILLAR_AIR, make_id


# ---------------------------------------------------------------------------
# Per-pollutant configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PollutantConfig:
    """Static config for one of the nine air-pollution single-value indicators.

    `scale_factor` converts native physical units to the display unit;
    `scale_m` is the EE reduceRegion scale (metres), set per data source to
    match the asset's native pixel resolution.
    """

    asset_id: str
    band: str
    scale_factor: float
    scale_m: float
    display_unit: str
    direction: str = "higher_is_worse"
    score_cap: float | None = None
    preprocess: Callable[[ee.Image], ee.Image] | None = None


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
        band="particulate_matter_2.5um",
        scale_factor=1e9,                 # kg/m³ → µg/m³
        scale_m=44544.0,                  # CAMS NRT global grid
        display_unit="µg/m³",
    ),
    "pm10": PollutantConfig(
        asset_id="ECMWF/CAMS/NRT",
        band="particulate_matter_10um",
        scale_factor=1e9,
        scale_m=44544.0,
        display_unit="µg/m³",
    ),
    "aod": PollutantConfig(
        asset_id="MODIS/061/MCD19A2_GRANULES",
        band="Optical_Depth_055",
        scale_factor=1.0,
        scale_m=1000.0,                   # MODIS MAIAC AOD native
        display_unit="dimensionless",
        preprocess=apply_aod_qa_mask,
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

    result[f"_provenance.air.{pollutant}"] = {
        "asset_id": cfg.asset_id,
        "time_range": time_range,
    }
    return result
