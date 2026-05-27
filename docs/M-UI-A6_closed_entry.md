# M-UI-A6 — Closed-entry verification

**Date closed.** 28 May 2026 (v1.0).
**Scope delivered.** Reference-dataset display in C5 for Hansen forest loss
and ODIAC CO₂: a dedicated "Reference datasets" sub-section with muted,
non-scored card chrome; conditional C7 verbal-summary integration for
Hansen; a PDF reference-datasets section; and the supporting tests + docs.

This milestone is **UI-only** — no engine computation changed (per spec
§2.2). Vintage is derived in the UI from existing provenance (Step B
decision), so no engine field was added.

> **Follow-up: M-V1x-STANDING-WINDOW (28 May 2026).** Review after close
> surfaced that the values feeding these cards were window-bounded in the
> engine, contradicting the audit doc's standing-exposure intent (§9.3
> lines 982/1002) — Hansen reported 0 and ODIAC was skipped for any
> present-day analysis window. A separate engine reconciliation now reads
> both from fixed windows independent of the analysis window (Hansen: most
> recent `HANSEN_LOOKBACK_YEARS`; ODIAC: latest coverage year). With it, the
> Hansen card's "5-year cumulative" label and both vintage lines are
> accurate. Files: `engine/nature.py` (`compute_forest_loss`),
> `engine/ghg.py` (`run_pillar` dispatch + `_latest_coverage_year_window`),
> `tests/test_nature_defensive.py`, `tests/test_ghg.py`. Demo saved-analysis
> fixtures were regenerated against live Earth Engine (28 May 2026) and now
> carry real standing-exposure values (Sapezal: Hansen 0.13%, ODIAC 48;
> Brasília: Hansen 0.56%, ODIAC 1888); golden tests pin these.

## Step B decisions (locked 28 May 2026)

| Topic | Decision |
|---|---|
| Vintage source | Derive in UI, no engine change. ODIAC from `_provenance.ghg.co2.coverage_window`; Hansen from the year in `_provenance.nature.forest_loss.asset_id`, fallback constant. |
| P-09 link | Affordance only — the M-UI-A2 name popover's built-in "Learn more →" is the P-09 route; no separate bottom link. |
| Habitat dedup | Removed the inline "Hansen forest loss: X ha" line from the Nature habitat caption; Hansen now lives only in the reference card. |
| Q-A6-1 explainer | Single "Why reference data?" expander at the sub-section level. |
| Q-A6-2 | Hansen audit footnote stays a single italic line (spec default). |
| Q-A6-3 | ODIAC is not mentioned in C7 (spec default). |

## Files touched

| File | Change |
|---|---|
| `ui/components/c5_drilldown.py` | **+** "Reference datasets" sub-section: vintage/interpretation/field helpers, `_ReferenceCardFields`, `_render_reference_card`, `_render_reference_datasets_section`, wired into `render_c5_drilldowns`. **−** inline Hansen-ha line from the habitat caption. |
| `engine/verbal_summary.py` | **+** `_hansen_reference_clause` + §6.1/§6.2 templates; appended to the Nature paragraph in `generate_verbal_summary`. |
| `engine/constants.py` | **+** `HANSEN_VERBAL_MENTION_THRESHOLD = 1.0` (C7 mention gate). |
| `ui/components/p11_sections.py` | **+** `_render_reference_datasets` / `_render_reference_dataset_block`; registered `"reference_datasets"` in `_SECTION_REGISTRY`. |
| `ui/components/p11_templates.py` | **+** `"reference_datasets"` in both template section tuples (after the scored-indicator section, before provenance). |
| `tests/test_reference_datasets.py` | **new** — 36 tests across §8.1–8.7. |
| `docs/M-UI-A6_plain_language_explainer.md` | **new** — stakeholder explainer. |
| `docs/M-UI-A6_closed_entry.md` | **new** — this file. |

## RD lock verification

- [x] **RD1** — Only Hansen + ODIAC in scope. The sub-section renders
  exactly two cards (`_render_reference_datasets_section`); no other
  indicator was added.
- [x] **RD2** — Section lives in C5, after the scored Nature deep-dive,
  before C6. `render_c5_drilldowns` calls `_render_reference_datasets_section`
  after `_render_nature_panel`; P-05 renders C6/C7 after C5.
- [x] **RD3** — No severity reading. Cards render no severity badge and call
  no `band_*`/severity helper. Regression: `test_both_cards_share_field_structure`
  asserts the field set carries no severity attribute; the card renderer has
  no severity branch.
- [x] **RD4** — No confidence dot. Cards do not call `confidence_glyph`.
- [x] **RD5** — Badge text matches the canonical string.
  `test_badge_text_is_canonical_string`.
- [x] **RD6** — Visual chrome differentiated: muted small-caps badge,
  1.6em headline (vs the severity tiles' larger verdict), neutral greys, no
  severity hue, italic footnote. (Code: `_render_reference_card`; visual
  review recommended at demo time.)
- [x] **RD7** — Standardised card structure. Both cards build the same
  `_ReferenceCardFields` shape; `test_both_cards_share_field_structure` and
  the two `*_card_fields_present` tests assert identical structure.
- [x] **RD8** — Hansen `regional_loss_evidence` named in the audit footnote.
  `test_hansen_card_fields_present` asserts `"regional_loss_evidence"` and
  `"External Driver Screening"` appear.
- [x] **RD9** — C7 templates fire conditionally. `test_corroboration_*`,
  `test_divergence_fires_when_loss_but_quiet`, `test_quiet_no_mention_below_threshold`.
- [x] **RD10** — PDF section included, after scored indicators, before
  provenance. `test_reference_datasets_section_registered_and_in_templates`,
  `test_pdf_section_includes_disclaimer_and_both_datasets`.
- [x] **RD11** — "Why reference data?" expander present (sub-section level,
  per Q-A6-1). Code: `_render_reference_datasets_section`.
- [x] **RD12** — Missing-data shows "Data not available for this AOI";
  card still renders. `test_*_card_missing_value`, `test_pdf_section_handles_missing_values`,
  and the golden-fixture test (ODIAC is `None` in both demo fixtures).
- [x] **RD13** — Hansen/ODIAC absent from the headline grid.
  `test_hansen_odiac_absent_from_c4b_headline_grid`. (M-UI-A4 v1.1 owns the
  removal; this milestone only regression-checks it.)
- [x] **RD14** — Reusable structure. Adding a reference dataset = one field
  helper + one card column in `_render_reference_datasets_section`; the
  `_ReferenceCardFields` + `_render_reference_card` pattern is dataset-agnostic.

## Interpretation note (RD9 / §6.1)

The §6.1 examples ("KBA Concern/High, DW Built/Bare, NDVI deviation") are
operationalised in `_hansen_reference_clause` via the **Nature pillar
priority bucket** (high/moderate = concern, low = quiet) — the same reading
the rest of `engine/verbal_summary.py` uses. This keeps the engine
self-contained (no import of the UI severity grammar). If a future milestone
wants per-indicator severity gating, that's a clean extension point.

## Out of scope (unchanged, per spec §12)

Engine computation; severity/confidence on reference cards; map-view layers
(M-UI-A5); other reference datasets; automated vintage refresh; ODIAC C7
integration.

## Tests

`tests/test_reference_datasets.py` — 36 tests, all passing. Full suite at
close: **1437 passed, 19 skipped** (skips are pre-existing EE integration
tests).

## Pending doc-sync (requires explicit confirmation per CLAUDE.md §8)

These authoritative docs were **not** modified by this milestone; the edits
are proposed and await sign-off:

1. `Wireframes_All_v4.md` §P-05 C5 — add the "Reference datasets"
   sub-section + card layout (spec §9).
2. `Indicators_Audit_and_v1x_Roadmap.md` §9.3 v1.4 (Hansen) and M5.5b
   (ODIAC) — add a "v1.x UI treatment" note referencing M-UI-A6 (spec §9).
   *(The audit doc is the master authority and is explicitly protected — no
   edit without confirmation.)*
3. `Verbal_Summary_Templates_v1.md` — record the new §6 Hansen
   corroboration/divergence clause (flagged in reconnaissance; not in the
   spec §9 list, but this doc is authoritative for verbal-summary prose).

`GSCO_v1x_TodoList.md` (referenced by spec §9) does not exist in the repo,
so item 2.1 could not be marked.
