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

# M-TIER-A3 LM7 — when the Background_Ring's geometric land fraction
# (MOD44W mean over the annulus) is below this threshold, treat the ring
# as effectively-water-only and route through the existing ring-empty
# skip path (BackgroundRingNoDataError) with a distinct `reason_detail`
# so analytics can separate "ring over ocean" from "ring sparse-coverage".
# Below 5% land coverage the residual land-pixel set is too small to
# carry a meaningful background reduction.
LAND_MASK_FRACTION_MIN_THRESHOLD: float = 0.05

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
# Wind_Consistency (0.15) and Sector_Match (0.10) are deferred to v1.x.
# M-ATTRIB-A1 (AT15): nearby_source_isolation (was 0.13) is removed from this
# *measurement-quality* aggregate — it's an attributability concept, not a
# measurement-quality term, and its v1 value is a fixed 1.0 placeholder that
# inflated the aggregate. `compute_nearby_source_isolation` still emits the
# field (reserved for a future attributability surface, per AT2 system-wide
# framing) but it no longer enters this dict. The surviving three terms are
# renormalised per spec §4.5; sums to 1.00.
GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS: dict[str, float] = {
    "ghg.temporal_coverage":              0.34,
    "ghg.spatial_resolution_suitability": 0.33,
    "ghg.retrieval_inventory_quality":    0.33,
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

# M-UI-A6 §6 — cumulative Hansen loss (%) at or above which the C7 verbal
# summary may mention Hansen as reference context (corroboration or
# divergence vs the live nature signal). Below this, Hansen is omitted from
# the prose to avoid noise (§6.3). Hansen remains visible as a C5 reference
# card regardless. Shares the card's "moderate" boundary in
# ui.components.c5_drilldown (kept numerically aligned by intent).
HANSEN_VERBAL_MENTION_THRESHOLD: float = 1.0

# IC_v4 §3.2 + §7.4 — Vegetation_Condition_v1 (EVI removed). The negative
# weight on recovery is intentional: positive recovery signal subtracts
# from concern.
VEGETATION_CONDITION_WEIGHTS: dict[str, float] = {
    "nature.ndvi.inverted_anomaly": 0.45,
    "nature.ndvi.negative_trend":   0.25,
    "nature.low_ndvi.pct_norm":     0.20,
    "nature.recovery.score":       -0.10,
}

# IC_v4 §3.3 — Nature measurement quality (renamed from Quality_Attribution).
# M-ATTRIB-A1 (AT13 / AT14): this aggregate is now *measurement quality* only.
# Two terms were removed because they are not measurement quality:
#   - supplier_spatial_link (was 0.15) → categorical attributability surface
#     (centroid offset; see engine.core.attributability + nature.habitat
#      .attributability_state). It does NOT enter any composite.
#   - external_driver_screening (was 0.10) → reference data (regional loss
#     evidence ratio on the M-UI-A6 Hansen card). It does NOT enter any
#     composite or measurement-quality score.
# The four surviving sub-scores are renormalised per spec §4.2 first-pass.
# Sums to 1.00.
NATURE_MEASUREMENT_QUALITY_WEIGHTS: dict[str, float] = {
    "nature.valid_pixel_coverage":      0.35,   # was 0.20
    "nature.cloud_observation_quality": 0.25,   # was 0.20
    "nature.dw.class_confidence":       0.20,   # unchanged
    "nature.seasonal_comparability":    0.20,   # was 0.15
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

# Per-indicator chunk size for _server_side_hf. Indicators not in this dict
# fall through to the default. Calibrated against Sapezal 5 km and Distrito
# Federal 43.1 km buffers, 90-day windows (v1x followup #1, 24 May 2026).
#
# Rationale: Step 8 Option A introduced client-side date chunking to keep
# each per-indicator getInfo() under EE's 5-minute hard timeout for
# high-cadence multi-swath products (MAIAC AOD at ~58 granules/day,
# S5P L3 CH4 at ~14/day). For low-cadence products (~1 image/day), the
# chunking is pure overhead — ~30-45s per indicator burned on graph
# compilation + 9 sequential getInfo round-trips when one call would
# have sufficed. Sapezal's ~7-minute total runtime is dominated by this.
# The lookup keeps chunking ONLY where it's needed.
SERVER_SIDE_HF_CHUNK_DAYS_PER_INDICATOR: dict[str, int] = {
    # Low-cadence products: single chunk = full window, no chunking overhead.
    "air.no2":     90,
    "air.so2":     90,
    "air.co":      90,
    "air.hcho":    90,
    "air.o3":      90,
    "air.aai":     90,
    "air.pm25":    90,
    "air.pm10":    90,
    "ghg.viirs":   90,
    "nature.ndvi": 90,
    # High-cadence multi-swath products: keep chunked to stay under EE's
    # 5-minute getInfo timeout at large buffers (Distrito Federal 43.1 km).
    "air.aod":     10,   # ~58 granules/day → ~5,200/window → needs chunking
    "ghg.ch4":     10,   # ~14 granules/day, conservative chunking until verified
}
SERVER_SIDE_HF_CHUNK_DAYS_DEFAULT: int = 10  # fallback when indicator not in map


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

# M-UI-A1-SURFACE Sub-milestone 4 (24 May 2026): per-indicator family
# classifier driving the P-09 Indicator Library's "What confidence
# means for this indicator" expander. Three families:
#
#   - live_revisit:   sensors with per-observation noise; the A1
#                     confidence_terms (qa/n_valid/anomaly_strength/
#                     spatial_context × column_to_surface multiplier)
#                     genuinely move with the data per screening.
#   - single_snapshot: static or annual reference datasets without
#                     per-observation noise; confidence saturates at
#                     1.0 by construction.
#   - derived:        sub-aggregates / pillar priorities / composite
#                     score. Their confidence flows from the
#                     survivor-renormalised aggregate of contributing
#                     indicators (strict-None propagation; composite
#                     uses the conservative-aggregation min rule).
#
# Keys are mixed full-id and base-id. The lookup helper in
# `ui.components.p09_library._confidence_explanation_for` tries the
# full ID first, then falls back to the first two dot-segments — the
# raw-vs-derived collision at "nature.habitat" (raw natural_loss_ha vs
# derived conversion_score) is disambiguated by registering the
# derived ID's FULL form explicitly.
INDICATOR_CONFIDENCE_FAMILY: dict[str, str] = {
    # Raw — live-revisit (base form, matches all .score / .* suffixes).
    "air.no2":     "live_revisit",
    "air.so2":     "live_revisit",
    "air.co":      "live_revisit",
    "air.hcho":    "live_revisit",
    "air.o3":      "live_revisit",
    "air.aai":     "live_revisit",
    "air.aod":     "live_revisit",
    "air.pm25":    "live_revisit",
    "air.pm10":    "live_revisit",
    "ghg.ch4":     "live_revisit",
    "ghg.viirs":   "live_revisit",
    "nature.ndvi": "live_revisit",
    # Raw — single-snapshot (base form).
    "ghg.co2":                       "single_snapshot",  # ODIAC annual
    "nature.kba":                    "single_snapshot",
    "nature.habitat":                "single_snapshot",
    "nature.forest_loss":            "single_snapshot",  # Hansen annual
    "nature.regional_loss_evidence": "single_snapshot",
    "nature.recovery":               "single_snapshot",
    "nature.water":                  "single_snapshot",
    "nature.dw":                     "single_snapshot",
    # Derived — full id, NOT base, so "nature.habitat.conversion_score"
    # is correctly tagged derived and doesn't fall through to the raw
    # "nature.habitat" single_snapshot entry via the base-form fallback.
    "air.pollution_proxy_score":        "derived",
    "air.spatiotemporal_anomaly_score": "derived",
    "air.trend_score":                  "derived",
    # M-ATTRIB-A1 (AT16): new measurement-quality ID + legacy alias (window).
    "air.measurement_quality_score":    "derived",
    "air.attribution_confidence_score": "derived",
    "ghg.core_audit_support":           "derived",
    "ghg.spatiotemporal_anomaly":       "derived",
    "ghg.trend":                        "derived",
    "ghg.data_quality_attribution":     "derived",
    "nature.biodiversity_exposure":     "derived",
    "nature.habitat.conversion_score":  "derived",
    "nature.vegetation_condition":      "derived",
    "nature.measurement_quality":       "derived",
    "air.audit_followup_priority":      "derived",
    "ghg.audit_followup_priority":      "derived",
    "nature.followup_priority":         "derived",
    "composite.overall_screening":      "derived",
}

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

# M-ATTRIB-A1 (AT12 / §4.7) — habitat-conversion attributability via the
# supplier→centroid distance (Approach C). These are categorical thresholds
# for `engine.core.attributability.compute_habitat_attributability`; they do
# NOT enter any composite or measurement-quality score.
#   high      ≤ HABITAT_SPATIAL_LINK_HIGH_KM
#   moderate  (HIGH, MOD]
#   low       > HABITAT_SPATIAL_LINK_MOD_KM
#   sparse    n_change_pixels < N_MIN_PIXELS_FOR_CENTROID (or no centroid)
# CALIBRATION (AT20 / Q-AT-1): first-pass values; flagged for a joint
# calibration sweep with the M-WIND-A1 v2.0 thresholds after first demo runs.
# Note: N_MIN_PIXELS_FOR_CENTROID counts pixels at the *adaptive reduction
# scale*, not DW's 10 m native scale — so the represented area scales with
# AOI size. Revisit during calibration if region-scale AOIs over/under-trip
# the sparse gate.
N_MIN_PIXELS_FOR_CENTROID: int = 10
HABITAT_SPATIAL_LINK_HIGH_KM: float = 1.0
HABITAT_SPATIAL_LINK_MOD_KM: float = 3.0


# ---------------------------------------------------------------------------
# Wind attributability — M-WIND-A1 v2.0 (28 May 2026)
# ---------------------------------------------------------------------------
# Air-pillar attributability surface, parallel to the M-ATTRIB-A1 habitat
# layer (AT19 shared bucket grammar). Categorical only — does NOT enter the
# M-TIER-A1 confidence chain or any composite score (locked decision WA1).
#
# Per spec §5.2, the category depends on BOTH the mean wind speed and the
# upwind/downwind background-ring asymmetry ratio during anomaly days:
#
#   high      mean_wind_speed < WIND_SPEED_HIGH_MAX_MS   (< 2.0 m/s)
#             AND mean_asymmetry_ratio < WIND_ASYMMETRY_HIGH_MAX (< 1.5)
#   moderate  mean_wind_speed in [HIGH_MAX, LOW_MIN)  or
#             mean_asymmetry_ratio in [HIGH_MAX, LOW_MIN)
#   low       mean_wind_speed >= WIND_SPEED_LOW_MIN_MS  (>= 5.0 m/s)
#             OR mean_asymmetry_ratio >= WIND_ASYMMETRY_LOW_MIN (>= 2.5)
#   sparse    n_anomaly_days < WIND_N_MIN_ANOMALY_DAYS — too few anomaly
#             days to assess; no arrow rendered.
#
# The 2 m/s breakpoint aligns with the Pasquill calm-to-light wind threshold
# (WA8). The 5 m/s breakpoint matches the Pasquill light-to-moderate wind
# transition. Asymmetry breakpoints (1.5, 2.5) are first-pass intuitions
# flagged for calibration sweep alongside M-ATTRIB-A1's habitat thresholds
# (Q-WA-1 / Q-AT-1, joint sweep after first demo runs).
WIND_SPEED_HIGH_MAX_MS: float = 2.0
WIND_SPEED_LOW_MIN_MS:  float = 5.0
WIND_ASYMMETRY_HIGH_MAX: float = 1.5
WIND_ASYMMETRY_LOW_MIN:  float = 2.5

# WA9 — days where mean wind speed is below this threshold are excluded
# from the direction / asymmetry calculation (no meaningful direction at
# calm), but still count toward the speed mean and the anomaly-day total.
WIND_CALM_THRESHOLD_MS: float = 1.0

# WA10 — minimum anomaly-day sample size. Below this, attributability is
# "sparse" and no arrow renders on the M-UI-A5 map.
WIND_N_MIN_ANOMALY_DAYS: int = 5

# WA2 — five in-scope Air-pillar indicators. Wind attribution is computed
# only for these; out-of-scope indicators emit no wind fields in
# provenance.extra. Frozenset so the membership check is O(1) and the
# constant is hashable / immutable.
WIND_ATTRIBUTABILITY_INDICATORS: frozenset[str] = frozenset({
    "air.no2",
    "air.so2",
    "air.hcho",
    "air.aai",
    "air.aod",
})

# ERA5 hourly reanalysis — wind components at 10 m. Spec §5.1 sampling.
# Asset choice locked by docs/v1x_followups.md correction (24 May 2026):
# the v1.0 spec pointed at ERA5_LAND/HOURLY but that asset lacks the
# boundary-layer-height band; ECMWF/ERA5/HOURLY is the right asset for the
# shared ERA5 helper (also serves the deferred Tier C2 BLH work). Surface-
# resolution: ~28 km grid (single cell carries the supplier point cleanly).
ERA5_HOURLY_ASSET:    str = "ECMWF/ERA5/HOURLY"
ERA5_WIND_U_BAND:     str = "u_component_of_wind_10m"
ERA5_WIND_V_BAND:     str = "v_component_of_wind_10m"
# ERA5_LAND_HOURLY_ASSET retained for reference — works for wind-only but
# lacks boundary_layer_height for the Tier C2 follow-on.
ERA5_LAND_HOURLY_ASSET: str = "ECMWF/ERA5_LAND/HOURLY"


# ---------------------------------------------------------------------------
# Analysis window — user-configurable per M-UI-A3
# ---------------------------------------------------------------------------
# Default screening window length. Previously hard-coded at the UI layer
# (p04_form.py _SCREENING_WINDOW_DAYS and a stray literal in p07_form.py
# _commit_and_navigate) — centralised here so the picker fixture
# (demo/window_picker_profiles.json) and any future caller share a
# single source of truth. M-UI-A3 wires the window picker on top of
# this default; users override per-screening via the picker.
SCREENING_WINDOW_DAYS_DEFAULT: int = 90

# ---------------------------------------------------------------------------
# Cloudy-period & climatology fallbacks  (M-FALLBACK-A1)
# ---------------------------------------------------------------------------
# Two coordinated fallbacks for sparse-coverage AOIs (spec §4):
#   1.1 SPPY  — when the SITE buffer has zero usable pixels, substitute the
#               same calendar period of the previous year. Confidence ×0.60.
#   1.2 CLIM  — when the BACKGROUND ring is unavailable (water-only post
#               land-mask, or empty), substitute per-country climatology
#               (median ± σ) for the ring baseline. Confidence ×0.75.
# Both compose multiplicatively with the M-TIER-A1 COLUMN_TO_SURFACE chain
# (engine/core/confidence.compute_indicator_confidence). Each defaults to
# 1.0 when its condition didn't fire — see spec §4.6.
#
# FB4 (locked 28 May 2026): the SPPY trigger is the engine's *existing*
# zero-pixel failure (SiteBufferNoDataError), NOT a new coverage-fraction
# threshold — the engine has no such fraction today. "Sparse-but-nonzero"
# coverage still computes normally and is surfaced via the N_valid
# confidence term; only true zero-coverage triggers a fallback.
TEMPORAL_FALLBACK_MULTIPLIER: float = 0.60      # FB8 — SPPY (year-old data)
CLIMATOLOGY_FALLBACK_MULTIPLIER: float = 0.75   # FB11 — regional baseline

# Sliding-lookback retry (FB5, single-supplier only): step backward from the
# window start in fixed increments, taking the first window with coverage.
SLIDING_LOOKBACK_STEP_DAYS: int = 90
SLIDING_LOOKBACK_MAX_STEPS: int = 8   # ~2 years of 90-day steps before giving up

# AOI scale class (FB19 / §4.7) — derived from the site-buffer radius and
# stamped into provenance.extra.aoi_scale_class. The >100 km / >200 km
# cutoffs also drive the Mode-3 large-AOI setup warning (P-04/P-07). The
# thresholds are deliberately loose (Q-FB-4) — tune on demo experience.
AOI_SCALE_CLASS_SITE_MAX_KM: float = 25.0       # ≤25 km  → "site"
AOI_SCALE_CLASS_REGIONAL_MAX_KM: float = 100.0  # 25–100 km → "regional"; >100 km → "biome"

# Climatology fixture (1.2). Lives alongside the other demo fixtures
# (demo/climatology.json); the loader is engine/core/climatology.py. The
# 11 in-scope indicators (FB10): 9 Air + CH₄ + VIIRS. KBA/DW/Hansen/ODIAC/
# NDVI are out of 1.2's scope by construction (no background ring / weak
# per-country median).
CLIMATOLOGY_INDICATORS: tuple[str, ...] = (
    "air.no2", "air.so2", "air.co", "air.hcho", "air.o3",
    "air.aai", "air.pm25", "air.pm10", "air.aod",
    "ghg.ch4", "ghg.viirs",
)
# Country-boundary asset for centroid→country lookup (A.4 recon: reuse the
# asset already in the repo for consistency — demo/regions.py uses GAUL
# level1; level0 is its country-polygon parent). Resolves Q-FB-1 toward
# consistency.
CLIMATOLOGY_COUNTRY_ASSET: str = "FAO/GAUL/2015/level0"

# Earliest valid start date for screening. ODIAC CO₂ has the most
# restrictive coverage window (2020-01-01 to 2023-12-31, per
# engine.ghg coverage_window) but it routinely silent-skips with
# skipped_reason='out_of_coverage' for screening windows that fall
# outside its vintage — so we don't let it set the floor. The
# second-most-restrictive dataset is Sentinel-5P TROPOMI, which
# powers most of the air pillar (NO₂, SO₂, CO, HCHO, O₃, AAI) and
# the GHG CH₄ indicator. S5P became operational in late 2018; CH₄
# specifically stabilised in early 2019. The 2019-01-01 floor below
# is the safe "all S5P products available" date.
EARLIEST_SCREENING_DATE: str = "2019-01-01"
