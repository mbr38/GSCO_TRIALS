# M-CH4-A1 — Closed Entry

**Milestone.** Reclassify CH₄ from severity scoring to reference data (Response A).
**Status.** DONE.
**Date closed.** 30 May 2026.
**Branch.** `m-ch4-a1` (off the validation branch `ghg-odiac-oco-validation`, so the cited `docs/ghg_odiac_validation.md` is present).
**Authority.** `M-CH4-A1_spec.md` v2.0; `docs/ghg_odiac_validation.md` §1/§6.1/§10 (evidence); operator Step-B decisions (30 May 2026).
**Tests.** Full suite green — 1898 passed, 28 skipped.

---

## Summary

CH₄ has left the severity-scoring system entirely and joined Hansen + ODIAC as the third reference-data indicator. The GHG composite renormalised from three live terms to two (`0.815·Combustion_Proxy + 0.185·Activity_Score`), VIIRS-driven combustion now dominating — which the validation supports (VIIRS↔ODIAC Spearman 0.70). The CH₄ snapshot is still computed unchanged (extraction preserved, CH12); only its downstream consumption changed: it no longer feeds the composite, the spatiotemporal anomaly, the scored quality aggregates, the C4b grid, the trend view, or the verbal summary, and it now renders as a muted reference card in C5 and a reference row in P-11.

---

## Two operator decisions that overrode the spec

1. **Confidence-family → `single_snapshot`** (Step B). The spec/CH4 framing emphasised CH₄'s live-window cadence asymmetry; the operator chose full reference-data consistency instead. **Implementation nuance:** `INDICATOR_CONFIDENCE_FAMILY["ghg.ch4"]` is now `single_snapshot` (this drives **only** the P-09 confidence *explanation text* — verified it is consumed nowhere else). CH₄ was **deliberately NOT** added to `SINGLE_SNAPSHOT_INDICATORS`, because that frozenset drives N_valid→confidence *math* in `engine/core/confidence.py` and CH₄ retains genuine per-day TROPOMI observations — mislabelling it would corrupt the live value. The card's date-stamp shows the screening window (`Data window: YYYY-MM-DD – YYYY-MM-DD`), preserving the cadence transparency the asymmetry called for.
2. **P-11 → CH₄ included** (Step B), overriding spec **CH7** / operator answer Q-4 (which said "no PDF inclusion"). CH₄ now appears as a third row in the P-11 "Reference datasets" section, treated identically to Hansen + ODIAC.

---

## CH1–CH14 verification

- [x] **CH1 — Wholesale reclassification (not "remove + caveat").** CH₄ joins Hansen + ODIAC via the same `_ReferenceCardFields` / `_render_reference_card` machinery in `ui/components/c5_drilldown.py` (`_ch4_card_fields`, `_ch4_window_line`).
- [x] **CH2 — Removed from C4b grid.** CH₄ `_TileSpec` deleted from `ui/components/c4b_kpi_grid.py::_TILES` (14→13 tiles; ghg 2→1). Regression tests `test_hansen_and_odiac_not_in_headline_grid` (extended to CH₄) + `test_visible_tiles_ch4_yields_no_tile`.
- [x] **CH3 — Added to C5 reference section.** Third card, 2-col → 3-col layout, matching the M-UI-A6 pattern. Tests `test_ch4_reference_card_fields`, `test_ch4_reference_card_missing_value`.
- [x] **CH4 — Date-stamp metadata on all three cards.** Hansen + ODIAC already surfaced `vintage_line`; CH₄ adds a `Data window: …` line sourced from `_provenance.ghg.ch4.time_range` (the screening window — the cadence asymmetry).
- [x] **CH5 — No P-05 flagging.** No banner / info-icon / caveat copy added. (The tool hasn't shipped to a prior-mental-model audience.)
- [x] **CH6 — No trend view for CH₄.** `ghg.ch4` removed from `TREND_SERIES_INDICATOR_IDS`; `is_series_indicator("ghg.ch4.*")` now False. Test moved CH₄ to the excluded parametrize list.
- [x] **CH7 — PDF inclusion → OVERRIDDEN to included** (see above). CH₄ is a row in P-11's reference-datasets block. Tests `test_pdf_section_includes_ch4_reference_row`, missing-values count 2→3.
- [x] **CH8 — No verbal-summary inclusion.** `ghg.ch4_context_adjusted` removed from `_GHG_DOMINANT_CANDIDATES` and its slot formatter deleted (`engine/verbal_summary.py`); doc template + worked example updated to a CO₂-dominant example.
- [x] **CH9 — P-09 entry restyled.** `demo/indicator_library.json::ghg.ch4.score` reframed to the reference pattern (why-reference + validation citation + "Future work: MethaneSAT/GHGSat" per Q-CH-B = yes). The "Parameters & calibration" section now auto-omits (no parameters resolve — see CH11). Test `test_ch4_has_no_scored_parameters`.
- [x] **CH10 — Composite renormalisation.** `CORE_GHG_AUDIT_SUPPORT_WEIGHTS = {combustion 0.815, activity 0.185}` (sums 1.00). Tests `test_two_term_weighted_sum_post_m_ch4_a1`, `test_ch4_not_in_composite_weights`.
- [x] **CH11 — Parameter-registry exit.** **Finding (deviation from the spec's premise):** there were *zero* CH₄-specific `_INVENTORY` entries — CH₄ only appeared inside shared `applies_to` lists. Removed `ghg.ch4` from 8 lists in `engine/constants.py` + 1 in `engine/parameter_registry.py`'s docstring example region (actually the live ones) + the `SEVERITY_BANDS` list in `ui/components/severity.py`. **Inventory size is unchanged (23)** and the `test_honest_tier_distribution` lock still passes — contrary to CH11's "inventory shrinks". Documented here as the actual outcome.
- [x] **CH12 — Engine extraction preserved.** `compute_ch4_snapshot` and the `run_pillar` CH₄ path are untouched; all nine `ghg.ch4.*` measurements + provenance still emit. Test `test_full_payload_with_air_keys_injected` asserts the measurements present *and* the two CH₄ scored sub-aggregates absent.
- [x] **CH13 — Seed regeneration.** All 5 seeds regenerated (see movement table below).
- [x] **CH14 — Documentation.** `Indicators_Computation_v4.md` §2.3 (formula, change-note, worked example) + `Verbal_Summary_Templates_v1.md` updated. **Audit-doc sync flagged** (see below) — not modified, per CLAUDE.md.

---

## Thorough-removal decision (Step B)

CH₄ was removed from **all** scored aggregates, not just the composite:
- `_GHG_PER_INDICATOR_QA_KEYS`: `(ch4, co2, viirs)` → `(co2, viirs)`.
- `compute_ghg_spatiotemporal_anomaly`: CH₄ excluded (now VIIRS-only; CO₂ has no `.z`).

**Note:** `compute_ghg_spatiotemporal_anomaly`'s docstring previously claimed "only CH₄ has a `.z`" — stale; VIIRS emits a `.z`, so the aggregate survives on VIIRS after CH₄'s removal. `compute_fire_or_regional_transport_risk` is now computed-but-unconsumed (its only consumer was `ch4_context_adjusted`) — left in place (Air-borrowed, cheap, reserved).

---

## Step D — seed movement (CH13)

Regenerated deterministically by re-running `recompute_ghg_aggregates` + the composite on each stored payload (pure functions of the unchanged per-indicator values — no EE round-trips, so the movement is the *isolated* effect of the reclassification, free of EE-data drift). Script: `tools/regen_m_ch4_a1_seeds.py`.

| Seed | core_audit_support | spatiotemporal_anomaly | audit_followup_priority | composite | confidence |
|---|---|---|---|---|---|
| amazon | 0.028 → 0.051 | 0.139 → 0.278 | 0.205 → 0.292 | 0.228 → 0.257 | 0.752 → 0.752 |
| brasilia | 0.171 → 0.245 | 0.232 → 0.380 | 0.320 → 0.420 | 0.274 → 0.308 | 0.750 → 0.750 |
| norilsk | 0.384 → 0.712 | 0.500 → 1.000 | 0.512 → 0.848 | 0.423 → 0.535 | 0.720 → 0.720 |
| patagonia | 0.380 → 0.703 | 0.500 → 1.000 | 0.519 → 0.843 | 0.474 → 0.582 | 0.776 → 0.776 |
| suape | 0.019 → 0.036 | 0.096 → 0.192 | 0.203 → 0.257 | 0.253 → 0.272 | 0.741 → 0.741 |

**All movements are upward, and defensible.** Two drivers, both consequences of the locked decisions:
1. **Composite reweight** — combustion's weight rose 0.44 → 0.815, so its score now carries the GHG composite (VIIRS-driven, the validated channel).
2. **VIIRS-only anomaly** — `spatiotemporal_anomaly` was `mean(ch4.z, viirs.z)`; with CH₄ gone it equals the VIIRS nightlight anomaly alone. Because VIIRS.z exceeded CH₄.z at every seed, the mean was being *diluted by the CH₄ noise the validation identified*. Removing it sharpens the real signal — the anomaly term rises (doubling at norilsk/patagonia, where VIIRS saturates to 1.0). This is the intended effect of treating CH₄ as unreliable, not a regression.

**Composite confidence is unchanged at all 5 seeds** — GHG was not the conservative-min limiting pillar, so dropping CH₄'s QA term did not move the composite confidence.

These shifts are accepted per the locked "accept defensible movement" disposition. The largest mover (norilsk/patagonia composite +0.11) reflects a genuine VIIRS anomaly previously masked by CH₄ averaging.

---

## Flag — audit-doc sync (M-V1x-RECONCILE)

`docs/Indicators_Audit_and_v1x_Roadmap.md` is the v1.x master and was **not** modified (CLAUDE.md: no audit-doc edits without explicit confirmation). The CH₄ reclassification is a v1.x indicator decision analogous to the Hansen/ODIAC demotions it records, so the audit doc likely warrants a sync entry (a new row noting "CH₄ → reference data, M-CH4-A1, evidence in ghg_odiac_validation.md §10"). **Proposed for operator confirmation** rather than applied here.

---

## Out of scope (unchanged, per spec §9)

M-DIAG-A4 (denominator fix); higher-resolution methane (MethaneSAT/GHGSat) and plume detection (v2); time-domain (Option G) and lower-threshold (Option C) CH₄ detectors (both eliminated by evidence); other GHG indicators; Hansen/ODIAC scoring.
