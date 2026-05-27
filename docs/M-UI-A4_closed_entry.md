# M-UI-A4 — Closed-entry verification

**Date closed.** 27 May 2026 (v1.0); amended for spec v1.1, 27 May 2026.
**Scope delivered.** C4b indicator-snapshot redesign (P-05): three severity
grammars, scored Nature tiles (KBA, DW, NDVI) in the headline grid,
critical-snapshot filter + expander, per-tile severity badge + map-link
affordance, C5 restructure.

> **v1.1 amendment.** Hansen forest loss and ODIAC CO₂ were removed from the
> headline grid as reference datasets (SR4/SR7/SR13). 16 → **14 tiles** (9 air
> + 2 GHG + 3 Nature); 4 → **3 grammars** (loss-fraction removed; categorical
> is DW-only; ODIAC scheme + percentile constants deleted). Their
> reference-dataset treatment in C5 is M-UI-A6's job.

## Files touched

| File | Change |
|---|---|
| `ui/components/severity.py` | **new** — three severity grammars (v1.1) + `SEVERITY_BANDS` + Sparse override + helpers |
| `ui/components/c4b_kpi_grid.py` | rewritten — polymorphic `_TileSpec`, **14 tiles** (9 air + 2 GHG + 3 Nature), 2 layout variants, severity badge, map link, critical-snapshot partition, restyled failure tile, map anchor |
| `ui/components/c5_drilldown.py` | C5c reframed as "Nature/Land — details (deep-dive)" with snapshot cross-reference; Hansen/ODIAC left in place for M-UI-A6 (SR13) |
| `pages/05_Screening_Results.py` | map anchor wired between C4b and C5 (Q-A4-4) |
| `engine/ghg.py` | `ghg.viirs.z` added to VIIRS emitted set (was computed, filtered) |
| `docs/Indicator_ID_Schema_v2.md` | VIIRS `.z` row + footnote |
| `tests/test_severity.py` | **new** — 47 tests (v1.1: ODIAC/Hansen tests removed) |
| `tests/test_c4b_kpi_grid.py` | rewritten — 41 tests (incl. Hansen/ODIAC-not-on-grid regression) |
| `tests/test_ghg.py` | 3 VIIRS-count assertions updated for the 6-measurement set |
| `docs/M-UI-A4_severity_thresholds.md`, `…_plain_language_explainer.md`, `…_closed_entry.md` | **new** |

**Test status.** Full suite green (see Step C verification below).

## Decisions taken (Step B reconciliation, 27 May 2026)

- **VIIRS z** — surfaced the real, already-computed z (1-line engine + schema
  note) rather than a UI-side pseudo-z (which couldn't be statistically valid:
  no σ in the payload).
- **Component name** — kept `c4b_kpi_grid.py` (Q-A4-2).
- **Map anchor** — between C4b and C5 (Q-A4-4).
- **Thresholds** — shipped §4 defaults as v1.0, tunable (Q-A4-1/A4-3).
- **v1.1** — removed Hansen + ODIAC from the headline grid as reference
  datasets (supersedes the v1.0 SR4/SR7/SR13 build).

## SR-lock verification

- [x] **SR1** — Severity word + dot top-right of each tile; z-score huge,
  centred; raw values demoted to a secondary line.
  *Cite:* `_render_zscore_tile` / `_tile_header` / `_secondary_line_html`;
  `test_severity_badge_contains_word`.
- [x] **SR2** — Critical-only default + "Show all indicators" expander.
  *Cite:* `render_c4b_kpi_grid` (expander), `_snapshot_partition`;
  `test_snapshot_shows_only_critical_when_many_fire`.
- [x] **SR3** — Severity from local threshold functions only; no engine flag.
  *Cite:* `ui/components/severity.py`; `test_no_engine_critical_field_dependency`.
- [x] **SR4 (v1.1)** — Scored Nature tiles (KBA, DW, NDVI) in the headline
  registry; **Hansen + ODIAC excluded** as reference datasets.
  *Cite:* `_TILES`; `test_nature_tiles_present_in_headline_registry`,
  `test_hansen_and_odiac_not_in_headline_grid` (§8.6 regression).
- [x] **SR5** — `View on map →` on every tile, scrolls to placeholder anchor.
  *Cite:* `_map_link_html`, `render_multi_indicator_map_anchor`, `MAP_ANCHOR_ID`;
  `test_map_link_targets_anchor`.
- [x] **SR6 (v1.1)** — Scope A delivered: 14 tiles, 3 grammars, scored-Nature
  inclusion. *Cite:* `test_tile_count_is_fourteen`, `test_three_grammars_used`.
- [x] **SR7 (v1.1)** — Three grammars implemented (loss-fraction removed).
  *Cite:* `severity_zscore` / `severity_categorical` (DW-only) /
  `severity_distance`; `test_*_dispatch`, `test_three_grammars_used`.
- [x] **SR8** — Sparse a distinct fourth state, muted grey dot, non-critical.
  *Cite:* `_is_sparse`, `_SEVERITY_STYLE["Sparse"]`, `is_critical`;
  `test_sparse_*`.
- [x] **SR9** — Minimum 3 tiles in the default snapshot.
  *Cite:* `_snapshot_partition` top-up; `test_snapshot_min_three_topup_when_few_critical`,
  `test_sapezal_snapshot_respects_min_three`.
- [x] **SR10** — M-UI-A2 hover preserved (name remains the popover trigger).
  *Cite:* `_tile_header` → `render_indicator_name_with_info` (unchanged signature).
- [x] **SR11** — Confidence dot preserved (`confidence_glyph`).
  *Cite:* `_confidence_line_html`.
- [x] **SR12** — Failure tile pattern preserved, restyled; counts as Sparse.
  *Cite:* `_render_failed_tile`, `_tile_severity` (failed→Sparse);
  `test_failed_tile_reports_sparse_for_filter`, `test_resolve_reason_*`.
- [x] **SR13 (v1.1)** — C5c restructured into "Nature details" deep-dive;
  scored Nature content (KBA/DW/NDVI) migrated to the headline grid. Hansen +
  ODIAC left in their current C5 representation for M-UI-A6 (this milestone
  does not preempt their reference-dataset redesign).
  *Cite:* `c5_drilldown._render_nature_panel` (renamed label + corrected
  cross-reference caption + docstring).
- [x] **SR14** — Confidence and severity orthogonal (high-z + low-conf reads
  as a magnitude severity with an independent Sparse confidence dot; the dot
  glyph is never collapsed into the severity word).
  *Cite:* `test_sparse_fires_on_low_confidence_even_with_high_z`; `_confidence_line_html`
  independent of `_severity_badge_html`. (See thresholds doc §5 for the nuance.)

## Known follow-ups

- **CLOSED (not needed, v1.1).** The ODIAC percentile-constant calibration is
  no longer required — ODIAC was removed from the headline grid.
- Severity-threshold calibration sweep narrows to **§4.6 Q1–Q2** (z High
  threshold; KBA overlap floor). Q3–Q5 dropped with the v1.1 amendment.
- Hansen + ODIAC reference-dataset treatment in C5 → **M-UI-A6** (sibling
  milestone; deliberately not touched here).
- Real scroll-to-anchor / the multi-indicator map itself land in M-UI-A5 (2.3b).
- PDF report still renders the prior C4b (§2.2 — deferred to a PDF refresh).
- `Wireframes_All_v4.md` §P-05 C4b/C5c rewrite + `GSCO_v1x_TodoList.md` item
  2.3a remain **on hold for explicit confirmation** (per the amendment note);
  the TodoList is not present in the repo.
