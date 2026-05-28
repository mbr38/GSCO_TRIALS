"""Canonical indicator IDs from docs/Indicator_ID_Schema_v2.md.

Every value the engine returns — and every entry in `selected_indicators`,
CSV column headers, and JSON exports — uses one of these IDs. Adding a new
ID requires updating the schema doc first (CLAUDE.md §7).

Pattern: ``<pillar>.<indicator>[.<measurement>]`` — see schema §1.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Pillars  (schema §1)
# ---------------------------------------------------------------------------
PILLAR_AIR = "air"
PILLAR_GHG = "ghg"
PILLAR_NATURE = "nature"
PILLAR_COMPOSITE = "composite"

PILLARS: tuple[str, ...] = (PILLAR_AIR, PILLAR_GHG, PILLAR_NATURE, PILLAR_COMPOSITE)
# CLAUDE.md §7 fixes the pillar order for UI, verbal summary, and CSV exports.
PILLAR_ORDER: tuple[str, ...] = (PILLAR_AIR, PILLAR_GHG, PILLAR_NATURE)


# ---------------------------------------------------------------------------
# Measurement suffixes  (schema §1)
# ---------------------------------------------------------------------------
MEASUREMENT_SUFFIXES: tuple[str, ...] = (
    "site", "background", "anomaly", "z", "hf",
    "trend", "trend_p", "confidence", "score",
)

# CO2 is an emissions inventory, not a column density — different
# measurements (schema §3.1). M5.5 renamed `.anomaly` → `.relative_intensity`
# because ODIAC is an emissions allocation product, not an atmospheric
# observation; "anomaly" implied a physical baseline measurement it doesn't
# actually have. `.trend_p` joins the set so CO₂ matches CH₄'s trend
# reporting shape. Schema_v2 §3.1 doc update is pending — see
# docs/v1x_followups.md.
CO2_MEASUREMENT_SUFFIXES: tuple[str, ...] = (
    "mean", "total", "relative_intensity",
    "trend", "trend_p", "confidence", "score",
)

# VIIRS NTL — reduced set (schema §3.1)
VIIRS_MEASUREMENT_SUFFIXES: tuple[str, ...] = (
    "site", "anomaly", "trend", "confidence", "score",
)


def make_id(pillar: str, indicator: str, measurement: str | None = None) -> str:
    """Compose a canonical ID: ``<pillar>.<indicator>[.<measurement>]``.

    Pass values drawn from the tuples in this module. The function does not
    validate; use `is_valid_id` or `ALL_INDICATOR_IDS` for validation.
    """
    if measurement is None:
        return f"{pillar}.{indicator}"
    return f"{pillar}.{indicator}.{measurement}"


# ---------------------------------------------------------------------------
# Air Pollution pillar  (schema §2)
# ---------------------------------------------------------------------------

# §2.1 — each pollutant gets the full MEASUREMENT_SUFFIXES set.
AIR_POLLUTANTS: tuple[str, ...] = (
    "no2", "so2", "co", "hcho", "o3", "aai", "pm25", "pm10", "aod",
)

# §2.2 — single 0–1 sub-aggregate scores (no measurement suffix).
AIR_SUB_AGGREGATES: tuple[str, ...] = (
    "air.industrial_combustion_proxy",
    "air.heavy_industry_score",
    "air.voc_photochemical",
    "air.smoke_dust_regional_transport",
    "air.industrial_air_pollution_burden",
    "air.pm_or_aerosol",
)

# §2.3 — pillar aggregates (single 0–1 values).
AIR_AGGREGATES: tuple[str, ...] = (
    "air.pollution_proxy_score",
    "air.spatiotemporal_anomaly_score",
    "air.trend_score",
    # M-ATTRIB-A1 (AT16): renamed measurement-quality ID. The legacy
    # `air.attribution_confidence_score` is kept valid for the 1-milestone
    # dual-emit window (remove it next milestone, per spec §4.6).
    "air.measurement_quality_score",
    "air.attribution_confidence_score",
    "air.audit_followup_priority",
)


# ---------------------------------------------------------------------------
# GHG pillar  (schema §3)
# ---------------------------------------------------------------------------

# §3.1 — single-value indicators; measurement set varies per source.
GHG_REPEATABLE_INDICATORS: tuple[str, ...] = ("ch4",)
GHG_CO2_INDICATORS: tuple[str, ...] = ("co2",)
GHG_VIIRS_INDICATORS: tuple[str, ...] = ("viirs",)

# §3.2 — sub-aggregates.
GHG_SUB_AGGREGATES: tuple[str, ...] = (
    "ghg.combustion_proxy",
    "ghg.activity_score",
    "ghg.co2_context",
    "ghg.ch4_hotspot_signal",
    "ghg.fire_or_regional_transport_risk",
    "ghg.ch4_context_adjusted",
    "ghg.fossil_combustion_score",
    "ghg.activity_adjusted_co2",
)

# §3.3 — pillar aggregates.
GHG_AGGREGATES: tuple[str, ...] = (
    "ghg.core_audit_support",
    "ghg.spatiotemporal_anomaly",
    "ghg.trend",
    "ghg.data_quality_attribution",
    "ghg.audit_followup_priority",
)

# §3.4 — GHG quality sub-scores (v1). The first three compose
# `ghg.data_quality_attribution` per IC_v4 §2.3 (M-ATTRIB-A1 renormalised
# weights 0.34 / 0.33 / 0.33). `ghg.nearby_source_isolation` remains a valid
# emitted ID but, as of M-ATTRIB-A1 (AT15), no longer enters the aggregate —
# it is reserved for a future attributability surface. Promoted from v1.x
# reserved namespace in schema v2 (Bug 1 fix).
GHG_QUALITY_SUB_SCORES: tuple[str, ...] = (
    "ghg.temporal_coverage",
    "ghg.spatial_resolution_suitability",
    "ghg.retrieval_inventory_quality",
    "ghg.nearby_source_isolation",  # M-ATTRIB-A1: emitted but not in aggregate
)


# ---------------------------------------------------------------------------
# Nature/Land pillar  (schema §4)
# ---------------------------------------------------------------------------

# §4.1 — KBA proximity / overlap.
NATURE_KBA: tuple[str, ...] = (
    "nature.kba.dist_km",
    "nature.kba.overlap_ha",
    "nature.kba.overlap_pct",
    "nature.kba.proximity_score",
)

# §4.2 — Dynamic World. DW class labels (left) map to shorter ID slugs (right)
# for three of the nine classes. ID-prefix slug matches the schema doc exactly.
DW_CLASS_TO_ID_SLUG: dict[str, str] = {
    "trees":              "trees",
    "crops":              "crops",
    "built":              "built",
    "bare":               "bare",
    "grass":              "grass",
    "shrub_and_scrub":    "shrub",
    "flooded_vegetation": "flooded_veg",
    "water":              "water",
    "snow_and_ice":       "snow",
}
DW_CLASSES: tuple[str, ...] = tuple(DW_CLASS_TO_ID_SLUG.keys())
NATURE_DW_PER_CLASS_MEASUREMENTS: tuple[str, ...] = ("pct", "ha")
NATURE_DW_OTHER: tuple[str, ...] = (
    "nature.dw.dominant_class",
    "nature.dw.class_confidence",
)

# §4.3 — Habitat conversion.
NATURE_HABITAT: tuple[str, ...] = (
    "nature.habitat.natural_loss_ha",
    "nature.habitat.natural_loss_pct",
    "nature.habitat.nat_to_built_ha",
    "nature.habitat.nat_to_bare_ha",
    "nature.habitat.nat_to_crop_ha",
    "nature.habitat.built_expansion_ha",
    "nature.habitat.bare_expansion_ha",
    "nature.habitat.annualised_rate",
    "nature.habitat.conversion_score",
)

# §4.4 — Hansen forest loss.
NATURE_FOREST_LOSS: tuple[str, ...] = (
    "nature.forest_loss.ha",
    "nature.forest_loss.pct",
)

# §4.5 — NDVI / vegetation condition.
NATURE_NDVI: tuple[str, ...] = (
    "nature.ndvi.mean",
    "nature.ndvi.anomaly",
    "nature.ndvi.z",
    "nature.ndvi.slope",
    "nature.ndvi.slope_p",
    "nature.ndvi.score",
    "nature.low_ndvi.ha",
    "nature.low_ndvi.pct",
    "nature.vegetation_condition",
)

# §4.6 — Bare / built / water exposure.
NATURE_EXPOSURE: tuple[str, ...] = (
    "nature.bare.area_now_ha",
    "nature.bare.area_now_pct",
    "nature.bare.expansion_ha",
    "nature.built.area_now_ha",
    "nature.built.area_now_pct",
    "nature.water.area_now_ha",
    "nature.water.dist_km",
    "nature.flooded_veg.area_now_ha",
    "nature.water_or_flooded_veg_exposure",
    "nature.sensitive_land_cover_presence",
)

# §4.7 — Restoration / recovery.
NATURE_RECOVERY: tuple[str, ...] = (
    "nature.recovery.ndvi_improvement_pct",
    "nature.recovery.natural_cover_gain_ha",
    "nature.recovery.bare_reduction_ha",
    "nature.recovery.score",
)

# §4.8 — Quality-attribution sub-scores. `nature.biodiversity_exposure` was
# wrongly grouped here in schema v1; schema v2 (Bug 2 fix) moves it to the
# new §4.9 sub-aggregates section below. `nature.dw.class_confidence` is
# intentionally cross-listed: it appears here in its quality-attribution role
# (§4.8) and in NATURE_DW_OTHER in its DW-output role (§4.2) — same pattern
# as `nature.habitat.conversion_score` (NATURE_HABITAT + NATURE_SUB_AGGREGATES).
# M-ATTRIB-A1 (AT13 / AT14): the four measurement-quality sub-scores.
# `nature.supplier_spatial_link` (now categorical attributability — see
# NATURE_ATTRIBUTABILITY below) and `nature.external_driver_screening`
# (now reference data — see NATURE_REFERENCE below) were removed.
NATURE_QUALITY: tuple[str, ...] = (
    "nature.valid_pixel_coverage",
    "nature.cloud_observation_quality",
    "nature.dw.class_confidence",
    "nature.seasonal_comparability",
)

# M-ATTRIB-A1 (AT5 / AT7): reference-data + categorical-attributability IDs
# that replaced the two removed quality sub-scores. These are emitted by the
# Nature pillar (regional_loss_evidence reframe + supplier_spatial_link
# centroid offset) but do NOT enter any composite or measurement-quality
# aggregate. Registered here so `is_valid_id` accepts them.
NATURE_REFERENCE: tuple[str, ...] = (
    "nature.regional_loss_evidence.ratio",
    "nature.regional_loss_evidence.window",
)
NATURE_ATTRIBUTABILITY: tuple[str, ...] = (
    "nature.supplier_spatial_link.centroid_offset_km",
    "nature.supplier_spatial_link.centroid_lat",
    "nature.supplier_spatial_link.centroid_lon",
    "nature.supplier_spatial_link.n_change_pixels",
    "nature.habitat.attributability_state",
)

# §4.9 — Sub-aggregate scores. The three *exposure-side* terms that feed
# `nature.followup_priority` per IC_v4 §3.3. The latter two are also surfaced
# under their natural domain headers (NATURE_HABITAT, NATURE_NDVI); this
# tuple is the canonical reference for "the three sub-aggregates that compose
# the pillar follow-up priority".
NATURE_SUB_AGGREGATES: tuple[str, ...] = (
    "nature.biodiversity_exposure",
    "nature.habitat.conversion_score",
    "nature.vegetation_condition",
)

# §4.10 — Pillar aggregates.
# M-ATTRIB-A1 (AT13): nature.quality_attribution → nature.measurement_quality.
NATURE_AGGREGATES: tuple[str, ...] = (
    "nature.measurement_quality",
    "nature.followup_priority",
)


# ---------------------------------------------------------------------------
# Cross-pillar composite  (schema §5)
# ---------------------------------------------------------------------------
COMPOSITE_OVERALL_SCREENING = "composite.overall_screening"
COMPOSITE_CONFIDENCE = "composite.confidence"

COMPOSITE_AGGREGATES: tuple[str, ...] = (
    COMPOSITE_OVERALL_SCREENING,
    COMPOSITE_CONFIDENCE,
)


# ---------------------------------------------------------------------------
# v1.x reserved namespace  (schema §3.5 and §8)
# Not part of ALL_INDICATOR_IDS — listed so future PRs don't collide.
# Trimmed in schema v2 (Bug 1 fix): the four `ghg.*` quality sub-scores that
# used to live here are v1 indicators now and live in `GHG_QUALITY_SUB_SCORES`.
# ---------------------------------------------------------------------------
RESERVED_FOR_V1X: frozenset[str] = frozenset({
    "ghg.high_gwp_sector_risk",
    "ghg.wind_consistency",
    "ghg.sector_match",
    "nature.buffer_sensitivity",
    "air.fire_active_detection",
})


# ---------------------------------------------------------------------------
# Flat enumeration of every canonical v1 indicator ID.
# ---------------------------------------------------------------------------

def _build_all_indicator_ids() -> frozenset[str]:
    ids: set[str] = set()

    for pol in AIR_POLLUTANTS:
        for meas in MEASUREMENT_SUFFIXES:
            ids.add(make_id(PILLAR_AIR, pol, meas))
    ids.update(AIR_SUB_AGGREGATES)
    ids.update(AIR_AGGREGATES)

    for ind in GHG_REPEATABLE_INDICATORS:
        for meas in MEASUREMENT_SUFFIXES:
            ids.add(make_id(PILLAR_GHG, ind, meas))
    for ind in GHG_CO2_INDICATORS:
        for meas in CO2_MEASUREMENT_SUFFIXES:
            ids.add(make_id(PILLAR_GHG, ind, meas))
    for ind in GHG_VIIRS_INDICATORS:
        for meas in VIIRS_MEASUREMENT_SUFFIXES:
            ids.add(make_id(PILLAR_GHG, ind, meas))
    ids.update(GHG_SUB_AGGREGATES)
    ids.update(GHG_AGGREGATES)
    ids.update(GHG_QUALITY_SUB_SCORES)

    ids.update(NATURE_KBA)
    for dw_slug in DW_CLASS_TO_ID_SLUG.values():
        for meas in NATURE_DW_PER_CLASS_MEASUREMENTS:
            ids.add(f"nature.dw.{dw_slug}_{meas}")
    ids.update(NATURE_DW_OTHER)
    ids.update(NATURE_HABITAT)
    ids.update(NATURE_FOREST_LOSS)
    ids.update(NATURE_NDVI)
    ids.update(NATURE_EXPOSURE)
    ids.update(NATURE_RECOVERY)
    ids.update(NATURE_QUALITY)
    ids.update(NATURE_REFERENCE)          # M-ATTRIB-A1 (AT5)
    ids.update(NATURE_ATTRIBUTABILITY)    # M-ATTRIB-A1 (AT7)
    ids.update(NATURE_SUB_AGGREGATES)
    ids.update(NATURE_AGGREGATES)

    ids.update(COMPOSITE_AGGREGATES)

    return frozenset(ids)


ALL_INDICATOR_IDS: frozenset[str] = _build_all_indicator_ids()


def is_valid_id(indicator_id: str) -> bool:
    """True iff `indicator_id` is a canonical v1 indicator ID."""
    return indicator_id in ALL_INDICATOR_IDS
