# M-DOCS-CLEANUP-A3 — Closed Entry

**Status.** CLOSED — 1 June 2026.
**Type.** Documentation + small UI surface. Engine emits one new informational provenance field per pollutant (`display_unit`); no computation change.
**Branch.** `m-docs-cleanup-a3` off `main`.
**Spec.** `M-DOCS-CLEANUP-A3_spec.md` v1.0.

---

## 1. What landed

Three bundled deliverables, one milestone:

1. **IC v4 §0.9 — "Severity, absolute level, and attributability."** New §0 framing sub-section documenting the severity-vs-absolute distinction; closes item 14a (regional washout) as documentation-only. Cross-references §0 (M-ATTRIB-A2), §0.8 (CS9), §2.4 (M-VIIRS-REDESIGN-A1 VR16).
2. **Units in the C5 drilldown.** Air uniform rows now show the native unit on **Site value** and **Anomaly** cells; the GHG VIIRS card's brightness now reads its unit from provenance (was hardcoded).
3. **Units in the P-11 report.** Air detail table (**Site value** + **Background**) and GHG detail table (**Site brightness**) now carry units.

Engine emits `display_unit` in `_provenance.air.<pollutant>.extra` (9 pollutants) and `_provenance.ghg.viirs.extra`, sourced from the existing config dicts — single source of truth for both UI consumers (DC5).

---

## 2. Step A reconnaissance findings (deltas from spec premises)

- **§0 numbering.** §0 series ended at **§0.8** (the CS9 section landed by M-DOCS-CLEANUP-A2), so the spec's placeholder "§0.Y" was realised as **§0.9**, placed after §0.8 / before §1. The §4.1 cross-references to "§0.X" were mapped to the actual **§0.8**.
- **GHG VIIRS is a card, not a uniform row.** The spec assumed VIIRS sat in `_render_uniform_row`. Post-M-VIIRS-REDESIGN-A1 it is a dedicated contributor card (`_render_viirs_card`) that **already rendered "nW/cm²/sr"** at the brightness line. So the C5 VIIRS unit was effectively already present; this milestone repointed it at the provenance field for DC5 consistency rather than adding a missing unit.
- **`_render_uniform_row` is Air-only.** Used solely by `_render_air_panel`, so threading a `display_unit` kwarg is clean and side-effect-free.
- **P-11 surface.** Per-indicator Site values render in two HTML tables in `ui/components/p11_sections.py`: `_render_air_detail_table` (Site value + Background) and `_render_ghg_detail_table` (Site brightness). Both read from `payload` and now read `display_unit` from provenance via a shared `_display_unit_for` helper.
- **No IC v4 docx.** `docs/Indicators_Computation_v4.md` has no `.docx` counterpart → C7 N/A.
- **Earlier P-11 WIP** is now committed on `main` (`6784693 M-REPORT A1/2, CLEANUP-A2`); the working tree was clean at branch creation.
- **Seed-regression interaction (see §4).** The EE-gated baseline regression flags `added_path` as a categorical failure and its `_SKIP_PATHS` only excluded `_meta.computed_at`. The new `display_unit` leaf would have tripped it.

---

## 3. Implementation summary

| Step | File | Change |
|---|---|---|
| C1 | `engine/air.py` | `_format_result`: `extra["display_unit"] = cfg.display_unit` (1 line + comment). 9 pollutants automatic. |
| C2 | `engine/ghg.py` | `_format_viirs_result`: `"display_unit": cfg.display_unit` in the VIIRS provenance `extra` (1 line + comment). |
| C3 | `ui/components/c5_drilldown.py` | New `_with_unit()` helper; `_render_uniform_row` gains a `display_unit` kwarg; Site value + Anomaly cells suffixed. |
| C4 | `ui/components/c5_drilldown.py` | `_render_air_panel` threads `display_unit` from `_provenance.air.<ind>.extra`; `_render_viirs_card` reads the unit from provenance (fallback to native string). |
| C5 | `ui/components/p11_sections.py` | New `_fmt_num_unit()` + `_display_unit_for()` helpers; Air table (Site value + Background) and GHG table (Site brightness) suffixed. |
| C6 | `docs/Indicators_Computation_v4.md` | §0.9 sub-section per §4.1 wording. |
| C7 | — | Docx re-export N/A (no IC v4 docx). |
| C8 | `tests/` | 24 new assertions (see §5). |
| C9 | — | Defensive regression: **2047 passed, 34 skipped, 0 failed**. |

**Step B operator decisions:** unit suffix form = plain `47 µg/m³`; dimensionless (AAI/AOD) = omit the suffix.

---

## 4. Seed-regression guard interaction (important)

The `@_skip_unless_ee` per-AOI baseline regression (`tests/test_m_perf_a1_regression.py::TestM_PERF_A1_Regression`) walks **every** payload leaf and treats an `added_path` as a categorical failure. The committed baselines in `tests/baselines/m_perf_a1/*.json` predate the `display_unit` field, so when that suite runs **with EE credentials** it would have flagged `_provenance.*.extra.display_unit` as `added_path` on every AOI.

Because the field is additive, informational, and provably scoring-irrelevant (DC3/DC9), the comparator was taught to skip leaves ending in `.extra.display_unit` (new `_SKIP_PATH_SUFFIXES`, mirroring the existing `_SKIP_PATHS` mechanism that already ignored `_meta.computed_at`). A unit test (`test_display_unit_provenance_leaf_skipped`) locks this behaviour. The guard remains fully intact for every other field.

**Alternative not taken:** regenerating the baseline JSONs. That requires live EE (unavailable in this session). If the operator prefers regenerated baselines over the comparator skip, that can be done in a follow-up with EE credentials and the skip-suffix removed.

---

## 5. Test additions

- `tests/test_air.py` — `display_unit` present in provenance.extra for all 9 Air pollutants (parametrized; matches `AIR_POLLUTANT_CONFIG`).
- `tests/test_ghg.py` — `display_unit` present in `_provenance.ghg.viirs.extra` (== `"nW/cm²/sr"`).
- `tests/test_c5_drilldown.py` — `_with_unit`: appends dimensional unit; omits for `dimensionless`; omits when missing; passes em-dash through.
- `tests/test_p11_v11_refinements.py` — Air detail table renders unit when present; omits for dimensionless; GHG table renders the brightness unit.
- `tests/test_m_perf_a1_regression.py` — the display_unit provenance leaf is skipped by the comparator.

---

## 6. Decision-criteria walk (DC1–DC10)

- **DC1 — Three deliverables bundled.** §0.9 doc + C5 units + P-11 units in one commit on `m-docs-cleanup-a3`.
- **DC2 — §0.9 operator-approved wording.** Landed verbatim per §4.1, cross-refs mapped to the real §0.8.
- **DC3 — Engine emits `display_unit` as provenance field.** `air.py` +1 line, `ghg.py` +1 line, sourced from the config dicts; no new computation.
- **DC4 — UI minimum-change.** No row/table restructuring; units are cell suffixes only. C5 6-column schema and the P-11 HTML tables are unchanged in structure.
- **DC5 — Single source of truth.** Both C5 and P-11 read `display_unit` from `_provenance.<pillar>.<indicator>.extra`; the VIIRS card was repointed off its hardcoded literal.
- **DC6 — Units only on dimensional values.** Site value / Background / Anomaly carry units; Z / Conf / Score / HF do not. Dimensionless indicators omit the suffix.
- **DC7 — No benchmark integration.** None added; §0.9 names WHO AQG / EU AAQD / US NAAQS only as user-side interpretive frames.
- **DC8 — Item 14a closed.** Documentation-only resolution recorded in §0.9 and here; no further engine/UI work.
- **DC9 — No engine value changes.** `git diff engine/` is +8 lines, all the additive `display_unit` field + comments. Full suite green; seed-regression identity preserved via the informational-leaf skip (§4).
- **DC10 — Branch + commit pattern.** Branch `m-docs-cleanup-a3` off `main`; single atomic commit (matching the A1/A2 precedent).

---

## 7. Carried forward / out of scope

- Benchmark integration (WHO AQG / EU AAQD / NAAQS thresholds) — deferred (DC7).
- Inline "regional washout detected" row text — handled by §0.9 framing + methodology explainer (separate).
- Verbal-summary per-indicator units (Q-DC-D) — out of scope; revisit with the methodology explainer.
- Baseline JSON regeneration with EE (vs the comparator skip) — operator's option for a follow-up (§4).

---

*Closed 1 June 2026. IC v4 §0.9 framing + units in C5 and P-11. Engine adds one informational provenance field per pollutant; no scoring change. Full suite 2047 passed / 34 skipped / 0 failed.*
