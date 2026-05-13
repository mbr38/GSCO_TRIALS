# Page-Level Functional Specification (PLFS)

**Tool:** GSCO Environmental Monitoring & Decision-Support Platform
**Author:** Benedetta Radice Fossati
**Version:** v4 — reconciled with Wireframes v3 (demo scope)
**Date:** 13 May 2026

### Changes since v3

This version reconciles the PLFS with the demo-scope decisions locked in `Wireframes_All_v3.md` (11 May 2026). The PLFS is now the single source of truth for *what each page does and produces*; the Wireframes document is the single source of truth for *how each page behaves*; `Indicators_Computation_v3.md` is the single source of truth for *all indicator names, formulas, and weights actually used by v1*.

- **Authentication deferred.** P-01 (§5) no longer describes a sign-in form. The page is user-type selection only. Sign-out resets session state on every page; the full auth design is preserved in `Wireframes_All_v3.md` Appendix A.
- **Two-supplier comparison scrapped from v1.** P-07 (§11) mode toggle is *Whole supply chain* / *Filtered subset* only. `prioritisationConfig.comparisonPair` removed from §18. P-08 (§12) comparison panel removed. Appendix A journey for MNCs updated.
- **Risk matrix axes changed.** P-08 (§12) now plots two of the three pillar Follow-Up Priority Scores against each other (user-selectable). Default x=Air, y=Nature. Quadrants are pillar-based, not severity/confidence.
- **Top-N default = 5** on P-08 (was 10).
- **"Save as report" unified action.** P-05, P-06 and P-08 (§§9, 10, 12) no longer have separate Save and Generate buttons; one button writes to both Saved Analyses and to a report draft consumed by P-11.
- **P-06 user-type variation removed.** Both Policy Maker and MNC see the same trend view: trend map prominent, alert panel collapsed.
- **P-04 indicator-selection default.** All indicators pre-selected by default; the user deselects to narrow. No user-type-specific default.
- **P-07 prioritisation preset.** Selects the three pillar Follow-Up Priority Scores plus the single highest-contributing single value per pillar (replaces the earlier "key contributing single values" phrasing).
- **P-09 Indicator Library — reference-only.** No selection propagation back to the active workflow.
- **P-10 Saved Analyses — minimal.** List + open + delete only. Bulk select, side-by-side compare, tags, search, "Add to report" deferred.
- **Formulas in §9.** The pillar aggregate formulas in this document are *reference* (they show the original full weights including sector and wind context). **The formulas actually computed in v1 are the rescaled forms in `Indicators_Computation_v3.md` §1.3, §2.3, §3.3.** Cross-reference added below each formula block.
- **Indicator names.** `Indicators_Computation_v3.md` is the authoritative source for indicator names, formulas, weights, and units. Appendix B (§17) defers to it.
- **Screening time-range selector hidden (H4 — added 13 May follow-up).** P-04's time-range selector is hidden in screening mode and shown only when the user selects Run Trend. Screening always uses the latest valid 90-day composite for each dataset. The monitoring/trend background window is locked to the 3 years immediately preceding the user's analysis-window start (see `Indicators_Computation_v3.md` §0.5).

### Changes since v2

- **Risk matrix folded into Prioritisation Results.** What was P-09 (Risk Matrix View) in v2 is now a **visualisation option within P-08 (Prioritisation — Results)**, not a separate page. The page presents a view toggle between *Ranking table* (default) and *Risk matrix* over the same underlying result. Total page count drops to 11.
- **Audit / ESG report templates defined concretely.** The Policy audit report and the ESG / due-diligence report are now specified as **a structured summary of every indicator available in the Screening section (P-05)** for the chosen target(s). They are no longer ambiguous "audit-ready evidence summaries" — they are screening-coverage dumps, formatted to PDF.
- **Page renumbering.** With P-09 absorbed into P-08, Indicator Library is now P-09, Saved Analyses is P-10, and Reports Page is P-11. The v2 → v3 mapping appears in §4.

### Changes since v1

- **Front-end environment.** Decision taken: the tool moves to **Python plus a separate map environment**. The existing GEE JavaScript files (`Vegetation.js`, `AirQuality.js`, `Inspection.js`) are now reference for *computation logic*, not direct UI ports. The Code Reuse appendix has been re-framed accordingly.
- **Map / AOI Tools persistent module deferred.** The standalone exploration / marker / AOI-export functionality from `Inspection.js` is dropped from the v1 build. The persistent navigation rail is therefore three modules, not four. The two analysis setup pages now use a simpler **point-plus-radius** AOI model with no polygon drawing.
- **Policy Maker scope set-up extended.** Policy Makers can either connect to the GSCO supply-chain catalogue *or* upload their own region set, mirroring the MNC path (added for regional regulators with bespoke jurisdictions).
- **Cross-pillar composite weights.** Confirmed at ⅓ each for v1; sector-aware weighting flagged as a future extension rather than an open question.
- **Two-supplier comparison.** Confirmed as a Prioritisation-only option, not extended to Inspect.

---

## 1. Purpose of this document

This specification merges the three preceding workstreams — **Sitemap Draft 2**, **Final Indicators List / Indicators Full Research**, and **Stakeholders List Summary** — into a single page-by-page reference. Each section below describes one page (or sub-view) of the tool and tells you, for that page:

- which user types reach it and how their experience differs,
- what the page receives from earlier steps,
- which indicators it computes (with the formulas drawn directly from the indicator research),
- which UI components must appear,
- what it produces and where outputs flow,
- which existing GEE code can be reused.

The document is the single source of truth for the next two stages: detailed wireframing and tool coding.

## 2. How to use this document

Read the **page index** in §4 to orient yourself. When wireframing, work through the pages one at a time using the corresponding section as a checklist — every "UI Components" bullet must appear on the wireframe. When coding, the "Indicator Computations" and "Code Reuse Notes" sections together define the back-end work for that page.

The three supporting artefacts referenced in the previous stage (user-flow diagrams, indicator engine module map, persistent state model) sit in §17–§19 as appendices.

## 3. Reconciliation: Sitemap workflows vs Stakeholder decisions

The Sitemap shows **two workflows** (Inspect, Prioritisation) plus a persistent Reports Page. The Stakeholders summary shows **four decisions** (Screening, Monitoring, Prioritisation, Reporting). They map cleanly:

| Stakeholder decision | Sitemap location |
|---|---|
| Screening | Inspect → Results → Screening View |
| Monitoring | Inspect → Results → Trend View |
| Prioritisation | Prioritisation → Results (Ranking table or Risk matrix visualisation) |
| Reporting | Reports Page (persistent module) |

This mapping is assumed throughout. Any future change to the Sitemap must preserve it.

## 4. Page index

| § | Page ID | Sitemap location |
|---|---|---|
| 5 | P-01 | Landing |
| 6 | P-02 | Scope set-up |
| 7 | P-03 | Workflow Hub |
| 8 | P-04 | Inspect — Setup |
| 9 | P-05 | Inspect — Results — Screening View |
| 10 | P-06 | Inspect — Results — Trend View |
| 11 | P-07 | Prioritisation — Setup |
| 12 | P-08 | Prioritisation — Results (Ranking table + Risk matrix views) |
| 13 | P-09 | Indicator Library (persistent) |
| 14 | P-10 | Saved Analyses (persistent) |
| 15 | P-11 | Reports Page (persistent) |

*Note: the Map / AOI Tools persistent module (formerly v1's P-12) is deferred; see header changelog. The Risk Matrix View (formerly v2's P-09) is now folded into P-08 as a visualisation option.*

**v2 → v3 page ID mapping:** P-01 through P-08 unchanged. v2's P-09 (Risk Matrix) absorbed into P-08. v2's P-10 → v3's P-09 (Indicator Library). v2's P-11 → v3's P-10 (Saved Analyses). v2's P-12 → v3's P-11 (Reports Page).

---

## 5. P-01 — Landing

**Purpose.** Entry point. Capture user type for the session. Authentication is deferred to a future build (see `Wireframes_All_v3.md` Appendix A).

**User access.** Anyone — no sign-in.

**Decision supported.** None — gateway.

**Inputs received.** None.

**Indicator computations.** None.

**UI components.**
- Brand mark and brief tool overview / value proposition.
- User-type selector with two cards (no defaulting; the user must make an explicit choice):
  - *Policy Maker* — short description of the regional / supply-chain-level monitoring use case.
  - *MNC* — short description of the supplier-level due-diligence use case.
- "Continue" primary action (disabled until a card is selected).
- Footer link to overview documentation.

**Outputs produced.** Session containing `userType ∈ {policy_maker, mnc}` and a randomly generated `session.id`. Both are consumed by every subsequent page.

**Persistent modules touched.** None. Saved Analyses and Reports are held in browser state only for the demo (no per-user persistent store yet).

**Code reuse.** None — the page is new UI shell.

---

## 6. P-02 — Scope set-up

**Purpose.** Define the supply-chain context the tool will operate on for this session.

**User access.** Both user types, with **diverging defaults but the same available actions** (this is the most important user-type fork in the tool):

- *Policy Maker (default path)* — connect to GSCO's existing supply-chain catalogue (already produced by the wider GSCO platform). Select an industry or named supply chain to load.
- *Policy Maker (alternative path)* — upload a custom region set, for regional regulators with bespoke jurisdictions that don't match a GSCO catalogue entry. Same upload mechanism as the MNC path.
- *MNC* — upload or define their own supply chain. The MNC is responsible for providing supplier locations.

**Decision supported.** None — context-setting for all downstream workflows.

**Inputs received.** `userType` from P-01.

**Indicator computations.** None at this page, but the page produces the inputs every indicator computation will use:
- Geocoding of supplier addresses (if the MNC uploads a list with addresses rather than coordinates).
- Coordinate validation (reject lat ∉ [−90, 90], lon ∉ [−180, 180]).
- Construction of the working `supplyChain` dataset.

**UI components.**
- Conditional UI block by `userType`, with a sub-toggle for Policy Maker:
  - *Policy Maker — Connect to GSCO catalogue:* dropdown of GSCO supply chains organised by the GSCO target industries (Critical minerals, EV battery, Solar PV, Food systems, Electronics & semiconductors); preview panel showing nodes on a world map; "Load this supply chain" button.
  - *Policy Maker — Upload custom regions / MNC view:* file upload (CSV / Excel template with columns: `node_id, node_name, lat, lon, tier, sector, country` plus optional `address` for geocoding); manual-entry table for small chains; downloadable CSV template; validation messages panel. The same uploader serves both Policy Maker custom uploads and MNC supplier uploads — column semantics adapt to user type.
- Map preview of the loaded scope with markers per node.
- "Confirm scope and continue" button → Workflow Hub.
- "Save scope as session" button → Saved Analyses.

**Outputs produced.**
- `supplyChain` object: `{name, industry, nodes: [{id, name, lat, lon, tier, sector, country}, …]}`.
- Stored in session state and optionally persisted via Saved Analyses.

**Persistent modules touched.**
- Saved Analyses — optional save.

**Code reuse.**
- From `Inspection.js`: the lat/lon validation logic (`goToLocationButton.onClick`) is the only reusable element; port the validation rules conceptually into the Python upload validator. The marker rendering on the preview map will be handled by the chosen separate map environment, not by reused GEE code.
- New: file upload, CSV parsing, geocoding service integration, GSCO-catalogue API connection.

---

## 7. P-03 — Workflow Hub

**Purpose.** Branch into one of the two analysis workflows. This is the persistent home of the tool.

**User access.** All authenticated users with a defined `supplyChain`.

**Decision supported.** Routing decision only.

**Inputs received.** `userType`, `supplyChain`.

**Indicator computations.** None.

**UI components.**
- Two large workflow cards:
  - *Inspect a region / supplier* — short description: "Run a screening or monitoring analysis on a specific location."
  - *Prioritisation* — short description: "Rank and compare locations across your supply chain."
- Persistent navigation rail to the three persistent modules: Indicator Library, Saved Analyses, Reports Page.
- Top bar showing the active scope ("Working on: <scope name>") with a "Change scope" link back to P-02.

**Outputs produced.** `selectedWorkflow ∈ {inspect, prioritisation}`.

**Persistent modules touched.** All three — the hub is where the persistent modules become reachable.

**Code reuse.** None — UI shell is new.

---

## 8. P-04 — Inspect — Setup

**Purpose.** Configure an Inspect analysis (one location with a user-defined radius).

**User access.** Both user types.
- *Policy Maker* — typically picks a region or a node from the loaded supply chain.
- *MNC* — typically picks a specific supplier from their uploaded chain.
- Both can also enter free coordinates or draw an AOI.

**Decision supported.** Pre-Screening / Pre-Monitoring (the same setup feeds both Result views).

**Inputs received.** `supplyChain`, `userType`.

**Indicator computations.** None until Run is clicked. At setup time:
- Suggested radius computation based on selection type:
  - Single supplier → suggested 5 km buffer (site-level audit), with options 1, 5, 10, 25 km.
  - Region → suggested 25 km, with options 10, 25, 50, 100 km.
- AOI generation as a circular buffer around the chosen point at the chosen radius. (No polygon drawing in v1; deferred with the Map / AOI Tools module.)

**UI components.**
- Selection mode toggle: *Region* / *Supplier* / *Free coordinates*.
- For *Supplier*: dropdown of nodes from `supplyChain` (searchable).
- For *Region*: dropdown of regions from the loaded scope (Policy Maker only) or a manual region entry.
- For *Free coordinates*: lat / lon inputs (validated as in P-02).
- Radius slider with labelled stops: site-level (1 km), facility buffer (5 km), local context (10 km), regional context (25 km+).
- Map showing the selected centre and the resulting circular buffer.
- Indicator selection block (collapsible by pillar): Air Pollution, GHG, Nature/Land. Each pillar lists single-value indicators and the corresponding aggregate scores. **All indicators are pre-selected by default**; the user deselects to narrow. A "Reset to all selected" link restores the default. No user-type-specific defaulting. "Open Indicator Library" link for reference.
- Time range selector — **hidden in screening mode**; shown when the user toggles toward Run Trend. Screening always uses the latest valid 90-day composite for each dataset (see `Indicators_Computation_v3.md` §0.5). Trend mode requires ≥ 12 months and offers sensible defaults per indicator.
- Two run buttons: "Run Screening" (→ P-05) and "Run Trend" (→ P-06).

**Outputs produced.**
- `aoi` (circular geometry derived from `centre` and `radius`) — used by every indicator computation.
- `selectedIndicators` (list of indicator IDs).
- `analysisMode ∈ {screening, monitoring}`.
- `timeRange` (start, end).
- `centreMetadata` (supplier ID or coordinates, used for confidence weighting and report attribution).

**Persistent modules touched.**
- Indicator Library (selection state).

**Code reuse.**
- From `Inspection.js`: the lat/lon validation rules (port concept, not code, into Python).
- From `Vegetation.js` and `AirQuality.js`: the multi-step accordion guide pattern is a useful reference for how to structure a guided setup flow, even though the implementation will be re-written in the new front-end.

---

## 9. P-05 — Inspect — Results — Screening View

**Purpose.** Snapshot of current environmental conditions at the selected location.

**User access.** Both user types, with **divergent framing** (per Stakeholders summary):
- *Policy Maker* — labelled **Regional Environmental Screening Score**; primary visualisation is a hotspot map plus a traffic-light score for the region.
- *MNC* — labelled **Supplier Environmental Screening Score**; primary visualisation is a supplier dashboard plus a traffic-light score.

The underlying computation is identical for both; only the framing, default indicator set and report template differ.

**Decision supported.** Screening.

**Inputs received.** `aoi`, `selectedIndicators`, `timeRange`, `centreMetadata`, `userType`.

**Indicator computations.** Per the Final Indicators List, compute **current snapshot values plus the screening-mode aggregates** in the three pillars. The repeatable core method (site value, background value, absolute anomaly, normalised z, hotspot frequency, confidence) applies to every Sentinel-5P pollutant.

*Air Pollution pillar (single values):*
- For each of NO₂, SO₂, CO, CH₄, HCHO, O₃, AAI: site mean, background median, absolute anomaly, normalised z, hotspot frequency, confidence — using the repeatable core method.
- PM₂.₅ proxy from CAMS (site mean, anomaly, trend, quality).
- Optional AOD from MODIS MAIAC for additional aerosol context.

*Air Pollution pillar (aggregates).* The formulas below are the original reference formulas. **For v1, the rescaled forms in `Indicators_Computation_v3.md` §1.3 are computed** — sector- and wind-context terms are absent and weights rescaled to sum to 1.0.

```
Air_Pollution_Proxy_Score = 0.30·NO₂_score + 0.20·SO₂_score
                          + 0.15·CO_score  + 0.15·HCHO_score
                          + 0.10·PM_or_Aerosol_score
                          + 0.10·O₃_context_score

Air_Pollution_Audit_FollowUp_Priority =
    0.35·Air_Pollution_Proxy_Score
  + 0.30·SpatioTemporal_Anomaly_Score
  + 0.20·Trend_Score              (Trend_Score := 0 in Screening mode)
  + 0.15·Attribution_Confidence_Score
```

*GHG pillar.* The formulas below are the original reference formulas. **For v1, the rescaled forms in `Indicators_Computation_v3.md` §2.3 are computed** — `High_GWP_Sector_Risk`, `Wind_Consistency` and `Sector_Match` are deferred (set to 0 and remaining weights rescaled).

```
Core_GHG_Audit_Support =
    0.35·CO₂_Context  + 0.25·CH₄_Hotspot_Signal
  + 0.20·Combustion_Proxy + 0.10·Activity_Score
  + 0.10·High_GWP_Sector_Risk

GHG_Data_Quality_Attribution =
    0.25·Temporal_Coverage + 0.20·Spatial_Resolution_Suitability
  + 0.20·Retrieval_or_Inventory_Quality + 0.15·Wind_Consistency
  + 0.10·Sector_Match + 0.10·Nearby_Source_Isolation

GHG_Audit_FollowUp_Priority =
    0.40·Core_GHG_Audit_Support
  + 0.25·GHG_SpatioTemporal_Anomaly
  + 0.20·GHG_Trend                (Trend := 0 in Screening mode)
  + 0.15·GHG_Data_Quality_Attribution
```

*Nature pillar (single values):*
- Current land-cover composition from Dynamic World (class areas, percentages, dominant class, classification confidence).
- Biodiversity exposure from KBA layer (distance to nearest KBA, overlap area, overlap %, exposure class).
- Vegetation condition from Sentinel-2 NDVI (mean NDVI, anomaly, low-NDVI area, NDVI quality), masking built/water/permanent-bare with Dynamic World.
- Habitat conversion (current Dynamic World composite vs baseline composite from X years earlier).
- Bare-ground / disturbance expansion.
- Built-up expansion.
- Water / flooded-vegetation exposure.

*Nature pillar (aggregates):*
```
Nature_Quality_Attribution =
    0.20·Valid_Pixel_Coverage  + 0.20·Cloud_or_Observation_Quality
  + 0.20·DynamicWorld_Class_Confidence + 0.15·Seasonal_Comparability
  + 0.15·Supplier_Spatial_Link + 0.10·External_Driver_Screening

Nature_FollowUp_Priority =
    0.30·Biodiversity_Exposure + 0.30·Habitat_Conversion
  + 0.25·Vegetation_Condition  + 0.15·Nature_Quality_Attribution
```

*Composite (proposed for the screening summary card):*
```
Overall_Screening_Score = ⅓ Air_Pollution_Audit_FollowUp_Priority
                        + ⅓ GHG_Audit_FollowUp_Priority
                        + ⅓ Nature_FollowUp_Priority
```
Equal ⅓ weights are the v1 default. **Future extension:** sector-aware weighting (e.g. Air higher for industrial sectors, Nature higher for agricultural / land-use sectors) would be added by storing a per-sector weight vector and resolving it from the node's `sector` field at compute time. Confidence is reported as the minimum of the three pillar confidences (a conservative choice that prevents one strong pillar from masking weak signal in another).

**UI components.**
- Header card: location name + coordinates + AOI summary + analysis date stamp.
- **Traffic-light summary** (top): three pillar Follow-Up Priority Scores rendered as red/amber/green chips with numeric value and a confidence indicator beside each.
- **Primary visualisation** depending on `userType`:
  - *Policy Maker:* hotspot map of the AOI with selectable layer (Air, GHG, Nature) showing intensity overlaid on satellite imagery.
  - *MNC:* dashboard grid with one KPI tile per indicator, each showing value, anomaly direction (↑/↓), and confidence dot.
- **Per-pillar drill-down panels** (collapsible): each shows the constituent single values and the aggregate scoring. **The drill-down panel surfaces single-value indicators and the pillar Follow-Up Priority Score in v1.** The interpretive sub-aggregates from `Indicators_Computation_v3.md` §1.2 (`Heavy_Industry_Score`, `VOC_Photochemical`, `Industrial_Air_Pollution_Burden`, `Fossil_Combustion_Score`, `Activity_Adjusted_CO2`) are **deferred to v1.x** as standalone "lens views". The formula-internal sub-aggregates (`PM_or_Aerosol_score`, `Combustion_Proxy`, `Fire_or_Regional_Transport_Risk`, `CH4_Context_Adjusted`) are computed in the engine and carried in the result payload but are not shown as separate UI rows — they're plumbing inside the pillar formulas.
- **Confidence panel:** the three pillar Quality / Attribution Confidence Scores with a brief explanation of the limiting factor for each (e.g. "GHG confidence limited by coarse spatial resolution of CH₄ retrievals").
- **Verbal summary** (one paragraph) of the overall screening result, generated server-side from the scores — addresses the gap that the existing GEE tool flagged areas without providing summary text.
- **Save as report** button — writes the result to Saved Analyses *and* creates a report draft accessible from P-11 (single unified action).
- "Switch to Trend View" button → re-runs as P-06 with the same setup.

**Outputs produced.**
- `screeningResult` object containing all single values, aggregates, confidence scores, AOI metadata, computation timestamp, and provenance (which dataset asset IDs / dates were used).

**Persistent modules touched.**
- Saved Analyses (on save).
- Reports Page (on report generation).
- Indicator Library (drill-downs link to definitions).

**Code reuse.**
- From `Vegetation.js`: the AOI statistics block (`reduceRegion` with combined mean / min / max / stdDev reducer) is the **logic reference** for computing site values per indicator; the equivalent in the Python Earth Engine API is a near-identical call pattern. The Point Inspector and Time Series Inspection patterns become drill-down components in the new front-end.
- From `AirQuality.js`: identical AOI-statistics pattern adapted for Sentinel-5P bands; same logic reference.
- From `Inspection.js`: the "Download Analysis Results" pattern is a reference for the report data dump structure.
- New: composite score computation, traffic-light rendering, server-side verbal-summary generator.

---

## 10. P-06 — Inspect — Results — Trend View

**Purpose.** Time-series view of indicators at the selected location, showing how things have evolved.

**User access.** Both user types see the same trend view. Framing strings differ (Policy Maker: **Regional Environmental Trend Indicator**; MNC: **Supplier Environmental Performance Trend**), but the visualisation set is identical: trend map prominent by default, alert panel collapsed by default. Both panels are user-expandable. Per `Wireframes_All_v3.md` P-06, the earlier user-type variation in primary visualisation is removed.

**Decision supported.** Monitoring.

**Inputs received.** Same as P-05 plus an explicit `timeRange` (default 3 years; user-configurable from 1 to 10 years).

**Indicator computations.** All P-05 single values **per time bin** (monthly or annual depending on indicator frequency), plus:
- Trend coefficients per indicator (linear slope of the indicator over time, with significance / p-value).
- Anomaly frequency = (number of anomalous observations) / (number of valid observations) — already in the repeatable core method (Step 5).
- Baseline deviation (current period mean vs full-history baseline mean).
- Repeated anomalies count (anomalies in N consecutive periods).
- For Nature: annualised conversion rate (hectares of natural land converted per year), restoration / recovery signal flag.

The three pillar Follow-Up Priority aggregates are recomputed with the **Trend term active**: the `0.20·Trend_Score` term for Air and the `0.20·GHG_Trend` term for GHG, both of which are zero in Screening mode (see `Indicators_Computation_v3.md` §1.3 and §2.3). The Nature pillar formula does *not* contain a separate Trend term because `Habitat_Conversion` is already a temporal-difference indicator (current 90-day composite vs baseline composite from X years earlier — see Indicators_Computation §3.1). What changes for Nature in trend mode is that `Habitat_Conversion` is computed over the user's selected time range (its `annualised_rate` sub-score becomes meaningful), and the `Vegetation_Condition` slope-based term gains statistical power. The Nature_FollowUp_Priority formula itself is identical in both modes.

**UI components.**
- Header card as in P-05, plus the time range and bin size.
- Time-series chart per selected indicator, with anomaly markers and a moving baseline overlay.
- Trend map (spatial display of rate-of-change across the AOI for indicators with sufficient resolution — primarily Nature pillar).
- Alert panel listing: most recent anomalies, indicators with a worsening trend significant at p<0.05, repeated anomaly clusters.
- Per-pillar trend score cards.
- Anomaly-frequency mini-charts.
- Verbal trend summary paragraph (server-generated).
- **Save as report** button (writes to Saved Analyses *and* creates a report draft for P-11) and **Switch to Screening View** button.

**Outputs produced.**
- `trendResult` object with full time-series, slopes, anomaly stats, and trend versions of all aggregate scores.

**Persistent modules touched.** Saved Analyses, Reports Page, Indicator Library.

**Code reuse.**
- From `Vegetation.js`: time-series inspection logic is the **logic reference** for the trend computation; the Vegetation Evolution GIF generator is a useful precedent for "render evolving raster" but its concrete implementation does not port (Python alternative needed). Point Inspector ports as a click-to-see-time-series feature on the trend map (re-implemented).
- From `AirQuality.js`: time-series inspection adapted across Sentinel-5P bands; same logic reference.
- New: linear-regression / Mann-Kendall trend computation per indicator, alert-rule engine (what counts as a "worsening trend"), verbal-summary generator.

---

## 11. P-07 — Prioritisation — Setup

**Purpose.** Configure a batch analysis across many or all nodes of the supply chain.

**User access.** Both user types.
- *Policy Maker* — selects from the loaded scope. Filters available: industry, region, tier (or by region for custom-uploaded region sets).
- *MNC* — selects from uploaded chain. Filters: tier, region, sector, individual supplier list.

Two-supplier comparison mode is **scrapped for v1** per `Wireframes_All_v3.md` P-07 — modes are *Whole supply chain* and *Filtered subset* only. It may return as a future extension.

In both cases, the radius is **fixed across all nodes** (this is the key constraint that makes the prioritisation comparable; the Stakeholders table specifies "fixed radius around each node"). **A hard cap of 30 nodes per run applies for the demo** to keep satellite compute manageable.

**Decision supported.** Pre-Prioritisation.

**Inputs received.** `supplyChain`, `userType`.

**Indicator computations.** None until Run. At setup time:
- Filter `supplyChain.nodes` to selected subset.
- Compute the AOI per node from the fixed radius.
- Estimate compute time and warn if the node count × indicator count is high.

**UI components.**
- Mode toggle: *Whole supply chain* / *Filtered subset*.
- Filter panel matching the selected mode.
- Fixed radius selector — same six-option set as P-04 (1, 5, 10, 25, 50, 100 km) but applied to all nodes; tooltip explains why this is locked-in.
- Time range selector.
- Indicator selection block. Same panel as P-04, but the v1 **"prioritisation defaults" preset** selects: the three pillar Follow-Up Priority Scores (Air, GHG, Nature) **plus the single highest-contributing single value per pillar** (i.e. four picks per pillar = 12 indicators). The user can adjust the selection after the preset loads. A "Reset to prioritisation defaults" link is provided.
- Selected-nodes preview list with map markers.
- Estimated compute time and node-count indicator with a **hard cap of 30 nodes** for the demo build.
- "Run Prioritisation" button. (Save Configuration is scrapped per Wireframes v3 — saving happens on the result page via "Save as report".)

**Outputs produced.**
- `prioritisationConfig` object: `{nodes: [...], radius, timeRange, selectedIndicators, mode}`. Mode is one of `whole_chain` or `filtered_subset`.

**Persistent modules touched.** Indicator Library.

**Code reuse.**
- New: batch-job orchestration, per-node circular-buffer AOI generation. The per-node AOI is the same point-plus-radius construction as P-04 applied in batch.

---

## 12. P-08 — Prioritisation — Results

**Purpose.** Rank and visualise nodes by overall audit priority so the user knows which to follow up on first. The same underlying result drives two visualisation options on this page, toggled by the user.

**User access.** Both user types, with divergent framing strings only:
- *Policy Maker* — labelled **Regional Environmental Audit Priority Score**; presented as a ranked list of regions / suppliers and a risk matrix.
- *MNC* — labelled **Supplier Environmental Audit Priority Score**; presented as a ranked list of suppliers and a risk matrix.

**Decision supported.** Prioritisation.

**Inputs received.** `prioritisationConfig` from P-07.

**Indicator computations.** Per node, compute the **trend-aware Follow-Up Priority Score for each pillar** (i.e. the same aggregates as P-06), the composite, and the per-node confidence (minimum of pillar confidences). Then:

- Severity = the node's composite Follow-Up Priority Score.
- Recurrence = anomaly frequency over the time range.
- Affected area = hectares within the AOI flagged as anomalous (Air / GHG) or converted (Nature).
- Data confidence = composite of the three pillar confidence scores.
- Rank order over the node set.
- Percentile placement.

The computations are run once and feed both visualisation modes; the page never re-computes when the user toggles between Ranking table and Risk matrix.

**UI components.**

*Shared (always visible):*
- Header card: scope summary (e.g. "12 suppliers in EV battery chain, 5 km radius, last 3 years"), computation timestamp.
- **View-mode toggle:** *Ranking table* (default) / *Risk matrix*. Sits at the top of the results area; toggling re-renders without re-running.
- **Save as report** button (writes to Saved Analyses *and* creates a report draft for P-11) and Export buttons (CSV in Ranking table view; image in Risk matrix view).

*Ranking table view (default):*
- Sortable, filterable table:
  - Columns: Rank, Node name, Composite priority score, Air score, GHG score, Nature score, Confidence, Trend arrow (↑ worsening / → stable / ↓ improving), Affected area (ha), Recurrence.
  - Each row is a clickable drill-down → P-05 / P-06 for that node.
- **Top-N highlight banner — default top 5** with a control to change.
- Filters on the table (by tier, region, score band).
- Export table button (CSV).

*Risk matrix view:*
- 2-D scatter plot:
  - **Axes are two of the three pillar Follow-Up Priority Scores (user-selectable).** Default: x = Air Pollution, y = Nature. A pillar-pair toggle lets the user swap to Air × GHG or GHG × Nature.
  - Each point = a node. **Point size = composite priority score**; point colour = traffic-light band on the composite.
  - **Quadrant lines sit at the median of each pillar score across the result set.** Quadrant labels are pillar-based: top-right *Worst across both pillars*; top-left *Worst in {y} pillar*; bottom-right *Worst in {x} pillar*; bottom-left *Low concern*. Labels are rendered in the empty corners.
- Hover tooltip with node name and key scores; click → drill into P-05.
- Side mini-table of nodes in the "Worst across both pillars" quadrant.
- Export-as-image button.

Retry-failed-nodes is **deferred to a future extension**; in the demo, partial results are accepted as-is and the user can re-run from P-07 if they want another attempt.

**Outputs produced.**
- `prioritisationResult` containing the ordered node list, all per-node score sets, and the composite confidence. (Renamed from v2's `rankingResult` — one result object feeds both views.)

**Persistent modules touched.** Saved Analyses, Reports Page, Indicator Library.

**Code reuse.**
- The per-node computations are batch invocations of the same indicator engine functions used in P-05 and P-06 (logic refs from `Vegetation.js` and `AirQuality.js`); no new computation logic, just batching and aggregation.
- New: ranking table UI, risk-matrix scatter plot with pillar-pair selector, top-N highlight rule. The scatter plot in particular requires charting capability in the new Python + separate map environment — the existing GEE UI could not host this.

---

## 13. P-09 — Indicator Library (persistent)

**Purpose.** Reference catalogue of every indicator the tool can compute.

**User access.** All authenticated users. Content is identical for both user types — the framing varies in the workflow pages, not in the library itself.

**Decision supported.** None directly; supports interpretability of every other page.

**Inputs received.** None.

**Indicator computations.** None.

**UI components.**
- Top-level pillar tabs: **Air Pollution**, **GHG Emissions**, **Nature/Land**.
- Within each tab, three sub-sections: *Single values*, *Component scores*, *Decision aggregates*.
- Per indicator card showing:
  - Name and definition (names per `Indicators_Computation_v3.md`).
  - Formula (where applicable; rendered via MathJax/KaTeX).
  - Data source (Earth Engine asset ID, from `GEE_Database_List_v3.md`).
  - Temporal frequency.
  - Spatial resolution.
  - ESG / regulatory alignment (e.g. ESRS E1 / E2 / E4, GRI 305, TNFD).
  - Decision relevance (which of Screening / Monitoring / Prioritisation / Reporting it informs).
  - Limitations and confidence considerations.
- Filter by usefulness criteria (the ten-criterion scorecard from Tier 3 of the indicator research).
- **"Active in current workflow" toggle — visual indicator only**, mirroring the indicator selection state of the open workflow (when one exists). It dims indicators not in the active selection but **does not let the user edit selections from this page**. Per `Wireframes_All_v3.md` P-09, the library is reference-only — there is no "Add to workflow" or "Open in workflow" shortcut. A per-indicator "Open in workflow" shortcut may return as a future extension.
- Search bar.

**Outputs produced.** None — the library is reference-only. No state changes propagate to other pages.

**Persistent modules touched.** This *is* a persistent module; reads selection state from the active workflow for the dimming behaviour.

**Code reuse.** New — this is content drawn directly from `Indicators_Computation_v3.md` and the Indicator Library entries in `Final Indicators List.pdf`, rendered as a structured reference UI. The content is static enough that it should live as a JSON manifest the front-end reads, with each entry referencing the function in the indicator engine that computes it.

---

## 14. P-10 — Saved Analyses (persistent)

**Purpose.** List of saved analyses with the ability to open each one back into its workflow page.

**User access.** Each user sees only their own saves (browser-state-only in the demo build; per-user persistent store post-auth).

**Decision supported.** Indirect — enables Reporting (Reports pull from saved analyses).

**Inputs received.** None directly; loads the user's saved-analysis index on session start.

**Indicator computations.** None on the index page; opening a saved analysis re-hydrates its result into the corresponding workflow page without re-running compute.

**Demo scope.** This page is deliberately minimal for the demo per `Wireframes_All_v3.md` P-10: list + open + delete only. Bulk-select with side-by-side compare, tags / labels, search, and "Add to report" from this page are all deferred to future extensions.

**UI components.**
- Analyses table — columns: Name, Type (screening / monitoring / prioritisation), Scope, Date saved.
- Per-row actions: Open, Delete (with confirmation dialog).
- Empty-state placeholder when the list is empty (explains how to save: via "Save as report" on P-05/P-06/P-08).
- Demo-mode banner warning that saves are held in browser state only and will clear if browser storage clears.

**Outputs produced.** When a saved analysis is opened, its result object is loaded into the corresponding workflow page (P-05, P-06, or P-08) so the page can render its results state directly (no recompute).

**Persistent modules touched.** Reports Page (the "Save as report" action on the result pages writes here *and* creates a report draft simultaneously).

**Code reuse.** New.

---

## 15. P-11 — Reports Page (persistent)

**Purpose.** Build, customise and export automatic reports from saved analyses.

**User access.** Both user types. Reached either from the persistent nav or from a "Save as report" action on P-05 / P-06 / P-08 (which both writes to Saved Analyses *and* pre-populates a report draft on this page). The available report templates differ by user type and decision context, per the Stakeholders summary:

| User type | Source decision | Report template |
|---|---|---|
| Policy Maker | Screening | Regional screening report |
| Policy Maker | Monitoring | Periodic monitoring report |
| Policy Maker | Prioritisation | Policy prioritisation report |
| Policy Maker | Reporting | Policy audit report |
| MNC | Screening | Supplier screening report |
| MNC | Monitoring | Supplier monitoring report |
| MNC | Prioritisation | Supplier prioritisation report |
| MNC | Reporting | ESG / due-diligence report |

**Reporting-decision template content (Policy audit report and ESG / due-diligence report).** These two templates are structurally identical and differ only in framing, header content, and user-context labels (region-centric vs supplier-centric). Both render **a comprehensive summary of every indicator available in the Screening view (P-05)** for the chosen target(s):

- All Air Pollution single values (NO₂, SO₂, CO, CH₄, HCHO, O₃, AAI, PM₂.₅ proxy) — site mean, background median, absolute anomaly, normalised z, hotspot frequency, confidence.
- The Air Pollution Proxy Score and the Air Pollution Audit Follow-Up Priority Score, with the contribution breakdown.
- All GHG component scores actually computed in v1 — `CO₂_Context`, `CH₄_Context_Adjusted` (the fire-downweighted hotspot signal), `Combustion_Proxy`, `Activity_Score` — the Core GHG Audit-Support Score (rescaled v1 form), the GHG Data Quality & Attribution Confidence Score, and the GHG Audit Follow-Up Priority Score. `High_GWP_Sector_Risk`, `Wind_Consistency` and `Sector_Match` are not in v1 and the templates carry an explanatory footnote rather than placeholder slots.
- All Nature single values (current land-cover composition, biodiversity exposure, NDVI condition, habitat conversion, bare-ground expansion, built-up expansion, water/flooded-vegetation exposure, restoration signal) and the Nature Follow-Up Priority Score with its quality-attribution counterpart.
- The Overall Screening Score (composite of the three pillar Follow-Up Priority Scores).
- For every value: confidence score, AOI metadata (centre, radius, area), dataset provenance (Earth Engine asset IDs and the actual data dates used), and computation timestamp.
- The verbal summary paragraph from the Screening view, plus a per-pillar interpretation block.

The two templates differ only in framing strings — the Policy audit report is region-centric ("Region X"), the ESG / due-diligence report is supplier-centric ("Supplier X"). Same data, same structure.

**Source-analysis handling.** The user picks one or more saved screening analyses as the source. If the source analysis did not have every indicator selected, missing ones appear in the report marked "not computed" with a one-click **"Run comprehensive screening for this target"** shortcut. The shortcut routes to P-04 with:
- All indicators pre-selected (already the P-04 default).
- Centre pre-filled from the source analysis's `centreMetadata`.
- **Radius = 5 km** (facility-level, the P-04 single-supplier default per `Indicators_Computation_v3.md` §6.2).
- **Mode = screening** (so the time-range selector is hidden per H4; the screening composite is the latest valid 90 days for each dataset).

The user can still adjust radius or switch to trend mode on P-04 before running; the defaults match the most common audit pattern.

**Other templates (Screening / Monitoring / Prioritisation reports).** These render only the indicators that were selected in their source analysis — they are not comprehensive coverage. They map directly to the source view (P-05 / P-06 / P-08) rendered to PDF, with user notes appended.

**Decision supported.** Reporting.

**Inputs received.**
- One or more entries from Saved Analyses.
- `userType` (filters templates).
- Selected template.
- Optional user-added notes.

**Indicator computations.** None new — reports render already-computed results. The audit / ESG templates may surface "not computed" placeholders when their source screening was partial.

**UI components.**
- Template selector (filtered by `userType`; only the four templates for the current user are visible).
- Source-analysis selector (multi-select from Saved Analyses).
- Coverage indicator showing what fraction of the screening indicator set is present in the chosen source (only displayed for audit / ESG templates).
- "Run comprehensive screening" shortcut when coverage is incomplete (audit / ESG templates only).
- Report preview pane showing the rendered report.
- Editing controls: report title, user notes, optional section toggles. (The depth of customisation is still TBD per the open questions; the v1 build will support title + notes + a small set of section toggles, and grow from there.)
- KPI table block (mandatory for the ESG / due-diligence template per the Stakeholders summary's "Report builder + KPI table" requirement).
- Export buttons: PDF (primary), CSV of underlying data, JSON export of the full result objects for downstream tools.

**Export schema.** CSV column headers and JSON keys both use the canonical indicator IDs from `Indicator_ID_Schema_v1.md` §6. CSV applies the `.` → `__` substitution from §7 (e.g. `air.no2.site` → `air__no2__site`) for tools that disallow dots in column names; the substitution is reversible. JSON exports use the IDs directly. The full output shape is the result-payload example in `Indicator_ID_Schema_v1.md` §6, with a `provenance` block alongside the indicator values.

**Outputs produced.** Generated PDF report; optionally a CSV/JSON sidecar.

**Persistent modules touched.** Saved Analyses (source).

**Code reuse.** New. Reporting is not present in the current GEE codebase. A Python-side templating pipeline (e.g. Jinja → HTML → PDF via WeasyPrint, or a similar stack) is the natural fit and aligns with the v2 decision to move to Python.

---

## 16. Appendix A — User flow diagrams (per user type)

**Policy Maker journey (default).**
P-01 (pick "Policy Maker") → P-02 (connect to GSCO supply chain catalogue, select an industry) → P-03 → choose Inspect → P-04 → run Screening → P-05 → Save as report → P-11 (regional screening report). Periodically: P-03 → Inspect → P-06 → Save as report → P-11 (periodic monitoring report). Quarterly: P-03 → Prioritisation → P-07 → P-08 (toggle between Ranking and Risk matrix views) → Save as report → P-11 (policy prioritisation report). Annually for audit: P-03 → Inspect → P-04 (all indicators selected — the default) → P-05 → Save as report → P-11 (Policy audit report).

**Policy Maker journey (custom region upload).**
Same as above, except P-02 uses the upload path rather than the GSCO catalogue.

**MNC journey.**
P-01 (pick "MNC") → P-02 (upload supplier list) → P-03 → choose Inspect → P-04 (pick a specific supplier) → P-05 (supplier screening) → Save as report → P-11 (supplier screening report). For ongoing visibility: P-06 (supplier monitoring) feeds the alert panel and the supplier monitoring report. For audit prep: P-07 (whole chain or filtered tier) → P-08 (toggle between Ranking and Risk matrix views) → Save as report → P-11 (supplier prioritisation report). For ESG reporting: P-03 → Inspect → P-04 (all indicators selected — the default) → P-05 → Save as report → P-11 (ESG / due-diligence report).

## 17. Appendix B — Indicator engine module map

The back-end indicator engine has three modules, one per pillar, each exposing functions consumed by the UI pages. **`Indicators_Computation_v3.md` is the authoritative source for all indicator names, formulas, weights, units, and the canonical indicator IDs used in `selectedIndicators` and in result payloads.** This appendix lists the function surface only; for the exact return-field names and their definitions, the implementer should refer to Indicators_Computation §1, §2 and §3.

**Module: Air Pollution.**
- `compute_pollutant_snapshot(aoi, pollutant, date) → {site, background, anomaly, z, hotspot_freq, confidence}` — implements the repeatable core method (Indicators_Computation §0.2) for any Sentinel-5P band.
- `compute_pm25_proxy(aoi, date_range) → {mean, anomaly, trend, quality}` — CAMS NRT (Indicators_Computation §1.1).
- `compute_sub_aggregates(scores) → {industrial_combustion_proxy, heavy_industry_score, voc_photochemical, smoke_dust_regional_transport, industrial_air_pollution_burden, pm_or_aerosol}` — Indicators_Computation §1.2.
- `compute_air_pollution_proxy_score(scores) → score` — Indicators_Computation §1.3.
- `compute_air_audit_followup_priority(proxy, anomaly, trend, confidence) → score` — Indicators_Computation §1.3.

**Module: GHG.**
- `compute_ch4_context_adjusted(aoi, date_range) → score` — Indicators_Computation §2.2, includes the Fire/Regional Transport downweight (§7.3).
- `compute_co2_context(aoi, date_range) → score` — ODIAC; vintage-lag flag in result.
- `compute_combustion_proxy(aoi, date_range) → score` — reuses NO₂, CO from the Air module.
- `compute_activity_score(aoi, date_range) → score` — VIIRS nighttime lights.
- `compute_core_ghg_audit_support(...) → score` — Indicators_Computation §2.3 (rescaled v1 form).
- `compute_ghg_data_quality_attribution(...) → score` — Indicators_Computation §2.3 (rescaled v1 form; `Wind_Consistency` and `Sector_Match` deferred).
- `compute_ghg_audit_followup_priority(...) → score`.

**Module: Nature.**
- `compute_current_land_cover(aoi, date) → {class_areas, class_percents, dominant_class, class_confidence}` — Dynamic World.
- `compute_biodiversity_exposure(aoi) → {dist_to_kba_km, overlap_ha, overlap_pct, kba_score}` — Indicators_Computation §3.1, §3.2.
- `compute_ndvi_condition(aoi, date_range) → {ndvi_mean, ndvi_anomaly, ndvi_slope, ndvi_p, low_ndvi_ha, low_ndvi_pct}`.
- `compute_habitat_conversion(aoi, baseline_date, current_date) → {natural_loss_ha, nat_to_built_ha, nat_to_bare_ha, nat_to_crop_ha, built_expansion_ha, annualised_rate, score}` — Indicators_Computation §3.1, §3.2 (with the calibration note on saturation point).
- `compute_bare_ground_expansion(...)`, `compute_built_up_expansion(...)`, `compute_water_exposure(...)`, `compute_restoration_signal(...)`.
- `compute_supplier_spatial_link(aoi, change_mask, supplier_point) → score` — Indicators_Computation §7.5.
- `compute_external_driver_screening(aoi, ...) → score` — Indicators_Computation §7.5.
- `compute_nature_quality_attribution(...) → score` — Indicators_Computation §3.3.
- `compute_nature_followup_priority(...) → score`.

**Cross-module composite.**
- `compute_overall_screening_score(air_priority, ghg_priority, nature_priority) → {composite, limiting_confidence}` — composite via the equal ⅓ weighting (Indicators_Computation §4); `limiting_confidence = min(air_conf, ghg_conf, nature_conf)`.

## 18. Appendix C — Persistent state model

In the demo build, "persistent user store" means browser-state-only (e.g. localStorage). When authentication is added (Wireframes Appendix A), the same contract is backed by a real per-user store.

| Key | Scope | Lives in | Set by | Read by |
|---|---|---|---|---|
| `userType` | session | session store | P-01 | every page |
| `supplyChain` | session | session store + Saved Analyses | P-02 | P-03, P-04, P-07 |
| `aoi` | workflow-scoped | session store | P-04 (point + radius) | P-05, P-06 |
| `selectedIndicators` | workflow-scoped | session store | P-04, P-07 | P-05, P-06, P-08 |
| `analysisMode` | workflow-scoped | session store | P-04 | P-05, P-06 |
| `prioritisationConfig` | workflow-scoped | session store | P-07 | P-08 |
| `screeningResult`, `trendResult`, `prioritisationResult` | per analysis | session store + Saved Analyses + Report draft on Save-as-report | P-05, P-06, P-08 | P-11 |
| `savedAnalyses` | per user | browser-state-only in demo; per-user store post-auth | P-05, P-06, P-08 (on save), P-02 (on save scope) | P-10, P-11 |

## 19. Open questions — status after v3

| # | Question | Status |
|---|---|---|
| 1 | Composite weights — equal ⅓ vs sector-aware? | **Closed for v1.** Equal ⅓ across the three pillar Follow-Up Priority scores. Sector-aware weighting recorded as a future extension (per-sector weight vectors resolved from `node.sector`). |
| 2 | GSCO catalogue API — what does the existing GSCO supply-chain platform expose for the Policy Maker connection in P-02? | **Deferred — to review later.** P-02 is built to support both connection and upload, so the upload path is fully functional regardless of the catalogue connection's status. |
| 3 | Two-supplier comparison — also offered in Inspect? | **Closed.** Scrapped from v1 entirely per `Wireframes_All_v3.md` P-07. Modes are *Whole supply chain* and *Filtered subset* only. May return in a future extension on the Prioritisation flow. |
| 4 | Policy Maker upload path — needed for regional regulators? | **Closed.** Yes. Implemented in P-02. |
| 5 | Report customisation depth — how much editing should the report builder allow? | **Partially resolved.** The two Reporting-decision templates (Policy audit report and ESG / due-diligence report) are now concretely defined as comprehensive screening-indicator summaries — no template-level customisation required. The remaining open question is how much customisation to allow on the *other six* templates (Screening / Monitoring / Prioritisation reports per user type). v1 will offer title + notes + a small set of section toggles; depth grows from there. |
| 6 | Front-end environment — stay in GEE JS or move to Python? | **Closed.** Moving to Python plus a separate map environment. Code-reuse expectations updated throughout the spec; the GEE JS files become logic references rather than direct ports. |

## 20. Appendix D — Code reuse summary by source file

The decision to move to Python plus a separate map environment changes what "reuse" means. The existing GEE JavaScript files are now **logic references** — they tell us *what* to compute and the patterns that work, but the actual implementation is re-written in the Python Earth Engine API.

| Source file | Reused at | What is reused | Notes |
|---|---|---|---|
| `Inspection.js` | P-02, P-04, P-07 | Lat/lon validation rules. | Marker placement, drawing tools, AOI export, navigation panel — **deferred with the Map / AOI Tools module**. The standalone Inspection page is not in v1. |
| `Vegetation.js` | P-05, P-06, Nature module | NDVI compute pattern (`normalizedDifference`), AOI statistics pattern (`reduceRegion` with combined reducer), point inspector concept, time-series inspection concept, vegetation evolution GIF concept, multi-step accordion guide pattern. | All re-implemented in Python EE API; near-identical call patterns are available. |
| `AirQuality.js` | P-05, P-06, Air module | Sentinel-5P band selection logic, visualisation parameter defaults, gas time-series compute pattern, AOI statistics, multi-step accordion guide pattern. | Same — Python re-implementation. |

The pieces that are genuinely new (no existing code or pattern to reference) are: composite scoring across pillars, traffic-light rendering, ranking and risk-matrix UIs, Saved Analyses, Reports Page, the Indicator Library content browser, the verbal-summary generator, and the user / scope set-up flow. These are all front-end and back-end work in the new Python plus separate-map-environment stack.
