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

# IC_v4 §2.3 — Core GHG Audit Support (v1 rescaled form)
CORE_GHG_AUDIT_SUPPORT_WEIGHTS: dict[str, float] = {
    "ghg.co2_context":          0.39,
    "ghg.ch4_context_adjusted": 0.28,
    "ghg.combustion_proxy":     0.22,
    "ghg.activity_score":       0.11,
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
