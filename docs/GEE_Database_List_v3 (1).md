# GSCO Environmental Tool — GEE Database List (v3)

**Purpose:** Reference list of all satellite and open environmental databases planned for the GSCO supplier-screening tool, with their current Google Earth Engine availability and update status as of May 2026.

**Scope:** Sourced from `Final_Indicators_List.pdf` and `Indicators_Full_Research.pdf`, organised by the three pillars of the tool — Air Pollution, GHG Emissions, and Nature/Land — plus operational notes.

**Changes from v2:**
- Added **ERA5 reanalysis wind** to Section 7 ("Considered but not included") as a v1.x dataset for the deferred `Wind_Consistency` sub-score and for directional buffer construction.
- Added **FAO GAUL 2015** to Section 4 (Nature/Land) as the source for region-mode AOI resolution in P-04 (MNC country-level selection).
- Cross-references updated to `PLFS_v4.md` and `Indicators_Computation_v3.md`.

---

## 1. Summary status table

| # | Dataset | GEE asset ID | Native in GEE? | Update status | Pillar |
|---|---|---|---|---|---|
| 1 | Sentinel-5P NO₂ (OFFL + NRTI) | `COPERNICUS/S5P/OFFL/L3_NO2`, `COPERNICUS/S5P/NRTI/L3_NO2` | Yes | Live, daily | Air Pollution |
| 2 | Sentinel-5P SO₂ (OFFL + NRTI) | `COPERNICUS/S5P/OFFL/L3_SO2`, `COPERNICUS/S5P/NRTI/L3_SO2` | Yes | Live, daily | Air Pollution |
| 3 | Sentinel-5P CO (OFFL + NRTI) | `COPERNICUS/S5P/OFFL/L3_CO`, `COPERNICUS/S5P/NRTI/L3_CO` | Yes | Live, daily | Air Pollution |
| 4 | Sentinel-5P HCHO (OFFL + NRTI) | `COPERNICUS/S5P/OFFL/L3_HCHO`, `COPERNICUS/S5P/NRTI/L3_HCHO` | Yes | Live, daily | Air Pollution |
| 5 | Sentinel-5P O₃ (OFFL + NRTI) | `COPERNICUS/S5P/OFFL/L3_O3`, `COPERNICUS/S5P/NRTI/L3_O3` | Yes | Live, daily | Air Pollution |
| 6 | Sentinel-5P Absorbing Aerosol Index | `COPERNICUS/S5P/OFFL/L3_AER_AI`, `COPERNICUS/S5P/NRTI/L3_AER_AI` | Yes | Live, daily | Air Pollution |
| 7 | Sentinel-5P CH₄ (OFFL only) | `COPERNICUS/S5P/OFFL/L3_CH4` | Yes | Live, daily — known historical gaps | GHG |
| 8 | CAMS Global Near-Real-Time (PM₂.₅, PM₁₀, AOD) | `ECMWF/CAMS/NRT` | Yes | Live, daily | Air Pollution |
| 9 | MODIS MAIAC AOD | `MODIS/061/MCD19A2_GRANULES` | Yes | Live, daily | Air Pollution |
| 10 | Dynamic World V1 (10 m LULC, NRT) | `GOOGLE/DYNAMICWORLD/V1` | Yes | Live, every 2–5 days | Nature / Land |
| 11 | Sentinel-2 Surface Reflectance Harmonised | `COPERNICUS/S2_SR_HARMONIZED` | Yes | Live, every 2–5 days | Nature / Land |
| 12 | Landsat 8 L2 (longer-history NDVI) | `LANDSAT/LC08/C02/T1_L2` | Yes | Live, 16-day | Nature / Land |
| 13 | Landsat 9 L2 (longer-history NDVI) | `LANDSAT/LC09/C02/T1_L2` | Yes | Live, 16-day | Nature / Land |
| 14 | MODIS NDVI/EVI 16-day | `MODIS/061/MOD13Q1` | Yes | Live, 16-day | Nature / Land |
| 15 | Hansen Global Forest Change | `UMD/hansen/global_forest_change_2024_v1_12` (or later) | Yes | Annual update | Nature / Land |
| 16 | VIIRS Black Marble nighttime lights | `NASA/VIIRS/002/VNP46A2` | Yes | Live, daily | GHG (activity proxy) |
| 17 | World Database of Key Biodiversity Areas | `projects/ee-kbas-in-gee/assets/current` | Yes — access granted | Updated every 6 months | Nature/Land |
| 18 | ODIAC fossil-fuel CO₂ emissions | *(none — upload as asset)* | No | Annual release, ~1-year lag | GHG |
| 19 | FAO GAUL 2015 — administrative boundaries (level 0 / 1) | `FAO/GAUL/2015/level0`, `FAO/GAUL/2015/level1` | Yes | Static (2015 vintage) | Operational — region-mode AOI lookup |

---

## 2. Air Pollution pillar

### 2.1 Sentinel-5P TROPOMI gases (NO₂, SO₂, CO, HCHO, O₃, AAI, CH₄)

All seven gases are available natively in Earth Engine and are ingested continuously. The Sentinel-5P satellite is in nominal operational mode with planned end-of-life September 2027, so the feed is safe for the audit horizon of the tool.

Key points to handle in code:

- All gases except CH₄ have **two variants**: Near Real-Time (`NRTI`) and Offline (`OFFL`). NRTI appears faster but covers smaller areas per scene; OFFL is more complete and more accurate. For screening, prefer **OFFL** with NRTI as a fallback for very recent dates.
- **CH₄ is OFFL only.** There is no NRTI methane product. Historical gap to be aware of: no data between 2022-07-26 and 2022-08-31 due to a provider outage.
- All seven assets are already correctly wired in `Inspection.js` (`FP_DATASETS` registry), so the air-pollution pillar can be coded against the existing structure.

### 2.2 PM₂.₅ / PM₁₀ / AOD

| Need | Dataset | GEE asset | Notes |
|---|---|---|---|
| Modelled surface PM₂.₅ (primary) | CAMS Global NRT | `ECMWF/CAMS/NRT` | Daily, global, ~44.5 km pixel. Surface PM₂.₅ band in kg/m³ — multiply by 1e9 for µg/m³. Also contains PM₁, PM₁₀, AOD and chemical species. Modelled product, not a direct sensor measurement |
| Column aerosol loading (supporting) | MODIS MAIAC AOD | `MODIS/061/MCD19A2_GRANULES` | Daily, 1 km. Use AOD at 0.55 µm. Apply the `AOD_QA` quality mask (bits 8–11) |
| Absorbing aerosol context | Sentinel-5P AAI | `COPERNICUS/S5P/OFFL/L3_AER_AI` | Already in the Sentinel-5P table — useful for smoke/dust events |

**Note:** CAMS PM₂.₅ is coarse (~44.5 km). For supplier-site screening it's the best globally consistent NRT option, but it cannot be presented as facility-level PM concentration. Frame outputs as a "modelled PM₂.₅ proxy" with a quality score, in line with `Final_Indicators_List.pdf`.

---

## 3. GHG pillar

### 3.1 Atmospheric methane (native in GEE)

- `COPERNICUS/S5P/OFFL/L3_CH4` — band `CH4_column_volume_mixing_ratio_dry_air`, in ppb.
- Best native GHG signal for the tool. Suitable for methane hotspot screening (fossil-fuel, waste, agriculture, some industrial processes).
- Attribution remains weak at facility level due to coarse TROPOMI pixels — present as a screening signal, not as proof of supplier emissions.

### 3.2 Fossil CO₂ emissions context (upload required)

**ODIAC (Open-Data Inventory for Anthropogenic CO₂)** — primary CO₂ layer for the tool.

- Not in the GEE public catalogue. Must be downloaded from the NIES CGER data server and uploaded as a GEE asset.
- Latest version: **ODIAC2024**, covering 2000–2023. Monthly 1 × 1 km grids.
- Recommended folder structure: `projects/<gsco-project>/assets/odiac/odiac2024_YYYYMM`, ingested as an `ImageCollection`.
- Refresh cadence: annual. The ODIAC team typically releases a new vintage mid-year; the tool's CO₂ values will always lag the present by roughly 12–18 months, which must be surfaced in the tool's data-quality output.

### 3.3 Activity proxy

- `NASA/VIIRS/002/VNP46A2` — Black Marble daily nighttime lights. Already in GEE and updating. Useful for combining with CO₂ inventory and combustion proxies into the "Activity Score" component of the GHG aggregate.

---

## 4. Nature / Land pillar

### 4.1 Land cover (current and change)

| Asset | Use | Notes |
|---|---|---|
| `GOOGLE/DYNAMICWORLD/V1` | Primary current land cover and habitat-change source | 10 m, NRT, nine classes with per-pixel probabilities. Updated every 2–5 days with Sentinel-2 |
| `COPERNICUS/S2_SR_HARMONIZED` | Secondary confirmation; source for NDVI, NDBI, NDWI, BSI | 10 m, every 2–5 days |
| `UMD/hansen/global_forest_change_<year>_v1_<n>` | Annual forest-specific loss confirmation | Annual updates; check exact asset ID — Hansen versions increment yearly |
| `LANDSAT/LC08/C02/T1_L2`, `LANDSAT/LC09/C02/T1_L2` | Longer-history NDVI / trend context | 30 m, 16-day |
| `MODIS/061/MOD13Q1` | Currently used in `Vegetation.js`. Useful for long-term NDVI baseline and anomaly | 250 m, 16-day |

### 4.2 Biodiversity exposure

`projects/ee-kbas-in-gee/assets/current` — World Database of Key Biodiversity Areas (WDKBA), September 2025 release.

**Status: access granted.** The Nature pillar's biodiversity-exposure indicators are wired against this asset for v1.

- Updated every 6 months. The `…/current` alias always points to the latest version.
- Versioned snapshots (e.g., `…/202503`, `…/202509`) are also kept, which is useful for reproducibility of historical audits.

### 4.3 Note on JRC Global Surface Water

The `Indicators Full Research` doc explicitly notes that JRC GSW is not updated to "today" in GEE — use Dynamic World water/flooded-vegetation classes plus Sentinel-2 NDWI for current water exposure instead. JRC GSW can still be used as a long-term historical reference if needed.

### 4.4 Administrative boundaries — region-mode AOI resolution

`FAO/GAUL/2015/level0` — country polygons (249 countries / territories).
`FAO/GAUL/2015/level1` — first-level administrative divisions globally (~3,600 polygons).

Used by P-04 in *Region* mode (per `PLFS_v4.md` §8 / E5 in the v3 reconciliation discussion):

- **MNC users** picking "Region" mode get a country-level dropdown sourced from `level0`. The chosen country's centroid populates the AOI centre; the buffer radius defaults to a country-area-aware value (50 km for small countries, 100 km for medium, 200 km for large — capped at the global 200 km maximum).
- **Policy Maker users** picking "Region" mode get sub-national regions from the loaded GSCO catalogue (their primary source). `level1` is the v1.x fallback when the GSCO catalogue lacks coverage for a country.

GAUL is a 2015 vintage and is not refreshed — adequate for region centroids and approximate boundaries; not adequate for any indicator that requires up-to-date polygons. The tool uses GAUL *only* for AOI lookup, never as an indicator data source.

---

## 5. Operational considerations

### 5.1 GEE quota tier change — 27 April 2026

Earth Engine has introduced noncommercial quota tiers. All noncommercial projects need to select a quota tier or use the Community Tier by default. Tier quotas have been in effect since 27 April 2026.

**Action:** confirm with GSCO whether the project's Google Cloud project is on a commercial tier or noncommercial / Community tier. A production audit tool that screens many supplier sites can hit Community Tier limits quickly.

### 5.2 Ingestion status monitoring

Bookmark and check periodically:

`https://developers.google.com/earth-engine/datasets/status`

This page reports live ingestion status of the continuously updated datasets (Sentinel-5P, CAMS, Dynamic World, Sentinel-2, Landsat, VIIRS). A status of "OK" means data ingestion is working within a margin of error. This page is the canonical source for the tool's data-quality / attribution sub-scores and should ideally be referenced by the tool's user-facing "data confidence" indicator.

### 5.3 Recommended asset organisation for uploaded layers

Only one dataset must be uploaded in v1 (ODIAC). Suggested structure:

```
projects/<gsco-gcp-project>/assets/
└── odiac/
    ├── odiac2024_200001
    ├── odiac2024_200002
    └── …
```

Every ingested image should carry an "as-of" property (the ODIAC vintage and month it represents), so the tool can compute and display the data-vintage lag relative to the current Sentinel-5P feed.

---

## 6. Pre-coding checklist

Before development of the supplier-screening modules begins:

1. ✅ **KBA access granted.** The Nature pillar's biodiversity-exposure indicators can be developed against `projects/ee-kbas-in-gee/assets/current` directly.
2. **Confirm the GEE quota tier** on the GSCO Google Cloud project.
3. **Download the latest ODIAC vintage** (currently ODIAC2024) and ingest as a GEE `ImageCollection`. Decide on monthly vs annual aggregation for the supplier-buffer extraction step.
4. **Add a "data vintage" property** to every uploaded ODIAC asset, so the tool can compute lag automatically.
5. **Bookmark the GEE dataset status page** in the dev / monitoring environment.
6. **Verify GAUL collection access** for region-mode AOI lookup (P-04 MNC country-level selection).

---

## 7. Considered but not included in v1

The following datasets were reviewed during the indicator research phase and are noted here for reference. They are **not** part of the v1 tool scope. They may be reconsidered in future versions if facility-level GHG attribution or atmospheric CO₂ context become higher priority.

| Dataset | Type | Why considered | Why not included in v1 |
|---|---|---|---|
| **EDGAR** gridded inventories (CO₂, CH₄, by sector) | Annual inventory raster — upload required | Sector-disaggregated benchmark for ODIAC; widely cited in ESG / GHG reporting literature | Adds redundancy with ODIAC for v1 supplier screening. Larger lag (~2 years) than ODIAC. Sector allocation adds methodological complexity that is not needed for a screening-tier tool |
| **Climate TRACE** facility emissions | Facility-level point data — upload as FeatureCollection | Provides direct facility-level emissions estimates; rolling monthly updates; useful for cross-validation of supplier hotspots | Different ingestion model (vector rather than raster). Coverage is sector- and country-dependent. Out of scope for v1 — revisit when validation of v1 outputs against an external source is needed |
| **OCO-2 / OCO-3 GEOS XCO₂** | Atmospheric CO₂ column raster — upload required | Direct atmospheric CO₂ measurement context | Coarse (~0.05°) and gappy; weak facility attribution because CO₂ is long-lived and well-mixed. Adds little to ODIAC + Sentinel-5P CH₄ at the screening tier |
| **ERA5 hourly reanalysis — surface wind** (`u10`, `v10`) | Reanalysis raster, native in GEE (`ECMWF/ERA5_LAND/HOURLY` or `ECMWF/ERA5/HOURLY`) | Wind direction and speed enable the deferred `Wind_Consistency` sub-score in `Indicators_Computation_v3.md` §2.3 and directional buffers (plume-aware AOI construction) for v1.x. Routinely used in atmospheric source-attribution literature to separate local from transported pollution | Adds two non-trivial pieces of work: a wind-resampling pipeline (ERA5 hourly → buffer-mean per analysis window) and the `Wind_Consistency` formula calibration. Out of scope for v1 — the v1 fallback (`Fire_or_Regional_Transport_Risk`, §7.3) covers the most material case without wind |

If any of these are reintroduced later, the asset-organisation structure in Section 5.3 should be extended as follows:

```
projects/<gsco-gcp-project>/assets/
├── odiac/                          (v1)
├── edgar/                          (future)
├── climate_trace/                  (future — FeatureCollection)
├── xco2/                           (future)
└── era5_wind/                      (future — derived buffer summaries; raw ERA5 stays in-place in GEE)
```

---

*Document version 3.0 — May 2026. Based on `Final_Indicators_List.pdf`, `Indicators_Full_Research.pdf`, `PLFS_v4.md`, `Indicators_Computation_v3.md`, and live GEE catalogue verification.*
