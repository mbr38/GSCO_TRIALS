"""Tunable defaults for the engine.

All numeric thresholds, k-values, weight dicts, and class buckets live here.
Hard-coded magic numbers in pillar code are a smell — move them here.

Section refs point to docs/Engine_Module_Skeleton_v1.md §5 unless noted; some
values trace back to docs/Indicators_Computation_v4.md (IC_v4),
docs/Indicator_ID_Schema_v2.md, Wireframes, and Verbal_Summary. Cross-refs
are inline.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Traffic-light thresholds  (Wireframes Appendix C.1 / Verbal_Summary §1)
# ---------------------------------------------------------------------------
TRAFFIC_LIGHT_THRESHOLDS: tuple[float, float] = (0.33, 0.66)

# ---------------------------------------------------------------------------
# Repeatable core method  (IC_v4 §0.2 step 5, §0.4)
# ---------------------------------------------------------------------------
ANOMALY_Z_THRESHOLD: float = 2.0
NORMALISATION_K: float = 3.0

# ---------------------------------------------------------------------------
# Habitat conversion  (IC_v4 §3.1, §3.2)
# ---------------------------------------------------------------------------
HABITAT_BASELINE_YEARS: int = 5
CONVERSION_SATURATION_PCT: float = 0.10

# ---------------------------------------------------------------------------
# Dynamic World class buckets  (IC_v4 §3.2)
# ---------------------------------------------------------------------------
DW_NATURAL_CLASSES: tuple[str, ...] = (
    "trees",
    "grass",
    "shrub_and_scrub",
    "flooded_vegetation",
)
DW_NON_NATURAL_CLASSES: tuple[str, ...] = ("crops", "built", "bare")
DW_EXCLUDED_CLASSES: tuple[str, ...] = ("snow_and_ice",)
DW_WATER_CLASS: str = "water"

# ---------------------------------------------------------------------------
# Air sub-aggregate fallback  (IC_v4 §1.2 E4 trigger)
# ---------------------------------------------------------------------------
CAMS_MIN_VALID_PCT: float = 0.5

# ---------------------------------------------------------------------------
# Air Pollution pillar  (IC_v4 §1.3 / GEE_Database_List §2 / MAIAC user guide)
# ---------------------------------------------------------------------------

# IC_v4 §1.3 — O3 score is capped at 0.5: O3 is a context indicator, not a
# primary pollution-burden term.
O3_SCORE_CAP: float = 0.5

# MODIS MAIAC AOD_QA byte layout (MAIAC v6.1 user guide):
#   bits 0-2  : Cloud Mask
#   bit  3    : Land/Water Mask
#   bits 4-7  : Adjacency Mask
#   bits 8-11 : AOD QA  ← we keep pixels where these bits are 0 (best retrieval)
#   bits 12-14: Algorithm Initialization
#   bit  15   : Glint Mask
# 0b1111_0000_0000 == 0xF00 == 3840 isolates bits 8-11. engine/air.py masks
# any pixel where (AOD_QA & this mask) != 0.
AOD_QA_VALID_BIT_MASK: int = 0xF00

# ---------------------------------------------------------------------------
# Verbal summary  (Verbal_Summary §3)
# ---------------------------------------------------------------------------
DOMINANT_CONTRIBUTOR_SHARE_THRESHOLD: float = 0.40

# ---------------------------------------------------------------------------
# Buffer caps  (IC_v4 §6.2)
# ---------------------------------------------------------------------------
BACKGROUND_RING_MAX_KM: float = 200.0

# 5:1 background-to-site ratio per IC_v4 §6.2 — used by engine/core/buffers.py
# to default the background ring radius when not supplied explicitly.
BACKGROUND_RING_RADIUS_MULTIPLE = 5

# ---------------------------------------------------------------------------
# Pillar weights — v1 rescaled forms
# ---------------------------------------------------------------------------

# IC_v4 §1.3 — Air Pollution Proxy Score
# Engine_Module_Skeleton §2.1 imports this dict under the name
# AIR_POLLUTANT_WEIGHTS; §5 (which is the actual definition) names it
# AIR_POLLUTION_PROXY_WEIGHTS. The §5 name is canonical here; the §2.1
# name is kept as an alias below so the §2.1 import statement still works.
AIR_POLLUTION_PROXY_WEIGHTS: dict[str, float] = {
    "air.no2.score":     0.30,
    "air.so2.score":     0.20,
    "air.co.score":      0.15,
    "air.hcho.score":    0.15,
    "air.pm_or_aerosol": 0.10,
    "air.o3.score":      0.10,
}
AIR_POLLUTANT_WEIGHTS = AIR_POLLUTION_PROXY_WEIGHTS

# IC_v4 §1.3 — Air Audit Follow-Up Priority terms
AIR_FOLLOWUP_WEIGHTS: dict[str, float] = {
    "proxy":      0.35,
    "anomaly":    0.30,
    "trend":      0.20,
    "confidence": 0.15,
}

# IC_v4 §2.3 — Core GHG Audit Support (M5.5b: ODIAC demoted).
# ODIAC's CO₂ context is no longer in the live composite — its 2+ year
# vintage lag means it can't drive a live screening signal (present-day
# runs against time ranges outside 2020-2023 fail entirely with CO₂ in
# the formula). ODIAC still computes and displays as standing-exposure
# context; it's just outside the formula. The three live signals
# (CH₄ + combustion proxy + activity score) are rescaled by 1/0.61 to
# preserve their relative proportions over the surviving terms. Sums to 1.00.
#
# Methodological upgrade: this also resolves the VIIRS double-counting
# and the ODIAC "anomaly" framing concerns flagged in v1x_followups.md —
# ODIAC isn't competing with the activity / combustion terms any more.
#
# See docs/v1x_followups.md "M5.5b" section for the full rationale and
# the deferred validation-harness work that justifies the CH4 + combustion
# + activity trio as a live CO₂ proxy.
#
# Pre-M5.5b values (kept for reference): co2 0.39, ch4_adj 0.28,
# combustion 0.27, activity 0.06 (sum non-CO₂ = 0.61). Each non-CO₂
# weight is divided by 0.61, then rounded to two decimals so the dict
# reads cleanly: 0.46 + 0.44 + 0.10 = 1.00 exactly.
CORE_GHG_AUDIT_SUPPORT_WEIGHTS: dict[str, float] = {
    "ghg.ch4_context_adjusted": 0.46,   # M5.5b: 0.28 / 0.61 ≈ 0.459 → 0.46
    "ghg.combustion_proxy":     0.44,   # M5.5b: 0.27 / 0.61 ≈ 0.443 → 0.44
    "ghg.activity_score":       0.10,   # M5.5b: 0.06 / 0.61 ≈ 0.098 → 0.10
}

# IC_v4 §2.3 — GHG Data Quality Attribution (v1 rescaled form).
# Wind_Consistency (0.15) and Sector_Match (0.10) are deferred to v1.x, so the
# remaining four terms are rescaled by 1/(1−0.25) = 1.333…
# IC_v3 §2.3 had an incorrect rescale (0.30/0.24/0.24/0.12, sum 0.90); v4 fixed
# it. Sums to 1.00.
GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS: dict[str, float] = {
    "ghg.temporal_coverage":              0.33,
    "ghg.spatial_resolution_suitability": 0.27,
    "ghg.retrieval_inventory_quality":    0.27,
    "ghg.nearby_source_isolation":        0.13,
}

# IC_v4 §2.3 — GHG Audit Follow-Up Priority terms. Sums to 1.00.
GHG_FOLLOWUP_WEIGHTS: dict[str, float] = {
    "core_support": 0.40,
    "anomaly":      0.25,
    "trend":        0.20,
    "quality":      0.15,
}

# Schema_v2 §3.4 — Sentinel-5P CH₄'s real on-ground footprint is ~7 km
# due to swath geometry, even though the L3 grid is 1113 m. Used by
# engine/ghg.py's spatial_resolution_suitability placeholder.
CH4_NATIVE_SCALE_M: float = 7000.0

# Molecular-weight ratio CO₂ / C = 44 / 12 ≈ 3.667. ODIAC stores fossil
# emissions as t C (tonnes of carbon), not t CO₂; multiplying by this
# ratio converts carbon mass to the CO₂-mass units that downstream
# reporting / ESRS / GRI expect. Used by engine/ghg.compute_co2_snapshot.
CO2_TO_C_RATIO: float = 44.0 / 12.0

# IC_v4 §1.2 — Air sub-aggregate weights. Each dict sums to 1.00.
PM_OR_AEROSOL_WEIGHTS: dict[str, float] = {
    "air.pm25.score": 0.60,
    "air.aai.score":  0.40,
}
INDUSTRIAL_COMBUSTION_PROXY_WEIGHTS: dict[str, float] = {
    "air.no2.score": 0.60,
    "air.co.score":  0.40,
}
HEAVY_INDUSTRY_WEIGHTS: dict[str, float] = {
    "air.so2.score":     0.60,
    "air.no2.score":     0.30,
    "air.pm_or_aerosol": 0.10,
}
VOC_PHOTOCHEMICAL_WEIGHTS: dict[str, float] = {
    "air.hcho.score": 0.50,
    "air.no2.score":  0.30,
    "air.o3.score":   0.20,
}
SMOKE_DUST_TRANSPORT_WEIGHTS: dict[str, float] = {
    "air.co.score":      0.40,
    "air.aai.score":     0.40,
    "air.pm_or_aerosol": 0.20,
}
INDUSTRIAL_BURDEN_WEIGHTS: dict[str, float] = {
    "air.no2.score":     0.40,
    "air.so2.score":     0.35,
    "air.pm_or_aerosol": 0.25,
}

# IC_v4 §3.2 — Nature sub-aggregate weights.
# Biodiversity_Exposure rescales over the three v1 terms (the
# Buffer_Sensitivity_v1 term is 0 in v1 per §7.1). Each rescaled weight is
# the IC raw weight divided by the surviving sum 0.90.
BIODIVERSITY_EXPOSURE_WEIGHTS: dict[str, float] = {
    "nature.kba.proximity_score":           0.40 / 0.90,
    "nature.sensitive_land_cover_presence": 0.30 / 0.90,
    "nature.water_or_flooded_veg_exposure": 0.20 / 0.90,
}

# IC_v4 §3.2 — Habitat_Conversion. Each `_pct` term is clamped to [0, 1]
# via `clamp(loss_fraction / CONVERSION_SATURATION_PCT, 0, 1)` before
# weighting; the `_norm` suffix marks the post-clamp ID in the payload.
#
# Hansen forest_loss demoted from the live composite per audit §9.3 v1.4:
# its standing-exposure framing (cumulative loss since 2000) breaks the
# live-window semantics of the other four Dynamic-World-based terms.
# Hansen survives outside this composite as (a) a reference layer in the
# Indicator Library and (b) an input to `compute_regional_loss_evidence`
# (audit §9.3 / IC_v4 §7.5). Its previous 0.10 weight was redistributed
# proportionally over the four surviving terms (rescale factor 1/0.90).
# Pre-demotion values (kept for reference): 0.35 / 0.25 / 0.20 / 0.10 / 0.10.
HABITAT_CONVERSION_WEIGHTS: dict[str, float] = {
    "nature.habitat.natural_loss_pct_norm": 0.40,
    "nature.habitat.nat_to_built_pct_norm": 0.27,
    "nature.habitat.nat_to_bare_pct_norm":  0.22,
    "nature.habitat.annualised_rate_score": 0.11,
}

# IC_v4 §7.5 / audit §9.3 — `regional_loss_evidence` parameters.
# Fixed 5-year Hansen lookback (independent of time_range) and the
# ring-vs-buffer loss-rate threshold above which an external driver is
# flagged. See `engine.nature.compute_regional_loss_evidence`.
HANSEN_LOOKBACK_YEARS: int = 5
HANSEN_LOSS_RATIO_THRESHOLD: float = 2.0

# IC_v4 §3.2 + §7.4 — Vegetation_Condition_v1 (EVI removed). The negative
# weight on recovery is intentional: positive recovery signal subtracts
# from concern.
VEGETATION_CONDITION_WEIGHTS: dict[str, float] = {
    "nature.ndvi.inverted_anomaly": 0.45,
    "nature.ndvi.negative_trend":   0.25,
    "nature.low_ndvi.pct_norm":     0.20,
    "nature.recovery.score":       -0.10,
}

# IC_v4 §3.3 — Nature_Quality_Attribution. Six confidence-side sub-scores.
# Sums to 1.00.
NATURE_QUALITY_ATTRIBUTION_WEIGHTS: dict[str, float] = {
    "nature.valid_pixel_coverage":      0.20,
    "nature.cloud_observation_quality": 0.20,
    "nature.dw.class_confidence":       0.20,
    "nature.seasonal_comparability":    0.15,
    "nature.supplier_spatial_link":     0.15,
    "nature.external_driver_screening": 0.10,
}

# IC_v4 §3.3 — Nature_FollowUp_Priority. Sums to 1.00.
NATURE_FOLLOWUP_WEIGHTS: dict[str, float] = {
    "biodiversity_exposure": 0.30,
    "habitat_conversion":    0.30,
    "vegetation_condition":  0.25,
    "quality_attribution":   0.15,
}

# ---------------------------------------------------------------------------
# A1 confidence formula  (IC_v4 §6.3; audit §1.1)
# ---------------------------------------------------------------------------

# Universal per-indicator confidence formula weights. Sums to 1.00.
# QA + N_valid carry the data-quality bulk (clean inputs, enough of them);
# anomaly_strength weighs whether the observed signal is strong enough to
# trust; spatial_context is the lowest weight because the pixel-buffer
# warning chip in the UI already flags sub-pixel buffers — this term is
# the formula's belt-and-braces capture of the same idea.
CONFIDENCE_FORMULA_WEIGHTS: dict[str, float] = {
    "qa":               0.30,
    "n_valid":          0.30,
    "anomaly_strength": 0.25,
    "spatial_context":  0.15,
}

# spatial_context saturates when the buffer covers ≥3 native pixels in
# each linear dimension. See engine.core.confidence.compute_spatial_context_term.
SPATIAL_CONTEXT_THRESHOLD: float = 3.0

# Column-to-surface uncertainty multiplier applied as the final step to
# c_raw. Encodes the per-gas tag from audit §1.5 as a defensibility
# weight: `n_a` and `strong` carry no penalty, `weak` drops the
# confidence by 20 % so CH₄/CO visibly trail NO₂ at identical
# observational quality. The lookup IDs match the enum in
# engine.core.provenance._ALLOWED_COLUMN_TO_SURFACE_UNCERTAINTY.
COLUMN_TO_SURFACE_MULTIPLIER: dict[str, float] = {
    "strong":         1.00,
    "moderate":       0.95,
    "moderate_weak":  0.88,
    "weak":           0.80,
    "n_a":            1.00,
}

# Per-indicator QA defaults — v1.x A1 ships per-indicator static QA values
# reflecting retrieval-quality consensus for each asset family. Plumbing
# real per-image qa_value pass-rates into the EE pipeline is logged as
# Layer B follow-up (sensitivity analysis target in Tier B1).
#
# The values are calibrated so that:
#   * Asset families with mature, well-validated retrievals (NO₂, NDVI,
#     MAIAC AOD, ODIAC, KBA, Hansen) → 0.90+.
#   * Noisier retrievals (SO₂ over low-emission regions, CAMS PM at
#     ~44 km native pixel relative to fenceline buffers) → 0.70–0.80.
#   * O₃ and AAI sit in the middle (~0.85) — both have well-understood
#     retrievals but are framed as context indicators in IC_v4 §1.3.
# These are intentionally conservative-on-the-noisier-end; the
# recalibration check (M-TIER-A1 Step 8) ratifies them against demo
# locations.
QA_PER_INDICATOR: dict[str, float] = {
    # Air pillar
    "air.no2":   0.90,
    "air.so2":   0.75,
    "air.co":    0.85,
    "air.hcho":  0.85,
    "air.o3":    0.85,
    "air.aai":   0.85,
    "air.pm25":  0.80,
    "air.pm10":  0.80,
    "air.aod":   0.90,
    # GHG pillar
    "ghg.ch4":   0.85,
    "ghg.co2":   1.00,    # ODIAC inventory; no per-pixel QA concept
    "ghg.viirs": 0.85,
    # Nature pillar
    "nature.kba":         1.00,                       # Vector reference data
    "nature.dw":          0.90,
    "nature.habitat":     0.85,
    "nature.forest_loss": 1.00,                       # Annual Hansen rasters
    "nature.ndvi":        0.90,
    "nature.water":       0.90,
    "nature.recovery":    0.85,
    "nature.regional_loss_evidence": 1.00,            # Hansen-derived
}

# Expected observations per analysis-window day. N_valid normalises against
# `expected_n = expected_per_day · window_days` so cloud-affected windows
# surface low N_valid even at full QA.
#
# Asset notes:
#   * S5P TROPOMI gases + CAMS PM + MAIAC AOD + VIIRS NTL: ~daily revisit.
#   * MODIS NDVI (MOD13Q1): 16-day composites → ~1 every 16 days ≈ 0.0625;
#     conservatively raised to 0.0625 (no fractional revisit credit).
#   * Indicators in SINGLE_SNAPSHOT_INDICATORS use a 1.0 pass-through.
EXPECTED_N_PER_WINDOW_DAY: dict[str, float] = {
    # TROPOMI gases — tropical-latitude clean-pixel rate is ~30 % per day
    # after qa_value filtering and cloud masking. Calibrated against
    # Sapezal + Brasilia 90-day Feb–May 2026 window (Step 8 recalibration,
    # 22 May 2026).
    "air.no2":   0.3,
    "air.so2":   0.3,
    "air.co":    0.3,
    "air.hcho":  0.3,
    "air.o3":    0.3,
    "air.aai":   0.3,
    # CAMS PM is daily model output regardless of cloud cover.
    "air.pm25":  1.0,
    "air.pm10":  1.0,
    # MODIS MAIAC AOD — cloudy-sky retrieval limited; ~30 % is realistic.
    "air.aod":   0.3,
    # Sentinel-5P CH4 — same cadence as other TROPOMI gases.
    "ghg.ch4":   0.3,
    # VIIRS NTL — nightly composite generally produced.
    "ghg.viirs": 1.0,
    "nature.ndvi": 0.2,
}

# Single-snapshot indicators: N_valid pass-through to 1.0 when the
# composite / annual raster was produced, 0.0 when skipped. These don't
# have a per-day observation count.
SINGLE_SNAPSHOT_INDICATORS: frozenset[str] = frozenset({
    "ghg.co2",
    "nature.dw",
    "nature.habitat",
    "nature.forest_loss",
    "nature.kba",
    "nature.water",
    "nature.recovery",
    "nature.regional_loss_evidence",
})

# Native pixel area (m²) per indicator, used by the spatial_context term.
# `0.0` flags vector / non-raster data → spatial_context = 1.0 (no penalty).
NATIVE_PIXEL_AREA_M2: dict[str, float] = {
    # S5P TROPOMI L3 grid is ~1113 m; on-ground footprint per audit is
    # different but we score the L3-grid since that's what we reduce over.
    "air.no2":   1113.2 ** 2,
    "air.so2":   1113.2 ** 2,
    "air.co":    1113.2 ** 2,
    "air.hcho":  1113.2 ** 2,
    "air.o3":    1113.2 ** 2,
    "air.aai":   1113.2 ** 2,
    "air.pm25":  44500.0 ** 2,                        # CAMS ~44.5 km
    "air.pm10":  44500.0 ** 2,
    "air.aod":   1000.0 ** 2,                         # MAIAC 1 km
    "ghg.ch4":   CH4_NATIVE_SCALE_M ** 2,             # ~7 km on-ground footprint
    "ghg.co2":   1000.0 ** 2,                         # ODIAC 1 km
    "ghg.viirs": 463.83 ** 2,
    "nature.kba":         0.0,                        # Vector data
    "nature.dw":          10.0 ** 2,
    "nature.habitat":     10.0 ** 2,
    "nature.forest_loss": 30.92 ** 2,                 # Hansen native pixel
    "nature.ndvi":        250.0 ** 2,
    "nature.water":       10.0 ** 2,
    "nature.recovery":    250.0 ** 2,
    "nature.regional_loss_evidence": 30.92 ** 2,
}

# IC_v4 §3.2 sub-formula tunables.
# KBA proximity decay (km): `exp(-dist_km / KBA_DISTANCE_DECAY_KM)` halves
# every ~7 km — concern decays fast but not catastrophically.
KBA_DISTANCE_DECAY_KM: float = 10.0
# Negative_Vegetation_Trend threshold: −0.01 NDVI/yr means losing 0.10 NDVI
# over a decade. Below that rate the slope is inside natural inter-annual
# variability and not reliably distinguishable from noise.
NDVI_NEGATIVE_TREND_THRESHOLD: float = -0.01
# Water_or_FloodedVegetation_Exposure saturation point: 20% combined
# aquatic/wetland cover = score 1.0.
WATER_FLOODED_VEG_SATURATION_PCT: float = 20.0
