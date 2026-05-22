# GSCO Environmental Tool — Indicator ID Schema (v2)

**Purpose.** Single source of canonical IDs for every indicator the v1 tool computes. These IDs are what the engine returns in result payloads, what `selectedIndicators` lists, what the Indicator Library renders, what the CSV/JSON exports column-name, and what the Reports Page templates address.

**Authority.** Names and groupings derive from `Indicators_Computation_v4.md`. Any new indicator must first be added there, then surfaced here.

**Date.** 22 May 2026 (v2.2 — M-TIER-A1).

**Changes from v2.1 (M-TIER-A1, 22 May 2026).** Single-line footnote in §6.1 noting that the `column_to_surface_uncertainty` field doubles as the A1 confidence multiplier — same enum value drives both the audit-§1.5 provenance honesty tag and the IC_v4.2 §8.1 confidence formula's `[1.00 / 0.95 / 0.88 / 0.80 / 1.00]` multiplier lookup. One source of truth for the per-gas penalty.

**Changes from v2.0 (M-V1x-RECONCILE, 22 May 2026).** Reconciles the schema with `Indicators_Audit_and_v1x_Roadmap.md` v1.5 and the live engine state. Ten patches:
- **Patch 1:** measurement-suffix table extended with `.pct_norm`, `.dist_km`, `.mean`, `.total`, `.relative_intensity`, `.slope`, `.slope_p` — these are emitted by the engine but were undocumented in v2.0.
- **Patch 2:** CAMS band names corrected — `particulate_matter_2.5um` → `particulate_matter_d_less_than_25_um_surface` (same pattern for PM₁₀). The legacy strings in v2.0 reflected a prior CAMS catalogue revision; the live engine has used the surface-suffixed names since M-CAMS-BAND-FIX.
- **Patch 3:** §3.1 — `ghg.co2.anomaly` renamed to `ghg.co2.relative_intensity` to reflect the engine-canonical measurement name introduced in M5.5b.
- **Patch 4:** §3.5 — `ghg.sector_match` removed from the deferred list per audit §9.2 (deprecated on metadata-completeness-bias grounds, not deferred).
- **Patch 5:** §4.4 — Hansen forest loss annotated as demoted from the live Habitat_Conversion composite per audit §9.3 v1.4; surviving roles documented.
- **Patch 6:** §4.9 — `nature.external_driver_screening` annotated as sourced from the new `compute_regional_loss_evidence` helper.
- **Patch 7:** new §4.8 — `nature.regional_loss_evidence` derived-indicator section. (§4.9-§4.11 renumbered from §4.8-§4.10.)
- **Patch 8:** §6 — engine output shape replaced with the canonical 15-field provenance schema (M5.6 11 fields + 4 v1.x additions: `indicator_id`, `column_to_surface_uncertainty`, `temporal_mode`, `sector_signal_anomaly`).
- **Patch 9:** new §6.2 — `skipped_reason` enumeration documented.
- **Patch 10:** §8 — `ghg.sector_match` removed from the reserved namespace.

**Changes from v1.**
- **Bug 1 fix — GHG quality sub-scores promoted to v1.** The four terms in the v1 `GHG_Data_Quality_Attribution_v1` formula (`Temporal_Coverage`, `Spatial_Resolution_Suitability`, `Retrieval_or_Inventory_Quality`, `Nearby_Source_Isolation`) were wrongly listed as deferred-to-v1.x in v1's §3.4 and §8. They are v1 — IC_v4 §2.3 has them weighted 0.33 / 0.27 / 0.27 / 0.13. Surfaced here as a new §3.4 "GHG quality sub-scores (v1)". The §8 reserved namespace now lists only the genuinely deferred terms.
- **Bug 2 fix — Nature sub-aggregates de-mixed from quality.** `nature.biodiversity_exposure` was wrongly grouped under §4.8 "Quality-attribution sub-scores" in v1. It is in fact a *sub-aggregate that feeds `Nature_FollowUp_Priority`* (IC_v4 §3.3), not a quality term. Moved into a new §4.X "Nature sub-aggregates" section that also explicitly groups `nature.habitat.conversion_score` and `nature.vegetation_condition` (which remain in their natural domain sections too — the new section is the canonical reference for "the three things that feed the pillar follow-up").
- **§8 trimmed.** With the bug fixes above, the v1.x reserved namespace shrinks to: `ghg.high_gwp_sector_risk`, `ghg.wind_consistency`, `ghg.sector_match`, `nature.buffer_sensitivity`, `air.fire_active_detection`. `ghg.nearby_source_isolation` is now a v1 ID (the satellite-only proxy in IC_v4 §7.2); v1.x will *upgrade the implementation* using external registries but the ID stays the same. *(v2.1 update: `ghg.sector_match` was further removed from the reserved namespace per audit §9.2 — see patch 4 / patch 10 above.)*
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
| `.relative_intensity` | Ratio of site flux to background flux, clamped at 10× (`ghg.co2` only — see §3.1) | Dimensionless |
| `.z` | Normalised z-statistic | Dimensionless |
| `.hf` | Hotspot frequency (fraction of dates with Z ≥ threshold) | 0–1 |
| `.trend` | Theil-Sen slope | Indicator-native per year |
| `.trend_p` | Mann-Kendall two-sided p-value | 0–1 |
| `.slope` | Synonym for `.trend` (used by `nature.ndvi.slope`) | Indicator-native per year |
| `.slope_p` | Synonym for `.trend_p` (used by `nature.ndvi.slope_p`) | 0–1 |
| `.confidence` | Per-indicator confidence | 0–1 |
| `.score` | Normalised 0–1 score (Indicators_Computation §0.4) | 0–1 |
| `.mean` | Annual flux mean (`ghg.co2` only — ODIAC inventory framing) | Indicator-native |
| `.total` | Area-integrated annual total (`ghg.co2` only) | Indicator-native |
| `.ha` | Area in hectares | hectares |
| `.pct` | Percentage of buffer | 0–100 |
| `.pct_norm` | Saturation-normalised percentage, post-clamp (used inside aggregate formulas; e.g. `clamp(loss_fraction / CONVERSION_SATURATION_PCT, 0, 1)`) | 0–1 |
| `.dist_km` | Distance in kilometres | kilometres |

### Rules

1. **No `.score` suffix on already-0–1 quantities.** Sub-aggregates like `air.industrial_combustion_proxy` are by definition 0–1 scores; the suffix would be redundant.
2. **Areas use `.ha` suffix; percentages use `.pct`; saturation-normalised percentages use `.pct_norm`.** Raw `.pct` is in [0, 100]; `.pct_norm` is clamped to [0, 1] for use inside aggregate formulas.
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
| `air.pm25` | CAMS `particulate_matter_d_less_than_25_um_surface` | kg m⁻³ | µg m⁻³ |
| `air.pm10` | CAMS `particulate_matter_d_less_than_10_um_surface` | kg m⁻³ | µg m⁻³ |
| `air.aod` | MODIS MAIAC `Optical_Depth_055` | dimensionless | dimensionless |

`air.o3.score` is capped at 0.5 (O₃ is context, not primary — Indicators_Computation §1.3).

**Footnote (v2.1 patch 2).** CAMS band names verified against the live CAMS catalogue as of May 2026 (M-CAMS-BAND-FIX). The legacy strings `particulate_matter_2.5um` / `particulate_matter_10um` shown in v2.0 of this schema and in IC_v3 reflected a prior CAMS catalogue revision; the live engine has used the surface-suffixed band names throughout v1. Update IC_v3 → IC_v4 reflects the same correction.

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
| `ghg.co2` | ODIAC (uploaded asset) | kg CO₂ m⁻² yr⁻¹ (flux); t CO₂ yr⁻¹ (total) | `.mean`, `.total`, `.relative_intensity`, `.trend`, `.confidence`, `.score` |
| `ghg.viirs` | VIIRS Black Marble NTL | nW cm⁻² sr⁻¹ | `.site`, `.anomaly`, `.trend`, `.confidence`, `.score` |

CO₂ uses `.mean` and `.total` (annual flux mean and annual area-integrated total) instead of `.site` because ODIAC is an emissions inventory, not a column density.

**Footnote (v2.1 patch 3).** `ghg.co2.anomaly` was renamed to `ghg.co2.relative_intensity` to reflect the engine-canonical measurement name introduced in M5.5b. The renamed measurement is the ratio of site flux to background flux, clamped at 10× as a CARMA-overlap proxy (see IC_v4 §2.1). The `.anomaly` form is no longer emitted; consumers (Indicator Library, Reports, CSV/JSON exports) must use `.relative_intensity`. The audit doc §1.4 flagged this drift between v2.0 of this schema and `engine/ghg.py`.

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

`ghg.high_gwp_sector_risk` (sector input required), `ghg.wind_consistency` (ERA5 wind ingest required — see `GEE_Database_List_v3.md` §7).

**v2.1 deprecation note (patch 4).** `ghg.sector_match` was listed here in v2.0 as deferred-to-v1.x. **It is now scrapped pre-implementation** on methodological grounds per `Indicators_Audit_and_v1x_Roadmap.md` §9.2: any confidence-formula term that requires user-supplied metadata of variable completeness introduces metadata-completeness bias into the confidence score. The cross-checking semantics of `Sector_Match` — comparing prior (sector tag) against observation (satellite signal) — have no clean default when the prior is missing: zero implies "low consistency", one implies "high consistency", and neither is true. Rule 1 rescaling (set to 0, renormalise) would silently encode "no sector data = full confidence", which is wrong.

`Sector_Match` survives conceptually only as the standalone `sector_signal_anomaly` provenance flag (see §6.1) — informational, fires only when both a sector tag is present AND the satellite signal is inconsistent with it. Suppliers without a sector tag generate `null`, preserving the no-metadata-bias rule. This flag does not enter any score or confidence arithmetic.

**`High_GWP_Sector_Risk` is not affected by the same critique** and remains deferred (not scrapped). `High_GWP_Sector_Risk` is an additive upward correction representing "the satellites are blind to your sector's dominant gases, so add prior-information risk." Absence means "add nothing" — the correct conservative default. Rule 1 rescaling works cleanly there.

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

**v2.1 status note (patch 5).** Per `Indicators_Audit_and_v1x_Roadmap.md` §9.3 v1.4, `nature.forest_loss.*` is **demoted from the live `Habitat_Conversion` composite**. The 0.10 weight it previously carried in `Habitat_Conversion` has been redistributed proportionally across the four remaining Dynamic-World-based terms (new weights: 0.40 / 0.27 / 0.22 / 0.11 — see IC_v4 §3.2). Hansen survives in two scoped roles:

1. **Input to `regional_loss_evidence`** (see new §4.8 below), which feeds `nature.external_driver_screening` (§4.9). The 5-year fixed Hansen lookback compares loss rates inside the site buffer vs the background ring; large divergence flags external drivers.
2. **Standing-exposure reference layer** displayed in the Indicator Library (P-09). Cumulative loss across the 5-year window with the Hansen vintage and lookback span shown.

**Provenance carries `data_type = "reference_dataset"` and `temporal_mode = "standing_exposure"`** (see §6.1), mirroring ODIAC's post-M5.5b treatment in the GHG pillar. The plantation-cycle false-positive caveat (Hansen detects woody-cover removal without distinguishing managed-plantation harvest from primary-forest loss) is now low-stakes — Hansen no longer drives the live screening score.

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

### 4.8 Regional loss evidence (derived; v2.1 patch 7)

| ID | Type | Notes |
|---|---|---|
| `nature.regional_loss_evidence` | 0–1 (binary in v1) | Computed by `engine.nature.compute_regional_loss_evidence` from Hansen `lossyear`. Returns **1.0** when `ring_loss_rate > 2 × buffer_loss_rate` over the most recent 5 Hansen loss years, else **0.0**. Both buffer and ring use the same fixed 5-year Hansen lookback (independent of the user's analysis-window `time_range` — Hansen's annual cadence is too coarse for short windows). Feeds `nature.external_driver_screening` (§4.9). Provenance: `data_type = "reference_dataset"`, `temporal_mode = "standing_exposure"`. Not user-selectable; runs automatically whenever the Nature pillar runs (cheap — one reduce-region call). See IC_v4 §7.5 for the formula and audit §9.3 v1.4 for the methodological rationale. |

### 4.9 Quality-attribution sub-scores

These are the six terms in `Nature_Quality_Attribution` (IC_v4 §3.3). All are 0–1 confidence-side scores.

| ID | Type | Notes |
|---|---|---|
| `nature.valid_pixel_coverage` | 0–1 | §3.3 |
| `nature.cloud_observation_quality` | 0–1 | §3.3 |
| `nature.dw.class_confidence` | 0–1 | §3.3 (same underlying value as in §4.2; used both as a DW output and as a quality-attribution input) |
| `nature.seasonal_comparability` | 0–1 | §3.3 |
| `nature.supplier_spatial_link` | 0–1 | §7.5 |
| `nature.external_driver_screening` | 0–1 | §7.5; v2.1: computed by `engine.nature.compute_regional_loss_evidence` (§4.8 above) — returns 1.0 if `ring_loss_rate > 2 × buffer_loss_rate` over the most recent 5 Hansen loss years, else 0.0. |

### 4.10 Sub-aggregate scores

The three terms that feed `Nature_FollowUp_Priority` (IC_v4 §3.3) — *exposure-side* scores, not quality-side. Two of them are also surfaced under their natural domain headers above (§4.3 for habitat, §4.5 for vegetation); this section is the canonical reference for "the three sub-aggregates that compose the pillar follow-up priority".

| ID | Type | Defined in | Notes |
|---|---|---|---|
| `nature.biodiversity_exposure` | 0–1 | IC_v4 §3.2, weight 0.30 | KBA-driven exposure: `0.40·KBA + 0.30·Sensitive_LandCover + 0.20·Water_Exposure + 0.10·Buffer_Sensitivity_v1` (last term = 0 in v1, weights rescaled per §7.1) |
| `nature.habitat.conversion_score` | 0–1 | IC_v4 §3.2, weight 0.30 | `Habitat_Conversion` aggregate; also listed in §4.3 |
| `nature.vegetation_condition` | 0–1 | IC_v4 §3.2, weight 0.25 | `Vegetation_Condition_v1` (EVI removed; weights rescaled per §7.4); also listed in §4.5 |

### 4.11 Pillar aggregates

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

Every engine function returns its results keyed by these IDs. Example for a single supplier screening, abbreviated:

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

  "_provenance.air.no2":   { /* 15 fields — see §6.1 */ },
  "_provenance.ghg.ch4":   { /* 15 fields */ },
  "_provenance.nature.kba":{ /* 15 fields */ }
}
```

### 6.1 Canonical provenance block (15 fields)

Every single-value indicator emits a `_provenance.<pillar>.<indicator>` block with the 15 fields below. Schema is enforced by `engine.core.provenance.build_provenance` — typos in any validated field raise `ValueError` at construction. Insertion order is stable across all blocks so downstream consumers (P-05 UI, P-11 reports, audit logs) can rely on field ordering.

| Field | Type | Source | Notes |
|---|---|---|---|
| `indicator_id` | string | **v1.x** | Self-describing — e.g. `"air.no2"`, `"ghg.ch4"`, `"nature.regional_loss_evidence"`. Also drives auto-lookup of `column_to_surface_uncertainty` and `temporal_mode` defaults. |
| `asset_id` | string | M5.6 | EE asset path used (e.g. `COPERNICUS/S5P/OFFL/L3_NO2`) |
| `band` | string \| null | M5.6 | Band name (or `null` for vector / derived) |
| `data_type` | enum | M5.6 | `satellite_observation` \| `ml_classified_satellite` \| `gridded_model_output` \| `emissions_inventory_allocation` \| `reference_dataset` |
| `data_source` | string | M5.6 | Human-readable origin (e.g. `"BirdLife International (Key Biodiversity Areas)"`) |
| `native_scale_m` | float | M5.6 | Native pixel size in metres (0.0 for vector data) |
| `method_note` | string \| null | M5.6 | One-line computation summary |
| `time_range` | tuple[str, str] | M5.6 | Request window in `("YYYY-MM-DD", "YYYY-MM-DD")` form, or `("static", "static")` sentinel for time-invariant reference data |
| `coverage_window` | tuple[str, str] \| null | M5.6 | Effective data-coverage window (may differ from request if the dataset is sparse) |
| `skipped_reason` | string \| null | M5.6 | See §6.2 enumeration |
| `observations` | dict \| null | M5.6 | `{count: int, unit: str}` where `unit` ∈ {`daily_images`, `monthly_grids`, `annual_rasters`, `16day_composites`, `static_snapshot`} |
| `column_to_surface_uncertainty` | enum | **v1.x** | `strong` \| `moderate` \| `moderate_weak` \| `weak` \| `n_a`. Auto-looked-up from `indicator_id` against the audit §1.5 per-gas table: NO₂ = `moderate`, SO₂ = `moderate_weak`, CO = `weak`, HCHO = `moderate`, CH₄ = `weak`, O₃ / AAI / PM / AOD / ODIAC / DW / Hansen / KBA / NDVI = `n_a`. Explicit override allowed via kwarg. **Also drives the A1 confidence multiplier** (M-TIER-A1 / `IC_v4.2 §8.1`): the same enum value indexes a `[1.00 / 0.95 / 0.88 / 0.80 / 1.00]` lookup that scales the per-indicator confidence raw score, so the column-vs-surface honesty tag and the confidence multiplier come from one source of truth. |
| `temporal_mode` | enum | **v1.x** | `live_window` \| `standing_exposure`. Auto-looked-up: `ghg.co2` (ODIAC) and `nature.forest_loss` (Hansen) → `standing_exposure` per audit §9.3; all others → `live_window`. |
| `sector_signal_anomaly` | bool \| null | **v1.x** | Always `null` in v1. Lights up with Tier C2 sector plumbing per audit §9.2 — fires only when (a) supplier has a sector tag AND (b) the satellite signal is inconsistent with the tag. Suppliers without a sector tag generate `null`, preserving the no-metadata-bias rule. **Informational only — does not enter any score or confidence arithmetic.** |
| `extra` | dict | M5.6 | Indicator-specific extension (e.g. ODIAC's `c_to_co2_factor`; KBA's `distance_decay_km`; `regional_loss_evidence`'s rate calculations) |

### 6.2 `skipped_reason` enumeration

`build_provenance` accepts any string for `skipped_reason` (validation is on `data_type` and `observations.unit`, not on this field), but the engine emits one of the codes below. UI's `detect_e1_reason()` (per the locked architecture rule M-RING-UX) routes E1_AllFailed messages off these codes.

| Code | Meaning |
|---|---|
| `null` | Indicator computed successfully |
| `background_ring_no_data` | Background ring overlaps ocean / lacks usable pixels (per IC_v4 §6.3 point 6) |
| `no_<gas>_pixels` | Site buffer has zero valid pixels for the given pollutant after QA filtering (e.g. `no_no2_pixels`, `no_ch4_pixels`) |
| `no_dw_pixels` | Dynamic World composite has no valid pixels in buffer or window (e.g. heavy cloud cover) |
| `no_hansen_pixels` | Hansen lossyear has no usable pixels in AOI (rare; coastal / polar edges) |
| `no_data_at_all` | All indicator inputs returned empty — AOI may be over water or outside coverage |

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
| `nature.buffer_sensitivity` | Sector input (currently set to 0 inside `nature.biodiversity_exposure` per IC_v4 §3.2 / §7.1) |
| `air.fire_active_detection` | FIRMS upload |

**v2.1 deprecation note (patch 10).** `ghg.sector_match` was listed here in v2.0 as a reserved v1.x ID. It has been **removed from the reserved namespace** and should not be re-introduced. The deprecation is methodological, not operational: per `Indicators_Audit_and_v1x_Roadmap.md` §9.2, any confidence-formula term requiring user-supplied metadata of variable completeness introduces metadata-completeness bias. See §3.5 for the full rationale. The concept survives only as the `sector_signal_anomaly` provenance flag (see §6.1) — informational, not in any score or confidence arithmetic, and emits `null` when no sector tag is present.

---

*Document version 2.1 — 22 May 2026. Anchored to `Indicators_Computation_v4.md` and `Indicators_Audit_and_v1x_Roadmap.md` v1.5.*
