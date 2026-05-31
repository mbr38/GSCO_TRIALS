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
# @parameter
# tier: spec-mandated
# rationale: The green / amber / red cut points for the headline composite
#     score and the per-pillar follow-up priorities. A score below 0.33 reads
#     green, 0.33-0.66 amber, above 0.66 red. These boundaries are prescribed
#     by the Wireframes traffic-light spec, not chosen by judgment — changing
#     them is a methodology decision (it reframes what "low/moderate/high
#     concern" means across the whole tool).
# source: docs/Wireframes_All_v4.md Appendix C.1; docs/Verbal_Summary_Templates_v1.md §1
# last_reviewed: 2026-05-29
# applies_to: [composite.overall_screening, air.audit_followup_priority, ghg.audit_followup_priority, nature.followup_priority]
TRAFFIC_LIGHT_THRESHOLDS: tuple[float, float] = (0.33, 0.66)

# ---------------------------------------------------------------------------
# Repeatable core method  (IC_v4 §0.2 step 5, §0.4)
# ---------------------------------------------------------------------------
# @parameter
# tier: spec-mandated
# rationale: Per-day z-score gate for an "anomalous day" — the standard 2σ
#     threshold. M-DIAG-A1 originally pre-diagnosed this as a calibration
#     concern, but that "AAI fires every day / Norilsk fires never" symptom
#     turned out to be a key-naming bug in `_server_side_hf` (see
#     docs/M-DIAG-A1_diagnosis_report.md §7), not a threshold problem.
#     M-DIAG-A2 Step C.3 (29 May 2026) reviewed the post-fix per-day z
#     distribution at the 5 calibration seeds: per-day-z spans realistic
#     ranges (e.g. Norilsk NO2 median +2.18, max +24.4); the 2.0 gate
#     produces hf values 0.26-0.84 across pollutants and seeds. The spec
#     value stands; promoted from "first-pass" to "spec-mandated" per
#     IC §0.4's 2σ convention now that the detector is functional.
# source: docs/Indicators_Computation_v4.md §0.4; M-DIAG-A1 fix; M-DIAG-A2 §4.2 calibration record
# last_reviewed: 2026-05-29
# applies_to: [air.no2, air.so2, air.co, air.hcho, air.o3, air.aai, air.aod, air.pm25, air.pm10, ghg.viirs, nature.ndvi]
ANOMALY_Z_THRESHOLD: float = 2.0

# @parameter
# tier: spec-mandated
# rationale: The squashing constant k in the repeatable-core normalisation
#     that maps an unbounded magnitude onto a 0-1 score. Its value is fixed by
#     the methodology document, not tuned per indicator — it sets how quickly
#     the score saturates and is shared across every normalised indicator, so
#     changing it is a cross-cutting methodology decision.
# source: docs/Indicators_Computation_v4.md §0.4
# last_reviewed: 2026-05-29
# applies_to: [air.no2, air.so2, air.co, air.hcho, air.o3, air.aai, air.aod, air.pm25, air.pm10, ghg.viirs, nature.ndvi]
NORMALISATION_K: float = 3.0

# ---------------------------------------------------------------------------
# Habitat conversion  (IC_v4 §3.1, §3.2)
# ---------------------------------------------------------------------------
HABITAT_BASELINE_YEARS: int = 5
# @parameter
# tier: first-pass
# rationale: The natural-habitat loss fraction at which a habitat-conversion
#     `_pct` term saturates to a score of 1.0 — i.e. losing 10% of natural
#     cover over the analysis window is treated as maximal concern, and
#     anything above is clamped. The 10% figure is a first-pass judgment about
#     where "alarming" begins; it has not been calibrated against observed
#     conversion-rate distributions.
# source: docs/Indicators_Computation_v4.md §3.1, §3.2; calibration pending
# last_reviewed: 2026-05-29
# applies_to: [nature.habitat]
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

# IC_v4 §1.3 — Air Audit Follow-Up Priority terms.
# M-TREND-A1 (TR10 / decision-log E3): the "trend" term (was 0.20) is
# removed — trend is now a per-indicator drill-down only and never enters
# composite arithmetic. The surviving three terms are renormalised over the
# remaining 0.80 so the dict still sums to 1.00.
# Pre-change values: proxy 0.35, anomaly 0.30, trend 0.20, confidence 0.15.
AIR_FOLLOWUP_WEIGHTS: dict[str, float] = {
    "proxy":      0.35 / 0.80,   # 0.4375
    "anomaly":    0.30 / 0.80,   # 0.3750
    "confidence": 0.15 / 0.80,   # 0.1875
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
# M-CH4-A1 (30 May 2026): CH₄ reclassified from severity scoring to
# reference data (alongside Hansen + ODIAC), per the GHG↔ODIAC+OCO-2/OCO-3
# validation (docs/ghg_odiac_validation.md §1, §6.1, §10): the CH₄ anomaly-z
# proxy fired at only 1/25 stratified sites at 5 km AOI, and §10 Response B
# showed widening to 15 km drops that to 0/25 — the TROPOMI ~7 km footprint
# vs screening-AOI ratio cannot be fixed by geometry. CH₄_Context_Adjusted is
# therefore removed from this composite; the surviving two live signals
# renormalise over 0.54 → 0.815 / 0.185. VIIRS-driven combustion now
# dominates, which the validation supports (VIIRS↔ODIAC Spearman 0.70).
#
# Pre-M-CH4-A1 values (kept for reference): ch4_adj 0.46, combustion 0.44,
# activity 0.10. Pre-M5.5b: co2 0.39, ch4_adj 0.28, combustion 0.27,
# activity 0.06.
CORE_GHG_AUDIT_SUPPORT_WEIGHTS: dict[str, float] = {
    "ghg.combustion_proxy":     0.815,   # M-CH4-A1: 0.44 / 0.54 ≈ 0.8148 → 0.815
    "ghg.activity_score":       0.185,   # M-CH4-A1: 0.10 / 0.54 ≈ 0.1851 → 0.185
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
# M-TREND-A1 (TR10 / decision-log E3): the "trend" term (was 0.20) is
# removed for the same reason as Air — trend is drill-down-only. The
# surviving three terms are renormalised over the remaining 0.80.
# Pre-change values: core_support 0.40, anomaly 0.25, trend 0.20, quality 0.15.
GHG_FOLLOWUP_WEIGHTS: dict[str, float] = {
    "core_support": 0.40 / 0.80,   # 0.5000
    "anomaly":      0.25 / 0.80,   # 0.3125
    "quality":      0.15 / 0.80,   # 0.1875
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
# @parameter
# tier: first-pass
# rationale: Ring-vs-buffer Hansen loss-rate ratio above which the regional
#     loss evidence flags an external driver — i.e. when forest loss in the
#     surrounding ring is running at 2× the site-buffer rate, the loss looks
#     regional rather than supplier-specific. The 2× factor is a first-pass
#     judgment about what counts as "notably higher"; not calibrated against
#     observed loss-rate distributions.
# source: docs/Indicators_Computation_v4.md §7.5; docs/Indicators_Audit_and_v1x_Roadmap.md §9.3; calibration pending
# last_reviewed: 2026-05-29
# applies_to: [nature.forest_loss, nature.regional_loss_evidence]
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
# M-TREND-A1 (TR17 / decision-log N2): the NDVI *slope* term
# (`nature.ndvi.negative_trend`, was 0.25) is demoted to drill-down-only —
# an NDVI slope is environmentally valid only over the long-window trend
# view, not the seasonally-honest screening snapshot (N2-ENV). The freed
# 0.25 is redistributed across the POSITIVE terms only (0.45/0.65 and
# 0.20/0.65), keeping recovery's −0.10 offset. composite keeps the
# vegetation-*state* signal (inverted_anomaly) + the multi-year land-change
# signal (Habitat_Conversion, untouched).
# Pre-change values: inverted_anomaly 0.45, negative_trend 0.25,
# low_ndvi.pct_norm 0.20, recovery −0.10.
VEGETATION_CONDITION_WEIGHTS: dict[str, float] = {
    "nature.ndvi.inverted_anomaly": 0.45 / 0.65,   # 0.6923
    "nature.low_ndvi.pct_norm":     0.20 / 0.65,   # 0.3077
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
    "ghg.viirs":   "live_revisit",
    "nature.ndvi": "live_revisit",
    # Raw — single-snapshot (base form).
    # M-CH4-A1: ghg.ch4 reclassified as reference data — its P-09 entry shows
    # the single-snapshot confidence explanation (matching Hansen/ODIAC). This
    # tag drives only the P-09 explanatory text; CH₄ is NOT added to
    # SINGLE_SNAPSHOT_INDICATORS (it retains genuine per-day TROPOMI data, so
    # its N_valid→confidence math stays on the live-revisit path).
    "ghg.ch4":                       "single_snapshot",  # M-CH4-A1 reference data
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
    # M-TREND-A1 (TR10): air.trend_score removed (drill-down-only).
    # M-ATTRIB-A1 (AT16): new measurement-quality ID + legacy alias (window).
    "air.measurement_quality_score":    "derived",
    "air.attribution_confidence_score": "derived",
    "ghg.core_audit_support":           "derived",
    "ghg.spatiotemporal_anomaly":       "derived",
    # M-TREND-A1 (TR10): ghg.trend removed (drill-down-only).
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
# @parameter
# tier: first-pass
# rationale: Decay length (km) in the KBA proximity score `exp(-dist_km / k)`.
#     With k = 10 km the concern halves roughly every 7 km — fast enough that a
#     supplier 30 km from a Key Biodiversity Area scores near zero, slow enough
#     that adjacency isn't a step function. The decay shape comes from the
#     methodology; the 10 km length scale is a first-pass judgment.
# source: docs/Indicators_Computation_v4.md §3.2; calibration pending
# last_reviewed: 2026-05-29
# applies_to: [nature.kba]
KBA_DISTANCE_DECAY_KM: float = 10.0
# Negative_Vegetation_Trend threshold: −0.01 NDVI/yr means losing 0.10 NDVI
# over a decade. Below that rate the slope is inside natural inter-annual
# variability and not reliably distinguishable from noise.
NDVI_NEGATIVE_TREND_THRESHOLD: float = -0.01
# Water_or_FloodedVegetation_Exposure saturation point: 20% combined
# aquatic/wetland cover = score 1.0.
# @parameter
# tier: first-pass
# rationale: Combined aquatic / flooded-vegetation cover percentage at which
#     the water-exposure term saturates to 1.0. At 20% wetland/water cover the
#     site is treated as maximally water-exposed. The 20% saturation point is a
#     first-pass judgment about where exposure is "as high as it matters"; not
#     calibrated.
# source: docs/Indicators_Computation_v4.md §3.2; calibration pending
# last_reviewed: 2026-05-29
# applies_to: [nature.water, nature.biodiversity_exposure]
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
# @parameter
# tier: first-pass
# rationale: Minimum number of change pixels needed to compute a habitat-loss
#     centroid for the supplier→loss spatial link. Below 10 pixels the centroid
#     is too noisy, so attributability is reported "sparse". Counted at the
#     adaptive reduction scale (not DW's 10 m native scale), so the represented
#     area scales with AOI size — flagged for revisit if region-scale AOIs
#     over/under-trip this gate during calibration.
# source: M-ATTRIB-A1 §4.7 (AT20 / Q-AT-1); calibration pending
# last_reviewed: 2026-05-29
# applies_to: [nature.habitat]
N_MIN_PIXELS_FOR_CENTROID: int = 10
# @parameter
# tier: first-pass
# rationale: Upper distance bound (km) for "high" habitat attributability —
#     when the supplier point is within 1 km of the loss centroid, the loss is
#     plausibly attributable to the supplier. First-pass value flagged for a
#     joint calibration sweep with the wind thresholds (Q-AT-1 / Q-WA-1).
# source: M-ATTRIB-A1 §4.7 (AT12 / Approach C); calibration pending
# last_reviewed: 2026-05-29
# applies_to: [nature.habitat]
HABITAT_SPATIAL_LINK_HIGH_KM: float = 1.0
# @parameter
# tier: first-pass
# rationale: Upper distance bound (km) for "moderate" habitat attributability;
#     beyond 3 km the link is "low". The 1 km / 3 km pair carves the
#     high/moderate/low bands. First-pass values pending the joint calibration
#     sweep (Q-AT-1).
# source: M-ATTRIB-A1 §4.7 (AT12 / Approach C); calibration pending
# last_reviewed: 2026-05-29
# applies_to: [nature.habitat]
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
#
# Q-WA-1 calibration finding (29 May 2026, M-WIND-A1 v2.0 demo seed prep).
# Across five seeded demos (Sapezal, Brasilia, Suape, Comodoro Rivadavia,
# Norilsk smelter) NONE landed at state="low":
#   - The three tropical seeds (Sapezal, Brasilia, Suape) land at AAI
#     Moderate because AAI's bg_std collapses to ~0 there, inflating the
#     anomaly day count to ~89 days at speeds in the 2.4-4.1 m/s range —
#     below the 5.0 m/s Low speed gate.
#   - Patagonian Comodoro lands sparse: genuinely clean uniform air, no
#     per-day z>=2 spike.
#   - Norilsk Nornickel (world's strongest single-source SO2) returns
#     NO2 aggregate z=3.25 but per-day hf=0 — the M-TIER-A1 HF detector's
#     ring-spatial-std baseline includes part of the plume, so per-day
#     spikes can't cross 2σ even when the aggregate clearly does.
# The structural blocker is in the HF detector + ring architecture, not
# in these thresholds. v1.x calibration should consider:
#   (a) dropping WIND_SPEED_LOW_MIN_MS to ~3.5 m/s so realistic 3-4 m/s
#       wind regimes can produce Low — would flip Suape and many real
#       coastal industrial sites to Low without a detector change;
#   (b) revisiting the HF detector to use a temporal std baseline rather
#       than ring-spatial std (would catch the Norilsk case structurally);
#   (c) per-pollutant bucket calibration (AAI's bg_std issue suggests
#       AAI may need its own wind thresholds or be removed from scope).
# Deferring the change to v1.x is the right call — the M-WIND-A1 spec
# lock WA7 stands, the surfaces are validated by unit tests + smoke tool.
# @parameter
# tier: first-pass
# rationale: Upper wind-speed bound for "high" attributability — below 2 m/s
#     the air is calm enough that an observed plume is plausibly local to the
#     site. Aligns with the Pasquill calm-to-light wind threshold (WA8).
#     M-DIAG-A2 Step C.3 (29 May 2026) reviewed against post-fix 5-seed
#     baseline: kept unchanged. The Norilsk NO2 case (s=2.8 m/s wind, lands
#     "moderate" not "high") suggested raising to ~3.0 m/s would match the
#     operator's high-attributability intuition there, but doing so flips
#     Sapezal NO2/AAI (s=2.0-2.7 m/s) to "high" which contradicts the
#     "moderate" intuition for tropical clean-air seeds. Anti-overfitting
#     argued against. The Brasilia NO2/SO2 cases firing "high" (s=1.2-1.8 m/s)
#     are methodologically defensible. Stays first-pass — re-review when
#     additional non-tropical industrial seeds enter the calibration set.
# source: M-WIND-A1 v2.0 spec §5.2 (Pasquill calm-to-light); M-DIAG-A2 §4.2 (no change)
# last_reviewed: 2026-05-29
# applies_to: [air.no2, air.so2, air.hcho, air.aai, air.aod]
WIND_SPEED_HIGH_MAX_MS: float = 2.0
# @parameter
# tier: calibrated
# rationale: Lower wind-speed bound for "low" attributability — at or above
#     3.5 m/s the wind is brisk enough that an observed plume is more likely
#     advected from elsewhere than emitted locally. M-DIAG-A2 Step C.3
#     (29 May 2026) lowered this from the original 5.0 m/s to 3.5 m/s based
#     on post-fix 5-seed baseline evidence: Suape (coastal industrial, ~4 m/s
#     wind regime) was operator-expected "moderate-to-low" but landed
#     uniformly moderate because every Air indicator's wind speed sat just
#     below the 5 m/s gate; dropping to 3.5 m/s shifts Suape NO2/HCHO/AAI/SO2
#     to "low" matching expectation, and Q-WA-1 explicitly predicted this
#     adjustment. The 3.5 m/s value is approximately the Pasquill light-to-
#     moderate transition's lower edge (the original 5.0 m/s was its upper
#     edge); both are defensible meteorologically. Anti-overfitting note:
#     Sapezal/Brasilia/Comodoro/Norilsk indicators are not affected by this
#     change (their speeds are well below or well above the 3.5 m/s pivot).
# source: M-WIND-A1 v2.0 spec §5.2; M-DIAG-A2 §4.2 calibration record
# last_reviewed: 2026-05-29
# applies_to: [air.no2, air.so2, air.hcho, air.aai, air.aod]
WIND_SPEED_LOW_MIN_MS:  float = 3.5
# @parameter
# tier: first-pass
# rationale: Upper bound on the upwind/downwind background-ring asymmetry
#     ratio for "high" attributability. A near-symmetric ring (ratio < 1.5)
#     is consistent with a local source dominating in all directions.
#     M-DIAG-A2 Step C.3 (29 May 2026) reviewed against post-fix 5-seed
#     baseline: most observed ratios cluster within 0.9-1.1 (effectively
#     symmetric), so the 1.5 vs 2.5 buckets are exercised mostly by speed,
#     not ratio. The 1.5 value held up — kept unchanged. Re-review when
#     calibration set includes locations with stronger directional
#     contrast.
# source: M-WIND-A1 v2.0 spec §5.2; M-DIAG-A2 §4.2 (no change)
# last_reviewed: 2026-05-29
# applies_to: [air.no2, air.so2, air.hcho, air.aai, air.aod]
WIND_ASYMMETRY_HIGH_MAX: float = 1.5
# @parameter
# tier: first-pass
# rationale: Lower bound on the upwind/downwind asymmetry ratio for "low"
#     attributability. A strongly directional ring (ratio >= 2.5) points to
#     an off-site source advected past the supplier. M-DIAG-A2 Step C.3
#     (29 May 2026) reviewed against post-fix 5-seed baseline: no observed
#     ratio crossed 2.5 in the 5-seed set (highest was Norilsk AAI at 1.65
#     post-abs-fix), so the gate was not exercised. Kept unchanged; re-review
#     when calibration set includes locations with stronger directional
#     contrast.
# source: M-WIND-A1 v2.0 spec §5.2; M-DIAG-A2 §4.2 (no change)
# last_reviewed: 2026-05-29
# applies_to: [air.no2, air.so2, air.hcho, air.aai, air.aod]
WIND_ASYMMETRY_LOW_MIN:  float = 2.5

# WA9 — days where mean wind speed is below this threshold are excluded
# from the direction / asymmetry calculation (no meaningful direction at
# calm), but still count toward the speed mean and the anomaly-day total.
# @parameter
# tier: first-pass
# rationale: Calm-day cutoff (1 m/s) below which wind direction is too
#     ill-defined to contribute to the asymmetry calculation. Such days still
#     count toward the speed mean and the anomaly-day total — only their
#     direction is dropped. M-DIAG-A2 Step C.3 (29 May 2026) reviewed against
#     post-fix 5-seed baseline: no seed has a non-trivial fraction of days
#     below this threshold (the per-seed mean speeds all sit well above 1 m/s).
#     Kept unchanged.
# source: M-WIND-A1 v2.0 spec §5.2 (WA9); M-DIAG-A2 §4.2 (no change)
# last_reviewed: 2026-05-29
# applies_to: [air.no2, air.so2, air.hcho, air.aai, air.aod]
WIND_CALM_THRESHOLD_MS: float = 1.0

# WA10 — minimum anomaly-day sample size. Below this, attributability is
# "sparse" and no arrow renders on the M-UI-A5 map.
# @parameter
# tier: first-pass
# rationale: Minimum number of anomaly days needed to assess wind
#     attributability. Below 5 days the directional sample is too thin to
#     trust, so the state is reported as "sparse" and no arrow renders.
#     M-DIAG-A2 Step C.3 (29 May 2026) reviewed against post-fix 5-seed
#     baseline: all wind-eligible (seed × indicator) cells in the calibration
#     set had N >= 6 (lowest was Suape NO2 at 7, Brasilia SO2 at 6). The
#     5-day gate fires "sparse" cleanly for cases that truly need it
#     (Norilsk SO2/AOD skipped for other reasons; not gated by N). Kept
#     unchanged; not derived from a power analysis.
# source: M-WIND-A1 v2.0 spec §5.2 (WA10); M-DIAG-A2 §4.2 (no change)
# last_reviewed: 2026-05-29
# applies_to: [air.no2, air.so2, air.hcho, air.aai, air.aod]
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

# M-DIAG-A2 §4.1 — sign-bearing wind-attribution indicators.
#
# Most wind-attribution indicators (NO₂, SO₂, HCHO, AOD) report strictly-
# non-negative concentrations, so the upwind/downwind asymmetry ratio
# `bg_upwind / bg_downwind` is always non-negative and the bucket logic in
# `compute_wind_attributability_state` works as the spec describes.
#
# AAI (Aerosol Absorbing Index) is the exception: it is a SIGNED
# dimensionless index where positive = absorbing aerosols (smoke, dust)
# and negative = scattering aerosols (clean air). At locations where the
# two half-rings span both signs (e.g. Norilsk post-fix), the raw ratio
# can be negative and the `mean_asymmetry_ratio must be non-negative`
# validator at engine/core/wind.py:118-121 raised, silent-degrading wind
# attribution to sparse via the `six_step` try/except.
#
# Fix per M-DIAG-A2 Step B (operator-locked 29 May 2026): for indicators
# in this set, `measure_ring_asymmetry` computes the ratio on absolute
# values — `abs(bg_upwind) / abs(bg_downwind)` — preserving the magnitude-
# asymmetry semantic without sign issues. Validator stays as defense-in-
# depth. Out-of-set indicators use the unchanged
# `bg_upwind / bg_downwind` formula.
SIGN_BEARING_WIND_INDICATORS: frozenset[str] = frozenset({
    "air.aai",
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


# ---------------------------------------------------------------------------
# M-DIAG-A4 — climatology-baseline denominator (engine/core/repeatable_core.py)
# ---------------------------------------------------------------------------
# The per-day / aggregate anomaly detector's denominator (`bg_std`) is the
# *temporal* standard deviation of the site's per-day value series over a
# trailing clean prior period — NOT the spatial std of the time-averaged ring
# (the M-DIAG-A3 H1c scale mismatch). The fix is numerical-correctness: the
# spatial std of a time-averaged field is the wrong scale to normalise per-day
# temporal deviations. See docs/M-DIAG-A4_spec.md and the M-DIAG-A3 addendum.

# DGC1 — baseline window = max(90, screening_window_length) trailing. When the
# screening window is ≤ 90 days the baseline is 90 trailing days; when it is
# longer the baseline grows to match. The floor gives a strong σ estimate even
# for short (30-day) screenings.
CLIMATOLOGY_BASELINE_MIN_DAYS: int = 90

# §4.4 — sparse-coverage flag. When the trailing prior period yields fewer than
# this many valid per-day site observations, the temporal σ is still used (we
# use what's available) but the indicator's provenance is flagged
# `clim_baseline_sparse=True` so auditors can see the estimate rests on thin
# data (e.g. early-2019 screenings near the S5P/AAI archive floor).
CLIMATOLOGY_BASELINE_SPARSE_MIN_VALID_DAYS: int = 30

# A standard deviation needs at least two observations. Below this the temporal
# denominator cannot be computed at all; the detector then leaves `bg_std`
# unchanged (the spatial std) and flags `clim_baseline_applied=False` — a loud
# fallback, never a silent default (CLAUDE.md §7 "no silent defaults").
CLIMATOLOGY_BASELINE_MIN_COMPUTABLE_DAYS: int = 2

# Engine methodology version (M-DIAG-A4 / DGC5, Q-DGC-B → numeric integer).
# Bumped whenever a change to the anomaly-detection methodology means a saved
# trend record computed under an older engine is no longer directly comparable
# to a fresh screening. Saved trend records written before this field existed
# default to 0 on read → the stale-data banner fires. Version map:
#   0 — pre-M-DIAG-A4 (spatial-std denominator)
#   1 — M-DIAG-A4 (climatology-baseline temporal denominator)
ENGINE_METHODOLOGY_VERSION: int = 1


# ---------------------------------------------------------------------------
# M-TREND-A1 — per-indicator trend drill-down (engine/core/trend.py)
# ---------------------------------------------------------------------------
# Theil–Sen slope + Mann–Kendall significance over a server-side per-day
# site series, reduced OUTSIDE six_step and invoked on demand after a
# screening. None of these enter composite.overall_screening (decision-log
# E1) — they tune the drill-down only. All first-pass values; rationale in
# docstrings, bundled into the deferred calibration sweep.

# Two-threshold minimum-points handling (decision-log B4 / TR4). Below the
# hard floor no slope is emitted ("trend unavailable"); between hard and
# soft the slope is emitted but the confidence length-term drives the score
# toward zero. Soft floor = 12 matches Wireframes P-06.
# @parameter
# tier: first-pass
# rationale: Hard floor on the number of valid per-day points below which no
#     Theil–Sen slope is emitted at all (the trend drill-down reads "trend
#     unavailable"). Four points is the bare minimum for a slope to be more
#     than line-fitting noise; a first-pass judgment, the obvious calibration
#     target alongside the rest of the trend thresholds.
# source: M-TREND_Decision_Log B4 / TR4; calibration pending
# last_reviewed: 2026-05-29
# applies_to: [air.no2, air.so2, air.co, air.hcho, air.o3, air.aai, air.pm25, air.pm10, air.aod, ghg.viirs, nature.ndvi]
TREND_HARD_FLOOR_POINTS: int = 4
# @parameter
# tier: first-pass
# rationale: Soft floor on valid per-day points: between the hard floor (4)
#     and this value the slope is shown but the confidence length-term drives
#     the trend score toward zero, flagging the result as low-reliability.
#     Soft floor = 12 matches the Wireframes P-06 guidance; a first-pass value
#     pending calibration.
# source: M-TREND_Decision_Log B4 / TR4; Wireframes_All_v4.md §P-06; calibration pending
# last_reviewed: 2026-05-29
# applies_to: [air.no2, air.so2, air.co, air.hcho, air.o3, air.aai, air.pm25, air.pm10, air.aod, ghg.viirs, nature.ndvi]
TREND_SOFT_FLOOR_POINTS: int = 12

# Display-severity cap (decision-log E-SEV / TR12). The slope is normalised
# to background-sigmas-per-year (sibling of IC §0.4); k_trend is the σ/yr
# that saturates severity to 1.0. 1.0 σ/yr is a large year-on-year drift —
# a first-pass judgement, the obvious calibration target.
# @parameter
# tier: first-pass
# rationale: The σ/yr drift at which the trend drill-down's display severity
#     saturates to 1.0 (the trend equivalent of NORMALISATION_K's k). The
#     slope is normalised to background-sigmas-per-year — a sibling of the
#     IC §0.4 normalisation convention — and 1.0 σ/yr is a large year-on-year
#     drift. The value is a first-pass judgment and the obvious calibration
#     target; the normalisation *method* follows the spec.
# source: M-TREND_Decision_Log E-SEV / TR12 (method per IC §0.4); calibration pending
# last_reviewed: 2026-05-29
# applies_to: [air.no2, air.so2, air.co, air.hcho, air.o3, air.aai, air.pm25, air.pm10, air.aod, ghg.viirs, nature.ndvi]
TREND_SEVERITY_K_SIGMA_PER_YEAR: float = 1.0

# Seasonal flag (decision-log C-ii / TR15). A SEPARATE categorical signal,
# never folded into the confidence scalar. Fires when the window spans less
# than ~one year, where an un-deseasonalised slope risks reading phenology
# as trend.
# @parameter
# tier: first-pass
# rationale: Window span (days) below which the trend drill-down raises a
#     separate "seasonal caveat" flag — under roughly one year an
#     un-deseasonalised slope risks reading phenology (the seasonal cycle) as
#     a real trend. 365 days is the natural one-cycle cutoff; the choice to
#     gate the caveat exactly there is a first-pass judgment.
# source: M-TREND_Decision_Log C-ii / TR15; calibration pending
# last_reviewed: 2026-05-29
# applies_to: [air.no2, air.so2, air.co, air.hcho, air.o3, air.aai, air.pm25, air.pm10, air.aod, ghg.viirs, nature.ndvi]
TREND_SEASONAL_FLAG_MIN_DAYS: int = 365

# Significance buckets (decision-log D2 / TR9). Presentation-layer constants,
# NOT a gate — the raw slope + p-value are always emitted above the hard
# floor; these only choose the displayed bucket.
# @parameter
# tier: spec-mandated
# rationale: Mann–Kendall p-value at/below which a trend is displayed as
#     "significant". p < 0.05 is the standard statistical-significance
#     convention; using it as the display-bucket boundary is prescribed by the
#     trend decision-log, not tuned per indicator. Changing it is a
#     methodology decision (it redefines what "significant trend" means to the
#     user across every series indicator).
# source: M-TREND_Decision_Log D2 / TR9; standard p<0.05 significance convention
# last_reviewed: 2026-05-29
# applies_to: [air.no2, air.so2, air.co, air.hcho, air.o3, air.aai, air.pm25, air.pm10, air.aod, ghg.viirs, nature.ndvi]
TREND_SIGNIFICANT_P: float = 0.05
# @parameter
# tier: spec-mandated
# rationale: Upper p-value bound for the "weak / emerging" trend bucket:
#     p in [0.05, 0.10) reads as weak-emerging, p >= 0.10 as not significant.
#     The p < 0.10 marginal-significance convention and the bucketing scheme
#     are prescribed by the trend decision-log; a change is a methodology
#     decision, not a calibration tweak.
# source: M-TREND_Decision_Log D2 / TR9; standard p<0.10 marginal-significance convention
# last_reviewed: 2026-05-29
# applies_to: [air.no2, air.so2, air.co, air.hcho, air.o3, air.aai, air.pm25, air.pm10, air.aod, ghg.viirs, nature.ndvi]
TREND_WEAK_EMERGING_P: float = 0.10

# Trend-confidence base terms (decision-log C-TERMS / TR13). Additive base
# (length + span + coverage), mirroring the M-TIER-A1 house confidence
# pattern, before the multiplicative column_to_surface + fallback chain.
# Length dominates because too-few-points is the primary trend-reliability
# risk (ties to the B4 floors). Sums to 1.00.
TREND_CONFIDENCE_TERM_WEIGHTS: dict[str, float] = {
    "length":   0.50,
    "span":     0.25,
    "coverage": 0.25,
}
# Window length (days) at/above which the span-term saturates to 1.0 — a
# year of data carries full statistical power in the span sense.
TREND_CONFIDENCE_SPAN_SATURATION_DAYS: int = 365

# M-TREND-A2 (UT7) — series-eligible indicators: the ones with a real per-day
# site series (so a Theil–Sen slope is meaningful). These are the only
# indicators that carry a "view trend" affordance and a saved trend record.
# Base IDs (pillar.slug); the entry points pass select_keys like
# "air.no2.score", so eligibility matches on the base prefix. ODIAC CO₂
# (standing-exposure), KBA, Dynamic World, and Hansen are deliberately absent
# — they have no per-day slope (decision-log U6).
# M-CH4-A1 (30 May 2026): ghg.ch4 removed — CH₄ is now reference data (not a
# scored severity series), so it carries no trend affordance, matching Hansen
# and ODIAC. The engine still computes the CH₄ snapshot, but it is shown as a
# raw observational reading only (docs/ghg_odiac_validation.md §10).
TREND_SERIES_INDICATOR_IDS: frozenset[str] = frozenset({
    "air.no2", "air.so2", "air.co", "air.hcho", "air.o3",
    "air.aai", "air.pm25", "air.pm10", "air.aod",
    "ghg.viirs",
    "nature.ndvi",
})
