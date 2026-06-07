# GSCO Environmental Tool — Handoff Document

**What it is.** A working v1 demo of the **GSCO Environmental Monitoring & Decision-Support Platform**: a Streamlit web tool that runs satellite-based environmental screening on a supplier site or region, scores it across three pillars (Air Pollution, GHG, Nature/Land), and presents a traffic-light verdict with full drill-down. Built for two audiences — **Policy Makers** and **MNCs** (multinational corporations screening their supply chains).

**Status at handoff (6 June 2026).** All 11 pages (P-01 → P-11) are built and live. The engine computes real indicators against Google Earth Engine. The milestone table in `CLAUDE.md §6` is stale — it predates ~40 shipped milestones; treat this document and the code as the current truth.

---

## 1. How to run it

```bash
# Python 3.11 only (3.12+ breaks the geospatial stack)
source .venv/bin/activate
earthengine authenticate                       # one-time
export EE_PROJECT_ID=supply-chain-observatory  # required for any extraction
streamlit run gsco_app.py                       # NOT app.py — gsco_app.py is the router
```

`gsco_app.py` is the entry point: it registers all pages with explicit sidebar labels and applies the global theme. The app opens on the Landing page (P-01). Earth Engine must be authenticated and `EE_PROJECT_ID` set in the same terminal, or result pages will error.

---

## 2. The user journey

The tool is organised as a **landing → scope → hub → workflow → output** flow, with a persistent top navigation on every inner page (Change scope, Workflow Hub, Library, Saved, Reports).

### Step 1 — Landing & role (P-01, `app.py`)
The user picks a role: **Policy Maker** or **MNC**. This is the only "auth" in the demo (sign-in is deferred). The choice shapes scope options and report templates downstream. Two demo Saved Analyses are seeded on first entry so the tool never feels empty.

### Step 2 — Pick a scope (P-02, Scope Setup)
A curated picker, branched by role:
- **MNC** → choose a demo supply chain, or "no scope".
- **Policy Maker** → choose a country / administrative region, or "no scope".

The scope sets the geographic context for everything that follows. (It is *not* a CSV uploader — geocoding happens later, on P-04.) The scope can be changed any time from the top nav.

### Step 3 — Workflow Hub (P-03)
The home base after picking a scope. It offers the two analysis workflows plus the three persistent modules:
- **Inspect** → screen a single site (P-04 → P-05)
- **Prioritisation** → batch-rank many suppliers (P-07 → P-08)
- **Indicator Library** (P-09), **Saved Analyses** (P-10), **Reports** (P-11)

### Step 4a — Inspect: single-site screening (P-04 → P-05)
**Setup (P-04):** pick a centre point (a node from the supply chain, a locked region centroid, or free coordinates via a geocoder), a buffer radius (default 5 km), the indicators to run (all 19 pre-selected; deselect to narrow), and a screening window (default 90 days). Hit **Run Screening**.

**Results (P-05)** — the core experience. While the engine runs, a spinner shows; then the page renders:
- **Headline traffic light** — overall screening verdict (green / amber / red) with a confidence indicator.
- **Per-pillar summary** (Air → GHG → Nature) and a **KPI grid** of every indicator with its own severity tile and confidence dot.
- **Interactive maps** — multi-indicator map (and a single-indicator map in the lean view); click a tile to see it on the map.
- **Drill-downs** per indicator, a **confidence panel** explaining data quality, and a deterministic **plain-language verbal summary** (shown only when the full indicator set was run).
- **Partial-result handling** — if some indicators fail (e.g. sparse satellite coverage), a banner explains what's missing rather than failing the whole run; a dedicated all-failed state gives methodology-aware guidance (smaller buffer, better-covered region, etc.).
- **Action bar** — save the analysis or push it into a report.

The page adapts to the selection: ≥2 indicators → full multi-indicator view; 1 indicator → a lean single-indicator inspection view.

### Step 4b — Trend drill-down (P-06)
From any indicator tile on P-05, "view trend →" opens a per-indicator time-series chart over the screening window. Saved trends re-open from stored data with no recompute.

### Step 5 — Prioritisation: batch screening (P-07 → P-08)
**Setup (P-07):** screen up to **20 suppliers** in one run — from the loaded supply chain's nodes, multiple regions, or a pasted `name, lat, lon` list. Choose a shared radius, indicators, and window. A **Strict audit mode** toggle controls whether sparse-coverage sites fail openly or fall back to climatology.

**Results (P-08):** suppliers are screened sequentially (with live progress and cancel-between-suppliers) and presented two ways:
- **Ranked table** — sortable by Composite or by any single pillar; failed/cancelled sites sink to the bottom. Click a row to drill into that supplier's full P-05 result and back.
- **Risk matrix** — a 3×3 traffic-light scatter with user-selectable axes (any two pillars + Composite), so cross-pillar hotspots (e.g. high Air *and* high Nature) stand out at a glance.

This turns "which of my 20 suppliers do I audit first?" into a defensible, evidence-ranked answer.

### Step 6 — Persistent modules
- **Indicator Library (P-09):** a reference catalogue of every indicator — definition, decision relevance, data source, limitations, and regulatory (ESG) alignment. Searchable, filterable by framework.
- **Saved Analyses (P-10):** list of saved screenings, prioritisations, and trends with open / delete / export-JSON / search.
- **Reports (P-11):** assemble a shareable report from saved analyses — see §4.

---

## 3. What the engine measures (the substance behind the scores)

Three pillars, scored independently then combined. **Pillar order is always Air → GHG → Nature → Composite.**

**Air Pollution** (Sentinel-5P TROPOMI, CAMS, MODIS): NO₂, SO₂, CO, formaldehyde, ozone, absorbing-aerosol index, PM2.5, PM10, aerosol optical depth.

**GHG** (Sentinel-5P, ODIAC, VIIRS nightlights): methane (reference), CO₂ inventory allocation (reference/display), and **VIIRS flaring / sustained-activity** as the live combustion-stock signal. *(Note: GHG deliberately uses a different scoring grammar from Air — sustained activity stock, not a transient anomaly — and is intentionally not unified with the z-score path.)*

**Nature/Land** (Dynamic World, Hansen, MODIS NDVI, KBA vectors): proximity to Key Biodiversity Areas, land-cover composition, habitat conversion, forest loss (standing-exposure reference), NDVI vegetation condition, water/flooded-vegetation exposure, and recovery signals.

**How scoring works.** Most indicators use a **repeatable-core z-score anomaly** method: extract a site value and a surrounding background ring, remove background, compute per-day z-scores against a 3-year baseline, count how often the site is anomalous, and squash that fraction onto a 0–1 severity score. Each indicator also carries a **0–1 confidence** built from data quality, observation count, anomaly strength, and spatial resolution.

Indicators roll up into pillar **follow-up priority** scores (≈80% severity + 20% measurement quality), and the three pillars average into a **Composite Overall Screening** score — but only when all three exist (strict-None; no silent defaults). Composite confidence is the conservative *minimum* across pillars.

**Traffic light:** ≤ 0.33 green, 0.33–0.66 amber, ≥ 0.66 red. **Confidence dots** sit alongside each score to show how trustworthy the data behind it is.

Every indicator emits a full **provenance block** (data source, dates, units, method), so any number on screen can be traced back to its satellite asset and computation.

---

## 4. Reporting & regulatory alignment

The Reports page (P-11) builds export-ready documents from saved analyses, with five templates filtered by role and source type:

| Template | Audience | Scope |
|---|---|---|
| General report | Both | All three pillars (ESRS-framed for MNC; plain for Policy Maker) |
| GHG report (**ESRS E1** — Climate change) | MNC | GHG pillar |
| Air report (**ESRS E2** — Pollution) | MNC | Air pillar |
| Nature report (**ESRS E4** — Biodiversity & ecosystems) | MNC | Nature pillar |
| Supplier cooperation report | Both | One chosen pillar, supplier-facing improvement framing |

Reports group findings under the correct **ESRS** topical headers and are honest about scope — policy/action/target sub-sections render as labelled out-of-scope stubs so the report never overclaims compliance. Exports: **PDF** (primary), **CSV** (flat per-indicator table), and **JSON**.

---

## 5. Main benefits

- **Satellite-based, no ground sensors.** Screen any supplier or region on Earth from coordinates alone — useful exactly where on-the-ground monitoring is weakest.
- **One verdict, fully traceable.** A single traffic-light answer ("audit this site or not") backed by per-indicator drill-down, confidence scoring, and provenance down to the satellite asset and date.
- **Honest about uncertainty.** Confidence dots, partial-result banners, strict-None composites, and "no silent defaults" mean the tool tells you when it doesn't know — rather than guessing.
- **From one site to a whole supply chain.** The same engine powers both a deep single-site inspection and a 20-supplier batch ranked by audit priority and plotted on a cross-pillar risk matrix.
- **Regulator-ready output.** Reports map directly onto ESRS E1/E2/E4 and export to PDF/CSV/JSON for due-diligence and disclosure workflows.
- **Two audiences, one tool.** Policy Makers screen regions and named supply chains; MNCs screen and prioritise their own suppliers — sharing engine, indicators, and reporting.
- **Deterministic & auditable.** Scoring and the verbal summary are rule-based (no LLM in the loop), so the same inputs always produce the same defensible output.

---

## 6. Architecture at a glance

- **`gsco_app.py`** — entry point / page router. **`app.py`** — the Landing page body.
- **`pages/`** — thin page shells (P-02 … P-11); each wires guards, EE init, and delegates rendering to `ui/components/`.
- **`ui/components/`** — all UI logic (the C1–C9 result components, P-02…P-11 forms/renderers, maps, traffic lights, report assembler).
- **`engine/`** — stateless pillar libraries (`air.py`, `ghg.py`, `nature.py`), the stateful `orchestrator.py` (ScreeningRun / TrendRun / PrioritisationBatch), reusable `core/`, and `constants.py` (all tunables).
- **`utils/`** — session state contract (`state.py`) and cached Earth Engine init (`ee_init.py`).
- **`docs/`** — authoritative specs (PLFS, Wireframes, Indicators, ID schema, GEE assets) plus a deep milestone/validation trail.
- **`tests/`** — ~100 pytest files covering engine formulas (synthetic, no EE) and UI component behaviour.

### Known remaining stubs
- P-07 country-supplier-database mode (disabled, v1.x).
- P-11 ESRS per-indicator datapoint codes and policy/action/target sub-sections (labelled out-of-scope).
- Authentication (deferred — role pick only).

---

*For implementation detail, start with `docs/Engine_Module_Skeleton_v1.md` (engine), `docs/Wireframes_All_v4.md` (UI behaviour), and `docs/Indicators_Computation_v4.md` (formulas). The PLFS reconciliation banner (`docs/PLFS_v4.md`, top) lists every behaviour delta since the specs were frozen.*
