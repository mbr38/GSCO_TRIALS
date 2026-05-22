# GSCO Environmental Tool — Indicators Computation Reference (v4.2)

**Changes from v4.1 (M-TIER-A1, 22 May 2026).**
- **New §8 — Confidence formula.** Pre-A1, `§0.2 step 6` promised a confidence formula in §6.3 but §6.3 was occupied by buffer-warning logic and the formula had no home in the doc (the engine docstring called this out as a known doc gap). §8 now carries the canonical 4-term + column-to-surface multiplier formula, the pillar-level rollup logic (Air uniform mean; GHG and Nature via existing weight dicts with re-derived sub-scores), and the composite `min(...)` rule. The §0.2 step 6 pointer should be read as `see §8` until the next renumbering.
- **GHG_Data_Quality_Attribution sub-scores rewired.** Three of the four — `temporal_coverage`, `spatial_resolution_suitability`, `retrieval_inventory_quality` — now derive from per-indicator A1 confidence terms (mean of `N_valid`, `spatial_context`, `QA` respectively across the three GHG indicators) instead of placeholders. Sums-to-1.00 weight dict (0.33 / 0.27 / 0.27 / 0.13) is unchanged. `nearby_source_isolation` stays an independent §7.2 spatial proxy.
- **Nature `valid_pixel_coverage` rewired.** Pre-A1 it echoed `dw.class_confidence`; post-A1 it's the mean of per-indicator A1 `QA` terms across Nature indicators. The other five Nature QA sub-scores keep their existing semantics. `NATURE_QUALITY_ATTRIBUTION_WEIGHTS` unchanged.



**Purpose.** Single reference for computing every indicator in the v1 tool: what is measured, the formula(s) required, the ESG-aligned unit of measurement, the assumptions behind each formula and which of those assumptions are scientifically weak, and the rules for buffer definition.

**Sources.** `Final_Indicators_List.pdf`, `Indicators_Full_Research.pdf`, `PLFS_v4.md`, `Wireframes_All_v4.md`, `GEE_Database_List_v3.md`, `Indicator_ID_Schema_v2.md`, `Indicators_Audit_and_v1x_Roadmap.md` v1.5.

**Changes from v4.0 (M-V1x-RECONCILE, 22 May 2026).**
- **§1.1 CAMS band names corrected.** `particulate_matter_2.5um` → `particulate_matter_d_less_than_25_um_surface`; same form for PM₁₀. Existing engine code already uses the correct names; the doc was drifted. (M-CAMS-BAND-FIX.)
- **New §1.5 — Column-to-surface uncertainty framing.** Condensed from `Indicators_Audit_and_v1x_Roadmap.md` §1.5: the science behind why column densities don't equal surface concentrations, how the Z-score mitigates this, the "context not measurement" framing, the O₃ cap rationale, and the per-gas uncertainty table. Surfaced as the `column_to_surface_uncertainty` provenance field — see `Indicator_ID_Schema_v2.md` §6.1.
- **§2.3 Core_GHG_Audit_Support_v1 — updated to engine-actual M5.5b form.** Three-key composite `0.46·CH₄_Context_Adjusted + 0.44·Combustion_Proxy + 0.10·Activity_Score` (sums 1.00). ODIAC demoted to standing exposure per M5.5b; live signals rescaled by 1/0.61. Pre-M5.5b values retained in the method-note for lineage.
- **§2.3 GHG_Data_Quality_Attribution_v1 method note refined.** `Sector_Match` reclassified from "deferred" to "scrapped" per audit §9.2 — metadata-completeness bias makes any sector-tag-conditioned confidence term invalid. `Wind_Consistency` remains deferred to v1.x Tier C1a.
- **§3.2 Habitat_Conversion — Hansen demoted per audit §9.3 v1.4.** Four-term post-demotion composite `0.40 / 0.27 / 0.22 / 0.11` (sums 1.00). Hansen's `Forest_Loss_pct` survives only as a standing-exposure reference layer and as input to `regional_loss_evidence`. Calibration note (10 % saturation) unchanged.
- **§7.1 Rule 1 example updated** from the pre-M5.5b CO₂-rescale to the M5.5b case (ODIAC demoted, three remaining terms rescaled by 1/0.61). Matches engine state.
- **§7.5 `regional_loss_evidence` promoted to a proper spec block.** Fixed 5-year Hansen lookback, ring-vs-buffer rate comparison with 2× threshold; cross-references `engine.nature.compute_regional_loss_evidence` and audit §9.3.

**Changes from v3.**
- **§2.3 GHG_Data_Quality_Attribution_v1 weights corrected.** The v3 version had weights 0.30 / 0.24 / 0.24 / 0.12 (sum 0.90) with an incorrect "rescaled by 1/0.85" comment. The actual deferred terms (Wind_Consistency 0.15 + Sector_Match 0.10) sum to 0.25, so the correct rescale factor is **1/(1−0.25) = 1.333…** giving weights **0.33 / 0.27 / 0.27 / 0.13** which sum to 1.00. Updated accordingly. The v1 quality sub-scores (Temporal_Coverage, Spatial_Resolution_Suitability, Retrieval_or_Inventory_Quality, Nearby_Source_Isolation) are all live in v1 — see `Indicator_ID_Schema_v2.md` §3.4.
- **Cross-reference bump.** Pointers updated from `Indicator_ID_Schema_v1.md` to `Indicator_ID_Schema_v2.md`.

**Changes from v2.**
- **§0.2 Step 5 — anomaly Z threshold raised to 2** (was 1). Z ≥ 2 corresponds to the ~95th percentile under Gaussian noise — matches standard atmospheric-science convention for "significant deviation" and makes `HF` interpretable as the fraction of *genuinely* anomalous observations.
- **§0.5 Time windows — screening time range fixed.** Screening always uses the latest valid 90-day composite for each dataset. The time-range selector is hidden in screening mode on P-04. The selector is only meaningful for monitoring/trend mode.
- **§0.5 Background window for monitoring locked to Option 1.** Background statistics use the 3 years immediately preceding the *user's analysis-window start*, not the 3 years preceding today. This keeps a 2020–2024 audit reproducible when re-run in 2027.
- **§1.2 `PM_or_Aerosol_score` fallback trigger formalised.** Fallback to AAI-only when CAMS valid-pixel coverage in the buffer falls below 0.5 or the CAMS site mean is null.
- **§3.1 Habitat conversion baseline X = 5 years.** Fixed for v1 (`HABITAT_BASELINE_YEARS = 5`). User override deferred to a future extension.
- **§3.2 Dynamic World class mapping made explicit.** `DW_NATURAL_CLASSES = ['trees', 'grass', 'shrub_and_scrub', 'flooded_vegetation']` locks the natural/semi-natural bucket used by `Sensitive_LandCover_Presence` and by habitat-conversion accounting.
- **§6.3 Pixel-size warning logic refined.** Trigger is "buffer < largest selected-indicator pixel"; warning surfaces the affected indicators rather than the comparison itself.
- **§7.2 `Nearby_Source_Isolation`** canonical formula is now the **average** of the NO₂-based and VIIRS-based formulations (was "the two can be averaged for a robust composite").
- **Indicator IDs.** `Indicator_ID_Schema_v2.md` is the canonical naming source. This document refers to indicators by their human-readable names; the schema doc translates to IDs.

**Changes from v1.** Added §3.4 (habitat conversion subtypes — distinction between habitat conversion, bare-ground and built-up expansion). Expanded §6.2 with rationale for the chosen site and background radii. Added §6.4 (sub-formula explanations for KBA, water exposure, recovery, seasonal comparability). Added same-month seasonality option to the repeatable core method (§0.6). Added calibration note to Habitat_Conversion (§3.2).

---

## 0. Conventions used in every formula

These conventions apply across all three pillars and need to be set explicitly before reading the tables, because half the apparent ambiguity in the source PDFs comes from these not being stated.

### 0.1 Two types of value: raw vs score

Every indicator produces **both**:

- A **raw value** in physical units (e.g. NO₂ in mol m⁻², NDVI dimensionless, hectares for habitat change). These are what the user sees in the dashboard. ESG standards care about these.
- A **0–1 score** used inside composite formulas. Whenever a formula in this document uses `X_score`, it means the 0–1 normalised version of `X`, derived as described in §0.4.

The composite formulas (e.g. `Core_GHG_Audit_Support = 0.35·CO₂_Context + …`) only operate on 0–1 scores, never on raw values. Mixing them would scramble the units.

### 0.2 The repeatable core method for any pollutant signal

For every Sentinel-5P pollutant and for CAMS PM₂.₅, the same six steps run (Final Indicators List, Source 11):

| Step | Output | Formula |
|---|---|---|
| 1 | Site value | `P_site = mean(pixels within Site_Buffer)` |
| 2 | Background value | `P_background = median(pixels within Background_Ring)` |
| 3 | Absolute anomaly | `Anomaly = P_site − P_background` |
| 4 | Normalised z | `Z = (P_site − P_background) / σ_background` |
| 5 | Hotspot frequency | `HF = N_anomaly_obs / N_valid_obs`, where an "anomaly observation" is a date on which `Z ≥ ANOMALY_Z_THRESHOLD`. Default `ANOMALY_Z_THRESHOLD = 2` (~95th percentile under Gaussian noise). Tunable as a single constant in code. |
| 6 | Confidence | `Confidence = f(QA, N_valid, anomaly_strength, spatial_context, wind)` — see §6.3 for the v1 implementation without wind |

`Site_Buffer` and `Background_Ring` are defined in §6.

### 0.3 Trend computation

For any time series of site values over the analysis window, trend is the **Theil–Sen slope** with its **Mann–Kendall p-value**:

- Theil–Sen slope `m` in raw units per year (e.g. mol m⁻² yr⁻¹, ha yr⁻¹, NDVI yr⁻¹).
- Mann–Kendall two-sided p-value.
- The slope's *direction* (sign) feeds the score. Magnitude is normalised by background variability.

Theil–Sen is preferred over OLS because it is robust to the heavy-tailed outliers in TROPOMI/CAMS time series (cloud-affected days, retrieval failures).

### 0.4 Normalisation from raw value to 0–1 score

For any raw value `X` with site value `X_site`, background median `X_bg` and background standard deviation `σ_bg`:

```
X_score = clamp( (X_site − X_bg) / (k · σ_bg) , 0 , 1 )      for "higher = worse"
X_score = clamp( (X_bg − X_site) / (k · σ_bg) , 0 , 1 )      for "lower = worse" (e.g. NDVI)
```

`k` is the cap multiplier; **default k = 3** (≈ 99th percentile), so a 3-σ exceedance saturates the score. `k` is exposed as a single tunable constant in the codebase, not as a user input.

For values that are already in [0, 1] (e.g. KBA overlap %, hotspot frequency, classification confidence), the raw value *is* the score.

### 0.5 Time windows

| Mode | Window |
|---|---|
| Screening (P-05) | Most recent valid 90-day composite ending on the latest valid date for that dataset. **The time-range selector is hidden in screening mode on P-04** — screening is always "now" relative to data availability. |
| Trend / Monitoring (P-06) | User-selected time range, minimum 12 months |
| Background statistics (screening) | Last 3 years preceding the screening composite end date |
| Background statistics (monitoring) | Last 3 years preceding the **user's analysis-window start** (not preceding today). This keeps a re-run of the same audit reproducible at any later date. |

### 0.6 Same-month seasonality baseline (recommended default)

For datasets with strong seasonal cycles — NDVI, Dynamic World composition, CAMS PM₂.₅, and CH₄ — the background statistics in §0.2 are computed only from observations in the **same calendar month(s)** as the current analysis window, over the last 3 years.

Example: if the screening composite ends in July, the background median and σ are computed from June–August observations over the last 3 years, not from all 36 months.

This removes the largest source of seasonal bias from the repeatable core method at near-zero implementation cost (one extra filter in the masking pipeline). It is on by default for NDVI and Dynamic World; optional for the air-pollution datasets where seasonality is weaker.

A full phenological baseline (per-day-of-year expected curve) is deferred to v1.x.

---

## 1. Air Pollution pillar

### 1.1 Single-value indicators

| Indicator | Raw value(s) measured | Computation formula | Unit (ESG-aligned) |
|---|---|---|---|
| **NO₂** | `NO₂_site`, `NO₂_background`, `NO₂_anomaly`, `Z_NO₂`, `HF_NO₂`, `Conf_NO₂` | Repeatable core method (§0.2) on band `NO2_column_number_density` from `COPERNICUS/S5P/OFFL/L3_NO2` | mol m⁻² (raw); convert to **µmol m⁻²** for display (×10⁶) to align with ESRS E2 / SASB convention |
| **SO₂** | `SO₂_site`, `SO₂_background`, anomaly, Z, HF, Conf | Repeatable core method on `SO2_column_number_density` | mol m⁻² → µmol m⁻² for display |
| **CO** | `CO_site`, `CO_background`, anomaly, Z, HF, Conf | Repeatable core method on `CO_column_number_density` | mol m⁻² → mmol m⁻² for display |
| **HCHO** | `HCHO_site`, anomaly, Z, HF, Conf | Repeatable core method on `tropospheric_HCHO_column_number_density` | mol m⁻² → µmol m⁻² |
| **O₃** | `O₃_site`, anomaly, Z, HF, Conf | Repeatable core method on `O3_column_number_density` | mol m⁻² → DU (Dobson Units), conversion factor 1 DU = 4.4615 × 10⁻⁴ mol m⁻² |
| **AAI** | `AAI_site`, anomaly, Z, HF, Conf | Repeatable core method on `absorbing_aerosol_index` | Dimensionless |
| **CH₄** | `CH₄_site`, anomaly, Z, HF, Conf | Repeatable core method on `CH4_column_volume_mixing_ratio_dry_air` | ppb (parts per billion) |
| **PM₂.₅ (modelled)** | `PM2.5_site`, `PM2.5_bg`, anomaly, trend slope, Conf | Repeatable core method on CAMS `particulate_matter_d_less_than_25_um_surface` band, ×10⁹ to convert kg m⁻³ → µg m⁻³ [^cams-band] | **µg m⁻³** (ESRS E2 / WHO AQG / GRI 305-7 standard unit) |
| **PM₁₀ (modelled)** | as above | CAMS `particulate_matter_d_less_than_10_um_surface` band, ×10⁹ [^cams-band] | µg m⁻³ |

[^cams-band]: M-CAMS-BAND-FIX. The legacy band aliases `particulate_matter_2.5um` and `particulate_matter_10um` referenced in earlier doc revisions never matched the CAMS asset; the asset always exposed the long-form surface-mass-mixing-ratio band names used above. Engine code already uses the correct names — this is a doc-drift correction only.
| **AOD (optional)** | `AOD_site`, anomaly, trend | MODIS MAIAC `Optical_Depth_055`, masked by `AOD_QA` bits 8–11 | Dimensionless |

### 1.2 Sub-aggregate indicators

| Indicator | Formula | Notes |
|---|---|---|
| Industrial Combustion Proxy Score | `0.60·NO₂_score + 0.40·CO_score` | NO₂ dominates because it's the more facility-attributable signal; CO supports |
| Heavy Industry / Sulphur-Heavy Activity Score | `0.60·SO₂_score + 0.30·NO₂_score + 0.10·PM_or_Aerosol_score` | SO₂ dominates because it's sector-specific |
| VOC / Photochemical Pollution Context Score | `0.50·HCHO_score + 0.30·NO₂_score + 0.20·O₃_score` | HCHO dominates as VOC proxy |
| Smoke / Dust / Regional Transport Score | `0.40·CO_score + 0.40·AAI_score + 0.20·PM_or_Aerosol_score` | Used as **`Fire_or_Regional_Transport_Risk`** in the GHG pillar (see §4.3) |
| Industrial Air Pollution Burden Score | `0.40·NO₂_score + 0.35·SO₂_score + 0.25·PM_or_Aerosol_score` | Most ESG-relevant; closest to ESRS E2 / GRI 305-7 framing |
| `PM_or_Aerosol_score` | `0.60·PM2.5_score + 0.40·AAI_score` when CAMS available; fallback to `1.00·AAI_score` otherwise | Fallback trigger: `cams_valid_pixel_pct < CAMS_MIN_VALID_PCT` (default 0.5) **or** the CAMS site mean is null over the analysis window. Below half-buffer coverage the CAMS mean is dominated by border-pixel noise. Tunable as `CAMS_MIN_VALID_PCT` in code. |

### 1.3 Pillar aggregates

```
Air_Pollution_Proxy_Score = 0.30·NO₂_score + 0.20·SO₂_score
                          + 0.15·CO_score + 0.15·HCHO_score
                          + 0.10·PM_or_Aerosol_score
                          + 0.10·O₃_context_score

SpatioTemporal_Anomaly_Score   = mean of Z_score across all selected pollutants
Trend_Score                    = mean of Trend_score across all selected pollutants
                                 (Trend_Score := 0 in Screening mode)
Attribution_Confidence_Score   = mean of Conf across all selected pollutants

Air_Pollution_Audit_FollowUp_Priority =
    0.35·Air_Pollution_Proxy_Score
  + 0.30·SpatioTemporal_Anomaly_Score
  + 0.20·Trend_Score
  + 0.15·Attribution_Confidence_Score
```

`O₃_context_score` is treated as context, not as a primary pollution score — it is the same Z-based score but capped at 0.5, because O₃ is a secondary pollutant and not directly emitted (Indicators Full Research, "Best interpretation" table).

### 1.5 Column-to-surface uncertainty (audit §1.5)

**The science.** Sentinel-5P TROPOMI measures the *total column density* of a gas — atoms per unit area integrated through the whole atmosphere. The number a permit officer or ESG auditor actually cares about is the *surface concentration* (µg m⁻³, ppb) at the supplier's fenceline. The mapping from column to surface depends on the gas's vertical distribution, which is set by boundary-layer height, photochemistry, lifetime, and transport — none of which TROPOMI directly resolves.

**Why the tool stays usable anyway.** The repeatable core method (§0.2) compares the supplier site to its own background ring using the *same* retrieval, on the *same* day, through the *same* atmospheric column. Whatever vertical structure inflates or deflates the absolute column value also affects the background, so the Z-score is largely insensitive to this bias. The honesty layer is in the *unit* and the *framing*: the raw values are reported in mol m⁻² (or display units derived from them) and labelled "column density", never as "surface concentration".

**The O₃ cap.** O₃ is the extreme case: nearly all the column is in the stratosphere, and surface O₃ is a *photochemical* product driven by NOₓ + VOCs + sunlight, not a primary emission. Surface O₃ also moves with regional weather over hundreds of kilometres. For these reasons §1.3 caps `O₃_context_score` at 0.5: the score can flag elevated tropospheric O₃ as context, but cannot drive a follow-up priority on its own.

**Per-gas uncertainty table** — populates the `column_to_surface_uncertainty` provenance field for each indicator (see `Indicator_ID_Schema_v2.md` §6.1):

| Indicator | Uncertainty tag | Reason |
|---|---|---|
| `air.no2` | `moderate` | Short lifetime (~hours in boundary layer); most of the column lives near the surface; column ↔ surface mapping is one of the better-understood retrievals. |
| `air.so2` | `moderate_weak` | Surface mapping is good for fresh, near-source plumes but degrades quickly for aged / transported air masses. |
| `air.co` | `weak` | Long lifetime (~weeks); column is dominated by regional / global background; supplier-attribution at fenceline is loose. |
| `air.hcho` | `moderate` | Short lifetime (~hours); useful as a VOC proxy but vertical distribution sensitive to photochemistry. |
| `air.o3` | `n_a` | O₃ is a secondary pollutant, not directly emitted. Capped via §1.3 instead. |
| `air.aai` | `n_a` | Absorbing aerosol *index*, not a column density — already a dimensionless aerosol indicator. |
| `ghg.ch4` | `weak` | Long lifetime (~decade); column is overwhelmingly background; sub-km supplier signal needs days-of-clear-sky aggregation to be visible. |

PM (CAMS), AOD (MAIAC), ODIAC CO₂, VIIRS NTL, Dynamic World, Hansen, NDVI, KBA all default to `n_a` — either they're already surface-level / vector / classification data, or they're modelled allocations rather than column retrievals.

**Operational implication.** The score arithmetic is unchanged. The provenance field puts the right epistemic weight on each indicator for the P-11 report and any future audit log. Reviewers reading a `weak` tag should treat the headline number as context, not as a quantitative emission claim.

---

## 2. GHG pillar

### 2.1 Single-value indicators

| Indicator | Raw value(s) measured | Computation formula | Unit (ESG-aligned) |
|---|---|---|---|
| **CH₄ atmospheric** | `CH₄_site`, anomaly, Z, HF, trend, Conf | Repeatable core method on `CH4_column_volume_mixing_ratio_dry_air` | ppb |
| **Fossil CO₂ emissions context** | `CO₂_mean` (annual), `CO₂_total` (annual), anomaly, trend, Conf | Sum ODIAC pixel values within `Site_Buffer`; `CO₂_total = Σ_pixels area·flux`; `CO₂_anomaly = CO₂_site − CO₂_bg` | **tonnes CO₂ yr⁻¹** for total; **kg CO₂ m⁻² yr⁻¹** for flux. ESG: ESRS E1 / GHG Protocol reports in t CO₂ |
| **Atmospheric XCO₂ context** | — | **Not in v1.** OCO-2/3 deferred per `GEE_Database_List_v2.md` §7 | n/a |
| **Nighttime-light activity** | `VIIRS_mean`, anomaly, trend, Conf | Repeatable core method on `NASA/VIIRS/002/VNP46A2` `Gap_Filled_DNB_BRDF_Corrected_NTL` band | nW cm⁻² sr⁻¹ |

### 2.2 Sub-aggregate indicators

| Indicator | Formula | Notes |
|---|---|---|
| Combustion_Proxy | `0.60·NO₂_score + 0.40·CO_score` | Borrowed from §1.2; same value, reused inside Core GHG |
| Activity_Score | `VIIRS_score` (Z-based, normalised against last 3 years background) | Single value used directly |
| Fossil_CO₂_Context | `CO₂_score` (normalised CO₂ flux within Site_Buffer) | Single value, but see §5.2 on data-vintage handling |
| High_GWP_Sector_Risk | **Deferred to v1.1.** Requires sector input. In v1 set to `0` and rebalance Core_GHG_Audit_Support to sum to 1.0 over the remaining four terms — see §7.1 | n/a in v1 |
| Fossil_Combustion_Score (optional) | `0.50·Fossil_CO₂_Context + 0.30·NO₂_CO_SO₂_Combustion_Proxy + 0.20·Activity_Score` | Useful for heavy-industry suppliers |
| CH₄_Context_Adjusted | `CH₄_Hotspot_Score − 0.20·Fire_or_Regional_Transport_Risk` | See §7.3 for `Fire_or_Regional_Transport_Risk` |
| Activity_Adjusted_CO₂ | `0.70·Fossil_CO₂_Context + 0.30·Nighttime_Light_Activity` | Useful when reported emissions are unavailable |

### 2.3 Pillar aggregates

**v1 (no sector context):**

```
Core_GHG_Audit_Support_v1 =                      (M5.5b: ODIAC demoted)
    0.46·CH₄_Context_Adjusted
  + 0.44·Combustion_Proxy
  + 0.10·Activity_Score                          (sums to 1.00)

  Method: ODIAC's CO₂_Context is no longer in the live composite. The
  1–2-year ODIAC vintage lag means it cannot drive a live screening
  signal (present-day runs against time ranges outside 2020–2023 fail
  entirely with CO₂ in the formula). ODIAC still computes and displays
  as standing-exposure context — see Schema_v2 §6.1 `temporal_mode`.
  High_GWP_Sector_Risk also stays at 0 in v1 pending sector input
  (Tier C1a). The three live signals are rescaled by 1/0.61 from the
  pre-M5.5b values: CO₂ 0.39, CH₄ 0.28, Combustion 0.22, Activity 0.11
  → drop CO₂, divide each remaining by 0.61, round to two decimals.
  See audit §3.4 for full trace.

GHG_Data_Quality_Attribution_v1 =
    0.33·Temporal_Coverage + 0.27·Spatial_Resolution_Suitability
  + 0.27·Retrieval_or_Inventory_Quality
  + 0.13·Nearby_Source_Isolation                 (sums to 1.00)

  Method: Wind_Consistency (0.15) deferred to v1.x Tier C1a (ERA5 wind).
  Sector_Match (0.10) is **scrapped** per audit §9.2 on
  metadata-completeness-bias grounds — any confidence term that requires
  user-supplied sector metadata of variable completeness produces a
  biased score (suppliers without sector tags get an undefined or
  defaulted term that systematically differs from tagged suppliers).
  It is not deferred, not coming back as a confidence-formula term; it
  survives only as the informational `sector_signal_anomaly`
  provenance flag (Schema_v2 §6.1). Remaining four weights rescaled by
  1/0.75 = 1.333…. Nearby_Source_Isolation in v1 uses the satellite-only
  proxy in §7.2.

GHG_Audit_FollowUp_Priority =
    0.40·Core_GHG_Audit_Support
  + 0.25·GHG_SpatioTemporal_Anomaly
  + 0.20·GHG_Trend                (set to 0 in Screening mode)
  + 0.15·GHG_Data_Quality_Attribution
```

**v1.1+ (with sector and wind context — for reference, not implemented in v1):** restore the original weights from `Final_Indicators_List.pdf`.

---

## 3. Nature / Land pillar

### 3.1 Single-value indicators

| Indicator | Raw value(s) measured | Computation formula | Unit (ESG-aligned) |
|---|---|---|---|
| **KBA proximity / overlap** | `dist_to_nearest_KBA`, `overlap_area`, `overlap_pct` | Vector distance from supplier point to `projects/ee-kbas-in-gee/assets/current`; intersect with Site_Buffer for overlap | km (distance); hectares (overlap area); % (overlap of buffer) — ESRS E4 / GRI 101 expect hectares and % |
| **Current land cover composition** | Per-class areas and percentages: trees, crops, built, bare, grass, shrub, flooded vegetation, water | Reduce `GOOGLE/DYNAMICWORLD/V1` 90-day mode composite over Site_Buffer; per-class area = pixel count × pixel area | hectares, % of buffer |
| **Dynamic World class confidence** | `mean_class_probability` for dominant class | Use the probability bands in Dynamic World, not just the discrete `label` band | Dimensionless [0, 1] |
| **Habitat conversion** | `natural_loss_ha`, `nat_to_built_ha`, `nat_to_bare_ha`, `nat_to_crop_ha`, `built_expansion_ha`, `annualised_rate` | Compare current 90-day composite vs baseline 90-day composite from **`HABITAT_BASELINE_YEARS` (default 5) years earlier**; per `Indicators Full Research`: `annualised_rate = converted_area_ha / HABITAT_BASELINE_YEARS`. The 5-year default sits at the noise/signal sweet spot — long enough that real conversion exceeds Dynamic World interannual variability, short enough that DW (2015→) has full coverage globally, and aligned with ESRS E4 and TNFD 5-year reporting horizons. In trend/monitoring mode the baseline is the user's analysis-window start instead of the 5-year fixed offset. Tunable as `HABITAT_BASELINE_YEARS` in code. | hectares; hectares yr⁻¹; % of buffer |
| **Forest loss** | `forest_loss_ha`, `forest_loss_pct` | Hansen `lossyear` band ≥ baseline year, within Site_Buffer | hectares, % |
| **NDVI mean** | `NDVI_site` | `NDVI = (B8 − B4) / (B8 + B4)` from `COPERNICUS/S2_SR_HARMONIZED`, masked by SCL classes 3, 8, 9, 10, 11 (cloud/shadow/snow) and by Dynamic World built/water/bare | Dimensionless [−1, +1] |
| **NDVI anomaly** | `NDVI_anomaly`, `Z_NDVI` | Repeatable core method, with masking as above | Dimensionless |
| **NDVI trend** | `NDVI_slope`, `NDVI_p` | Theil-Sen slope over the analysis window, on monthly NDVI medians | NDVI yr⁻¹ |
| **Low-NDVI / degraded area** | `low_NDVI_ha`, `low_NDVI_pct` | Pixels with NDVI < 0.3 within natural-cover mask; convert pixel count to area | hectares, % |
| **Bare-ground / disturbance expansion** | `bare_area_now`, `bare_expansion_ha`, anomaly, trend | Dynamic World "bare" class; optional Sentinel-2 BSI confirmation | hectares, hectares yr⁻¹ |
| **Built-up expansion** | `built_area_now`, `built_expansion_ha` | Dynamic World "built" class; optional Sentinel-2 NDBI confirmation | hectares |
| **Water / flooded vegetation exposure** | `water_area_now`, `flooded_veg_area_now`, `dist_to_nearest_water` | Dynamic World classes "water" and "flooded_vegetation" | hectares, km |
| **Restoration / recovery signal** | `NDVI_improvement_pct`, `natural_cover_gain_ha`, `bare_reduction_ha` | Positive NDVI trend AND increase in natural-cover classes between baseline and current | hectares; % |

**Note:** EVI is excluded from v1 per the user's request (see §7.4).

### 3.2 Sub-aggregate indicators

```
Biodiversity_Exposure =
    0.40·KBA_Proximity_or_Overlap
  + 0.30·Sensitive_LandCover_Presence
  + 0.20·Water_or_FloodedVegetation_Exposure
  + 0.10·Buffer_Sensitivity_v1   (= 0 in v1 without sector context; see §7.1)

Habitat_Conversion =                              (audit §9.3 v1.4: Hansen demoted)
    0.40·Natural_Habitat_Loss_pct
  + 0.27·Natural_to_Built_pct
  + 0.22·Natural_to_Bare_pct
  + 0.11·Annualised_Conversion_Rate_score         (sums to 1.00)

  Method: Hansen `Forest_Loss_pct` was removed from the live composite per
  audit §9.3 v1.4. Hansen's standing-exposure framing (cumulative loss
  since 2000) breaks the live-window semantics of the four Dynamic-World-
  based terms; the standing-exposure asset cannot meaningfully share a
  weighted sum with live-window observations. Hansen survives outside
  this composite as (a) a standing-exposure reference layer in the
  Indicator Library and (b) the only input to `regional_loss_evidence`
  (§7.5). Its pre-demotion 0.10 weight is redistributed proportionally
  over the four remaining terms (rescale factor 1/0.90). Pre-demotion
  values (for lineage): 0.35 / 0.25 / 0.20 / 0.10 / 0.10.

  Calibration note: each `_pct` term is a fraction in [0, 1] divided by a
  10 % saturation point, i.e. `Natural_Habitat_Loss_pct = clamp(loss_fraction / 0.10, 0, 1)`.
  Without this, a typical buffer with 5 % loss produces a misleadingly low
  ~0.05 score. The 10 % saturation point treats 10 % buffer conversion as
  "fully concerning" and matches the order of magnitude reported as material
  in ESRS E4 / GRI 101 case studies. Tunable as `CONVERSION_SATURATION_PCT`
  in code.

Vegetation_Condition_v1 =                          (EVI removed, weights rescaled — see §7.4)
    0.45·Inverted_NDVI_SpatioTemporal_Anomaly
  + 0.25·Negative_Vegetation_Trend
  + 0.20·Low_Vegetation_Area_pct
  − 0.10·Recovery_Signal
```

Sub-formula breakdowns:

| Sub-score | Formula | Meaning in plain English |
|---|---|---|
| `KBA_Proximity_or_Overlap` | `max( overlap_pct/100 , exp(−dist_km / 10) )` | Handles two cases. If the supplier is inside / partly inside a KBA, the overlap fraction drives the score directly. If the supplier is outside all KBAs, the `exp(−dist/10)` term takes over: 0 km → 1.0; 7 km → 0.50; 20 km → 0.14; 50 km → 0.007. The score halves every ~7 km — concern decays fast but not catastrophically. The `max` keeps whichever case is stronger. |
| `Sensitive_LandCover_Presence` | `(trees_pct + flooded_veg_pct + grass_pct + shrub_pct) / 100` (capped at 1.0) | The fraction of the buffer that is natural / semi-natural habitat. The four-class sum uses the Dynamic World class mapping below — `DW_NATURAL_CLASSES` is fixed in code, not a tunable. |
| `Water_or_FloodedVegetation_Exposure` | `min( (water_pct + flooded_veg_pct)/20 , 1.0 )` | The "/20" is the saturation point: 20 % combined aquatic / wetland cover = score 1.0. A supplier with 50 % water exposure is not 2.5× more concerning than one with 20 %; both are "highly water-adjacent". The cap stops one dimension from dominating Biodiversity_Exposure. |
| `Inverted_NDVI_SpatioTemporal_Anomaly` | `clamp( (NDVI_bg − NDVI_site) / (3·σ_bg) , 0, 1 )` | Inverted because *lower* NDVI is worse. Cap at 3·σ_bg (≈ 99th percentile). |
| `Negative_Vegetation_Trend` | `clamp( −NDVI_slope / typical_negative_slope_threshold , 0, 1 )` | Threshold ≈ −0.01 NDVI yr⁻¹ — a calibration, not a physical constant. A −0.01 NDVI/yr slope means losing 0.10 NDVI over a decade (visually obvious). Below that rate, the slope is usually inside natural interannual variability (σ ≈ 0.02–0.05 for stable ecosystems) and not reliably distinguishable from noise. |
| `Low_Vegetation_Area_pct` | `low_NDVI_ha / total_natural_ha`, in [0, 1] | Only counts pixels inside the natural-cover mask, so seasonally bare crop fields don't pollute the score. |
| `Recovery_Signal` | `min( NDVI_improvement_pct/100 + natural_cover_gain_pct/100 , 1.0 )` | Two positive signals: fraction of buffer with significant positive NDVI trend, plus fraction that transitioned from non-natural to natural cover. Subtracted from Vegetation_Condition (the −0.10 term) so recovery reduces priority by up to 10 %, but doesn't erase historical damage. |

### 3.3 Pillar aggregates

```
Nature_Quality_Attribution =
    0.20·Valid_Pixel_Coverage
  + 0.20·Cloud_or_Observation_Quality
  + 0.20·DynamicWorld_Class_Confidence
  + 0.15·Seasonal_Comparability
  + 0.15·Supplier_Spatial_Link              (see §7.5)
  + 0.10·External_Driver_Screening          (see §7.5)

Nature_FollowUp_Priority =
    0.30·Biodiversity_Exposure
  + 0.30·Habitat_Conversion
  + 0.25·Vegetation_Condition
  + 0.15·Nature_Quality_Attribution
```

Sub-formula breakdowns for the data-quality components:

| Sub-score | Formula | Meaning in plain English |
|---|---|---|
| `Valid_Pixel_Coverage` | `valid_pixel_count / total_pixel_count` in the composite | After cloud/shadow masking. Goes down automatically over water or in heavily cloud-covered regions, which is the right behaviour. |
| `Cloud_or_Observation_Quality` | `1 − mean_cloud_pct` weighted by SCL confidence | Sentinel-2-specific cloud quality. |
| `DynamicWorld_Class_Confidence` | Mean of `prob_<dominant_class>` band over Site_Buffer | Already in [0, 1]. High when one class clearly dominates, low when pixels are ambiguous. |
| `Seasonal_Comparability` | `1 − \|month_offset\| / 6`, where `month_offset` is the months between current and baseline composite | When current and baseline composites end in different months, NDVI and Dynamic World composition differ naturally (winter leaves, crop cycles, flooded seasons). Same month → 1.0. 3 months apart → 0.5. 6 months apart → 0.0. Divided by 6 because a 7-month offset is equivalent to a 5-month offset in the other direction. This term carries 0.15 weight inside Nature_Quality_Attribution — without it, comparing July to January would inflate Habitat_Conversion artificially and the user would not see it was seasonally confounded. |
| `Supplier_Spatial_Link` | See §7.5 | Confidence-side check: is the observed change clustered near the supplier point? |
| `External_Driver_Screening` | See §7.5 | Confidence-side check: is there an obvious non-supplier explanation (fire, drought, regional loss)? |

### 3.4 Habitat conversion vs Bare-ground expansion vs Built-up expansion — what's the difference?

These three indicators are nested, not parallel. Habitat conversion is the umbrella; bare-ground and built-up are named subtypes tracked separately because each has a different ESG meaning and a different attribution profile.

| Indicator | What it captures | Why we track it separately |
|---|---|---|
| **Habitat conversion** | *Any* transition from natural / semi-natural cover (trees, grass, shrub, flooded vegetation) to *any* non-natural cover (built, bare, crops) | The master metric. ESRS E4 and GRI 101 expect total habitat lost regardless of what it became. |
| **Built-up expansion** | Specifically the *natural → built* subset, plus growth of pre-existing built-up area | Most permanent kind of conversion and most attributable to a supplier when adjacent to the supplier footprint. Signals supplier-site expansion, industrial development, or surrounding urbanisation. |
| **Bare-ground / disturbance expansion** | Specifically the *natural → bare* subset, plus growth of pre-existing bare ground | Signals clearing, quarrying, construction prep, mining disturbance, land degradation. Most ambiguous subtype — Dynamic World's "bare" class confuses dry soil, rock, construction sites, and post-fire scars. |

The Habitat_Conversion aggregate (§3.2) intentionally double-counts the built and bare subsets as "bonus weight" on the ESG-priority subtypes — the 0.35 master term captures all conversion, then the 0.25 and 0.20 terms add weight on top for the two most material subtypes.

### 3.5 Dynamic World class mapping (natural / non-natural buckets)

Dynamic World V1 emits nine classes per pixel. The v1 tool maps them as follows. These groupings are fixed in code constants, not user-tunable:

| Dynamic World class | Bucket | Used in |
|---|---|---|
| `trees` | natural | `Sensitive_LandCover_Presence`, habitat conversion source |
| `grass` | natural | `Sensitive_LandCover_Presence`, habitat conversion source |
| `shrub_and_scrub` | natural | `Sensitive_LandCover_Presence`, habitat conversion source |
| `flooded_vegetation` | natural | `Sensitive_LandCover_Presence`, `Water_or_FloodedVegetation_Exposure`, habitat conversion source |
| `water` | semi-natural — context only | `Water_or_FloodedVegetation_Exposure`; **not** counted as habitat |
| `crops` | non-natural | habitat conversion *target* |
| `built` | non-natural | habitat conversion target, `built_expansion_ha` |
| `bare` | non-natural | habitat conversion target, `bare_expansion_ha` |
| `snow_and_ice` | excluded | masked out of all natural/non-natural accounting |

Code constants:

```python
DW_NATURAL_CLASSES = ['trees', 'grass', 'shrub_and_scrub', 'flooded_vegetation']
DW_NON_NATURAL_CLASSES = ['crops', 'built', 'bare']
DW_EXCLUDED_CLASSES = ['snow_and_ice']
DW_WATER_CLASS = 'water'  # tracked as exposure context, not a habitat class
```

`Habitat_Conversion` counts only natural → non-natural transitions. Pixels that change between two natural classes (e.g. trees → grass via succession or drought) are *not* counted as habitat loss; they're recorded separately as `natural_internal_change_ha` for context but do not contribute to the score.

The `flooded_vegetation → water` transition is a borderline case (could be a real ecological loss, could be a seasonal artefact) and is counted as habitat loss only when accompanied by a sustained NDVI drop in the same pixels over the analysis window — an additional check that prevents false positives from seasonal water-level changes.

---

## 4. Composite (cross-pillar) screening score

```
Overall_Screening_Score = ⅓ · Air_Pollution_Audit_FollowUp_Priority
                        + ⅓ · GHG_Audit_FollowUp_Priority
                        + ⅓ · Nature_FollowUp_Priority
```

Equal ⅓ weights are the v1 default per `PLFS_v4.md` §9. Sector-aware weighting is a v1.x extension. The composite confidence is `min(Air_Attribution_Confidence, GHG_Data_Quality_Attribution, Nature_Quality_Attribution)` — a conservative choice that prevents one strong pillar from masking weak signal in another.

---

## 5. Assumptions per formula — and which are scientifically weak

### 5.1 Assumptions that apply across every pillar

| # | Assumption | Strength | Notes |
|---|---|---|---|
| A1 | The site-buffer mean is representative of conditions at the supplier point | **Weak** when the supplier is a point in a heterogeneous landscape (city edge, river, valley); strong when supplier is in a uniform industrial cluster | Drives all repeatable-core-method values |
| A2 | The background ring is "clean enough" to serve as baseline | **Weak** in dense industrial regions (Po Valley, Pearl River Delta, Ruhr) where there is no clean comparator | The tool needs to flag this — see §7.2 |
| A3 | The 0–1 normalisation cap `k = 3·σ_bg` is calibrated correctly | **Moderate** — defensible default but depends on regional pollutant climatology | Tunable in code |
| A4 | The Theil-Sen slope is meaningful over the user-selected window | **Weak** below 12 months and at coarse temporal resolutions (e.g. ODIAC annual) | Mitigated by Wireframes V5 |
| A5 | A 0–1 score is comparable across pollutants and across pillars in the composite | **Weak** philosophically — they measure different physical phenomena | This is a screening tool, not a measurement tool; framing in the UI must be clear |

### 5.2 Air-pollution-specific assumptions

| # | Assumption | Strength |
|---|---|---|
| AP1 | TROPOMI column densities are a proxy for surface concentrations | **Weak for SO₂ and CO**, moderate for NO₂. Column ≠ surface, especially when boundary-layer height varies |
| AP2 | The supplier signal can be separated from regional transport | **Weak without wind data** — see §7.3 |
| AP3 | CAMS modelled PM₂.₅ at ~44.5 km resolution is meaningful at supplier-buffer scale | **Weak.** The pixel is bigger than most buffers. PM₂.₅ should always be framed as "modelled regional context" |
| AP4 | NRTI products are accuracy-equivalent to OFFL | **Weak.** Prefer OFFL; fall back to NRTI only for very recent dates |

### 5.3 GHG-specific assumptions

| # | Assumption | Strength |
|---|---|---|
| GHG1 | ODIAC fossil-fuel CO₂ flux is meaningful at the 1 km pixel | **Moderate.** ODIAC's point-source allocation is heuristic; it spreads power-plant emissions across multiple pixels |
| GHG2 | ODIAC's most recent vintage (2023 data, released 2024) is representative of "current" supplier CO₂ context | **Weak by design.** The ~1–2-year lag is inherent. Must be surfaced in the tool's data-vintage badge |
| GHG3 | TROPOMI CH₄ at ~7 × 5.5 km is a useful supplier-level methane signal | **Weak at 1–5 km buffers.** Frame as "screening only", never as quantification |
| GHG4 | VIIRS nighttime light radiance is an activity proxy for the supplier specifically | **Weak.** VIIRS sees urban spillover, traffic, gas flaring, and many non-industrial sources |
| GHG5 | The 0.35 weight on CO₂_Context is sector-agnostic | **Weak.** A semiconductor fab and a coal plant should not be weighted the same. v1.1 will sector-adjust |

### 5.4 Nature-specific assumptions

| # | Assumption | Strength |
|---|---|---|
| N1 | Dynamic World class probabilities accurately separate built / bare / dry vegetation | **Moderate.** Confusion is documented in arid/semi-arid landscapes, dry crop fields, and post-fire scars |
| N2 | A 90-day composite vs a 90-day baseline X years earlier is "comparable" | **Moderate.** Driven by `Seasonal_Comparability` sub-score |
| N3 | KBA boundaries are accurate enough to compute distance/overlap at km scale | **Moderate.** KBAs are polygons drawn from many source surveys with varying precision |
| N4 | NDVI < 0.3 is a meaningful "low-vegetation" threshold globally | **Weak.** This depends on biome (a deciduous forest in winter is naturally low NDVI) |
| N5 | The Habitat_Conversion score change is attributable to the supplier | **Weak by design.** This is exposure, not attribution. `Supplier_Spatial_Link` and `External_Driver_Screening` exist precisely to push back on this — see §7.5 |
| N6 | The recovery signal (positive NDVI trend, natural-cover gain) reflects actual ecosystem recovery | **Weak.** May reflect seasonal crops, plantation expansion, or irrigation rather than restoration |

---

## 6. Buffer definition

### 6.1 The two buffers used by every indicator

For each supplier point the tool constructs two concentric geometries from `(lat, lon, radius_km)`:

```
Site_Buffer      = circle of radius r_site_km around (lat, lon)
Background_Ring  = annulus from r_site_km outward to r_background_km
```

`Site_Buffer` is the "supplier exposure" zone — where indicator means are computed. `Background_Ring` is the "comparison" zone — where the median/std baseline is computed for the same date(s).

### 6.2 Default radii by use case

| Use case | `r_site_km` | `r_background_km` | Source |
|---|---|---|---|
| Single supplier — site-level audit | 1 | 10 | PLFS_v3 P-04 |
| Single supplier — facility buffer (default) | 5 | 25 | PLFS_v3 P-04, Inspect default |
| Single supplier — local context | 10 | 50 | PLFS_v3 P-04 |
| Region — regional context (default) | 25 | 100 | PLFS_v3 P-04, Region default |
| Region — large region | 50 | 200 | PLFS_v3 P-04 |

The user picks `r_site_km` from the stops above; `r_background_km` is automatically set to `min(5 × r_site_km, 200 km)`.

**Why these specific site radii (1, 5, 10, 25, 50 km).** Each one matches a real spatial scale of a question the tool needs to answer, *plus* the resolution of the underlying datasets:

| Radius | Matches the scale of | Why this exact number |
|---|---|---|
| **1 km** | Individual facility + immediate footprint (fenceline, access roads) | Below 1 km, most air-pollution and GHG datasets give zero or one pixel. 1 km is the smallest scale where the buffer is meaningful. |
| **5 km** | Standard "site impact zone" in EIA and ESRS E2 | Industrial NO₂ plumes are typically still attributable to source within ~5 km. Sits just above the Sentinel-5P NO₂ pixel (~3.5 × 7 km), so the buffer averages a handful of pixels. **Default for single-supplier analysis.** |
| **10 km** | Supplier + surrounding land-use cluster (industrial estate, port complex) | Picks up neighbouring facilities, useful for "is this an industrial corridor?", but facility-level attribution starts to weaken. |
| **25 km** | Small administrative region or metropolitan area | Matches the CAMS PM₂.₅ pixel (~44 km) closely enough for good coverage. **Default for regional analysis.** |
| **50 km** | Province or large metropolitan scale | Supplier becomes an anchor only — the buffer is really measuring regional climate. |
| **100 km** | State / province / small country | High-level country-portfolio screening. Beyond this point, "buffer around a supplier" stops being a useful concept. |

**Why the 5:1 background-to-site ratio.** Three reasons:

1. **Plume containment.** Most industrial point-source plumes attenuate to background within 10–20 km downwind. A 5× radius starts the ring past the typical plume reach, so the background isn't contaminated by the supplier's own emissions.
2. **Statistical independence.** At 5:1 the inner area is ~4 % of the outer-ring area, so site pixels don't bias ring statistics. A 3:1 ratio would let the site pull the background statistics in its own direction and artificially shrink the anomaly. A 10:1 ratio would push the background too far (a 1 km site would need a 100 km background, crossing multiple ecosystems).
3. **Practical cap at 200 km.** Beyond 200 km the ring spans multiple climate zones and emissions baselines, so the 50 km site gets a 200 km cap rather than 250 km.

**Why a fixed-step slider and not free input.** Fixed steps (1, 5, 10, 25, 50, 100) follow a 1–2–5 logarithmic progression — the same pattern used on graph axes because it gives good coverage across orders of magnitude with few steps. It also prevents the user from over-tuning the buffer until they get the answer they want. Resolved in Wireframes_All_v4.

### 6.3 Circumstances to consider when defining buffers

Six things change the right buffer size in practice. The tool should expose enough of these as either warnings or defaults that the user understands when the buffer is the wrong shape for the question.

1. **Sensor resolution.** A 1 km buffer with TROPOMI CH₄ (pixel ~7 × 5.5 km) gives one or zero pixels. **Warning trigger:** if `r_site_km < max(pixel_size of selected indicators)`, show one warning chip on the radius slider listing the indicators whose pixels exceed the buffer (e.g. "Buffer smaller than the pixel of: PM₂.₅ (CAMS), CH₄ (TROPOMI). These indicators will have limited spatial detail."). The single-chip-with-list pattern keeps the UI quiet when many indicators are coarse, and tells the user *which* ones are affected so they can choose whether to deselect or accept. Specified as error E2 in `Wireframes_All_v4.md`.

2. **Landscape heterogeneity.** A 5 km buffer that straddles a coastline, mountain ridge, or city boundary has a meaningless mean — averaging forest NDVI (~0.7), built NDVI (~0.1), and water NDVI (~−0.1) gives a number that describes no real surface. The same applies to mean NO₂ when the buffer mixes urban and rural pixels. The tool can detect this by computing intra-buffer variance of the Dynamic World composition; if the dominant class is < 50 % of the buffer, warn the user. The 50 % threshold guarantees at least half the buffer is one type, so the mean has at least partial physical meaning.

3. **Plume drift (without wind input in v1).** Industrial NO₂ plumes routinely drift 5–20 km downwind. A 1 km buffer will miss the plume even if the supplier is the source. v1 conservative default: 5 km. v1.1 will use ERA5 wind to construct a directional buffer.

4. **Background contamination.** If the 25 km background ring overlaps another industrial cluster, the background median is biased high and the supplier's anomaly is biased low. The `Nearby_Source_Isolation` sub-score (see §7.2) flags this; the user should be told to interpret a low isolation score as "the buffer's background is not clean — anomaly is conservative".

5. **Cross-border buffers.** A buffer that crosses a national border may pull in regions with very different emissions baselines and very different KBA reporting completeness. Surface this as a "buffer crosses border" warning.

6. **Coastal / over-water buffers.** A 25 km buffer near the coast spends a large fraction over open water, which has near-zero NO₂/SO₂/CO and inflated NDVI masking. The Valid_Pixel_Coverage sub-score handles this automatically by going down; no separate warning needed but the user should see the valid-pixel percentage in the result card.

### 6.4 Why we reject other plausible radii

A few values that get rejected by the reasoning in §6.2:

- **2 km, 3 km, 7 km, 15 km** — workable middle values, but a fixed-step slider prevents over-tuning. 15 km in particular would sit between local context (10 km) and regional context (25 km) without adding interpretive value.
- **20 km, 30 km** — close to 25 km but not aligned with administrative or sensor-pixel scales.
- **3:1 or 10:1 background ratios** — rejected per §6.2 rationale point 2.

---

## 7. Answers to the five flagged questions

### 7.1 v1 will not include context as an input — what does this mean for the formulas?

"Context" here means inputs the v1 tool will not collect:

- **Supplier sector** (used by `High_GWP_Sector_Risk`, `Sector_Match`, `Buffer_Sensitivity`)
- **Wind direction / speed** (used by `Wind_Consistency` and by directional buffers)
- **Active-fire detections** (used by `Fire_or_Regional_Transport_Risk` if implemented from FIRMS)

When these are not available, the v1 follows two rules:

**Rule 1 — set the term to zero and rescale the remaining weights so they sum to 1.0.**
This preserves the [0, 1] range of every score and keeps comparisons across suppliers fair.

Example for `Core_GHG_Audit_Support` (engine-actual M5.5b form):
- Original: 0.35·CO₂ + 0.25·CH₄ + 0.20·Combustion + 0.10·Activity + 0.10·Sector = 1.00
- Step 1 — drop Sector (deferred): rescale by 1/(1 − 0.10) = 1.111 → 0.39·CO₂ + 0.28·CH₄ + 0.22·Combustion + 0.11·Activity ≈ 1.00
- Step 2 — M5.5b demotes ODIAC CO₂ to standing exposure (not in live composite): drop CO₂'s 0.39, rescale the remaining three by 1/(1 − 0.39) = 1/0.61 ≈ 1.639 → 0.46·CH₄ + 0.44·Combustion + 0.10·Activity = 1.00.

The engine ships the post-Step-2 weights. CO₂ still computes and displays as standing-exposure context — see Schema_v2 §6.1 `temporal_mode`.

**Rule 2 — for `Fire_or_Regional_Transport_Risk`, use a satellite-only proxy.**
See §7.3.

The rescaling is computed once in the code (a `WEIGHTS_V1` constant), not at every call, so v1.x can flip a flag to restore the full formulas without touching the rest of the pipeline.

### 7.2 How to measure `Nearby_Source_Isolation`

`Nearby_Source_Isolation` is a [0, 1] sub-score that tells the user "is the supplier signal isolated, or is it contaminated by other emitters nearby?". A score near 1.0 means the background ring is clean. A score near 0 means the background is itself a hotspot, so the anomaly is small only because everything around is also dirty.

**Formulation A — NO₂ background statistics:**

```
1. Compute NO2_bg_mean = mean NO₂ in Background_Ring over the analysis window
2. Compute NO2_global_clean_median = a fixed regional/global "clean" reference
   (precomputed per latitude band; for the default v1 use the bottom 25th
    percentile of NO₂ from the same latitude band over the last 3 years)
3. excess_bg = max(0, NO2_bg_mean − NO2_global_clean_median)
4. isolation_from_no2 = clamp( 1 − excess_bg / (3 · σ_clean) , 0 , 1 )
```

**Formulation B — VIIRS nighttime-light activity:**

```
1. Count VIIRS nighttime-light "bright" pixels (radiance > P75 of global VIIRS
   distribution) within Background_Ring.
2. bright_pct = bright_pixels / total_pixels
3. isolation_from_viirs = 1 − bright_pct
```

The canonical v1 formula is the **average of the two**:

```
Nearby_Source_Isolation = 0.5 · isolation_from_no2 + 0.5 · isolation_from_viirs
```

The average is robust: if one of the two signals fails (e.g. a coastal site with no nighttime lights but real ship-track NO₂; or a flaring-heavy site with VIIRS-saturated nights but moderate NO₂), the other carries the score. Using either alone produces too many false confident-isolation flags.

What this score *doesn't* do without context: it can't tell *which* other sources are contaminating the background. That would need an industrial-facility registry (e.g. E-PRTR, GHGRP), which is a v1.x extension.

### 7.3 How to measure `Fire_or_Regional_Transport_Risk`

This is the score used to downweight the methane signal when the elevated CH₄ might actually be biomass burning or transported pollution rather than a local supplier source.

**v1 satellite-only computation (no FIRMS upload, no wind data):**

It is the same value as the **Smoke / Dust / Regional Transport Score** from §1.2:

```
Fire_or_Regional_Transport_Risk = 0.40·CO_score + 0.40·AAI_score + 0.20·PM_or_Aerosol_score
```

Rationale:
- Wildfire and biomass-burning plumes are dominated by **CO** (long-lived combustion product) and **absorbing aerosols (AAI)**, with secondary PM₂.₅.
- Industrial point sources are dominated by NO₂ and SO₂, with relatively less CO and AAI.
- A high `Fire_or_Regional_Transport_Risk` score therefore means "the air column looks like smoke / dust / transport, not like fresh local industrial emissions".

This is then subtracted from the CH₄ score:

```
CH4_Context_Adjusted = CH4_Hotspot_Score − 0.20 · Fire_or_Regional_Transport_Risk
```

If wildfires are confirmed (e.g. a NASA FIRMS active-fire detection in the background ring) the multiplier increases from 0.20 to ~0.40 — this is a v1.x extension, since v1 does not load FIRMS.

### 7.4 Removing EVI from `Vegetation_Condition`

The original formula was:

```
Vegetation_Condition = 0.35·Inverted_NDVI_anomaly + 0.20·Inverted_EVI_anomaly
                     + 0.20·Negative_Trend + 0.15·Low_Veg_Area_pct − 0.10·Recovery_Signal
```

Removing EVI and **rescaling the remaining positive weights to preserve the original 0.90 total positive weight** (proportional reallocation):

```
Vegetation_Condition_v1 = 0.45·Inverted_NDVI_anomaly
                        + 0.25·Negative_Vegetation_Trend
                        + 0.20·Low_Vegetation_Area_pct
                        − 0.10·Recovery_Signal
```

This is the formula used in §3.2 above. NDVI absorbs most of EVI's weight because the two are strongly correlated (NDVI captures essentially the same vegetation-health signal at the resolutions we use). The remaining weight is split into trend and low-veg area, both of which already represent independent dimensions of vegetation condition. The recovery signal stays at −0.10 because it's a separate, independent positive-direction signal.

If at any point you want EVI re-added (e.g. to discriminate dense-canopy stress where NDVI saturates), the original weighting can be restored as a `WEIGHTS_VEGETATION_FULL` constant.

### 7.5 What `Supplier_Spatial_Link` and `External_Driver_Screening` actually mean

These are the two trickiest terms in the Nature pillar. Both are confidence multipliers, not exposure scores. Both are inside `Nature_Quality_Attribution` (§3.3), which is the term that pushes back on overclaiming.

**`Supplier_Spatial_Link` (weight 0.15) — "is the observed change actually near the supplier?"**

When Dynamic World shows habitat conversion inside the supplier buffer, that change could be right next to the supplier point (highly attributable) or at the far edge of the buffer (weakly attributable). This sub-score captures the spatial distribution of the change.

```
1. Build a binary "change mask" of pixels converted between baseline and current
2. For each change pixel, compute distance d_i from the supplier point
3. d_centroid = mean(d_i)
4. Supplier_Spatial_Link = clamp( 1 − d_centroid / r_site_km , 0 , 1 )
```

A score near 1.0 means the change is concentrated near the supplier (high attributability). A score near 0 means the change is at the buffer edge (low attributability — the supplier is probably not the driver).

If there are no change pixels, the score is set to 1.0 (no claim to qualify).

**`External_Driver_Screening` (weight 0.10) — "is there an obvious non-supplier explanation?"**

This sub-score downweights confidence when the observed habitat/vegetation change can be explained by drivers the supplier has no control over: drought, fire scars, regional deforestation, large infrastructure projects.

In v1 only one of the three evidence terms is wired (`regional_loss_evidence`); `fire_evidence` and `drought_evidence` remain placeholders pending Tier C1a / Tier A2. The audit §9.3 v1.4 form is therefore:

```
external_driver_evidence  = regional_loss_evidence    (v1)
External_Driver_Screening = 1 − external_driver_evidence

# Tier C1a / A2 will restore the original max-of-three form:
# external_driver_evidence = max(fire_evidence, drought_evidence, regional_loss_evidence)
```

**`regional_loss_evidence` formula (audit §9.3 / engine).** Always uses the most recent `HANSEN_LOOKBACK_YEARS = 5` Hansen loss years, independent of the user's `time_range` (Hansen's annual cadence and standing-exposure framing make user-window-driven slices noisy and misleading):

```
buffer_loss_rate        = sum(hansen[y] in Site_Buffer for y in lookback) / area_buffer
ring_loss_rate          = sum(hansen[y] in Background_Ring for y in lookback) / area_ring
regional_loss_evidence  = 1.0 if ring_loss_rate > HANSEN_LOSS_RATIO_THRESHOLD · buffer_loss_rate
                          else 0.0          (HANSEN_LOSS_RATIO_THRESHOLD = 2.0)
```

Implementation lives in `engine.nature.compute_regional_loss_evidence` and emits canonical provenance under `_provenance.nature.regional_loss_evidence` (`data_type="reference_dataset"`, `temporal_mode="standing_exposure"`). The function runs unconditionally whenever the Nature pillar runs — it's a single Hansen reduceRegion pair, so the cost is negligible compared with the rest of the pipeline.

A score near 1.0 means no obvious external driver (high confidence the supplier is implicated). A score near 0 means the change is regional / explained by fires / drought (low confidence in supplier attribution).

Why these two terms are kept in `Nature_Quality_Attribution`, not in the exposure or conversion scores: they don't change *what* was observed. They change *how confidently we can blame the supplier for it*. That is a confidence concept and belongs in the data-quality aggregate, which is then surfaced next to the main Nature follow-up score in the UI per PLFS_v3 §9.

---

## 8. Confidence (M-TIER-A1)

> **Doc-structure note.** Pre-A1 §0.2 step 6 promised a confidence formula in §6.3, but §6.3 was occupied by buffer-warning logic and the confidence formula had no home. This section is where it lives. The §0.2 step 6 row's `see §6.3 for the v1 implementation` should be read as `see §8 for the v1 implementation`.

### 8.1 Per-indicator confidence formula

Universal across all indicators (no per-indicator weight overrides in v1.x):

```
c_raw_i  = 0.30·QA_i + 0.30·N_valid_i + 0.25·anomaly_strength_i + 0.15·spatial_context_i
c_final_i = c_raw_i · COLUMN_TO_SURFACE_MULTIPLIER[column_to_surface_uncertainty_i]
```

The weights are in `engine.constants.CONFIDENCE_FORMULA_WEIGHTS`; the multiplier table is in `engine.constants.COLUMN_TO_SURFACE_MULTIPLIER`. Both live in code so v1.x recalibration is a one-line change.

**Term definitions.**

| Term | What it measures | v1 source |
|---|---|---|
| `QA` | Data-quality flags pass rate over the site buffer. | Per-indicator static default from `engine.constants.QA_PER_INDICATOR` (e.g. `air.no2 = 0.90`, `air.so2 = 0.75`, `ghg.co2 = 1.00`). Plumbing real per-pixel TROPOMI `qa_value` filter pass-rates into the EE pipeline is logged as a Layer B follow-up — sensitivity-analysis target in Tier B1. |
| `N_valid` | Temporal coverage. `clamp(n_observations / expected_n, 0, 1)`. | Live-revisit indicators (TROPOMI gases, CAMS PM, MAIAC AOD, VIIRS, MODIS NDVI): `expected_n = EXPECTED_N_PER_WINDOW_DAY[indicator_id] · window_days`. Single-snapshot indicators (`ghg.co2`, all Nature composites + Hansen + KBA + `regional_loss_evidence`): bypass the ratio; emit 1.0 when the snapshot produced, 0.0 when skipped. |
| `anomaly_strength` | "Is the signal we observed strong enough to trust?". | Hotspot frequency `HF` from §0.2 step 5 (already in `[0, 1]`). Indicators with no HF concept (KBA, DW, habitat, Hansen, ODIAC, regional_loss_evidence) emit `1.0` unconditionally — "the formula doesn't apply, so don't drag confidence". This makes a low-priority supplier read as "low priority, low confidence in there being a signal" — honest about what HF actually measures. |
| `spatial_context` | Pixel-buffer ratio. `clamp(sqrt(buffer_area / native_pixel_area) / SPATIAL_CONTEXT_THRESHOLD, 0, 1)`. | Saturates at 1.0 when the buffer covers ≥3 native pixels in each linear dimension. `SPATIAL_CONTEXT_THRESHOLD = 3.0`. Returns 1.0 for vector / non-raster indicators (KBA). |

**Column-to-surface multiplier (audit §1.5 fold-in).** The static per-gas tag from `engine.core.provenance._COLUMN_TO_SURFACE_UNCERTAINTY` is read at the same time and applied as the final step:

| Tag | Multiplier | Notes |
|---|---|---|
| `strong` | 1.00 | Reserved for future use; no v1 indicator carries it. |
| `moderate` | 0.95 | Small penalty; the audit-§1.5 Z-score mitigation absorbs most of the bias. |
| `moderate_weak` | 0.88 | Midpoint. |
| `weak` | 0.80 | Meaningful penalty: CH₄ and CO confidence visibly trail NO₂ on equal observational data. |
| `n_a` | 1.00 | No penalty when the concept doesn't apply (PM/AOD, ODIAC, VIIRS, all Nature, O₃/AAI). |

**Numerical example.** A perfect-data NO₂ measurement (QA = 1, N_valid = 1, HF = 1, spatial_context = 1, multiplier = 0.95) lands at `c_final = 0.95`. A perfect-data CO measurement under the same conditions lands at `c_final = 0.80`. NO₂ is more trustworthy than CO at identical observational quality — encoded in the value, not buried in a footnote.

**Strict-None at the indicator level.** If any of `QA, N_valid, anomaly_strength, spatial_context` is None for indicator `i`, then `<indicator>.confidence` is None. The pillar rollup (§8.2) handles the dropout via survivor-renormalise; the composite (§8.3) propagates None through `min(...)`.

### 8.2 Pillar-level rollup

Each pillar continues to drive its own `*_attribution`/`*_quality_attribution` score via the existing weight dictionaries in `engine.constants`; the term *derivations* are what shift after A1.

**Air pillar — `air.attribution_confidence_score`.** Uniform mean of per-pollutant `air.<gas>.confidence` over the survivors. No weight dict (Air already used a uniform mean pre-A1).

**GHG pillar — `ghg.data_quality_attribution`.** Existing `GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS` (0.33 / 0.27 / 0.27 / 0.13) drives the rollup. Three of the four sub-scores now derive from per-indicator A1 inputs read from `_provenance.ghg.<ind>.extra.confidence_terms`; the fourth is unchanged:

| Sub-score | Post-A1 derivation |
|---|---|
| `ghg.temporal_coverage` | Mean of per-indicator `N_valid` across GHG indicators that emitted terms |
| `ghg.spatial_resolution_suitability` | Mean of per-indicator `spatial_context` across GHG indicators |
| `ghg.retrieval_inventory_quality` | Mean of per-indicator `QA` across GHG indicators |
| `ghg.nearby_source_isolation` | Unchanged — §7.2 satellite-only spatial proxy; methodologically independent of per-indicator data quality |

Survivor-renormalise applies: missing per-indicator terms drop out of the mean; missing sub-scores get renormalised against `GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS`.

**Nature pillar — `nature.quality_attribution`.** Existing `NATURE_QUALITY_ATTRIBUTION_WEIGHTS` (0.20 / 0.20 / 0.20 / 0.15 / 0.15 / 0.10) drives the rollup. Only one sub-score's derivation changes; the other five were already real (not placeholders):

| Sub-score | Post-A1 derivation |
|---|---|
| `nature.valid_pixel_coverage` | Mean of per-indicator `QA` across the Nature indicators that emitted terms |
| `nature.cloud_observation_quality` | Unchanged (Sentinel-2 cloud quality) |
| `nature.dw.class_confidence` | Unchanged (DW probability, already real) |
| `nature.seasonal_comparability` | Unchanged (months-offset placeholder pending Tier C) |
| `nature.supplier_spatial_link` | Unchanged (§7.5 placeholder) |
| `nature.external_driver_screening` | Unchanged — `compute_regional_loss_evidence` per audit §9.3 v1.4 |

### 8.3 Composite confidence

Unchanged formula:

```
composite.confidence = min(
    air.attribution_confidence_score,
    ghg.data_quality_attribution,
    nature.quality_attribution,
)
```

After A1, this `min` is genuinely informative — it surfaces the weakest-pillar confidence as the headline number. Strict-None propagates: if any pillar confidence is None, the composite is None.

### 8.4 Audit transparency — `provenance.extra.confidence_terms`

Every indicator emits its four input terms plus the column-to-surface tag inside its provenance block:

```
_provenance.<pillar>.<indicator>.extra.confidence_terms = {
    "qa":                            <0..1>,
    "n_valid":                       <0..1>,
    "anomaly_strength":              <0..1>,
    "spatial_context":               <0..1>,
    "column_to_surface_uncertainty": <enum>,
}
```

A reviewer reading a result payload can reproduce the per-indicator confidence value without re-running the engine; the pillar QA sub-scores (`ghg.temporal_coverage`, etc.) walk these dicts when assembling the pillar rollup.

### 8.5 What this unblocks

- **Verbal-summary tiering becomes meaningful** — `composite_confidence_bucket` actually corresponds to data quality.
- **P-05 / P-11 confidence dots tell a real story** — UI doesn't need to add a footnote.
- **Tier C1b (BLH-aware confidence)** extension point — replace the static `COLUMN_TO_SURFACE_MULTIPLIER` lookup with a BLH-modulated function.
- **Tier B1 (sensitivity analysis)** target — vary the four formula weights and the multiplier values on a 50-site sample.
- **Layer B QA plumbing** — replace `QA_PER_INDICATOR` static defaults with real per-image `qa_value` pass-rates from EE.

---

*Document version 4.2 — 22 May 2026 (M-TIER-A1). Built from `Final_Indicators_List.pdf`, `Indicators_Full_Research.pdf`, `PLFS_v4.md`, `Wireframes_All_v4.md`, `GEE_Database_List_v3.md`, `Indicator_ID_Schema_v2.md`, `Indicators_Audit_and_v1x_Roadmap.md` v1.5.*
