# 9.0 Platform and Visualisation Design

*This chapter shows how the indicator engine of Section 8 is surfaced to a user: the page-by-page workflow, the screening and trend result views, the batch prioritisation surface, the report export, and the visual alignment with the parent platform. It is illustrated throughout by a single supplier — the **Carajás iron-ore mine** (Brazil, Pará; −6.06, −50.16) — carried from set-up to export, the same Nature-led site introduced in Section 7 (Table 7.4, Figure 7.4a).*

---

## 9.1 Workflow and site architecture

The tool is organised as a single linear spine that opens onto two analysis branches and three persistent modules, realising the four decisions the tool must support — screening, monitoring, prioritisation, and reporting — set out in Section 5.2. A user lands and picks a type (P-01), fixes a scope (P-02), and arrives at the Workflow Hub (P-03), which routes to the **Inspect** branch (single-site screening, P-04 → P-05, with per-indicator monitoring drilling down to P-06) or the **Prioritisation** branch (batch screening, P-07 → P-08). Every result view writes into the persistent modules — Saved Analyses (P-10) and Reports (P-11) — so an analysis can be re-opened or exported without recomputation, while the Indicator Library (P-09) is a reference surface reachable from any page. The page graph and its branch points are shown in Figure 9.1a; the entry point (P-01) and the branch point (P-03) are in Figures 9.1b–9.1c.

**[Figure 9.1a: GSCO tool workflow and page structure — landing/user-type → scope set-up → Workflow Hub → Inspect and Prioritisation branches with their result views → persistent save modules. Author diagram (`GSCO_Section9_Diagrams.pptx`, slide 1).]**

**[Figure 9.1b: P-01 Landing — user-type selection (Policy Maker / MNC). Author screenshot (`fig_01_landing_usertype.png`).]**

**[Figure 9.1c: P-03 Workflow Hub — the branch point, showing the two workflows (Inspect, Prioritisation) and three persistent modules under the loaded scope. Author screenshot (`fig_03_workflow_hub.png`).]**

---

## 9.2 Set-up

Set-up is scope-aware: the Inspect — Setup page (P-04) exposes the centre as three tabs — a **Supplier node dropdown** when a supply chain is loaded, a **locked region AOI** in the policy-maker region mode, and **free coordinates** for any point — over a fixed six-stop buffer radius (1 / 5 / 10 / 25 / 50 / 100 km, defaulting to 5 km for a single site) and the canonical nineteen indicators pre-selected. Screening always runs against the most recent **90-day** composite, so the time-range selector stays hidden on this path and surfaces only when a trend is configured. Carajás is screened here through the free-coordinates tab at a 5 km buffer, matching the Section 7 sweep (Figures 9.2a–9.2c).

**[Figure 9.2a: P-02 Scope Setup — MNC mode picker (demo supply chain / no scope). Author screenshot (`fig_02a_scope_setup_mode.png`).]**

**[Figure 9.2b: P-04 Inspect — Setup in node-dropdown mode (supplier list, six-stop radius slider, 19 indicators grouped by pillar, 90-day window). Author screenshot (`fig_04a_inspect_setup_node.png`).]**

**[Figure 9.2c: P-04 Inspect — Setup, free-coordinates tab configuring Carajás (−6.06, −50.16), 5 km buffer. Author screenshot (`fig_04b_inspect_setup_carajas_freecoords.png`).]**

**[Figure 9.2d: P-04 Inspect — Setup, locked region AOI (policy-maker mode) — Pará, Brazil, centroid −3.99/−53.09, representative buffer capped at 400 km. Author screenshot (`fig_04c_inspect_setup_region_locked.png`).]**

---

## 9.3 Screening

The Screening Results page (P-05) presents the run as a stack of panels; for Carajás the live run reproduces the Section 7 result exactly — composite **0.30 (Low)**, pillar follow-up priorities Air 0.15 / GHG 0.16 / **Nature 0.60 (Moderate)**.

- **Analysis header, partial-coverage banner, traffic-light summary and indicator snapshot** (Figure 9.3a). The header records location, source, buffer, time range, indicator count and computation timestamp; a banner flags that **3 of 19 indicators returned no value** (the coarse-pixel air proxies at a 5 km buffer); the traffic-light row gives the overall composite and the three pillar follow-up priorities as coloured bars with a score to two decimal places and a confidence dot; the snapshot below surfaces the critical per-indicator tiles — for Carajás the **KBA** tile reads High / 0.0 km / **98.81 % buffer overlap** and **NDVI** reads High / −4.7σ.
- **Full per-indicator / KPI grid** (Figure 9.3b). The expanded severity grid (High / Concern / Normal / Sparse), each tile with a confidence dot (●/◐/○) and "view on map →" / "view trend →" links; the two coarse-pixel air proxies show as **Failed** tiles with a "Why?" explainer, illustrating the partial-coverage handling.
- **Map** (Figure 9.3c). A satellite base over the 5 km buffer; selecting the KBA tile renders the Key Biodiversity Area overlap that drives the Nature score (nearest KBA 0.0 km, **98.81 %** overlap) — the same view as Section 7's Figure 7.4a.
- **Per-pillar drill-down** (Figure 9.3d). Each pillar expands to its weighted formula breakdown; the Nature panel shows the 0.30/0.30/0.25/0.20 split across biodiversity exposure, habitat conversion, vegetation condition and measurement quality.
- **Confidence panel, verbal summary and action bar** (Figure 9.3e). The three pillar quality/attribution scores (Air 0.66, GHG 0.96, Nature 0.85 — all High) with their dominant limiting factor; the deterministic, rule-based summary (Section 7; no LLM) reading the result back in prose — *"…moderate exposure … with proximity to Key Biodiversity Areas as the main contributor (99 % of buffer overlaps a Key Biodiversity Area)…"* — above the **Save as report** / Switch-to-Trend action bar.

**[Figure 9.3a: P-05 Screening Results — analysis header, partial-coverage banner, traffic-light + composite, and critical indicator snapshot (Carajás). Author screenshot (`fig_05a_screening_headline.png`).]**

**[Figure 9.3b: P-05 — full per-indicator severity / KPI grid (with Failed tiles + "Why?"). Author screenshot (`fig_05c_kpi_grid.png`).]**

**[Figure 9.3c: P-05 — map, Carajás KBA overlap overlay (0.0 km, 98.81 %). Author screenshot (`fig_05d_map_kba.png`).]**

**[Figure 9.3d: P-05 — Nature/Land pillar drill-down with weighted formula breakdown. Author screenshot (`fig_05e_nature_drilldown.png`).]**

**[Figure 9.3e: P-05 — confidence panel, verbal summary, and action bar. Author screenshot (`fig_05f_confidence_summary.png`).]**

---

## 9.4 Trend

Monitoring is delivered as a per-indicator, on-demand drill-down rather than a separate mode: a tile's "view trend →" link opens the Trend View (P-06), which fits a **Theil–Sen** slope and a **Mann–Kendall** two-sided significance test to that one indicator's series and reports a directional verdict, never an aggregate across indicators (Section 7.10). For the Carajás NDVI series the tool returns a slope of +0.777 yr⁻¹ at **p = 0.806 — "no significant trend"**, with an explicit sub-year-window seasonality caveat (Figure 9.4). The composite and confidence chain are untouched, because a trend is a monitoring finding, not a screening one.

**[Figure 9.4: P-06 Trend View — Carajás NDVI, Theil–Sen line over the daily site series with the Mann–Kendall verdict and seasonality caveat. Author screenshot (`fig_06_trend_ndvi.png`).]**

---

## 9.5 Prioritisation

Prioritisation batch-screens a set of nodes under one common radius (capped at 20 per run) and ranks them by audit priority, here run across the ten Pará/Mato Grosso soy-and-cattle suppliers as a stand-in for the Section 7 cross-supplier sweep. The Setup page (P-07) offers supply-chain, ad-hoc and country-database (v1.x stub) modes over the node list (Figure 9.5a); the Results page (P-08) presents the same run as a **sortable ranked table** and a **risk matrix** scatter — pillar follow-up priority on each axis, point colour by composite band, quadrant lines at the set medians — switchable without recomputation (Figures 9.5b–9.5c). Partial-coverage nodes are carried through and marked rather than dropped.

**[Figure 9.5a: P-07 Prioritisation — Setup (mode tabs, node selection, shared radius, ≤20-node cap). Author screenshot (`fig_07_prioritisation_setup.png`).]**

**[Figure 9.5b: P-08 Prioritisation — Results, ranked table across the supplier set. Author screenshot (`fig_08a_prioritisation_table.png`).]**

**[Figure 9.5c: P-08 Prioritisation — Results, risk-matrix view. Author screenshot (`fig_08b_risk_matrix.png`).]**

---

## 9.6 Reporting

The Reports page (P-11) turns any saved analysis into a structured, exportable record: the user picks a template and source, sees a **live preview**, and exports to **PDF, CSV or JSON** (CSV/JSON carry the full payload keyed by canonical indicator IDs). The two decision templates frame the same content differently — a **policy-audit** report for the policy-maker case and an **ESG / due-diligence** report for the MNC case, mapping the three pillars onto ESRS E2/E1/E4 — and a coverage indicator warns when a partial source does not populate the full indicator set. The Carajás screening saved from P-05 is rebuilt and previewed here (Figures 9.6a–9.6c); ESRS datapoint codes and the policy/action/target sub-sections are honest v1 stubs, deferred to v1.x.

**[Figure 9.6a: P-11 Reports — template choice (ESRS E1/E2/E4 framing) and source selection of the saved Carajás screening. Author screenshot (`fig_11a_report_setup.png`).]**

**[Figure 9.6b: P-11 Reports — live preview of the Carajás report (title page, executive-summary table with composite 0.30 "Low", methodology / ESRS framing). Author screenshot (`fig_11b_report_preview.png`).]**

**[Figure 9.6c: P-11 Reports — export step (PDF primary; CSV 19-row per-indicator table; report-wrapped JSON). Author screenshot (`fig_11c_report_export.png`).]**

---

## 9.7 Alignment with the parent platform *(stretch goal)*

Integration with the parent platform is specified as a **two-way, node-keyed contract** (`GSCO_Screening_Interface_Spec_v1.1`): GSCO sends `node_id` + `latitude`/`longitude` + `name`, the tool returns a `headline` block (composite and per-pillar scores plus a `coverage` flag), `detail` (per-indicator scores + verbal summary) and `provenance`, with the saved result keyed back by `node_id` and **replacing the previous result on re-run**. A map click is a **no-login entry point** that lands directly on Inspect — Setup with coordinates pre-filled, and partial results carry a **mandatory `coverage: "partial"` flag** that the map must render distinctly so a partial composite is never read as complete; the round trip is shown in Figure 9.7. Separately, the Streamlit interface has been **restyled to the parent platform's design tokens** (`ui/theme/`, extracted from `app.cambridge-gsco.co.uk`) — this theming is designed and implemented, whereas the map↔tool data round-trip is designed and specified but not yet wired live.

**[Figure 9.7: Parent-platform integration — node-keyed screening round-trip (GSCO map node → Inspect Setup → ScreeningRun → result back to the map, with the request/response contracts and the partial-coverage flag). Author diagram (`GSCO_Section9_Diagrams.pptx`, slide 2).]**

---

## Figures captured (filename → page / state)

| Figure | File | Page / state |
|---|---|---|
| 9.1a | `GSCO_Section9_Diagrams.pptx` (slide 1) | Workflow / page-structure diagram |
| 9.1b | `fig_01_landing_usertype.png` | P-01 Landing — user-type selection |
| 9.1c | `fig_03_workflow_hub.png` | P-03 Workflow Hub — branch point |
| 9.2a | `fig_02a_scope_setup_mode.png` | P-02 Scope Setup — MNC mode picker |
| (ref) | `fig_02b_scope_preview_supplychain.png` | P-02 Scope Setup — soy supply-chain preview (10 nodes, map + table) |
| 9.2b | `fig_04a_inspect_setup_node.png` | P-04 Inspect Setup — node-dropdown mode (supplier) |
| 9.2c | `fig_04b_inspect_setup_carajas_freecoords.png` | P-04 Inspect Setup — free-coords Carajás |
| 9.2d | `fig_04c_inspect_setup_region_locked.png` | P-04 Inspect Setup — locked region AOI (Pará, policy-maker) |
| 9.3a | `fig_05a_screening_headline.png` | P-05 — header + partial banner + traffic-light + critical snapshot |
| 9.3b | `fig_05c_kpi_grid.png` | P-05 — full per-indicator / KPI grid (Failed tiles + "Why?") |
| 9.3c | `fig_05d_map_kba.png` | P-05 — map, Carajás KBA overlap (98.81 %) |
| 9.3d | `fig_05e_nature_drilldown.png` | P-05 — Nature drill-down (formula breakdown) |
| 9.3e | `fig_05f_confidence_summary.png` | P-05 — confidence panel + verbal summary + action bar |
| 9.4 | `fig_06_trend_ndvi.png` | P-06 Trend View — Carajás NDVI (Theil–Sen + Mann–Kendall) |
| 9.5a | `fig_07_prioritisation_setup.png` | P-07 Prioritisation Setup |
| 9.5b | `fig_08a_prioritisation_table.png` | P-08 Prioritisation Results — ranked table |
| 9.5c | `fig_08b_risk_matrix.png` | P-08 Prioritisation Results — risk matrix |
| 9.6a | `fig_11a_report_setup.png` | P-11 Reports — template + source selection |
| 9.6b | `fig_11b_report_preview.png` | P-11 Reports — live preview of Carajás report |
| 9.6c | `fig_11c_report_export.png` | P-11 Reports — PDF/CSV/JSON export step |
| 9.7 | `GSCO_Sectionq9_Diagrams.pptx` (slide 2) | Interface round-trip diagram |
