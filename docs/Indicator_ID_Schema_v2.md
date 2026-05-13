# GSCO Environmental Tool — Indicator ID Schema (v2)

**Purpose.** Single source of canonical IDs for every indicator the v1 tool computes. These IDs are what the engine returns in result payloads, what `selectedIndicators` lists, what the Indicator Library renders, what the CSV/JSON exports column-name, and what the Reports Page templates address.

**Authority.** Names and groupings derive from `Indicators_Computation_v4.md`. Any new indicator must first be added there, then surfaced here.

**Date.** 13 May 2026.

**Changes from v1.**
- **Bug 1 fix — GHG quality sub-scores promoted to v1.** The four terms in the v1 `GHG_Data_Quality_Attribution_v1` formula (`Temporal_Coverage`, `Spatial_Resolution_Suitability`, `Retrieval_or_Inventory_Quality`, `Nearby_Source_Isolation`) were wrongly listed as deferred-to-v1.x in v1's §3.4 and §8. They are v1 — IC_v4 §2.3 has them weighted 0.33 / 0.27 / 0.27 / 0.13. Surfaced here as a new §3.4 "GHG quality sub-scores (v1)". The §8 reserved namespace now lists only the genuinely deferred terms.
- **Bug 2 fix — Nature sub-aggregates de-mixed from quality.** `nature.biodiversity_exposure` was wrongly grouped under §4.8 "Quality-attribution sub-scores" in v1. It is in fact a *sub-aggregate that feeds `Nature_FollowUp_Priority`* (IC_v4 §3.3), not a quality term. Moved into a new §4.X "Nature sub-aggregates" section that also explicitly groups `nature.habitat.conversion_score` and `nature.vegetation_condition` (which remain in their natural domain sections too — the new section is the canonical reference for "the three things that feed the pillar follow-up").
- **§8 trimmed.** With the bug fixes above, the v1.x reserved namespace shrinks to: `ghg.high_gwp_sector_risk`, `ghg.wind_consistency`, `ghg.sector_match`, `nature.buffer_sensitivity`, `air.fire_active_detection`. `ghg.nearby_source_isolation` is now a v1 ID (the satellite-only proxy in IC_v4 §7.2); v1.x will *upgrade the implementation* using external registries but the ID stays the same.
- **Cross-reference bump.** Pointers updated from `Indicators_Computation_v3.md` to `Indicators_Computation_v4.md`.

---

## 1. Naming convention

```
<pillar>.<indicator>[.<measurement>]
```

- **Pillar:** `air`, `ghg`, `nature`, or `composite`.
- **Indicator:** lowercase, snake_case. Multi-word indicator names use underscores (`industrial_combustion_proxy`). Acronyms preserve case-insensitive form (`no2`, `co2`, `ch4`, `ndvi`).
- **Measurement (optional):** present only when an indicator produces multiple values (raw, anomaly, score, etc.). Single-value aggregates and sub-aggregates omit the measurement segment.

### Measurement suffixes (when applicable)

| Suffix | Meaning | Unit |
|---|---|---|
| `.site` | Site-buffer mean (raw value) | Indicator-native (see Indicators_Computation §1.1, §2.1, §3.1) |
| `.background` | Background-ring median (raw value) | Indicator-native |
| `.anomaly` | Absolute anomaly = site − background | Indicator-native |
| `.z` | Normalised z-statistic | Dimensionless |
| `.hf` | Hotspot frequency (fraction of dates with Z ≥ threshold) | 0–1 |
| `.trend` | Theil-Sen slope | Indicator-native per year |
| `.trend_p` | Mann-Kendall two-sided p-value | 0–1 |
| `.confidence` | Per-indicator confidence | 0–1 |
| `.score` | Normalised 0–1 score (Indicators_Computation §0.4) | 0–1 |

### Rules

1. **No `.score` suffix on already-0–1 quantities.** Sub-aggregates like `air.industrial_combustion_proxy` are by definition 0–1 scores; the suffix would be redundant.
2. **Areas use `.ha` suffix; percentages use `.pct`.** Both are raw units, not scores.
3. **The screening composite and pillar follow-up scores are 0–1; no suffix.**
4. **Provenance fields** (asset ID, data dates, vintage flag) are not indicator IDs — they live in the result payload's `provenance` block, keyed by indicator ID.

---

## 2. Air Pollution pillar

### 2.1 Single-value indicators (repeatable core method)

Every pollutant below produces the full measurement set: `.site`, `.background`, `.anomaly`, `.z`, `.hf`, `.trend`, `.trend_p`, `.confidence`, `.score`.

| ID prefix | Source | Native unit (raw) | Display unit |
|---|---|---|---|
| `air.no2` | Sentinel-5P `NO2_column_number_density` | mol m⁻² | µmol m⁻² |
| `air.so2` | Sentinel-5P `SO2_column_number_density` | mol m⁻² | µmol m⁻² |
| `air.co` | Sentinel-5P `CO_column_number_density` | mol m⁻² | mmol m⁻² |
| `air.hcho` | Sentinel-5P `tropospheric_HCHO_column_number_density` | mol m⁻² | µmol m⁻² |
| `air.o3` | Sentinel-5P `O3_column_number_density` | mol m⁻² | DU |
| `air.aai` | Sentinel-5P `absorbing_aerosol_index` | dimensionless | dimensionless |
| `air.pm25` | CAMS `particulate_matter_2.5um` | kg m⁻³ | µg m⁻³ |
| `air.pm10` | CAMS `particulate_matter_10um` | kg m⁻³ | µg m⁻³ |
| `air.aod` | MODIS MAIAC `Optical_Depth_055` | dimensionless | dimensionless |

`air.o3.score` is capped at 0.5 (O₃ is context, not primary — Indicators_Computation §1.3).

### 2.2 Sub-aggregate scores (single 0–1 value each)

| ID | Defined in | Notes |
|---|---|---|
| `air.industrial_combustion_proxy` | Indicators_Computation §1.2 | `0.60·air.no2.score + 0.40·air.co.score` |
| `air.heavy_industry_score` | §1.2 | `0.60·air.so2.score + 0.30·air.no2.score + 0.10·air.pm_or_aerosol` |
| `air.voc_photochemical` | §1.2 | `0.50·air.hcho.score + 0.30·air.no2.score + 0.20·air.o3.score` |
| `air.smoke_dust_regional_transport` | §1.2 | `0.40·air.co.score + 0.40·air.aai.score + 0.20·air.pm_or_aerosol` — also exported as `ghg.fire_or_regional_transport_risk` (same value, see §3) |
| `air.industrial_air_pollution_burden` | §1.2 | `0.40·air.no2.score + 0.35·air.so2.score + 0.25·air.pm_or_aerosol` |
| `air.pm_or_aerosol` | §1.2 | `0.60·air.pm25.score + 0.40·air.aai.score`; fallback to `1.00·air.aai.score` per E4 trigger |

### 2.3 Pillar aggregates (single 0–1 value each)

| ID | Defined in |
|---|---|
| `air.pollution_proxy_score` | §1.3 |
| `air.spatiotemporal_anomaly_score` | §1.3 |
| `air.trend_score` | §1.3 (= 0 in screening mode) |
| `air.attribution_confidence_score` | §1.3 |
| `air.audit_followup_priority` | §1.3 — the pillar Follow-Up Priority |

---

## 3. GHG pillar

### 3.1 Single-value indicators

| ID prefix | Source | Native unit (raw) | Measurements available |
|---|---|---|---|
| `ghg.ch4` | Sentinel-5P `CH4_column_volume_mixing_ratio_dry_air` | ppb | `.site`, `.background`, `.anomaly`, `.z`, `.hf`, `.trend`, `.trend_p`, `.confidence`, `.score` |
| `ghg.co2` | ODIAC (uploaded asset) | kg CO₂ m⁻² yr⁻¹ (flux); t CO₂ yr⁻¹ (total) | `.mean`, `.total`, `.anomaly`, `.trend`, `.confidence`, `.score` |
| `ghg.viirs` | VIIRS Black Marble NTL | nW cm⁻² sr⁻¹ | `.site`, `.anomaly`, `.trend`, `.confidence`, `.score` |

CO₂ uses `.mean` and `.total` (annual flux mean and annual area-integrated total) instead of `.site` because ODIAC is an emissions inventory, not a column density.

### 3.2 Sub-aggregate scores

| ID | Defined in | Notes |
|---|---|---|
| `ghg.combustion_proxy` | Indicators_Computation §2.2 | Same formula as `air.industrial_combustion_proxy`; aliased here for clarity in GHG context |
| `ghg.activity_score` | §2.2 | Alias of `ghg.viirs.score` |
| `ghg.co2_context` | §2.2 | Alias of `ghg.co2.score` |
| `ghg.ch4_hotspot_signal` | §2.2 | Alias of `ghg.ch4.score` (pre-adjustment) |
| `ghg.fire_or_regional_transport_risk` | §2.2 / §7.3 | Same value as `air.smoke_dust_regional_transport` |
| `ghg.ch4_context_adjusted` | §2.2 / §7.3 | `ghg.ch4_hotspot_signal − 0.20·ghg.fire_or_regional_transport_risk` |
| `ghg.fossil_combustion_score` | §2.2 (optional) | `0.50·ghg.co2_context + 0.30·ghg.combustion_proxy + 0.20·ghg.activity_score` |
| `ghg.activity_adjusted_co2` | §2.2 (optional) | `0.70·ghg.co2_context + 0.30·ghg.activity_score` |

### 3.3 Pillar aggregates

| ID | Defined in |
|---|---|
| `ghg.core_audit_support` | §2.3 — v1 rescaled form |
| `ghg.spatiotemporal_anomaly` | §2.3 |
| `ghg.trend` | §2.3 (= 0 in screening mode) |
| `ghg.data_quality_attribution` | §2.3 — v1 rescaled form (Wind_Consistency, Sector_Match deferred); weights 0.33 / 0.27 / 0.27 / 0.13 over the four terms in §3.4 below |
| `ghg.audit_followup_priority` | §2.3 — the pillar Follow-Up Priority |

### 3.4 Quality sub-scores (v1)

These are the four terms in the v1 `GHG_Data_Quality_Attribution` formula. All are computed and exposed as indicator IDs.

| ID | Type | Defined in | Notes |
|---|---|---|---|
| `ghg.temporal_coverage` | 0–1 | IC_v4 §2.3, weight 0.33 | Fraction of expected observations actually present in the analysis window. Goes down for cloud-heavy regions and short windows. |
| `ghg.spatial_resolution_suitability` | 0–1 | IC_v4 §2.3, weight 0.27 | How well the indicator's pixel size matches the buffer. Penalises CH₄ at sub-pixel buffers; rewarded when buffer covers ≥ 3 native pixels. |
| `ghg.retrieval_inventory_quality` | 0–1 | IC_v4 §2.3, weight 0.27 | Aggregate of per-source QA flags (TROPOMI retrieval QA for CH₄; ODIAC vintage lag for CO₂; VIIRS cloud / sun-glint flags). |
| `ghg.nearby_source_isolation` | 0–1 | IC_v4 §2.3 (weight 0.13) and IC_v4 §7.2 (formula) | "Is the background ring clean, or is the signal contaminated by other emitters?" v1 uses the satellite-only proxy: `0.5 · isolation_from_no2 + 0.5 · isolation_from_viirs`. v1.x will upgrade the implementation using E-PRTR / GHGRP registries; the indicator ID stays the same. |

### 3.5 Deferred (v1.x — not exposed in v1)

These are genuinely not in v1. They appear in the original full formulas in `Indicators_Computation_v4.md` §2.3 but are set to 0 in the v1 rescale.

`ghg.high_gwp_sector_risk` (sector input required), `ghg.wind_consistency` (ERA5 wind ingest required — see `GEE_Database_List_v3.md` §7), `ghg.sector_match` (sector input required).

---

## 4. Nature/Land pillar

### 4.1 KBA proximity / overlap

| ID | Type | Source |
|---|---|---|
| `nature.kba.dist_km` | raw km | Distance from supplier point to nearest KBA polygon |
| `nature.kba.overlap_ha` | raw hectares | Site-buffer ∩ KBA area |
| `nature.kba.overlap_pct` | raw % | `overlap_ha / buffer_area_ha · 100` |
| `nature.kba.proximity_score` | 0–1 | `max(overlap_pct/100, exp(−dist_km/10))` per §3.2 |

### 4.2 Land cover composition (Dynamic World)

Per-class percentages and absolute areas:

| ID prefix | Class label (DW V1) |
|---|---|
| `nature.dw.trees_pct`, `nature.dw.trees_ha` | trees |
| `nature.dw.crops_pct`, `nature.dw.crops_ha` | crops |
| `nature.dw.built_pct`, `nature.dw.built_ha` | built |
| `nature.dw.bare_pct`, `nature.dw.bare_ha` | bare |
| `nature.dw.grass_pct`, `nature.dw.grass_ha` | grass |
| `nature.dw.shrub_pct`, `nature.dw.shrub_ha` | shrub_and_scrub |
| `nature.dw.flooded_veg_pct`, `nature.dw.flooded_veg_ha` | flooded_vegetation |
| `nature.dw.water_pct`, `nature.dw.water_ha` | water |
| `nature.dw.snow_pct`, `nature.dw.snow_ha` | snow_and_ice |
| `nature.dw.dominant_class` | string (one of the above class names) |
| `nature.dw.class_confidence` | 0–1 (mean of `prob_<dominant_class>` band over buffer) |

The "natural / semi-natural" bucket used in `nature.sensitive_land_cover_presence` is the **sum of** `trees_pct + flooded_veg_pct + grass_pct + shrub_pct`. The mapping to natural/non-natural is fixed and lives in code as `DW_NATURAL_CLASSES = ['trees', 'grass', 'shrub_and_scrub', 'flooded_vegetation']`.

### 4.3 Habitat conversion

| ID | Type | Notes |
|---|---|---|
| `nature.habitat.natural_loss_ha` | raw ha | Any natural → non-natural transition |
| `nature.habitat.natural_loss_pct` | raw % | `/ buffer_area_ha · 100` |
| `nature.habitat.nat_to_built_ha` | raw ha | Subset: natural → built |
| `nature.habitat.nat_to_bare_ha` | raw ha | Subset: natural → bare |
| `nature.habitat.nat_to_crop_ha` | raw ha | Subset: natural → crops |
| `nature.habitat.built_expansion_ha` | raw ha | Net built growth |
| `nature.habitat.bare_expansion_ha` | raw ha | Net bare-ground growth |
| `nature.habitat.annualised_rate` | raw ha/yr | `converted_area_ha / X_years` |
| `nature.habitat.conversion_score` | 0–1 | `Habitat_Conversion` from §3.2 |

### 4.4 Forest loss (Hansen)

| ID | Type |
|---|---|
| `nature.forest_loss.ha` | raw ha |
| `nature.forest_loss.pct` | raw % |

### 4.5 NDVI / vegetation condition

| ID | Type |
|---|---|
| `nature.ndvi.mean` | dimensionless [−1, +1] |
| `nature.ndvi.anomaly` | dimensionless |
| `nature.ndvi.z` | dimensionless |
| `nature.ndvi.slope` | NDVI yr⁻¹ (Theil-Sen) |
| `nature.ndvi.slope_p` | 0–1 (Mann-Kendall) |
| `nature.ndvi.score` | 0–1 (inverted; higher = worse) |
| `nature.low_ndvi.ha` | raw ha |
| `nature.low_ndvi.pct` | raw % |
| `nature.vegetation_condition` | 0–1 (the v1 rescaled aggregate, Indicators_Computation §3.2) |

### 4.6 Bare / built / water exposure

| ID | Type |
|---|---|
| `nature.bare.area_now_ha` | raw ha |
| `nature.bare.area_now_pct` | raw % |
| `nature.bare.expansion_ha` | raw ha (per analysis window) |
| `nature.built.area_now_ha` | raw ha |
| `nature.built.area_now_pct` | raw % |
| `nature.water.area_now_ha` | raw ha |
| `nature.water.dist_km` | raw km |
| `nature.flooded_veg.area_now_ha` | raw ha |
| `nature.water_or_flooded_veg_exposure` | 0–1 score (§3.2) |
| `nature.sensitive_land_cover_presence` | 0–1 score (§3.2) |

### 4.7 Restoration / recovery

| ID | Type |
|---|---|
| `nature.recovery.ndvi_improvement_pct` | raw % |
| `nature.recovery.natural_cover_gain_ha` | raw ha |
| `nature.recovery.bare_reduction_ha` | raw ha |
| `nature.recovery.score` | 0–1 (Indicators_Computation §3.2 — subtracted from `nature.vegetation_condition`) |

### 4.8 Quality-attribution sub-scores

These are the six terms in `Nature_Quality_Attribution` (IC_v4 §3.3). All are 0–1 confidence-side scores.

| ID | Type | Notes |
|---|---|---|
| `nature.valid_pixel_coverage` | 0–1 | §3.3 |
| `nature.cloud_observation_quality` | 0–1 | §3.3 |
| `nature.dw.class_confidence` | 0–1 | §3.3 (same underlying value as in §4.2; used both as a DW output and as a quality-attribution input) |
| `nature.seasonal_comparability` | 0–1 | §3.3 |
| `nature.supplier_spatial_link` | 0–1 | §7.5 |
| `nature.external_driver_screening` | 0–1 | §7.5 |

### 4.9 Sub-aggregate scores

The three terms that feed `Nature_FollowUp_Priority` (IC_v4 §3.3) — *exposure-side* scores, not quality-side. Two of them are also surfaced under their natural domain headers above (§4.3 for habitat, §4.5 for vegetation); this section is the canonical reference for "the three sub-aggregates that compose the pillar follow-up priority".

| ID | Type | Defined in | Notes |
|---|---|---|---|
| `nature.biodiversity_exposure` | 0–1 | IC_v4 §3.2, weight 0.30 | KBA-driven exposure: `0.40·KBA + 0.30·Sensitive_LandCover + 0.20·Water_Exposure + 0.10·Buffer_Sensitivity_v1` (last term = 0 in v1, weights rescaled per §7.1) |
| `nature.habitat.conversion_score` | 0–1 | IC_v4 §3.2, weight 0.30 | `Habitat_Conversion` aggregate; also listed in §4.3 |
| `nature.vegetation_condition` | 0–1 | IC_v4 §3.2, weight 0.25 | `Vegetation_Condition_v1` (EVI removed; weights rescaled per §7.4); also listed in §4.5 |

### 4.10 Pillar aggregates

| ID |
|---|
| `nature.quality_attribution` |
| `nature.followup_priority` |

---

## 5. Cross-pillar composite

| ID | Type | Formula |
|---|---|---|
| `composite.overall_screening` | 0–1 | `⅓·air.audit_followup_priority + ⅓·ghg.audit_followup_priority + ⅓·nature.followup_priority` |
| `composite.confidence` | 0–1 | `min(air.attribution_confidence_score, ghg.data_quality_attribution, nature.quality_attribution)` |

---

## 6. Engine output shape

Every engine function returns its results keyed by these IDs. Example for a single supplier screening:

```json
{
  "air.no2.site":        4.2e-5,
  "air.no2.background":  3.1e-5,
  "air.no2.anomaly":     1.1e-5,
  "air.no2.z":           1.4,
  "air.no2.hf":          0.12,
  "air.no2.confidence":  0.78,
  "air.no2.score":       0.42,

  "air.industrial_combustion_proxy":    0.39,
  "air.pollution_proxy_score":          0.51,
  "air.audit_followup_priority":        0.58,

  "ghg.audit_followup_priority":        0.41,
  "nature.followup_priority":           0.33,
  "composite.overall_screening":        0.44,
  "composite.confidence":               0.62,

  "provenance": {
    "air.no2": {
      "asset_id": "COPERNICUS/S5P/OFFL/L3_NO2",
      "dates_used": ["2026-04-15", "..."],
      "valid_pixel_pct": 0.84
    },
    "...": "..."
  }
}
```

---

## 7. URL / CSV / JSON compatibility

- IDs contain only `[a-z0-9_.]`, so they're safe in URLs, CSV column headers, JSON keys, and Earth Engine asset properties.
- For CSV exports where some consumers dislike `.` in column names, the export layer substitutes `.` → `__` (e.g. `air__no2__site`). The substitution is reversible.

---

## 8. Future v1.x additions (not in v1; reserve namespace)

These names are reserved so v1.x extensions don't need a breaking change. `ghg.nearby_source_isolation` is **not** here — it is a v1 indicator (the satellite-only proxy in IC_v4 §7.2). v1.x will upgrade its implementation to use external registries, but the ID stays the same.

| ID | Source pending |
|---|---|
| `ghg.high_gwp_sector_risk` | Sector input |
| `ghg.wind_consistency` | ERA5 wind (see `GEE_Database_List_v3.md` §7) |
| `ghg.sector_match` | Sector input |
| `nature.buffer_sensitivity` | Sector input (currently set to 0 inside `nature.biodiversity_exposure` per IC_v4 §3.2 / §7.1) |
| `air.fire_active_detection` | FIRMS upload |

---

*Document version 2 — 13 May 2026. Anchored to `Indicators_Computation_v4.md`.*
