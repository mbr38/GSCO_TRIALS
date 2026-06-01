# GSCO — Report Creation: Code Handoff

> **Purpose of this document.** A single, self-contained map of every piece of
> code in `gsco-demo` that produces a *report, export, or summary*. Hand this to
> a design reviewer (e.g. Claude in the browser) so they can reason about the
> report-creation structure without reading the whole codebase. It describes
> **what exists today**, where it lives, what shape the data has, and where the
> seams / open questions are.
>
> Generated 1 June 2026. This is a derived/working doc — it is **not** an
> authoritative spec. Authority for report behaviour still lives in
> `docs/Wireframes_All_v4.md` (§P-05, §P-10, §P-11), `docs/PLFS_v4.md`, and
> `docs/Verbal_Summary_Templates_v1.md`.

---

## 0. TL;DR — the report stack at a glance

There are **three** distinct "output" surfaces, in increasing order of formality:

| Surface | Page | What it produces | Code home |
|---|---|---|---|
| **Verbal summary** | P-05 (C7), P-06, P-11 | 4-paragraph deterministic prose (overview + air/ghg/nature) | `engine/verbal_summary.py` |
| **Saved analysis** | P-05/P-08 → P-10 | A session-persisted record of a screening/prioritisation/trend run | `ui/components/c8_action_bar.py`, `ui/components/p10_list.py` |
| **Report** | P-11 | A multi-source HTML document, exportable to PDF / CSV / JSON | `ui/components/p11_*.py`, `ui/p11_state.py`, `templates/p11/` |

The **report** (P-11) is the thing the user most likely means by "report
creation". It is a 3-state wizard (pick → preview → export) that assembles HTML
from pluggable **section** functions chosen by a **template**, then renders that
HTML to PDF (or sidesteps to CSV/JSON). The verbal summary is *reused inside*
the report, so the two surfaces never disagree on prose.

```
                 ┌─────────────────────────────────────────────────┐
   ScreeningRun  │  payload dict  (engine/orchestrator.py)          │
   .run() ───────▶  air.* / ghg.* / nature.* / composite.* +        │
                 │  _provenance.* + _failures + _meta               │
                 └───────────────┬─────────────────────────────────┘
                                 │
              ┌──────────────────┼─────────────────────────────────┐
              ▼                  ▼                                  ▼
   engine/verbal_summary   C8 "Save as report"            P-11 report builder
   generate_verbal_summary  → saved_analyses[]            (consumes saved_analyses[])
              │                  │                                  │
       P-05 C7 / P-06            └──── P-10 list ──── select ───────┤
              │                                                     │
              └──────────────── reused by ────▶  p11_sections  ─────┤
                                                 (verbal summary       │
                                                  inside pillar_findings)│
                                                                     ▼
                                          p11_assembler → shell.html.j2
                                                     │
                                  ┌──────────────────┼──────────────────┐
                                  ▼                  ▼                  ▼
                            p11_pdf (weasyprint)  p11_csv          p11_json
```

---

## 1. The data contract — what a report consumes

Everything downstream reads one of two shapes.

### 1.1 Screening payload (the unit of analysis)

Produced by `engine.orchestrator.ScreeningRun.run()`. Flat dict keyed by
canonical indicator IDs. Abridged shape (full per-indicator set is 19
indicators):

```python
{
  # Per-pillar follow-up priority (0–1; the "severity" axis)
  "air.audit_followup_priority":   float,
  "ghg.audit_followup_priority":   float,
  "nature.followup_priority":      float,

  # Per-pillar measurement quality / attribution confidence (0–1)
  "air.measurement_quality_score":  float,   # M-ATTRIB-A1
  "ghg.data_quality_attribution":   float,   # M-ATTRIB-A1
  "nature.measurement_quality":     float,

  # Composite
  "composite.overall_screening":    float,
  "composite.confidence":           float,

  # Per-indicator detail (repeats for all 19)
  "air.no2.score":  float, "air.no2.site": float, "air.no2.z": float,
  "air.no2.anomaly": float, "air.no2.confidence": float,

  # Provenance, one block per indicator (see §5)
  "_provenance.air.no2": { ...11-field block... },

  "_meta":     {"computed_at": ISO8601},
  "_failures": {"air.no2": "reason", ...},   # skipped/failed indicators
}
```

> The **priority** and **confidence** keys are bucketed by the same tertile
> thresholds (`TRAFFIC_LIGHT_THRESHOLDS = 0.33 / 0.66`) the traffic-light chips
> use, so prose and chip colour never disagree.

### 1.2 Saved-analysis entry (the report source)

A "source" the report builder selects from. Lives in
`st.session_state["saved_analyses"]` (a list). Written by C8
([`c8_action_bar.py:82`](../ui/components/c8_action_bar.py#L82)):

```python
{
  "id":              str(uuid4),
  "name":            str,        # human-readable, built by _build_save_name
  "type":            "screening" | "prioritisation" | "trend",
  "screening_setup": {centre, radius_km, indicators, time_range, centre_metadata},
  "date_saved":      ISO8601,
  "payload":         { ...screening payload from §1.1... },
  # prioritisation/trend entries carry different keys:
  # "prioritisation_setup", "supplier_results", "summary"
}
```

> **Persistence caveat:** saves are **session-only** — they survive reruns but
> NOT a page reload or sign-out. Full localStorage persistence (PLFS_v4 §14) is
> a future milestone. This is the single biggest "is this demo-real?" caveat in
> the report stack.

---

## 2. Verbal summary — `engine/verbal_summary.py`  (✅ complete, ~1,000 LOC)

The deterministic prose engine. Authority: `docs/Verbal_Summary_Templates_v1.md`.

**Public API:**

```python
@dataclass(frozen=True)
class VerbalSummary:
    overview: str
    air: str
    ghg: str
    nature: str
    template_ids: dict[str, str]      # which template fired per paragraph (audit)
    def joined(self) -> str           # "\n\n".join(overview, air, ghg, nature)

def generate_verbal_summary(payload: dict) -> VerbalSummary
```

**Design properties (locked, do not regress):**
1. **Deterministic** — no LLM, no randomness, no state. Same input → same output.
   (CLAUDE.md §8 forbids introducing LLM calls here.)
2. **Defensible** — never invents values, never speculates causation, never
   implies facility-level attribution. Severity is *site-vs-region anomaly*.
3. **Auditable** — every sentence traces to a template ID + slot-resolution
   rule; `template_ids` records which fired.
4. **UI-aligned** — bucketing = `TRAFFIC_LIGHT_THRESHOLDS` (0.33 / 0.66).

**Internal shape:** `_bucket()` → tertile band; `_resolve_dominant()` +
`_*_dominant_slots()` pick the dominant contributor per pillar; `_render_pillar()`
and `_render_overview()` fill template strings; `_hansen_reference_clause()`
appends a forest-loss reference clause when above
`HANSEN_VERBAL_MENTION_THRESHOLD`.

**Consumed by:** P-05 C7 ([`c7_verbal_summary.py`](../ui/components/c7_verbal_summary.py)),
P-06 trend view, and P-11 `pillar_findings` section. Tests:
[`tests/test_verbal_summary.py`](../tests/test_verbal_summary.py).

---

## 3. Saving + listing — the bridge to reports

### 3.1 C8 action bar — `ui/components/c8_action_bar.py`  (✅ complete)

Bottom-of-P-05 buttons. Authority: Wireframes §P-05 C8.

- `render_c8_action_bar(payload)` — "Save as report" + (disabled) "Switch to Trend".
- `_save_as_report(payload)` — appends an entry (§1.2) to `saved_analyses`,
  stashes a sentinel for the post-save banner.
- `_render_post_save_banner()` — sticky success banner with **"Open in Reports"**
  → calls `route_to_p11_with_source()` then `st.switch_page("pages/11_Reports.py")`.
  This is the **primary entry path** into report creation.
- `_build_save_name(setup, scope, now)` — pure, testable name builder.
  Precedence: supply-chain node → region → coordinate+timestamp fallback.

### 3.2 P-10 saved-analyses list — `ui/components/p10_list.py`  (✅ complete)

- `render_saved_analyses()` — free-text search + per-row Open / Delete /
  Export-JSON. Open routes back to P-05 (screening) or P-08 (prioritisation).
- Per-row **Export JSON** is a *raw* per-analysis dump (distinct from the
  report-wrapped JSON in §4.4).

---

## 4. The report builder — P-11  (the main surface)

Page entry: [`pages/11_Reports.py`](../pages/11_Reports.py) → `render_p11()`.
Router-only page (no Earth Engine init). All logic in `ui/`.

### 4.1 State machine — `ui/p11_state.py`  (✅ complete)

```python
class ReportStateKind(str, Enum):
    S1_TEMPLATE_AND_SOURCE   # pick template + sources + title/notes → Preview
    S2_PREVIEW               # review assembled HTML in an iframe → Export
    S3_EXPORT                # download PDF / CSV / JSON
    E1_FAILED                # export generation failed

@dataclass
class ReportState:
    kind, template_id, source_ids: list[str], title, notes, error

def route_to_p11_with_source(session_state, source_id)  # pure mutator; pre-selects a source
```

State lives at `st.session_state["report_state"]`.

### 4.2 Renderer — `ui/components/p11_renderer.py`  (✅ complete)

`render_p11()` dispatches on `state.kind`:
- `_render_s1` — user-type → `templates_for()`; template selector; source
  multiselect (filtered to the template's `accepted_source_types`); title +
  notes; validation (template + ≥1 source + title required) → S2.
- `_render_s2` — assembles HTML via `build_report_html()`, renders in an iframe
  (`st.components.html`) → "Continue to Export" → S3.
- `_render_s3` — three columns: PDF (generate-then-download, cached), CSV
  (one-shot `st.download_button`), JSON (one-shot). PDF failures surface
  `PdfDependencyError` as a friendly install banner.

### 4.3 Templates registry — `ui/components/p11_templates.py`  (✅ complete, M-REPORT-A1)

```python
@dataclass(frozen=True)
class ReportTemplate:
    template_id, display_name, description
    user_types: frozenset[str]              # {"policy_maker","mnc"} — set, not scalar
    accepted_source_types: frozenset[str]   # {"screening","prioritisation","trend"}
    sections: tuple[str, ...]               # ordered section keys
    pillars: frozenset[str] = ALL_PILLARS   # which pillars this report renders
    esrs: bool = False                      # ESRS framing available (MNC renders only)
```

M-REPORT-A1 restructured the surface from two flat templates into a **five-registration**
family. The General report is **one** registration offered to both roles, **dual-framed**
by `user_type` at render time (RT8) — not two template IDs.

| template_id | user_types | pillars | esrs | sections (in order) |
|---|---|---|---|---|
| `general` | policy_maker, mnc | all 3 | true* | title_page, executive_summary, methodology, scope_summary, **pillar_findings**, indicator_detail, reference_datasets, provenance_appendix, **glossary** |
| `mnc_ghg` | mnc | ghg | true | title_page, executive_summary, methodology, scope_summary, **pillar_findings**, indicator_detail, reference_datasets, provenance_appendix, **glossary** |
| `mnc_air` | mnc | air | true | (same as mnc_ghg; reference_datasets renders empty → omitted) |
| `mnc_nature` | mnc | nature | true | (same as mnc_ghg) |
| `trend` | policy_maker, mnc | grouping only | false | title_page, scope_summary, **trend_indicator_sections**, provenance_appendix, **glossary** |

\* `esrs=true` only **takes effect** for MNC renders. A policy maker picking `general`
gets the same body with ESRS labels stripped (RT8). The ESRS layer + pillar filtering
resolve via a `RenderContext` (see §4.5) built by the assembler from the template + the
active `user_type` (captured on `ReportState.user_type` at S1).

`templates_for(user_type)` (now a **membership** test against `user_types`) and
`get_template(id)` are the lookups.

> **Extension point:** adding a report type = register a new `ReportTemplate` +
> implement any new section keys in the registry (§4.5). No renderer changes.

### 4.4 Assembler + shell — `ui/components/p11_assembler.py` + `templates/p11/shell.html.j2`  (✅ complete)

```python
def build_report_html(state, sources, template) -> str
```

Builds a `RenderContext` from the template + `state.user_type` (M-REPORT-A1),
loops `template.sections` calling each section fn via `get_section()` with that
ctx, and joins the HTML fragments inside the Jinja2 shell. The **`glossary`**
section is deferred: the assembler renders it from the joined body of the other
sections (content-aware scan, see `p11_glossary.py`) and slots it into its
declared position. **Per-section failures are caught and
inlined as an error fragment** — one broken section never blanks the whole
report. The shell (`shell.html.j2`) carries all print CSS: `@page` A4 +
margins + footer page numbering (weasyprint honours these), pillar-chip colour
classes (red/amber/green/grey), table styling, `color-scheme: light` to stop
Streamlit's dark theme bleeding into the iframe.

### 4.5 Section functions — `ui/components/p11_sections.py`  (✅ complete, ~1,100 LOC)

Each section is `def _render_X(state, sources, ctx=None) -> str` returning an
HTML fragment. M-REPORT-A1 added the third **`ctx`** arg — a `RenderContext`
(`user_type`, `pillars`, `apply_esrs`, `template_id`) built by the assembler
via `RenderContext.from_template(template, user_type)` and threaded into every
section. `ctx=None` defaults to all-pillars / no-ESRS so direct (test) calls
with two args keep working. Dispatched by `_SECTION_REGISTRY`:

| Section key | What it renders | Notes |
|---|---|---|
| `title_page` | report-type identity (RF1) + title, date, source count | M-REPORT-A1.1: names the template on the cover (ESRS E1/E2/E4, Environmental screening, Environmental trend) |
| `executive_summary` | notes + per-source composite/band table | M-REPORT-A2: single-pillar reports relabel the composite column "(all 3 pillars)" + add a scope-of-composite note (RA2) |
| `methodology` | fixed methodology prose | |
| `scope_summary` | screened scope | |
| `pillar_findings` | **dual-framed (RT8).** When `ctx.apply_esrs` (MNC): ESRS topical grouping (E1/E2/E4) + metrics-&-evidence intro + out-of-scope stubs, filtered to `ctx.pillars`. Otherwise (policy / no-ctx): plain narrative, **reusing `generate_verbal_summary`** for full 19-indicator screenings, caveat + score table for partial. Carries the pillar-level story (prose + pillar score/band). | M-REPORT-A1 |
| `priority_findings` | audit-priority ranking | |
| `indicator_detail` | **per-pillar audit tables** — one table per pillar, each with columns that fit its grammar (CLAUDE.md §7, don't harmonise): Air = site/background/z/anomaly-freq/confidence/attrib; GHG = VIIRS sustained-contrast (brightness / lit-contrast pct / flaring frac / lit ring pixels); Nature = headline key-metric per indicator. Screening-only; reference datasets (CH₄/ODIAC/Hansen) excluded; filtered to `ctx.pillars`. Distinct from `pillar_findings` (the pillar story). | M-REPORT-A1.1 |
| `per_supplier_detail` | per-supplier breakdown for prioritisation sources | |
| `trend_indicator_sections` | **Trend report body (Option A, RT9).** Per-indicator verdict + metrics + inline SVG, grouped under pillar headers (grouping only — no composite). | M-REPORT-A1 |
| `trend_graph` | inline SVG trend chart from saved trend records | **LEGACY / unwired** (M-REPORT-A2 RA5) — superseded by `trend_indicator_sections`; kept registered for fallback tests only |
| `reference_datasets` | Hansen / ODIAC / CH₄ context datasets; rows **and footnote clauses** filtered to `ctx.pillars` (RF4/RF5; Air report → empty → section omitted) | RF4 prose names each dataset's role + exclusion |
| `provenance_appendix` | 11-field provenance per indicator + special appendices (coastal, habitat-attribution, wind-attribution, fallback, extras). Provenance + every sub-appendice filtered to `ctx.pillars` (RF5). Each fallback/adjustment sub-appendice gated on an *effectively-applied* predicate (RF6) — e.g. coastal renders only when `land_mask_applied` and the ring rounds to <100% land. | see §5 |
| `composite_formula` | **composite-score methodology** — composite = equal-weighted mean of the 3 pillar follow-up priorities (IC_v4 §4); per-pillar term weights read from `engine.constants` (`AIR/GHG/NATURE_FOLLOWUP_WEIGHTS`). In General + pillar reports (not trend). | M-REPORT-A1.1 |

> `glossary` is **not** in `_SECTION_REGISTRY` — it is a content-aware appendix
> the **assembler** renders last by scanning the joined body of the other
> sections, then slots into its declared position. See `p11_glossary.py` (§7).

> This is the **largest and most design-relevant file**. The provenance
> appendix alone has five sub-renderers. If the design goal is "improve report
> structure", this file + the templates registry (§4.3) are where structure
> decisions land.

### 4.6 Export backends

| File | Function | Output | Notes |
|---|---|---|---|
| `p11_pdf.py` | `render_pdf(html) -> bytes` | PDF | Lazy-imports weasyprint (~200 MB resident); wraps missing Pango/Cairo/GLib as `PdfDependencyError`. |
| `p11_csv.py` | `render_csv(state, sources) -> str` | CSV | Flat, one row per (source, pillar, indicator); prioritisation expands per-supplier. 18 locked columns incl. confidence-term breakdown + provenance. UTF-8 BOM + `QUOTE_ALL` for Excel. |
| `p11_json.py` | `render_json(state, sources, template) -> str` | JSON | Report-wrapped: top-level `report` metadata block + `sources[]`. Self-describing; distinguishable from raw output by the `report` key. |

CSV column set (`_COLUMNS`): `source_name, source_type, pillar, indicator_id,
score, confidence, asset_id, native_scale_m, time_range_start, time_range_end,
skipped_reason, confidence_term_qa, confidence_term_n_valid,
confidence_term_anomaly_strength, confidence_term_spatial_context,
column_to_surface_multiplier, n_valid_dates, granule_count`.

---

## 5. Provenance — the audit backbone

Authority: `docs/provenance_schema.md`. Every single-value indicator emits a
`_provenance.<pillar>.<indicator>` block via `engine.core.build_provenance`
(11 canonical fields: indicator_id, asset_id, band, data_type, data_source,
native_scale_m, method_note, time_range, coverage_window, skipped_reason,
observations + `extra` escape hatch). The report's `provenance_appendix` section
and several CSV columns are pure projections of these blocks — so report
auditability is only as good as the provenance blocks the engine emits.

---

## 6. Tests (report-relevant)

```
tests/test_verbal_summary.py          ← prose engine (largest suite)
tests/test_p11_templates.py           ← registry + filtering
tests/test_p11_state.py               ← state machine + routing
tests/test_p11_assembler.py           ← HTML assembly + section-failure isolation
tests/test_p11_sections.py            ← section fragments
tests/test_p11_csv.py / _json.py / _pdf.py  ← export backends
tests/test_save_as_report_wiring.py   ← C8 → P-11 routing
tests/test_save_name_builder.py       ← _build_save_name precedence
tests/test_p08_save_action.py         ← prioritisation save
tests/test_seeded_saves.py            ← demo seed data
tests/test_habitat_attribution_pdf.py ← habitat-attribution appendix PDF
```

---

## 7. File index (every report-touching file)

| Path | Role | Status |
|---|---|---|
| [engine/verbal_summary.py](../engine/verbal_summary.py) | deterministic prose engine | ✅ |
| [ui/components/c7_verbal_summary.py](../ui/components/c7_verbal_summary.py) | P-05 C7 renderer | ✅ |
| [ui/components/c3_summary.py](../ui/components/c3_summary.py) | traffic-light chips | ✅ |
| [ui/components/c8_action_bar.py](../ui/components/c8_action_bar.py) | save-as-report + banner | ✅ |
| [ui/components/p10_list.py](../ui/components/p10_list.py) | saved-analyses list | ✅ |
| [pages/11_Reports.py](../pages/11_Reports.py) | P-11 page entry | ✅ |
| [ui/p11_state.py](../ui/p11_state.py) | report state machine | ✅ |
| [ui/components/p11_renderer.py](../ui/components/p11_renderer.py) | S1/S2/S3 dispatch | ✅ |
| [ui/components/p11_templates.py](../ui/components/p11_templates.py) | template registry — 5-template inventory; `user_types`/`pillars`/`esrs` (M-REPORT-A1) | ✅ |
| [ui/components/p11_assembler.py](../ui/components/p11_assembler.py) | HTML assembly — builds `RenderContext`, threads `ctx`, defers glossary post-pass (M-REPORT-A1) | ✅ |
| [ui/components/p11_sections.py](../ui/components/p11_sections.py) | section functions + `RenderContext`; ESRS-framed pillar findings, pillar filtering, `trend_indicator_sections` (M-REPORT-A1) | ✅ |
| [ui/components/p11_esrs.py](../ui/components/p11_esrs.py) | ESRS framing layer (M-REPORT-A1) — pillar→E1/E2/E4 map (RT6), topical headings, metrics-&-evidence intros, out-of-scope stubs (RT4); `datapoint_label()` deferred stub (§8.4) | ✅ |
| [ui/components/p11_glossary.py](../ui/components/p11_glossary.py) | content-aware glossary appendix (M-REPORT-A1) — master term set (§6), word-boundary fragment scan, family grouping; rendered by the assembler | ✅ |
| [ui/components/p11_pdf.py](../ui/components/p11_pdf.py) | PDF backend | ✅ |
| [ui/components/p11_csv.py](../ui/components/p11_csv.py) | CSV backend | ✅ |
| [ui/components/p11_json.py](../ui/components/p11_json.py) | JSON backend | ✅ |
| [templates/p11/shell.html.j2](../templates/p11/shell.html.j2) | print/PDF shell + CSS | ✅ |
| [ui/components/trend_record.py](../ui/components/trend_record.py) | trend persistence (report source) | ✅ |
| [ui/components/trend_svg.py](../ui/components/trend_svg.py) | inline trend SVG for reports | ✅ |
| [ui/prioritisation_state.py](../ui/prioritisation_state.py) | `SupplierResult` (report source) | ✅ |
| [docs/Verbal_Summary_Templates_v1.md](Verbal_Summary_Templates_v1%20(1).md) | prose authority | doc |
| [docs/provenance_schema.md](provenance_schema.md) | provenance authority | doc |
| [docs/Wireframes_All_v4.md](Wireframes_All_v4.md) | P-05/P-10/P-11 UI authority | doc |

---

## 8. Open questions / seams for a design review

These are the genuine decision points if the goal is to improve report-creation
structure. None are bugs — they are design choices currently locked one way.

1. **Section model is positional & flat.** A template is an ordered tuple of
   string keys; sections take `(state, sources, ctx=None)` and return HTML
   strings. There is no per-section config beyond the threaded `RenderContext`
   (M-REPORT-A1 kept the flat model deliberately — Step A §8.1 chose "flat +
   threading" over a structured-section refactor). Further configurability
   (reordering UI, per-section toggles) would still mean changing the
   `ReportTemplate` shape and the renderer.
2. **HTML-string sections, not a component tree.** Sections concatenate raw HTML
   strings. This is simple and weasyprint-friendly but hard to restyle/theme
   centrally beyond the shell CSS. A structured intermediate (dict/dataclass per
   section, rendered by one templating pass) would decouple content from layout.
3. **~~Two templates, hard-wired to user type.~~** *Resolved by M-REPORT-A1.*
   The inventory is now five templates; `user_types` is a set, so the General
   and Trend reports belong to both roles, and the General report is dual-framed
   by `user_type` at render time (RT8). The role filter (`templates_for`) is now
   a membership test.
4. **Session-only persistence.** Saved analyses (the report sources) vanish on
   reload. Any report-creation UX that assumes a durable library of past
   analyses is blocked on the localStorage milestone (PLFS_v4 §14).
5. **PDF requires native deps.** weasyprint needs Pango/Cairo/GLib on the host;
   absent them, PDF is unavailable (CSV/JSON still work). A pure-Python or
   headless-browser PDF path would remove that host dependency.
6. **Executive summary is mechanical.** It's a per-source composite/band table
   plus the user's notes — it does not synthesise across sources. A cross-source
   narrative would be a natural structural addition (but must stay deterministic
   per CLAUDE.md §8 — no LLM in the summary path).
7. **No report-level provenance/versioning.** The JSON carries `generated_at`
   but there's no tool-version / engine-version / indicator-schema-version stamp
   on the report itself for reproducibility.

---

*Maintenance note: this is a working handoff, not an authority doc. If the P-11
code structure changes materially, regenerate or update §4–§7 here. Do not let
this doc become a second source of truth that competes with the Wireframes /
PLFS specs.*
