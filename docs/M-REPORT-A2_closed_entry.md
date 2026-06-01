# M-REPORT-A2 — Closed Entry

*Report refinements following the M-REPORT-A1 build: pillar-report composite clarity, housekeeping, map-PNG retirement. 1 June 2026. Authority: `M-REPORT-A2_spec.md` (final spec, six locks RA1–RA6). Render-layer + docs only — no engine change, no reconnaissance gate.*

---

## What this milestone did

A small refinement pass closing the three loose ends surfaced by M-REPORT-A1.

1. **Composite-row disambiguation (RA2/RA3).** The executive-summary composite column shows the whole-screening `overall_screening` (all three pillars). In a single-pillar ESRS report that read ambiguously. Now, when the report covers one pillar (`len(ctx.pillars) == 1`), the column is relabelled **"Overall screening composite (all 3 pillars)"** and a one-line scope-of-composite note is added beneath the table, naming the report's pillar (ESRS topic resolved from the RT6 map). The General report (all three pillars, both framings) is unchanged. Static-string composition — deterministic, no LLM.
2. **`trend_graph` legacy marker (RA5).** Added a section-banner + docstring comment marking `_render_trend_graph` as legacy/unwired — superseded by `trend_indicator_sections` (M-REPORT-A1), kept registered only for the trend-view fallback tests. No behavioural change.
3. **Handoff-doc sync (RA4).** Updated the derived `Report_Creation_Handoff.md`: §4.3 (five-template inventory + `user_types`/`pillars`/`esrs`), §4.4 (RenderContext + glossary post-pass), §4.5 (added `trend_indicator_sections`, marked `trend_graph` legacy, noted the assembler-rendered glossary), §7 file index (added `p11_esrs.py`, `p11_glossary.py`, RenderContext), and retired the now-stale §8 open-questions item on "two templates hard-wired to user type". The doc's "derived, not authority" disclaimer is preserved.

## RA6 — Map-PNG download: RETIRED (won't-do)

The parked downloadable-map-PNG item (M-REPORT-A1 RT16) is formally **scrapped, not deferred**. The "what is the download for" decision (evidence vs. real-world context) will not be taken; the feature is out of v1.x report scope.

**Rationale.** Cost (headless-browser host dependency + map-tile licensing exposure) versus value is not justified at v1.x: the underlying data is already exportable via CSV/JSON, and the live map remains interactive in-app. No persistent parked-item entry existed to remove (RT16 lived only in the M-REPORT-A1 spec); this entry is its durable record.

## ESRS datapoint codes — still deferred (out of scope, §5)

`datapoint_label()` remains a `None`-returning stub. Per-indicator ESRS E1/E2/E4 datapoint codes are not in the project docs (M-REPORT-A1 Step A §8.4); this needs an external ESRS datapoint mapping reference before it can be specced. It is the single substantive ESRS follow-up — **not** addressed here.

## Files touched

- `ui/components/p11_sections.py` — `_render_executive_summary` composite relabel + note (RA2/RA3); `_render_trend_graph` legacy banner (RA5).
- `docs/Report_Creation_Handoff.md` — §4.3 / §4.4 / §4.5 / §7 / §8 sync (RA4).
- `tests/test_p11_composite_clarity.py` — new (6 tests, RA2/RA3 coverage incl. the cardinality predicate).
- `docs/M-REPORT-A2_closed_entry.md` — this entry (RA6 record).

No engine code touched; no authority-doc (Wireframes / PLFS / Verbal-Summary / Indicators) edits.

## Verification (RA1–RA6)

- [x] **RA1** — pillar reports keep exec summary + methodology + scope (no sections cut). Confirmed: `_PILLAR_SECTIONS` unchanged.
- [x] **RA2/RA3** — composite relabel + note fire for mnc_ghg/air/nature; absent in general (both framings). Cite: `tests/test_p11_composite_clarity.py`.
- [x] **RA4** — handoff §4.3/§4.4/§4.5/§7/§8 synced to post-A1 reality; disclaimer preserved.
- [x] **RA5** — `trend_graph` legacy comment added; still registered; fallback tests still green (`tests/test_trend_view.py`).
- [x] **RA6** — map-PNG retired here as won't-do with rationale.
- [x] **Predicate keys off `pillars` cardinality**, not user_type/template_id. Cite: `test_predicate_is_cardinality_not_user_type`.
- [x] **No determinism regression** — static-string note; full suite green (2004 passed / 34 skipped / 0 failures, deterministic order). The intermittent `test_c4b_kpi_grid` failure under `pytest-randomly` is a pre-existing P-05 test-isolation flake (passes in isolation; untouched by this milestone).
