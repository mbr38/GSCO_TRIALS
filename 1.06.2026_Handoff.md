# GSCO Environmental Tool — Report Handoff

*Prepared for whoever writes the project's final report. Built by reading the actual code and running the actual tests, not the design docs. Where the code and a doc disagree, this document follows the code and flags the disagreement. Plain language throughout; a few unavoidable technical IDs are explained on first use.*

*Snapshot date: 1 June 2026. Branch: `main`, working tree clean.*

---

## 1. What the tool is now

The GSCO tool is a **satellite-based environmental screening platform** for supply chains. You point it at a supplier site (or a whole region), it pulls down recent satellite and modelled-atmosphere data for that spot, and it produces a **traffic-light risk summary across three "pillars" — Air Pollution, Greenhouse Gas (GHG), and Nature/Land** — plus drill-down detail, a plain-English written summary, batch "prioritisation" across many suppliers, and exportable reports (PDF/CSV/JSON). It is aimed at two user types: **Policy Makers** (region-level) and **multinational corporations / MNCs** (supplier-level). It is a working demo, not a production system: it runs locally, computes live against Google Earth Engine, and is seeded with demo supply chains and saved analyses so it can be shown without setup.

The important headline for the report: **the tool is far more complete than its own documentation suggests.** Most page docstrings and several design docs describe earlier, half-built states ("placeholder", "lands in a later milestone", "P-08 doesn't exist yet"). In the actual code, P-01 through P-11 are all built and wired. The engine computes all three pillars and a composite. Trust the code.

### Tech stack
- **Language/runtime:** Python 3.11 (3.12+ deliberately avoided — it breaks the geospatial dependency stack).
- **Web framework:** Streamlit (≥1.30). Multi-page app driven by `gsco_app.py` using `st.Page`/`st.navigation`.
- **Satellite data:** Google Earth Engine (`earthengine-api`), accessed through a cached initialiser. Maps rendered with `geemap.foliumap` (+ folium / streamlit-folium).
- **Maths/stats:** numpy, pandas, scipy.
- **Reports:** Jinja2 (HTML templating) + WeasyPrint (HTML→PDF; needs system libs Pango/Cairo/GLib).
- **Misc:** geopy (geocoding), streamlit-option-menu (top nav).
- **Pins matter:** `setuptools<81` (newer drops `pkg_resources` that leafmap needs) and `ipython<9` (geemap uses the pre-9 API). geemap is pinned to `0.34.4`. Do not bump these without re-testing.

### How it's run
1. Python 3.11 venv → `pip install -r requirements.txt` (3–5 min).
2. `earthengine authenticate` once.
3. `export EE_PROJECT_ID=...`. **Note:** per project memory the live data path specifically needs `EE_PROJECT_ID=supply-chain-observatory` (that project owns the ODIAC and KBA assets the engine reads); this is not committed in the repo.
4. `streamlit run gsco_app.py` → browser opens at `localhost:8501`.

> **Disagreement flagged:** `README.md` is stale — it still says "P-02 is a placeholder with geemap test" and "Everything else (P-03 through P-11) — later iterations." That has not been true for many milestones. The README's *setup* instructions are still correct; its *scope* description is not.

> **Two entry files:** `gsco_app.py` is the real launcher. `app.py` is the P-01 Landing page body, which `gsco_app.py` mounts as the default page (it also still works as a standalone `streamlit run app.py` fallback). Don't be confused by the two.

---

## 2. The pages

Every page lives in `pages/` (Streamlit orders them by filename number, which is **not** the same as the "P-number" from the wireframes). Status below is from the code.

| Page (P-#) | File | What it does | Produces | State |
|---|---|---|---|---|
| **P-01 Landing** | `app.py` | Pick user type (Policy Maker / MNC); initialise session; seed demo saved-analyses | Sets `user_type`; routes to P-02 | ✅ Fully built |
| **P-02 Scope Setup** | `pages/02_Scope_Setup.py` | Pick a demo supply chain / region / "no scope" (branches on user type), two-step pick→confirm | Writes `scope` to session; routes to P-03 | ✅ Fully built (docstring calling itself a "placeholder" is stale) |
| **P-03 Workflow Hub** | `pages/03_Workflow_Hub.py` | Home base: scope summary + cards routing to the two workflows (Inspect, Prioritisation) and three modules (Library, Saved, Reports) | Navigation only | ✅ Fully built (docstring claims cards are placeholders — stale) |
| **P-04 Inspect Setup** | `pages/04_Inspect_Setup.py` | Configure a single screening: centre, radius, indicators, time window; scope-aware (node dropdown / locked region AOI / free coordinates) | Writes `screening_setup`; routes to P-05 | ✅ Fully built (docstring "tabs disabled until P-02 lands" is stale) |
| **P-05 Screening Results** | `pages/05_Screening_Results.py` | The core result page. Runs `ScreeningRun`, renders traffic light, map, KPI grid, drill-downs, confidence panel, written summary, action bar. Four states: computing / results / partial-results / all-failed | Computes & displays the screening payload | ✅ Fully built (docstring calling components "placeholders" is stale; one unused `_render_placeholder` helper is dead code) |
| **P-06 Trend View** | `pages/06_Trend_View.py` | Per-indicator trend drill-down over time. Two paths: re-open a saved trend (no EE) or compute live from the screening | Renders trend plot | ✅ Fully built. *Caveat:* the P-05 action-bar "Switch to Trend" button is hard-disabled dead control; trends are reached via per-tile "view trend →" links instead |
| **P-07 Prioritisation Setup** | `pages/07_Prioritisation_Setup.py` | Batch-screening setup (up to 20 suppliers): supply-chain nodes or pasted list; indicator/radius selection; "strict audit mode" toggle | Writes `prioritisation_setup`; routes to P-08 | ⚠️ Mostly built. **The "country supplier database" tab is a genuine stub** (disabled, "Coming in v1.x") |
| **P-08 Prioritisation Results** | `pages/08_Prioritisation_Results.py` | Runs the batch executor sequentially over suppliers; ranked table, risk matrix, save-as-report, per-supplier drill-in to P-05 | Runs batch; ranked outputs | ✅ Fully built |
| **P-09 Indicator Library** | `pages/09_Indicator_Library.py` | Static reference catalogue: pillar tabs, per-indicator cards (definition, data source, regulatory alignment, formula/weights). No EE | Read-only reference | ✅ Fully built. *Minor deferral:* exact component weights for some derived indicators aren't surfaced on the card (v1.x follow-up) |
| **P-10 Saved Analyses** | `pages/10_Saved_Analyses.py` | List saved analyses; open / delete / export JSON; search filter; seeded with demos | Reads/mutates `saved_analyses` | ✅ Fully built. Gracefully handles incomplete "stub" seed entries |
| **P-11 Reports** | `pages/11_Reports.py` | Report builder: pick template + sources → live HTML preview → export PDF / CSV / JSON. ESRS/GRI framing | Assembles & exports reports | ✅ Effectively fully built (docstring claims preview/export "stubbed" — stale). *Genuine content stubs:* ESRS per-indicator datapoint codes and policy/action/target sub-sections render as labelled "out of scope" |
| **99 Engine Scratch** (Dev) | `pages/99_engine_scratch.py` | Throwaway developer debug UI for the engine | Debug output | 🧪 Legacy dev tool, slated for deletion now that P-05 exists |

**Genuine remaining stubs (not stale docstrings):** P-07 country-database mode; P-09 per-component weight display; P-11 ESRS datapoint codes + policy/action/target sub-sections; the dead "Switch to Trend" button on P-05.

---

## 3. The indicator engine

The engine lives in `engine/`. It is a set of **stateless pillar function libraries** (`air.py`, `ghg.py`, `nature.py`) plus a single **stateful orchestrator** (`orchestrator.py::ScreeningRun`) and shared building blocks in `engine/core/`. Canonical indicator IDs are in `engine/ids.py`; all tunables in `engine/constants.py`.

### 3.1 The three pillars and what they actually compute

> **Key methodological point:** the three pillars deliberately use *different* scoring grammars because they ask different physical questions. This is intentional and is **not** going to be "harmonised."

#### Air Pollution pillar (`engine/air.py`)
Nine pollutants, all scored by the same "repeatable core" anomaly method (see §3.2).

| Canonical ID | Source dataset | Measures | Raw unit |
|---|---|---|---|
| `air.no2.score` | Sentinel-5P `COPERNICUS/S5P/OFFL/L3_NO2` | NO₂ tropospheric column | µmol/m² |
| `air.so2.score` | Sentinel-5P `…/L3_SO2` | SO₂ column | µmol/m² |
| `air.co.score` | Sentinel-5P `…/L3_CO` | Carbon monoxide column | mmol/m² |
| `air.hcho.score` | Sentinel-5P `…/L3_HCHO` | Formaldehyde column | µmol/m² |
| `air.o3.score` | Sentinel-5P `…/L3_O3` | Ozone column | Dobson Units |
| `air.aai.score` | Sentinel-5P `…/L3_AER_AI` | Absorbing aerosol index | dimensionless |
| `air.pm25.score` | CAMS `ECMWF/CAMS/NRT` | Modelled surface PM₂.₅ | µg/m³ |
| `air.pm10.score` | CAMS `ECMWF/CAMS/NRT` | Modelled surface PM₁₀ | µg/m³ |
| `air.aod.score` | MODIS MAIAC `MODIS/061/MCD19A2_GRANULES` | Aerosol optical depth (0.55 µm) | dimensionless |

These combine into sub-aggregates (e.g. `air.industrial_combustion_proxy`, `air.heavy_industry_score`, `air.pm_or_aerosol`) and then pillar aggregates: `air.pollution_proxy_score`, `air.spatiotemporal_anomaly_score`, `air.measurement_quality_score`, and the headline `air.audit_followup_priority`.

- **O₃ is capped at 0.5** by design — it is a context indicator, not a primary pollution-burden term.
- **PM₂.₅/PM₁₀ are modelled, not measured** (CAMS is a model output, ~44 km native resolution).

#### GHG pillar (`engine/ghg.py`) — three indicators, three different grammars
| Canonical ID | Source dataset | Measures | Raw unit | How scored |
|---|---|---|---|---|
| `ghg.viirs.score` | VIIRS night-lights `NASA/VIIRS/002/VNP46A2` | "Flaring"/intense-source brightness | nW/cm²/sr | **Absolute-anchor band**: fraction of site pixels brighter than ~100 nW, saturating at 10% of pixels. *Not* a z-score. |
| `ghg.ch4.*` | Sentinel-5P `…/L3_CH4` | Atmospheric methane column | ppb | z-score (but see "inert" note below) |
| `ghg.co2.*` | ODIAC fossil-CO₂ `projects/supply-chain-observatory/assets/odiac` | Fossil-fuel CO₂ emissions allocation | t CO₂/yr | log site-vs-ring ratio (but see "demoted" note below) |

The **live** GHG composite (`ghg.core_audit_support`) is built from just two terms: `ghg.combustion_proxy` (borrowed from Air's NO₂/CO signal, weight 0.60) and `ghg.activity_score` (= VIIRS flaring, weight 0.40). Pillar aggregates: `ghg.core_audit_support`, `ghg.data_quality_attribution`, `ghg.audit_followup_priority`.

#### Nature/Land pillar (`engine/nature.py`)
| Canonical ID | Source dataset | Measures | How scored |
|---|---|---|---|
| `nature.kba.proximity_score` | KBA polygons `…/assets/KBAsGlobal_2026_March_01_POL` | Proximity/overlap to Key Biodiversity Areas | distance decay (`exp(-dist/10km)`) or overlap % |
| `nature.dw.*`, `nature.sensitive_land_cover_presence`, `nature.water_or_flooded_veg_exposure` | Dynamic World `GOOGLE/DYNAMICWORLD/V1` | 90-day land-cover composition | direct fractions / saturation clamps |
| `nature.habitat.conversion_score` | Dynamic World | Natural→non-natural land conversion vs baseline | class-delta fractions, clamped at 10% loss |
| `nature.ndvi.score` | MODIS `MODIS/061/MOD13Q1` | Vegetation greenness anomaly | z-score (repeatable core), lower-is-worse |
| `nature.forest_loss.*` | Hansen `UMD/hansen/global_forest_change_2023_v1_11` | Cumulative forest loss | raw area only (see "demoted") |

Sub-aggregates: `nature.biodiversity_exposure`, `nature.habitat.conversion_score`, `nature.vegetation_condition`. Pillar aggregates: `nature.measurement_quality`, headline `nature.followup_priority`.

### 3.2 How raw values become 0–1 scores (the "repeatable core")

Most indicators (all Air pollutants, NDVI) use the **site-vs-background anomaly method** from `engine/core/normalisation.py` and `engine/core/repeatable_core.py`:

```
score = clamp( (site − background_median) / (k · σ) , 0, 1 )     # higher-is-worse
```
where `k = 3` (a 3σ exceedance saturates the score to 1.0), `site` is the mean over a circular **site buffer**, and `background_median` is the median over a surrounding **background ring** (annulus, default 5× the site radius, capped at 200 km, land-masked).

- **Important methodological detail (M-DIAG-A4):** the denominator `σ` is *not* the ring's spatial spread. It is the **temporal** standard deviation of the site's own day-by-day values over a trailing "climatology" baseline period before the analysis window. An earlier version used spatial spread and it inflated anomalies 2–14× too high; this was diagnosed and fixed. VIIRS is excluded from this (night-lights have near-zero temporal variance).
- The three non-repeatable-core scorers are deliberate exceptions: VIIRS (absolute anchor), ODIAC CO₂ (log ratio), KBA (distance decay).

### 3.3 How scores aggregate

- **Sub-aggregate / pillar scores** are fixed-weight sums of contributing scores (weights in `constants.py`; each weight dict sums to 1.0). Missing inputs are dropped and the surviving weights renormalised ("survivor renormalise") — there are no silent default substitutions.
- **Composite score** (`composite.overall_screening`) = the **equal-weighted mean of the three pillar follow-up priorities** (`air.audit_followup_priority`, `ghg.audit_followup_priority`, `nature.followup_priority`). **Strict-None:** if *any* pillar's priority is missing, the composite is `None` (not a partial mean) — a deliberate fix so a single surviving pillar can't masquerade as the whole-site score.
- The composite is therefore a **0–1 "audit follow-up priority"** number, where higher = more reason to look closely.

### 3.4 Scoring bands (traffic light)

From `TRAFFIC_LIGHT_THRESHOLDS = (0.33, 0.66)`:
- **< 0.33 → Green** (low concern)
- **0.33–0.66 → Amber** (moderate)
- **> 0.66 → Red** (high concern)

These are spec-mandated boundaries applied to the headline composite and to each pillar's follow-up priority.

### 3.5 The confidence model

Separate from the risk score, every indicator gets a **0–1 confidence** (`engine/core/confidence.py`), answering "how well did the satellites observe this site?":

```
c_raw   = 0.30·QA + 0.30·N_valid + 0.25·anomaly_strength + 0.15·spatial_context
c_final = c_raw · column_to_surface_multiplier [· fallback penalties]
```
- **QA** — a per-indicator static quality default (e.g. NO₂ 0.90, SO₂ 0.75, CAMS PM 0.80). *Real per-image quality pass-rates are not yet plumbed in — this is a known Layer-B follow-up.*
- **N_valid** — observations seen ÷ expected observations for the window (catches cloudy/sparse windows).
- **anomaly_strength** — the hotspot-frequency value; 1.0 for indicators with no anomaly concept.
- **spatial_context** — whether the site buffer covers ≥3 native pixels; penalises sub-pixel buffers.
- **column-to-surface multiplier** — penalises gases whose satellite *column* measurement is a weaker proxy for *ground-level* concentration (e.g. CH₄/CO down-weighted vs NO₂).
- **Fallback penalties** — if a "same-period-previous-year" or climatology fallback was used to recover missing data, confidence is multiplied by 0.60 / 0.75.
- **Strict-None:** any missing term collapses that indicator's confidence to `None`; pillars renormalise over survivors.
- **Composite confidence** = the **minimum** of the three pillar confidence aggregates (strict-None). The most-poorly-observed pillar caps the headline confidence.

In the UI this is shown as a confidence dot, and below ~0.40 an indicator reads as "Sparse".

### 3.6 Indicators that are DEFINED but INERT

This is important for an honest report — several indicators exist in the schema and are computed/displayed but **do not influence any score**:

- **CH₄ (`ghg.ch4`)** — *reclassified as reference data (M-CH4-A1).* Still computed and shown on a reference card, but **nothing scored consumes it**. Reason: validation against ODIAC/OCO showed the CH₄ anomaly proxy fired at only 1 of 25 test sites at 5 km, and 0 of 25 at 15 km — the TROPOMI ~7 km methane footprint is simply too coarse for a screening-size site. The scoring functions still exist in code but are no longer called.
- **ODIAC CO₂ (`ghg.co2`)** — *demoted from the live composite (M5.5b).* It only covers 2020–2023 (2+ year vintage lag), so a present-day screening can't use it as a live signal. It still computes and displays as "standing exposure" context, but is outside the formula.
- **Hansen forest loss (`nature.forest_loss`)** — *demoted to a reference layer.* Its "cumulative loss since 2000" framing breaks the live-window semantics of the other Dynamic-World-based nature terms. It survives as a reference card and as an input to `regional_loss_evidence` (the ring-vs-site external-driver check), but its weight in the habitat composite was removed.
- **`ghg.nearby_source_isolation`** — a **fixed 1.0 placeholder.** Emitted into the payload but removed from the data-quality aggregate (it was inflating it).
- **`ghg.spatiotemporal_anomaly`, `ghg.trend`, `air.trend_score`** — **retired.** After CH₄/VIIRS were re-framed, GHG has no anomaly source; trend is now a per-indicator drill-down only and never enters composite arithmetic.
- **`nature.recovery.score`** — **fixed 0.0 placeholder** (the FIRMS active-fire input it needs is deferred).
- **`nature.cloud_observation_quality` (0.8) and `nature.seasonal_comparability` (1.0)** — fixed placeholder quality sub-scores.
- **NDVI slope / negative-trend term** — demoted to drill-down-only; removed from the vegetation-condition score.
- **Attributability surfaces** (`nature.habitat.attributability_state`, `nature.supplier_spatial_link.*`, VIIRS `lit_contrast` percentile) and **wind attribution** — computed and shown as categorical context but **deliberately not in any composite or confidence score**.
- **`air.attribution_confidence_score`** — a deprecation alias duplicating `air.measurement_quality_score`.
- **Reserved-but-never-computed:** sector tags, wind-consistency, sector-match, high-GWP-sector-risk, EVI, FIRMS fire, JRC surface water.

---

## 4. Key methodological decisions

- **Site-vs-background anomaly approach.** *Chosen:* score each indicator as how far the site sits above (or below) its *local* surroundings, measured in standard deviations, rather than against an absolute threshold. This makes the tool location-relative and comparable across very different regions. *Refined:* the denominator was switched from the ring's *spatial* spread to the site's *temporal* day-to-day spread after the spatial version was shown to inflate anomalies (M-DIAG-A4). *Rejected:* absolute fixed thresholds (except where physically necessary — VIIRS flaring, ODIAC).
- **GHG / VIIRS / ODIAC treatment.** *Chosen:* lead the live GHG signal with VIIRS night-lights "flaring" (an absolute-anchored intense-source detector) plus a borrowed Air combustion proxy, validated against ODIAC (Spearman ρ ≈ 0.70). *Rejected:* (a) using CH₄ as a live scoring signal — footprint too coarse, reclassified to reference; (b) using ODIAC CO₂ in the live composite — vintage lag too large, demoted to context; (c) the earlier VIIRS "sustained ring-contrast" grammar — it couldn't rank intensity (heavy and middling sources looked identical), replaced by the absolute anchor.
- **Trend engine.** *Chosen:* trend (`engine/core/trend.py`) is a **Theil–Sen slope + Mann–Kendall significance** test on a per-day site series, computed **on demand after a screening**, for a **single indicator at a time**. *Rejected:* aggregating trend across indicators or feeding it into the composite — trend is drill-down-only and never enters the headline score.
- **Wind attribution.** *Status:* implemented (`engine/core/wind.py`, M-WIND-A1 v2.0) as a **categorical** label (high/moderate/low/sparse) based on ERA5 wind speed and upwind/downwind ring asymmetry on anomaly days. It is **purely informational — it does not enter any score or confidence.** *Honest caveat the code itself records:* across the five seeded demo sites essentially none land at "low", because of structural limits in the hotspot detector and ring geometry; a calibration sweep is deferred to v1.x. Treat the wind arrows as indicative only.

---

## 5. Testing

- **2,086 tests** collected across **98 test files** (`tests/`). A full run with no Earth Engine credentials gives roughly **2,052 passed, 34 skipped, 0 failed** in ~12 seconds.
- **Almost everything is pure unit / synthetic-payload testing** (~2,050 tests): engine formulas (`test_air.py` 95, `test_ghg.py` 76, `test_nature.py` 70, plus orchestrator, repeatable-core, normalisation, confidence, severity, trend, VIIRS, provenance, verbal-summary, fallback, etc.), UI-component render/state tests (the `test_c4*`/`test_c5*`/`test_p02*`…`test_p11*` families), and doc↔engine consistency guards (`test_doc_constants_sync.py`, `test_formula_keys_match_engine.py`).
- **Integration tests that hit Earth Engine** are the only ones needing network/credentials — 7 files, **auto-skipped** unless `RUN_EE_TESTS=1` and `EE_PROJECT_ID` are set (these are the 34 skips). So the EE-dependent assertions are **effectively unverified in the default run**.
- **What's NOT covered:**
  - The live Earth Engine path is only exercised when someone manually opts in; there's no CI enforcement that it ever runs.
  - Several UI components have no dedicated test: `c3_summary`, `c7_verbal_summary` (the engine-side generator *is* tested, the UI wrapper isn't), `indicator_info`, `p02_preview`, `p03_hub`, `p08_renderer`, `trend_plot`, `trend_view`, `theme.py`.
  - `tests/test_air_integration.py` is a **broken empty stub** (its entire content is the character `3`) — collects zero tests. Should be deleted or implemented.
  - The declared `integration` pytest marker is never actually applied, so `pytest -m integration` selects nothing. There is no `conftest.py` and `pytest-timeout` is not installed.

---

## 6. Honest limitations

- **PM₂.₅/PM₁₀ are modelled, not measured.** They come from the CAMS atmospheric *model* at ~44 km resolution — far coarser than a supplier fenceline. Treat as regional context.
- **Satellite columns ≠ ground concentrations.** Sentinel-5P measures whole-atmosphere *columns*; the tool uses them as proxies for surface pollution. The confidence model down-weights the weaker proxies (CH₄, CO), but the proxy assumption remains.
- **Static QA values.** The "QA" term in confidence is a per-indicator hand-set constant, not a real per-image quality pass-rate. Confidence is therefore approximate.
- **First-pass, uncalibrated thresholds.** Many saturation points and band cut-offs are explicitly marked "first-pass / calibration pending" in `constants.py`: the 10% habitat-loss saturation, 20% water-exposure saturation, the KBA 10 km decay length, the VIIRS 100 nW flaring anchor, the wind speed/asymmetry breakpoints, the habitat-attributability distance bands. They are reasonable judgments, not empirically tuned.
- **Data lag and coverage.**
  - **ODIAC CO₂** lags ~2 years (covers 2020–2023) — the reason it was demoted from the live score.
  - **Hansen forest loss** is annual and pinned to the **2023** vintage in code.
  - **CH₄** footprint (~7 km) is too coarse for site-scale screening — the reason it's reference-only.
  - **MODIS NDVI** is a 16-day composite, so short windows see few observations.
- **Attribution caveats.** Both attribution surfaces are *indicative only*. Habitat attributability is a simple distance-from-loss-centroid heuristic. Wind attribution rarely produces a "low" label on real sites (documented detector/geometry limitation). Neither affects the score — the tool flags *where to look*, it does not prove a supplier *caused* an observed signal.
- **Coastal / sparse AOIs.** When the background ring lands mostly over water or has persistent cloud, indicators are skipped with a specific reason rather than guessed — good for honesty, but it means some sites return partial results.

---

## 7. Known gaps / future work

- **P-07 country supplier-database mode** — stubbed, "Coming in v1.x".
- **Real per-image QA pass-rates** into confidence (Layer B) — deferred.
- **Calibration sweep** of the first-pass thresholds (habitat attributability + wind jointly) — deferred to v1.x.
- **Wind-attribution detector rework** — the structural fix (temporal-std baseline, per-pollutant thresholds) is logged for v1.x.
- **FIRMS active-fire input** for `nature.recovery` and air fire detection — deferred (recovery score currently fixed at 0.0).
- **CH₄ / OCO-2/OCO-3 validation harness** (Part B via Earthdata `earthaccess`) — OCO is not in Earth Engine; needs Earthdata credentials. Deferred.
- **P-11 ESRS** per-indicator datapoint codes and policy/action/target sub-sections — intentionally out of scope for v1.
- **P-09** per-component weight display — deferred.
- **Deferred datasets not yet wired:** EVI, JRC Global Surface Water, EDGAR, Climate TRACE, Sentinel-2/Landsat, S5P near-real-time variants.
- **The v1.x roadmap** (Tier A–F) lives in `docs/Indicators_Audit_and_v1x_Roadmap.md`, the designated authority for indicator decisions.
- **Cleanup:** delete the `99_engine_scratch.py` dev page, the empty `test_air_integration.py`, and the dead "Switch to Trend" button.

---

## 8. Datasets (live data sources actually read by the engine)

Asset IDs are taken from the **code** (where the code and `GEE_Database_List_v3` disagree, code wins — flagged).

| Dataset (asset ID in code) | Pillar / use | Provider | Update cadence |
|---|---|---|---|
| `COPERNICUS/S5P/OFFL/L3_NO2` (and SO2, CO, HCHO, O3, AER_AI) | Air pollutants | Copernicus / ESA (Sentinel-5P TROPOMI) | ~Daily |
| `ECMWF/CAMS/NRT` | Air PM₂.₅ / PM₁₀ | ECMWF Copernicus Atmosphere (CAMS) | Daily (modelled) |
| `MODIS/061/MCD19A2_GRANULES` | Air AOD (MAIAC) | NASA MODIS | ~Daily |
| `COPERNICUS/S5P/OFFL/L3_CH4` | GHG methane (reference) | Copernicus / ESA | ~Daily |
| `NASA/VIIRS/002/VNP46A2` | GHG VIIRS night-lights | NASA / NOAA | Nightly |
| `projects/supply-chain-observatory/assets/odiac` | GHG CO₂ (context) | ODIAC / NIES Japan | Annual, ~1+ yr lag (2020–2023) |
| `GOOGLE/DYNAMICWORLD/V1` | Nature land cover / habitat / water | Google + WRI | Every 2–5 days |
| `UMD/hansen/global_forest_change_2023_v1_11` | Nature forest loss (reference) | UMD / Hansen et al. | Annual |
| `MODIS/061/MOD13Q1` | Nature NDVI | NASA MODIS | 16-day composite |
| `…/assets/KBAsGlobal_2026_March_01_POL` | Nature KBA proximity | BirdLife International | ~6-monthly snapshot |
| `ECMWF/ERA5/HOURLY` | Wind attribution (categorical, not scored) | ECMWF ERA5 | Hourly reanalysis |
| `MODIS/006/MOD44W` | Internal land/water mask for the background ring | NASA MODIS | Static |
| `FAO/GAUL/2015/level0` | Country lookup for climatology baseline | FAO GAUL | Static (2015) |

**Code-vs-doc disagreements found (code wins in each case):**
- **CAMS band names** — code uses the renamed long band names (`particulate_matter_d_less_than_25_um_surface`); the doc lists older/short forms.
- **ODIAC asset** — code points at the uploaded GSCO asset `projects/supply-chain-observatory/assets/odiac`; the doc suggests a catalogue path that doesn't exist.
- **Hansen version** — code pins `global_forest_change_2023_v1_11`; the doc lists `2024_v1_12 (or later)`.
- **KBA asset** — code uses the uploaded snapshot `KBAsGlobal_2026_March_01_POL`; the doc lists `projects/ee-kbas-in-gee/assets/current`.
- **ERA5** — the doc lists ERA5 as "considered but not included in v1"; the code *does* use `ECMWF/ERA5/HOURLY` in the wind path (chosen over ERA5-Land because the latter lacks boundary-layer height).

---

## 9. Open questions (genuinely ambiguous in the code — verify before stating in the report)

1. **Composite when GHG is partly inert.** With CH₄ reference-only and ODIAC demoted, the live GHG follow-up priority rests on just VIIRS flaring + the borrowed Air combustion proxy. The composite weights all three pillars equally — it's worth confirming with the team whether equal weighting is still intended now that GHG's independent signal is so thin.
2. **Which `EE_PROJECT_ID` is canonical.** The README says "your own project ID"; project memory says the data assets live under `supply-chain-observatory`. A reader running the demo against a different project will silently fail to load ODIAC/KBA. Confirm the intended project.
3. **`docs/` was internally inconsistent — now reconciled (1 June 2026).** There is a `v4` doc set, an authoritative `Indicators_Audit_and_v1x_Roadmap.md`, and ~40 milestone close-out notes. The frozen behaviour docs (`PLFS_v4`, `Wireframes_All_v4`, `Engine_Module_Skeleton_v1`) had drifted from the code because the workflow froze docs while the engine evolved through milestones, with no write-back step. This has been addressed: each of the three now carries a dated **"Reconciliation banner — read first"** that re-anchors authority to v4/v2, lists every substantive behaviour delta with milestone attribution, and states "the code wins"; the worst inline traps (GHG formula block, P-06 trend mode, composite helper, state contract, P-07 cap, Appendix C Sparse band, weight dicts, non-existent files) were fixed in place. The three browser-download `(1)` filenames were renamed to the canonical names `CLAUDE.md` expects. Stale page docstrings (P-03/04/05/11) and the README scope section were refreshed. The `Indicators_Audit_and_v1x_Roadmap.md` was deliberately left untouched (it is the designated authority and already current). **Still true:** the audit doc + code remain ground truth; the milestone close-out notes are an append-only history, not a substitute for the canonical docs.
4. **CAMS resolution vs buffer size.** PM is read at ~44 km native pixel but applied to fenceline-scale buffers (often 5 km). The spatial-context confidence term should be flagging this; confirm it produces the intended low-confidence behaviour in practice (vs being masked by the static QA value).
5. **Wind "low" never firing.** The code comments document that no seeded site reaches `state="low"`. Whether this should be presented as a limitation or simply omitted from the report is a judgment call for the team.
