# GSCO Environmental Tool — Project Context for Claude Code

> **Read this file at the start of every session.** It is the source of truth for what this project is, what's been built, and how to make changes safely.

> **Authority pointer (M-V1x-RECONCILE, 22 May 2026).** `docs/Indicators_Audit_and_v1x_Roadmap.md` v1.5 is the master document for **v1.x indicator decisions** — Hansen demotion, ODIAC standing exposure, sector-tag deprecation, column-to-surface framing, the Tier A–F roadmap. When that doc disagrees with anything else in `docs/`, the audit doc wins; flag the disagreement and propose a doc-sync update. Engine code is the second source of truth: if the engine and a non-audit doc disagree, update the doc (per the M-V1x-RECONCILE verification protocol). Do NOT modify the audit doc without explicit confirmation.

## 1. What this project is

A v1 demo of the **GSCO Environmental Monitoring & Decision-Support Platform**: a Python web tool that runs satellite-based environmental screening on a supplier site or region, scoring the result across three pillars (Air Pollution, GHG, Nature/Land), and presenting a traffic-light summary plus drill-down detail. Built for two user types — Policy Makers and MNCs.

The architecture, page-by-page behaviour, indicator formulas, and engine code structure are **already specified in `docs/`** — your job is to implement them, not redesign them.

## 2. Authoritative documents

These documents in `docs/` are the source of truth. Cite them by name when answering questions, and never modify any of them without explicit confirmation.

| Document | Purpose |
|---|---|
| `docs/PLFS_v4.md` | Page-Level Functional Specification — what each page does and produces |
| `docs/Wireframes_All_v4.md` | How each page behaves; UI components; traffic-light + confidence-dot spec (Appendix C) |
| `docs/Indicators_Computation_v4.md` | What each indicator measures; formulas, weights, units, conventions |
| `docs/Indicator_ID_Schema_v2.md` | Canonical IDs for every indicator (used in `selectedIndicators`, result payloads, CSV/JSON exports) |
| `docs/GEE_Database_List_v3.md` | Earth Engine asset IDs and operational notes |
| `docs/Verbal_Summary_Templates_v1.md` | Deterministic prose generator for P-05's verbal summary |
| `docs/Engine_Module_Skeleton_v1.md` | **The implementation blueprint — directory layout, function signatures, orchestrator class structure.** Start here for any new code. |
| `docs/provenance_schema.md` | Canonical provenance schema (M5.6) — every indicator emits an 11-field provenance block via `engine.core.build_provenance`. |

If two documents disagree on a detail, **`Indicators_Computation_v4.md` wins for formulas, `Wireframes_All_v4.md` wins for UI behaviour, `PLFS_v4.md` wins for everything else.** Flag the conflict in chat — don't silently resolve it.

## 3. What's already built

The demo has a working stack and a functional P-01. Don't redo this work.

```
gsco-demo/
├── app.py                          ✅ P-01 Landing — user-type selection, session init, routes to P-02
├── pages/
│   ├── 01_scope_setup.py           ⚠️ P-02 placeholder — renders a Cambridge map to prove the stack
│   └── 99_engine_scratch.py        🧪 Developer scratch — Air pillar debug UI; throwaway when P-05 lands
├── utils/
│   ├── __init__.py
│   ├── state.py                    ✅ init_session / set_user_type / sign_out / require_user_type
│   └── ee_init.py                  ✅ require_earth_engine() — cached, reads EE_PROJECT_ID from env
├── docs/                           ⬅ drop the seven authoritative docs here
├── engine/                         ⏳ empty — milestones 1-6 will fill this (see §6)
├── data/
├── tests/                          ⏳ empty — add pytest tests as you build the engine
├── requirements.txt
└── README.md
```

Two existing files to know about specifically:

- **`utils/state.py`** defines the session contract. The keys currently in use are `user_type`, `user_type_label`, `supply_chain`, `session_id`. New keys for downstream pages (`aoi`, `selected_indicators`, `analysis_mode`, `time_range`, `screening_result`, `trend_result`, `prioritisation_result`, `saved_analyses`) should be added to `init_session()`'s defaults dict, **not** scattered across pages. Follow `docs/PLFS_v4.md` §18 for the full state contract.
- **`utils/ee_init.py`** is how every EE-touching page initialises Earth Engine. The pattern is: `require_user_type()` then `require_earth_engine()` then `import geemap.foliumap as geemap`. Use this pattern on every new result page.

The empty folder `indicators/` from the original layout is being replaced by `engine/` (matching the Engine Module Skeleton). If `indicators/` is still in the repo when you start, rename it to `engine/`.

## 4. Architecture (Option D — stateless modules + thin orchestrator)

The engine layout is in `docs/Engine_Module_Skeleton_v1.md` §1. Summary of what goes into `engine/`:

```
engine/
├── orchestrator.py        ← ScreeningRun, TrendRun, PrioritisationBatch (the only stateful classes)
├── air.py                  ← Air Pollution pillar functions (stateless)
├── ghg.py                  ← GHG pillar functions (stateless)
├── nature.py               ← Nature/Land pillar functions (stateless)
├── core/                   ← reusable building blocks (repeatable core method, buffers, etc.)
├── constants.py            ← all tunable defaults
├── ids.py                  ← canonical indicator IDs as constants
├── verbal_summary.py       ← deterministic prose generator
└── exceptions.py           ← IndicatorComputeError / PillarComputeError
```

Pillar modules are **stateless flat function libraries**. The orchestrator class is the **only stateful class** in the engine. Composite-score logic and partial-failure handling live in the orchestrator.

## 5. Stack and pinned versions

Already in `requirements.txt`. Do not bump pins without testing:

- **Python 3.11** (3.12+ breaks the geospatial stack)
- **streamlit ≥ 1.30**
- **geemap 0.34.4** (pinned — known-compatible with the leafmap/setuptools/ipython triad)
- **earthengine-api ≥ 0.1.380**
- **setuptools < 81** (newer versions remove `pkg_resources` which leafmap needs)
- **ipython < 9** (geemap uses pre-9 IPython API)
- **folium**, **streamlit-folium**, **numpy**, **pandas**, **scipy**, **geopy**

When the engine work starts you'll also need:

- **pytest** (add to `requirements.txt` when starting milestone 1)
- **pyproj** if buffers need a geodetic implementation that EE doesn't cover

## 6. Milestones — current status and next step

> **Status (6 June 2026).** The original build-out is **complete** — all six engine milestones and all UI pages (P-01 → P-11) are built and live. The table below is kept as a record. Current work is v1.x refinement (see `docs/Indicators_Audit_and_v1x_Roadmap.md`), not initial construction. For a journey/benefits overview of the finished tool, see `HANDOFF.md`.

| # | Milestone | Status | Files |
|---|---|---|---|
| 1 | `engine/constants.py` + `engine/ids.py` | ✅ done | `engine/constants.py`, `engine/ids.py` |
| 2 | `engine/core/` subpackage | ✅ done | `engine/core/*` |
| 3 | `engine/air.py` (simplest pillar) | ✅ done | `engine/air.py` |
| 4 | `engine/orchestrator.py::ScreeningRun` | ✅ done | `engine/orchestrator.py` (also `TrendRun`, `PrioritisationBatch`) |
| 5 | `engine/ghg.py` and `engine/nature.py` | ✅ done | `engine/ghg.py`, `engine/nature.py` |
| 6 | `engine/verbal_summary.py` | ✅ done | `engine/verbal_summary.py` |
| UI-A | P-01 Landing | ✅ done | `app.py` (router: `gsco_app.py`) |
| UI-B | P-02 Scope setup (real, not placeholder) | ✅ done | `pages/02_Scope_Setup.py` |
| UI-C | P-03 Workflow Hub | ✅ done | `pages/03_Workflow_Hub.py` |
| UI-D | P-04 Inspect setup | ✅ done | `pages/04_Inspect_Setup.py` |
| UI-E | P-05 Screening results | ✅ done | `pages/05_Screening_Results.py` |
| UI-F → UI-K | P-06 through P-11 | ✅ done | `pages/06_*` … `pages/11_*` |

All engine and UI milestones have shipped. Remaining work is v1.x indicator refinement and the genuine deferred stubs: P-07 country-database mode, and P-11 ESRS datapoint codes + policy/action/target sub-sections (see the reconciliation banner in `docs/PLFS_v4.md`).

## 7. Conventions

**Indicator names.** Every indicator value uses the canonical IDs from `docs/Indicator_ID_Schema_v2.md` §6. If a new indicator is introduced, add it to the schema doc first (ask before doing this).

**Formulas.** Every formula is in `docs/Indicators_Computation_v4.md`. Never copy a formula into code without a `# Indicators_Computation §X.Y` comment referencing the source.

**Constants.** Every tunable lives in `engine/constants.py`. Hard-coded magic numbers in pillar code are a smell — call it out and move to `constants.py`.

**Pillar order.** Always `air → ghg → nature → composite`. The UI assumes this, the verbal summary assumes this, the CSV exports assume this.

**Scoring grammars differ by pillar — do NOT harmonise.** The pillars deliberately use different scoring grammars because they ask different physical questions. The Air indicators (and the per-indicator severity tiles for most others) use the repeatable-core **z-score anomaly** grammar (transient event vs. the regional baseline). The **GHG VIIRS** term uses a **persistence-weighted ring-relative sustained-contrast** grammar (M-GHG-REDESIGN-A1) — sustained activity *stock*, not a transient anomaly — and is intentionally NOT routed through `six_step`; it has its own `engine.ghg.compute_viirs_sustained_contrast` and a `score_band` severity grammar. Cross-pillar normalisation consistency is **not** a goal. See `Indicators_Computation_v4.md §2.2a`. Don't "unify" VIIRS back onto the z-score path.

**Errors.** Use the exception hierarchy in `engine/exceptions.py` — `IndicatorComputeError` for single-indicator failures, `PillarComputeError` for non-recoverable pillar failures. The orchestrator catches `PillarComputeError` to render the partial-result UI (Wireframes P-05 S2_Partial).

**No silent defaults.** If a value is missing in a payload, mark it `None` and surface it in the failures list — do not substitute a default.

**Session state contract.** Add new state keys to `utils/state.py::init_session()` defaults, not scattered across pages. The full key list is in `docs/PLFS_v4.md` §18.

**Streamlit page rules.** `st.set_page_config()` must be the **first** `st.*` call on a page. Guards like `require_user_type()` that may call `st.warning` / `st.stop` must come **after** `set_page_config`. EE init (`require_earth_engine()`) is fine before page config because it doesn't call `st.*` on the happy path, but the safest order is: imports → `set_page_config` → guards → EE init → other imports that depend on EE.

**Streamlit page numbering.** Streamlit auto-orders pages alphabetically by filename. Use `01_`, `02_`, etc. to control the sidebar order. The P-number from the wireframes is **not** the same as the Streamlit page number — keep a mapping in the file's docstring.

**Tests first for the engine.** The pillar modules have no GEE side effects in synthetic-payload tests — test the formulas before testing the EE integration. See `docs/Engine_Module_Skeleton_v1.md` §8.

**Provenance (M5.6).** Every single-value indicator emits a `_provenance.<pillar>.<indicator>` block constructed via `engine.core.build_provenance(...)` — never inline as an ad-hoc dict. The canonical 11-field schema, the five `data_type` categories, and the `extra` escape-hatch policy live in `docs/provenance_schema.md`. New indicators must populate `data_type` and `data_source` on the indicator's config dataclass; the snapshot function then threads those through `build_provenance`. Strict validation: `build_provenance` raises `ValueError` for unknown `data_type` / `observations.unit` values at construction time.

## 8. Things to NOT do

- **Do not modify any file in `docs/` without explicit confirmation.** Those are authoritative inputs.
- **Do not invent indicator names.** Use `docs/Indicator_ID_Schema_v2.md`.
- **Do not invent formulas.** Use `docs/Indicators_Computation_v4.md`.
- **Do not hard-code numeric thresholds in pillar code.** They go in `engine/constants.py`.
- **Do not introduce LLM calls for the verbal summary.** The generator is deterministic and rule-based per `docs/Verbal_Summary_Templates_v1.md`.
- **Do not bump pinned versions in `requirements.txt`** without testing the full stack. The README documents which pins exist and why.
- **Do not replace `utils/ee_init.py`** with an inline `ee.Initialize()` — every page must go through the cached helper so EE init runs only once per Streamlit process.
- **Do not introduce a new map library.** Use `geemap.foliumap` for all pages that touch Earth Engine. For v1, standardise on `geemap.foliumap` everywhere (the README mentions a leafmap fallback but it isn't used).
- **Do not skip tests when adding a new `compute_*` function.** Synthetic-payload tests are cheap; write them first.

## 9. When you're unsure

Stop and ask. Specifically:

- If a doc says one thing and the existing code does another → flag both and ask which wins.
- If you need a constant that isn't in `constants.py` → propose the constant name, value, and source-doc reference; wait for confirmation.
- If a UI behaviour isn't in the Wireframes → flag it as an open design choice; do not invent.
- If a formula would require sub-aggregates marked "deferred to v1.x" in `Indicators_Computation_v4.md` §1.2 → omit them and rescale weights per §7.1.

## 10. Useful one-shot prompts

These are the prompts that match the structured docs well:

- **Milestone 1:** *"Implement milestone 1 (`engine/constants.py` and `engine/ids.py`) from `docs/Engine_Module_Skeleton_v1.md` §5 and `docs/Indicator_ID_Schema_v2.md`. Add pytest to requirements.txt and write a smoke test that imports both modules cleanly."*

- **Milestone 2:** *"Implement `engine/core/repeatable_core.py` per `docs/Indicators_Computation_v4.md` §0.2 and `docs/Engine_Module_Skeleton_v1.md` §4.1. Use the constants from `engine/constants.py`. Write synthetic-payload tests."*

- **Milestone 3:** *"Implement `engine/air.py` per `docs/Engine_Module_Skeleton_v1.md` §2.1 and `docs/Indicators_Computation_v4.md` §1. Use the repeatable core method from `engine/core/`. Wire it into a tiny smoke test against a known clean rural point (e.g. mid-Atlantic Ocean) to confirm the EE path works."*

- **UI-B (P-02 real scope setup):** *"Replace the placeholder in `pages/01_scope_setup.py` with the real P-02 implementation per `docs/Wireframes_All_v4.md` §P-02 and `docs/PLFS_v4.md` §6. Implement the upload path first (CSV with `node_name`, `lat`, `lon`); leave the GSCO-catalogue mode as a stub."*

- **Bug fixes:** *"In `pages/01_scope_setup.py`, remove the duplicate `require_user_type()` call and move `st.set_page_config()` to immediately after imports. Update README to reference `PLFS_v4.md` and `Wireframes_All_v4.md` instead of v3."*

---

*Last reviewed: 31 May 2026 (M-GHG-REDESIGN-A1). If the doc set evolves (new versions of PLFS, Wireframes, etc.), update §2 of this file before starting work against the new versions.*
