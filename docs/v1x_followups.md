# v1.x follow-ups

> **SUPERSEDED (22 May 2026, M-V1x-RECONCILE).** As of M-V1x-RECONCILE,
> `docs/Indicators_Audit_and_v1x_Roadmap.md` v1.5 is the master source
> for v1.x indicator decisions. This document is preserved as the
> historical record of individual follow-up entries up to that date.
> Items listed here are now consolidated under the audit doc's Tier A–F
> roadmap. Future entries should be added to the audit doc, not here.
>
> **One open follow-up logged after the rename (not in the audit doc):**
> `Indicator_ID_Schema_v2.md` §4.6 declares engine-orphan IDs that the
> engine doesn't emit — `nature.bare.area_now_ha` / `.area_now_pct` /
> `.expansion_ha`, `nature.built.area_now_ha` / `.area_now_pct`,
> `nature.water.area_now_pct`, `nature.water.dist_km`. Pick one of:
> (a) implement the missing reducers in `engine/nature.compute_water_exposure`
> and a new bare/built reducer (~1–2 hr work); (b) remove the orphan
> IDs from Schema_v2 §4.6 (5 min). Decision deferred to a separate
> small milestone.
>
> **Add confidence_terms to _DEFAULT_SIX_STEP to enable integration testing of pillar QA sub-score re-derivation paths.**
> M-TIER-A1 made the GHG_DQA sub-scores (`temporal_coverage`,
> `spatial_resolution_suitability`, `retrieval_inventory_quality`) and
> Nature's `valid_pixel_coverage` derive from per-indicator
> `confidence_terms` (qa / n_valid / anomaly_strength / spatial_context)
> stored in each indicator's `_provenance.<pillar>.<indicator>.extra.confidence_terms`.
> The integration-test fake in `tests/test_air.py::_DEFAULT_SIX_STEP`
> still has the pre-A1 9-key shape and lacks `confidence_terms`, so all
> three pillars' `_format_result` functions take the graceful-absence
> branch (the dict is omitted from provenance.extra) and the pillar
> QA sub-score derivations compute to None across the board in CI. The
> consumers correctly handle absence so nothing breaks, but the
> post-A1 rollup paths aren't exercised. Fix: update `_DEFAULT_SIX_STEP`
> to include a representative `confidence_terms` dict (and parallel
> updates for any GHG/Nature integration fakes that follow the same
> pattern). Pre-existing gap; surfaced by M-TIER-A1 Step B 23 May 2026.
>
> **Status (M-TIER-A1 Step D, 23 May 2026):** `_DEFAULT_SIX_STEP` in
> `tests/test_air.py` now carries `confidence_terms` (closed for the
> Air pillar's snapshot path). The GHG and Nature pillar test fakes
> are still open — see the dedicated entry below.
>
> **[CLOSED — M-TIER-A1 Step E, 23 May 2026] Thread confidence_terms through GHG/Nature pillar fakes (_fake_ch4_snapshot et al.) to enable integration-test coverage of pillar QA sub-score re-derivation paths.**
> Resolved by M-TIER-A1 Step E. `_fake_ch4_snapshot`,
> `_fake_viirs_snapshot`, and the inline `_fake_co2_snapshot` in
> `tests/test_ghg.py` now emit `extra.confidence_terms` in their
> provenance blocks; the eight Nature fakes in
> `tests/test_nature.py::_patch_all_indicators` now each return a
> complete 15-field-shaped `_provenance.nature.<ind>` block with
> `extra.confidence_terms`. Each fake's `confidence` field is
> mathematically consistent with `formula(confidence_terms)` to
> match the D1 consistency lesson. CI now exercises the GHG_DQA and
> Nature `valid_pixel_coverage` re-derivation end-to-end:
> `ghg.data_quality_attribution` is now ~0.83 in integration tests
> (was an artificial 1.0 from single-survivor renormalisation);
> `nature.valid_pixel_coverage` is now ~0.85 (was None). Original
> entry preserved below for reference.
>
> **Thread confidence_terms through GHG/Nature pillar fakes (_fake_ch4_snapshot et al.) to enable integration-test coverage of pillar QA sub-score re-derivation paths.**
> M-TIER-A1 Step D D1 added `confidence_terms` to
> `tests/test_air.py::_DEFAULT_SIX_STEP`, closing the integration-test
> gap for the Air pillar's confidence flow. The GHG pillar's test
> fakes (`_fake_ch4_snapshot` / `_fake_viirs_snapshot` /
> `_fake_co2_snapshot` in `tests/test_ghg.py`) mock at
> `compute_ghg_indicator_snapshot` / `compute_co2_snapshot` — one
> level above six_step — and their provenance dicts lack
> `extra.confidence_terms` entirely. Same gap on the Nature side
> wherever the pillar's `compute_*` functions are monkey-patched.
> D3.1 (M-TIER-A1 Step D, this milestone) adds *direct* unit-test
> coverage of the re-derivation functions (`compute_temporal_coverage`,
> `compute_spatial_resolution_suitability`,
> `compute_retrieval_inventory_quality`, Nature's
> `compute_nature_quality_sub_scores`), so the formula correctness is
> pinned in CI. What remains uncovered is the *integration* flow —
> i.e. that real `run_pillar` invocations propagate per-indicator
> confidence terms through to the pillar's QA sub-scores end-to-end.
> Fix: extend the GHG/Nature fakes to carry a representative
> `extra.confidence_terms` dict the same way `_DEFAULT_SIX_STEP` now
> does. Small standalone follow-up; logged here so it doesn't get
> lost.

> **Scope (historical).** This doc collects v1.x deferrals from across milestones, not
> just M5.5. The original "M5.5 follow-ups" header was retired when the
> list outgrew its origin; the M5.5/M5.5b/M5.5c/M5.6 sections below are
> preserved verbatim for historical context.

---

## M-TIER-A1 — closed 23 May 2026

**Summary.** Replaced the placeholder flat per-pillar confidence values (~1.0 / 0.7 / 0.8 across Air, GHG, Nature) with a real per-indicator confidence formula that aggregates to the pillar level via the existing weight dictionaries. Per audit §1.1, this was the single most important v1.x defensibility item — every confidence dot, every verbal-summary tier, and `composite.confidence = min(...)` had been uninformative placeholders since v1 launch.

After this milestone:
- Every single-value indicator emits a real `<indicator>.confidence` via the universal 4-term additive formula `c_raw = 0.30·QA + 0.30·N_valid + 0.25·anomaly_strength + 0.15·spatial_context`, then `c_final = c_raw × COLUMN_TO_SURFACE_MULTIPLIER[uncertainty_tag]`.
- Pillar-level aggregates recompute from per-indicator inputs via existing `*_QUALITY_ATTRIBUTION_WEIGHTS` dicts (audit doc §1.5 / §6.3.2 rollup pattern preserved).
- `composite.confidence = min(...)` becomes genuinely informative; produces realistic 0.60-0.80 values for typical sites rather than the prior 0.7 floor.
- Static `column_to_surface_uncertainty` multipliers are applied per audit §1.5, so NO₂ confidence > CO confidence on identical-quality observations even before BLH lands in Tier C1b.
- Hotspot Frequency is computed server-side over the full time window — no `.limit(N)` cap on the per-image map — restoring correct per-date semantics for multi-swath products (MAIAC AOD, S5P L3 CH4) per IC_v4 §0.2 step 5.

**Design decisions locked.** Eight decisions from the A1 design conversation (22 May 2026):

| # | Decision | Lock |
|---|---|---|
| Q1 | Granularity | Per-indicator + per-pillar |
| Q2 | Term combination | Additive |
| Q3 | anomaly_strength | HF-based (hotspot frequency) |
| Q4b | Existing pillar sub-score dicts | Survive, recomputed from per-indicator inputs |
| Q5 | composite.confidence rule | Keep `min(...)` |
| Q6 | Missing-term propagation | Strict-None at indicator level; survivor-renormalise at pillar level |
| Q7 | column_to_surface_uncertainty | Fold static multiplier into A1 |
| Q8 | Test fixtures | Synthesised for formula correctness; EE-snapshot goldens for integration |

**Step 8 recalibration and engine-architecture sub-milestones.** What was originally scoped as a one-hour calibration check unfolded into a 5-step sub-milestone (Steps A through E plus a critical Option-A fix), each of which uncovered and addressed a real engine issue masked by the prior placeholder confidence:

- **Step A — strict-None at n_valid=0.** Locked the design: zero observations propagates as None (no information), not 0.0 (perfect-bad coverage). Added 2 canary tests.
- **Step B — server-side HF computation.** Replaced the legacy `_per_date_site_series` with `_server_side_hf`, removing the `.limit(100)` cap that had been silently truncating coverage for every multi-image-per-day product since v1 launch. Killed the dead client-side trend code path (`engine/core/trend.py` doesn't exist; the consumer was always returning None — confirmed by inspection).
- **Step C — pre-flight smoke test + diagnostic.** Smoke test caught two real EE bugs in `_server_side_hf` that no CI test would have surfaced: (1) `ee.Dictionary.get(key, default)` returns null when key is present-but-null (masked-band case); fixed via combined Mean+Count reducer. (2) `ee.Algorithms.If(...)` evaluates both branches eagerly server-side; fixed via `default=0.0` on the lookup. **Both bugs would have shipped silently broken.** The Brasilia/Rotterdam diagnostic confirmed the `.limit(100)` cap was the dominant cause of zero-observation readings (Brasilia AOD: 0 → 107 valid samples; Rotterdam AOD: 1 → 169) — the "wet-season masking" story was wrong; we just had a sampling bug.
- **Step D — close the Air pillar integration-test coverage gap.** Updated `_DEFAULT_SIX_STEP` to carry `confidence_terms`, exposing the pillar QA sub-score re-derivation paths to CI for the first time. Added 11 new tests (`test_pillar_confidence_rollup.py` D3.1 + `test_repeatable_core.py` D3.2). D3.2 specifically defends against the two Step C EE bugs via faithful EE-semantic mocks — one test was even refactored mid-creation when its first mock was too lenient to catch the regression it targeted.
- **Step E — close GHG and Nature pillar integration-test coverage gaps.** Threaded `confidence_terms` through `_fake_ch4_snapshot`, `_fake_viirs_snapshot`, `_fake_co2_snapshot`, `fake_kba`, and six Nature fakes. Surfaced an interesting pre-existing artefact: `ghg.data_quality_attribution` had been reading as ~1.0 in integration tests because single-survivor renormalisation pushed the only non-None sub-score (`nearby_source_isolation = 1.0` placeholder) to full weight — a misleading signal hidden by defensive "is not None" assertions. Post-E, GHG_DQA lands in the realistic 0.7-0.8 range in CI.
- **Option-A — daily mosaic + chunked compute.** Step B's uncapped server-side HF surfaced a new problem at Distrito Federal scale: AOD's ~5,200 swath images per 90-day window pushed EE's compute graph past the 5-minute `.getInfo()` timeout. Implementation: per-image Feature tagged with `day_bucket` (UTC midnight-to-midnight); FeatureCollection-level distinct-day counting via `aggregate_array().distinct()`; client-side date chunking at `_SERVER_SIDE_HF_CHUNK_DAYS = 10`. Also corrected a latent semantic bug: `_server_side_hf` had been counting granules as `n_valid`, overcounting independent information by ~58× for MAIAC and ~14× for S5P L3 CH4. Post-fix, `n_valid` correctly represents distinct UTC dates. Surfaced `granule_count` in `provenance.extra` for audit transparency (informational only, not in any score arithmetic).

**Real Step 8 — recalibration verdict.** Sapezal Plantation and Distrito Federal re-screened against the full post-fix pipeline:

| | Sapezal | Brasilia | Healthy band |
|---|---|---|---|
| `air.attribution_confidence_score` | 0.699 | 0.699 | 0.65-0.80 ✓ |
| `ghg.data_quality_attribution` | 0.685 | 0.775 | 0.65-0.80 ✓ |
| `nature.quality_attribution` | 0.795 | 0.799 | 0.65-0.80 ✓ |
| `composite.confidence` | **0.685** | **0.699** | 0.60-0.80 ✓ |

Distribution sanity checks all pass: per-indicator spread is 0.27-1.00 (wide and intuitive); NO₂ confidence (0.684) > CO confidence (0.564) shows the multiplier effect working as designed; static-snapshot indicators (KBA, Hansen, regional_loss_evidence) saturate at 1.0; live-revisit indicators distribute across the band based on actual coverage; no silent dropouts that look like bugs (CO₂ skipping is `out_of_coverage` per ODIAC's 2020-2023 vintage, expected; PM₂.₅/PM₁₀ None is pre-existing, separate issue). `CONFIDENCE_FORMULA_WEIGHTS` did NOT require iteration — the 0.30/0.30/0.25/0.15 structure landed in the healthy range at first try.

**Test trajectory.**
- Entering milestone: ~1013 passed
- After M-TIER-A1 core: 1063 passed (+50: 32 formula + 17 pillar rollup + 1 GHG_DQA rewire)
- After Step A: 1065 (+2 strict-None canaries)
- After Steps B, C: 1065 (no test count change; smoke-test caught EE bugs that CI couldn't have surfaced)
- After Step D: 1076 (+11: 7 D3.1 pillar re-derivation tests + 4 D3.2 server-side HF tests)
- After Step E: 1076 (no count change; existing tests' defensive "is not None" assertions absorbed the value shifts)
- After Option-A: 1076 (test infrastructure extended with `_FakeFilter`, `_FakeList`, etc. for the chunked-aggregation path)

**Final state: 1076 passed, 8 skipped, 0 failures.**

**Deliverables.**

*Engine:*
- `engine/constants.py` — `CONFIDENCE_FORMULA_WEIGHTS` (0.30/0.30/0.25/0.15), `SPATIAL_CONTEXT_THRESHOLD = 3.0`, `COLUMN_TO_SURFACE_MULTIPLIER` (1.00/0.95/0.88/0.80/1.00), `QA_PER_INDICATOR`, `EXPECTED_N_PER_WINDOW_DAY` (TROPOMI gases at 0.3 after Step 8 recalibration), `SINGLE_SNAPSHOT_INDICATORS`, `NATIVE_PIXEL_AREA_M2`.
- `engine/core/confidence.py` (new, ~230 LOC) — universal additive formula × column multiplier; per-term helpers; survivor-renormalise pillar rollup with optional weight dict.
- `engine/core/repeatable_core.py` — `_server_side_hf` server-side computation; `_daily_mosaic_by_utc_day` helper; `_date_chunks_iso` for client-side chunking; legacy `_per_date_site_series` deprecated. `six_step` returns `confidence_terms` dict and surfaces `n_valid_dates` + `granule_count` in provenance.extra.
- `engine/{air,ghg,nature}.py` — per-indicator confidence wiring; GHG_DQA sub-scores re-derived from per-indicator A1 terms read from `provenance.extra.confidence_terms`; Nature `valid_pixel_coverage` recomputed from per-indicator QA; `_single_snapshot_confidence_terms` helper for non-six_step indicators.

*Docs:*
- `docs/Indicators_Computation_v4.md` v4.1 → v4.2: new §8 "Confidence (M-TIER-A1)" with canonical formula, per-term definitions, column-to-surface multiplier table, per-pillar rollup logic, composite rule, `provenance.extra` audit hook.
- `docs/Indicator_ID_Schema_v2.md` v2.1 → v2.2: footnote on `column_to_surface_uncertainty` row noting dual role as A1 confidence multiplier (single source of truth).
- `docs/provenance_schema.md`: extra-field surfacing of `n_valid_dates` and `granule_count` documented.

*Tests:*
- `tests/test_confidence_formula.py` (new, 32 tests) — per-term helpers, canonical universal-weight tests (perfect / NO₂-moderate / CO-weak / missing-term), HF=0 drag, multiplier dispatch parametrised over 10 indicator/uncertainty pairs, strict-None at n_valid=0 lock.
- `tests/test_pillar_confidence_rollup.py` (new, 24 tests: 17 from M-TIER-A1 core + 7 from Step D) — `compute_pillar_confidence` semantics, GHG_DQA sub-score derivation, Nature `valid_pixel_coverage` recompute, strict-None propagation when one indicator has no confidence_terms.
- `tests/test_repeatable_core.py` (new section, 4 D3.2 + 1 Option-A tests) — `_server_side_hf` EE-bug coverage via faithful `_FakeDict` / `_FakeFilter` / `_FakeList` mocks; daily-mosaic multi-image-per-day collapse.
- `tests/test_ghg.py` and `tests/test_nature.py` — fake snapshots threaded with `confidence_terms`; mathematical-consistency lock (`confidence == formula(terms)`).
- `tests/test_air.py` — `_DEFAULT_SIX_STEP` now provides `confidence_terms`; one direct-assertion update for the consistency requirement.

*Diagnostic scripts (for future regression):*
- `tools/diag_aod_ch4_zero_obs.py` — initial diagnostic at Brasilia.
- `tools/diag_aod_ch4_controls.py` — Rotterdam control + Brasilia point-sample.
- `tools/diag_aod_ch4_step8.py` — post-Option-A end-to-end.
- `tools/smoke_server_side_hf.py` — pre-flight EE smoke test (caught the two Step C bugs).

*Plain-language explainer:*
- `docs/M-TIER-A1_plain_language_explainer.md` — non-technical walkthrough of the whole story for non-engineer audiences.

**Followups logged for v1.x.**

1. **Performance: variable chunk size per indicator.** Current `_SERVER_SIDE_HF_CHUNK_DAYS = 10` is tuned to avoid Distrito Federal's per-chunk EE timeout, but creates 9 sequential chunks for every indicator including those (TROPOMI gases, MODIS NDVI) that have ~1 image/day and don't need chunking at all. Sapezal screening currently takes ~7 minutes total, dominated by 450s on AOD's 9 chunks. Fix: per-indicator chunk-size lookup in `engine/constants.py`; full-window for low-cadence products, 10-day chunks only for AOD + CH4. Estimated 1-2 hours. Big small-buffer win.

2. **Performance: consider parallel chunks within an indicator.** Independent chunks of the same indicator could run concurrently via `ThreadPoolExecutor`. Would further reduce single-slow-indicator dominance. Estimated 3-4 hours. Defer pending whether (1) above is sufficient.

3. **UX: drop AOD and CH4 from default indicator selection at small buffers.** Both are methodologically weak at sub-10 km scales and contribute most of the per-screening compute cost. Letting users opt in rather than opt out would dramatically improve default UX.

4. **PM₂.₅ / PM₁₀ persistently None at both demo sites.** Pre-existing engine issue, separate from A1. CAMS coverage at Brazilian latitudes or a band/QA filter issue. Worth a brief investigation.

5. **`composite.overall_screening` rank-order:** Brasilia (0.213) currently ranks above Sapezal (0.179) on the headline screening score. This is the *opposite* of the intended demo narrative ("high-priority Amazon vs low-priority capital region"). Separate from A1 — likely a sub-aggregate weight or calibration issue downstream of the pollution/habitat scores themselves. Worth a deliberate "demo calibration" pass before any external demo.

6. **`nature.dw.class_confidence` lands at 0.47-0.49 at both demo sites** — lowest Nature sub-score by margin. Sanity check that DW probability outputs are wired correctly.

7. **`_SERVER_SIDE_HF_CHUNK_DAYS = 10` constant tuning** — chosen empirically; sensitivity analysis recommended for Tier B1 alongside the confidence formula weights.

8. **Tier C1b — BLH-aware `column_to_surface_uncertainty` multiplier.** Currently a static enum lookup (audit §1.5 table). Once ERA5 wind/BLH ingest lands, replace static multiplier with BLH-modulated values. Extension point is `engine/constants.py:COLUMN_TO_SURFACE_MULTIPLIER`.

9. **`CONFIDENCE_FORMULA_WEIGHTS` calibration.** Current values 0.30/0.30/0.25/0.15 chosen on first principles; landed healthy at first try. Tier B1 sensitivity analysis should verify ±0.05 perturbations don't flip demo-site rankings.

10. **Saved-analyses regeneration.** Sapezal and Brasilia JSONs from the Step 8 verification run (23 May 2026) can be promoted to `demo/saved_analyses/high_priority_amazon.json` and `low_priority_brasilia.json` directly — they already reflect the post-Option-A pipeline.

**Unblocks.**

- **Tier A2 (trend engine).** `engine/core/trend.py` skeleton can now be built with the per-date semantic conventions established in Option-A. The placeholder M-FOLLOWUP-FALLBACK in Vegetation_Condition can be removed.
- **Tier B1 (sensitivity analysis).** Has concrete targets: `CONFIDENCE_FORMULA_WEIGHTS`, `COLUMN_TO_SURFACE_MULTIPLIER` values, `_SERVER_SIDE_HF_CHUNK_DAYS`.
- **Tier C1a / C1b / C2 (sector, wind, BLH).** All have clearly defined extension points in the A1 surface: `confidence_terms` dict structure, multiplier lookup table, `sector_signal_anomaly` provenance flag.
- **P-09 Indicator Library cards.** Can now display real per-indicator confidence values + the four constituent terms via `provenance.extra.confidence_terms`. Previously the cards had nothing meaningful to show.
- **P-05 / P-11 confidence dots.** Tell a real story for the first time.
- **Verbal summary tiering.** `composite_confidence_bucket` (`high ≥ 0.66`, `moderate 0.33-0.66`, `low < 0.33`) now corresponds to actual data quality.

**Methodological honesty notes (worth preserving).**

- The HF-based `anomaly_strength` (Q3=B) produces honest-but-occasionally-counterintuitive pairings at quiet sites: a supplier with low pollution and low HF gets "low priority, with moderate confidence — limited anomaly evidence in the observation window." This is the locked behaviour per Risk R2; verbal-summary template language already accommodates it.
- The strict-None lock at n_valid=0 (Step A) drops genuinely-zero-observation indicators from pillar rollups via survivor-renormalise. This is a deliberate "no data, no claim" semantic and is the right behaviour, but it means low-coverage indicators (e.g. CH4 at cloudy AOIs) silently absent themselves rather than producing very-low confidence. P-05 UI consumers should distinguish "indicator skipped due to zero coverage" from "indicator reported low confidence."
- The `column_to_surface_uncertainty` multiplier is a defensible v1 calibration based on audit §1.5 framing, not an empirical fit. Sensitivity analysis (Tier B1) should confirm the chosen values don't unduly suppress NO₂ confidence relative to CO at sites where NO₂ is the dominant indicator.
- The pre-fix "Brasilia AOD has 107 valid observations" finding from the Step C diagnostic was a granule count, not a date count. All comparisons of pre-fix to post-fix observation counts must account for this — granule counts and date counts are not the same unit.

*Closed by claude.ai planning session, 23 May 2026. Anchored to `Indicators_Audit_and_v1x_Roadmap.md` v1.5 §1.1 + §6 Tier A1. Authoritative for M-TIER-A1 milestone state.*

---

## Pillar-wide EE errors surface as raw server-side strings (M-UI-E.1)

**Update (M-NATURE-DEFENSIVE, May 2026).** The *expected* empty-result
case is now handled — every Nature reducer materialises EE dicts
client-side and falls through to a canonical skipped-result payload
with `skipped_reason` populated (`no_dw_pixels`, `no_hansen_pixels`,
etc.). The Altamira-style `Dictionary.get: Dictionary does not contain
key: 'label'` crash is fixed.

**Update (M-AIR-GHG-DEFENSIVE, May 2026).** Same pattern applied to
Air and GHG via a new `SiteBufferNoDataError` subclass: site-buffer
empties now route through the silent-skip payload with asset-family
codes (`no_s5p_pixels`, `no_cams_pixels`, `no_maiac_pixels`,
`no_viirs_pixels`) instead of bubbling as `_failures` entries. The
Acre-style E1_AllFailed silent crash is fixed. Combined with
M-NATURE-DEFENSIVE and M-OCEAN-RING, the engine now covers every
expected empty-data cause across all three pillars — site empty,
ring empty, asset coverage window — with user-readable per-indicator
reasons in C4b / C9.

The *unexpected* case — EE call literally fails (network error, asset
rename, planner timeout) — still bubbles up as a raw `ee.EEException`
to the UI. That's the v1.x scope below. Lower priority now that all
three pillars handle the common expected-empty cases.

Discovered during the P-05 smoke test of the `E1_AllFailed` path. Running
a screening at an ocean point (lat 0, lon -30) produced the user-facing
error `Dictionary.get: Dictionary does not contain key: 'label'` — the
raw EE server-side error from Dynamic World's `frequencyHistogram`
reducer when the buffer contains zero land pixels. M-NATURE-DEFENSIVE
made that case a silent skip instead of a crash; the same pattern fired
again at Altamira (rainforest + recent cloud cover).

The bare `except Exception` in
`pages/05_Screening_Results.py::_run_engine_and_transition` correctly
routes to `E1_AllFailed` — that part works as designed. What's still
missing is that the engine's pillar modules don't catch
`ee.EEException` and re-raise as `PillarComputeError` with sensible
context. v1 lets the raw EE string bubble to the UI for the unexpected
failure modes.

**Fix.** Wrap pillar-wide EE-touching code in `try/except ee.EEException`
inside `engine/air.py`, `engine/ghg.py`, `engine/nature.py` and re-raise
as `PillarComputeError` with a context-aware message:
- Nature → *"No land cover detected in buffer — check AOI lies on land."*
- Air → *"No valid satellite observations in time range."*
- GHG → similar.

**Why this is higher value than it sounds.** Every upstream EE drift
discovered this year — CAMS band renames (M-CAMS-BAND-FIX), DW empty
results (M-NATURE-DEFENSIVE), planner stalls at region scale
(M-ADAPTIVE-SCALE) — has surfaced as a cryptic Python error to the
user before the engineering caught it. Pillar-level wrapping turns
those into "X pillar failed: <reason>" toasts so the next regression
doesn't take a user-bug-report cycle to surface.

**v1 workaround.** Document in the user guide that the tool is for
land-based suppliers, and that some indicators may be unavailable for
specific AOIs (C9 banner now surfaces this cleanly).

---

## CAMS band rename — fixed M-CAMS-BAND-FIX (May 2026)

CAMS renamed several of its ``ECMWF/CAMS/NRT`` bands between the
engine's original implementation and May 2026. v1 only consumes two
of them; both drifted:

| Pollutant | Legacy name                  | Current name                                       |
|-----------|------------------------------|----------------------------------------------------|
| PM₂.₅     | `particulate_matter_2.5um`   | `particulate_matter_d_less_than_25_um_surface`     |
| PM₁₀      | `particulate_matter_10um`    | `particulate_matter_d_less_than_10_um_surface`     |

The other v1 pollutants don't hit CAMS — NO₂ / SO₂ / CO / HCHO / O₃ /
AAI all come from Sentinel-5P (`COPERNICUS/S5P/...`) and AOD from MODIS
MAIAC. None of those band names changed. `engine/air.py` was updated
in lockstep with this milestone.

**Discovery.** Bug surfaced during the M-P0103 smoke test — running a
Rio de Janeiro region screening crashed with a `reduce.mean: Error in
map(...) band pattern did not match` message, which is CAMS's cryptic
way of saying "no band with that name". The error doesn't name the
missing band; finding the drift required listing the asset's current
band catalogue and diffing it against the engine config.

**Spec-doc reference drift (not fixed here).** The legacy band names
still appear in `docs/Indicators_Computation_v4.md` §1.1 (table rows
for PM₂.₅ and PM₁₀) and `docs/Indicator_ID_Schema_v2.md` §2.1 (same
rows). Per CLAUDE.md §8, those authoritative spec docs aren't touched
without explicit confirmation — flagging here so the next IC/Schema
version bump can refresh those rows.

**Stability note.** Upstream CAMS asset evolution isn't tracked in the
GEE catalogue's change-log. If band names drift again, screening will
fail with the same cryptic message until somebody walks the configs.
**v1.x: add a `verify_bands.py` smoke script** that lists every
pollutant's band and asserts it's present in the asset's current band
catalogue. Run as a CI step so drift surfaces before users do.

---

## Retry failed indicators from C9 (deferred M-UI-E.5)

The wireframes (§P-05 C9) describe a **"Retry failed indicators"**
action that re-runs only the failed indicator IDs from the partial-
coverage banner. Implementing it requires
`engine/orchestrator.py::run_pillar` to accept an `indicators=<subset>`
parameter and to compose subset results with the existing payload. v1
ships C9 in display-only form per Wireframes §P-08 precedent (partial
results accepted as-is).

**Scope when picked up.**
- Add `indicators` kwarg to each pillar's `run_pillar` so it only
  computes the listed slugs.
- Have the orchestrator merge the subset result into the existing
  `st.session_state.page_state.result` rather than rebuilding from
  scratch — preserves the values that did succeed on the first run.
- Add a "Retry" button to C9 wired to the new orchestrator entry
  point. Targeted at **v1.x**.

---

## Indicator map coverage — extend the C4a registry (deferred M-UI-E.6)

M-UI-E.6 ships three indicator-map renderers as a proof-of-pattern:
`air.no2.score`, `nature.kba.proximity_score`, `nature.dw.trees_pct`.
Each demonstrates one of three visualisation grammars: continuous
z-raster, vector polygons, categorical raster. Remaining indicators
all fall into one of those three grammars; adding them is a matter of
registering a new entry in
`ui/components/c4a_indicator_map.py::_RENDERERS`.

**Outstanding indicators by grammar.**

*Continuous z-raster (follow the NO₂ pattern).*
- `air.so2.score`, `air.co.score`, `air.hcho.score`, `air.o3.score`,
  `air.aai.score`, `air.aod.score`, `air.pm25.score`, `air.pm10.score`
  — all 8 use `AIR_POLLUTANT_CONFIG[slug]` for asset + band.
- `ghg.ch4.score` (Sentinel-5P CH₄), `ghg.viirs.score` (VIIRS nightlights),
  `ghg.co2.score` (ODIAC CO₂ — note coverage_window = 2020-2023).
- `nature.ndvi.score` (MODIS MOD13Q1).

*Vector polygons.* KBA is the only vector indicator in v1; no others
pending.

*Categorical / specialised.*
- `nature.habitat.natural_loss_ha` — before/after DW composite,
  highlighting natural→non-natural transitions.
- `nature.forest_loss.ha` — Hansen `lossyear` band, single-class binary
  raster filtered to the screening window.
- `nature.water.area_now_ha` — DW water class composite, similar to the
  DW renderer but filtered to a single class.

Each renderer is independent — pick up in **v1.x** as demand warrants.

---

## P-04 — activate Region and Supplier centre modes (deferred M-P04)

M-P04 ships P-04 with the Region and Supplier centre tabs disabled.
Both require a `supplyChain` object from P-02 (Scope Setup), which
isn't built yet. Activate them when P-02 lands by replacing the
informational tab content in `ui/components/p04_form.py` with the
real selectors per Wireframes_All_v4 §P-04 C1–C2.

---

## P-04 — add the time-range selector + Run Trend (deferred M-P04)

The time-range selector (C7) is hidden in screening mode per
Wireframes §P-04 C7; screening always uses the latest 90-day window.
It appears with P-06 (Trend View). When P-06 lands:

- Activate the Run Trend button in `ui/components/p04_form.py`.
- Show the time-range selector only when trend mode is selected.
- Route Run Trend → P-06 with `mode = "monitoring"` in `screening_setup`.

Targeted at the P-06 milestone, not strict v1.x.

---

## P-02 — remember last scope across sessions (deferred M-P02)

M-P02 always opens P-02 at **ModePick**, regardless of the user's
prior scope choice. v1.x could persist the last scope in localStorage
and offer "Resume with last scope" as a fourth card on ModePick.

**Why held out of v1.** The localStorage migration is already pending
for Saved Analyses (PLFS_v4 §14). Doing both at once gives a coherent
persistence story; doing one without the other risks divergent
conventions across `st.session_state` keys.

**Fix when picked up.** Decide on a serialisation format for `scope`
(SupplyChain object → JSON via `dataclasses.asdict`; Region object →
similar). On P-02 entry, read from localStorage; surface a "Resume"
card with the chain/region name + a small preview. Confirm acts as
today; "Pick a different scope" routes to the existing ModePick flow.

---

## Background ring empty — global climatology baseline (discovered M-OCEAN-RING; updated M-RING-UX)

M-OCEAN-RING + M-RING-UX surfaced the failure mode to the user as a
per-indicator silent skip with
`skipped_reason="background_ring_no_data"`, broadened the prose to
acknowledge both root causes (ring over water *or* ring over a region
with persistent cloud cover / sparse satellite overpasses), and added
a methodology-aware E1_AllFailed page that detects the "every
indicator skipped via ring-empty" case and renders concrete try-this
suggestions (smaller buffer, Free Coordinates). What's left for v1.x
is fixing the underlying methodology, not the user-facing messaging.

Two distinct triggers fall under the same code path:

- **Ring over water.** Coastal AOIs (Rio de Janeiro at 281 km buffer →
  562 km ring, largely Atlantic): assets with no over-water values
  trip the skip even though the site buffer itself is over land.
- **Ring over sparse-coverage region.** Very large inland AOIs in
  tropical or polar regions (Acre, ~220 km buffer, deep Amazon):
  persistent cloud cover + sparse Sentinel-5P overpass density means
  the ring has no usable pixels in the screening window. M-RING-UX is
  what surfaced this case clearly; previously it bubbled to E1 as
  "All pillars returned no data".

In both cases the indicator's site value can sometimes be computed
cleanly but no z-score is possible because the ring has no baseline.
The screening either completes with Failed tiles in C4b (when some
indicators get past the ring path) or routes to E1_AllFailed (when
every selected indicator trips it).

**v1.x options.**

1. **Land-mask the ring.** Intersect the background ring with a global
   land mask before reducing — e.g. `ee.Image('users/.../land_mask')`
   or the static `OCEAN` band on a standard reference asset.
   Methodologically uncomplicated; just shrinks the effective ring
   area. Fixes the water case but not the sparse-coverage case.
   Risk: for purely-coastal AOIs the masked ring may be too small to
   produce a stable stdDev.
2. **Substitute a regional climatology baseline.** When the ring
   reduces to no usable pixels, fall back to a pre-computed regional
   median / stdDev for the same band — e.g. national-mean S5P NO₂ for
   the AOI's country. Fixes both the water case AND the sparse-coverage
   case. More defensible scientifically but requires per-indicator
   climatology references (S5P, CAMS PM, etc.) and a versioning /
   vintage story for them. Real R&D.

Option (1) is a quick v1.x ship for the coastal case; option (2) is
the right long-term answer once climatology fixtures exist and is the
only path that fixes Acre-style cases. Either way, the affected
indicators should emit a real z-score + score; today they emit None
and surface as Failed (or trigger E1).

---

## Compute `nature.vegetation_condition` aggregate (discovered M-NATURE-KEYS)

The Nature follow-up priority formula carries a **Vegetation condition**
term (weight 0.25, per `Indicators_Computation_v4.md` §3.3 and
`engine.constants.NATURE_FOLLOWUP_WEIGHTS`). The aggregate is wired in
`engine.nature.compute_vegetation_condition`, but its `negative_trend`
component depends on `nature.ndvi.negative_trend`, which is `None`
until `engine/core/trend.py` lands (M-TREND-ENGINE — the
`_trend = None` fallthrough in `engine/core/repeatable_core.py`).

**Current v1 behaviour (post-M-FOLLOWUP-FALLBACK).** The aggregate now
substitutes `0.0` for the known-zero `negative_trend` term and
computes from the three remaining components
(`nature.ndvi.inverted_anomaly`, `nature.low_ndvi.pct_norm`,
`nature.recovery.score`). So the aggregate is no longer perpetually
None — it produces a real value, but with one of four weighted terms
effectively zero. The Nature priority is therefore slightly
*under-weighted on vegetation* in v1: the 0.25 weight on
`negative_trend` contributes nothing until trend.py lands.

**Fix when picked up.** Land `engine/core/trend.py` per the existing
M-TREND-ENGINE scope (Theil-Sen slope + Mann-Kendall p-value over a
time series). Once `nature.ndvi.negative_trend` returns real floats,
the substitution in `compute_vegetation_condition` becomes a no-op
(the term is no longer None) and the formula's 0.25 weight pulls real
signal through. Remove the `M-FOLLOWUP-FALLBACK` known-zero
substitution at that point — it's tagged with a `TODO(M-TREND-ENGINE)`
comment in `engine.nature`.

The M-NATURE-KEYS canary
([tests/test_formula_keys_match_engine.py](../tests/test_formula_keys_match_engine.py))
ensures the key alignment stays correct as trend.py lands; the existing
sub-aggregate tests in `tests/test_nature.py` already cover the
weighted-sum logic once dependencies are populated.

---

## GAUL 2015 deprecation watch (discovered M-DEMO-DATA)

`demo/regions.py` uses `FAO/GAUL/2015/level1` as the source of
administrative boundaries. FAO has since published GAUL 2024 and
points users to GADM as the authoritative successor; the GAUL 2015
EE asset is stable but unmaintained. Administrative boundaries
haven't shifted meaningfully for v1 demo countries, so this is v1.x
housekeeping rather than a blocker.

**Fix when picked up.** Migrate the asset reference in
`demo/regions.py::_GAUL_LEVEL1_ASSET` to whatever GEE catalogue entry
replaces it. Surface fields may differ (`ADM0_NAME` / `ADM1_NAME` may
be renamed); update the property reads accordingly. Also revisit the
filter — GAUL 2024's island handling may differ; verify the
unnamed-and-tiny filter still produces sensible output.

**Filter rationale (kept for posterity).** GAUL 2015 lists Fernando de
Noronha, Trindade, Martim Vaz, and Ilhabela as separate Brazilian
admin1 features with null `ADM1_NAME` and/or sub-5 km natural radii.
M-DEMO-DATA polish drops both classes — unnamed AND sub-5 km — via
the combined filter in
`demo/regions.py::_build_region_or_none`. Brazil's region count goes
from 31 to the canonical 27. Similar quirks likely exist for other
coastal nations; the filter handles them uniformly.

---

## M5.5 follow-ups (original — do these when wiring ODIAC / CO₂)

## High priority
- **CARMA-overlap flag.** Add a sub-score / provenance flag that fires when 
  Site_Buffer overlaps a CARMA point source. Surface in limiting-factor 
  template as "CO₂ value influenced by reported power-plant allocation nearby."
- **VIIRS double-counting fix.** Either drop `ghg.activity_score` from 
  `Core_GHG_Audit_Support` when ODIAC is the CO₂ source, or reduce its weight 
  (currently 0.11) to acknowledge overlap with ODIAC's diffuse branch.

## Medium priority
- **Relabel `co2_anomaly` → `co2_relative_intensity`.** Background-ring 
  "anomaly" doesn't have the same physical meaning for ODIAC as for S5P. 
  Document σ_bg normalisation as an analytic choice, not a physical baseline.
- **Reconsider `Activity_Adjusted_CO₂`.** Triple-counts VIIRS. Either remove 
  from v1 or reframe as a diagnostic-only output.

## Documentation tier
- **Split `Spatial_Resolution_Suitability`** into CH4-specific and ODIAC-specific 
  sub-scores, OR update the limiting-factor template to mention both.
- **Default ODIAC to annual not monthly** for v1 (monthly has imposed 
  seasonality). Document the choice in IC docs.

## Cross-validation (not a v1 deliverable)
- Validate ODIAC `ghg.co2_context` against Climate TRACE for 5-10 known 
  large emitters before production.

## Engine performance — EE round-trip batching (v1.x)
M5b's Nature pillar issues many sequential `getInfo()` calls, which becomes 
the dominant runtime cost for full-screening mode and for P-08 batch runs.

- **`compute_kba_proximity` (engine/nature.py)** — currently issues 3–4 
  sequential EE round-trips (size check, distance, intersection area). 
  Combine into one server-side `ee.Dictionary` computation so the whole 
  KBA payload is a single `getInfo()`.
- **`compute_habitat_conversion` (engine/nature.py)** — same problem, 
  doubled. Calls `_dw_mode_histogram` twice (current + baseline window); 
  each call is itself a `getInfo()` plus a `.size().getInfo()` size check. 
  That's 4 round-trips for habitat conversion alone. Combine the two 
  histograms into one server-side call returning both windows in a single 
  Dictionary.
- **Knock-on impact.** With ~7 Nature indicators each doing similar 
  patterns, a single full screening run can issue 20–30 sequential EE 
  calls. P-08 batch mode (up to 30 nodes) compounds this. Target: cap 
  Nature at ≤ 10 round-trips per AOI.
- **`compute_co2_snapshot` (engine/ghg.py)** — issues 4 sequential 
  round-trips per AOI: `ic.size().getInfo()`, then three separate 
  `reduceRegion().get(band).getInfo()` calls (site sum, site mean, ring 
  mean). Same Dictionary-batching opportunity.

## M5.5 status (current)

### Completed in M5.5
- ODIAC asset ingested at `projects/supply-chain-observatory/assets/odiac`.
- `compute_co2_snapshot` implemented (relative-intensity model, not 
  six-step) — see engine/ghg.py.
- `co2_anomaly` renamed to `co2_relative_intensity` in engine code 
  (Schema_v2 §3.1 doc update is pending — see CLAUDE.md §8 confirmation 
  guard on the docs/ directory).
- `CORE_GHG_AUDIT_SUPPORT_WEIGHTS` rebalanced to reduce VIIRS 
  double-counting: `ghg.activity_score` 0.11 → 0.06, 
  `ghg.combustion_proxy` 0.22 → 0.27 (freed 0.05 redistributed). 
  Sum unchanged at 1.00.
- `CO2_TO_C_RATIO` constant (= 44/12) added to engine/constants.py with 
  inline comment explaining the molecular conversion.
- `engine/ids.py::CO2_MEASUREMENT_SUFFIXES` updated to the M5.5 7-key 
  set: `(mean, total, relative_intensity, trend, trend_p, confidence, 
  score)`.
- Scratch page renders CO₂ row in the GHG breakdown table with the 
  custom `mean` headline and an annualised-emissions caption.
- Synthetic-payload tests cover the score formula, the score 
  saturations, the C → CO₂ conversion arithmetic, the pixel-size guard, 
  and the empty-time-range failure path. Activated sub-aggregates 
  (`co2_context`, `fossil_combustion_score`, `activity_adjusted_co2`) 
  have happy-path tests.
- `tests/test_ghg_integration.py` added (skipped unless 
  `RUN_EE_TESTS=1`) — exercises ODIAC against the Ruhr Valley.

### Still deferred to v1.x
- **CARMA-overlap flag** — highest-leverage remaining ODIAC item. The 
  v1 score formula clamps `relative_intensity` at 10×, which is a 
  CARMA-overlap *proxy*; v1.x should detect overlap explicitly and set 
  `carma_overlap=True` in `_provenance.ghg.co2` so the limiting-factor 
  template can surface it.
- **`Activity_Adjusted_CO₂`** still triple-counts VIIRS by IC's own 
  reckoning. Kept active in v1 for completeness; v1.x should reframe 
  as diagnostic-only or remove.
- **JRC GSW long-term water** (Nature pillar) still pending IC docs.
- **EE round-trip batching** (engine performance section above) — 
  cross-pillar, including CO₂'s 4 round-trips per AOI.
- **IC_v5 confidence formula gap (§6.3)** — placeholder confidence 
  still flat 1.0 / 0.7 / 0.8 values across pillars.
- **ODIAC vintage flag** in `ghg.retrieval_inventory_quality` — ingest 
  added the asset, but the per-image `as-of` property isn't wired into 
  the quality sub-score yet.
- **Schema_v2 §3.1 doc update** — the rename from `.anomaly` to 
  `.relative_intensity` for CO₂ measurements is live in engine code 
  but the doc hasn't been edited (CLAUDE.md §8 requires explicit 
  confirmation to modify docs/).

## M5.5b — ODIAC demoted from live composite (current)

### What changed
- ODIAC removed from `CORE_GHG_AUDIT_SUPPORT_WEIGHTS`. The three live 
  signals (CH₄ + combustion proxy + activity score) rescaled by 1/0.61 
  to preserve relative proportions: 0.46 / 0.44 / 0.10.
- CO₂ snapshot still computes when ODIAC data is available (2020-2023). 
  Values still display (`ghg.co2.mean / total / relative_intensity / score`). 
  They no longer feed the live composite.
- The three CO₂-dependent sub-aggregates (`ghg.co2_context`, 
  `ghg.fossil_combustion_score`, `ghg.activity_adjusted_co2`) still 
  compute as display-only / diagnostic outputs.
- `_provenance.ghg.co2` carries `role_in_pillar="standing_exposure_context"` 
  so UI and offline validators can key on it.

### Why
- **Methodological**: ODIAC's 2+ year vintage lag means it cannot 
  drive a live signal. Including it in the live formula meant 
  present-day screening (e.g. May 2026) failed entirely. Removing it 
  makes the live formula honest about what data feeds it.
- **Defensibility**: Also resolves the VIIRS double-counting concern 
  (CO₂ formerly competed with VIIRS/Combustion via overlapping 
  coverage) and the "anomaly" framing problem (ODIAC's background-ring 
  isn't an atmospheric baseline). Both are now moot.

### What ODIAC still does in v1
- **Display**: standing-exposure context shown alongside the live GHG 
  composite (scratch page; will reappear in P-05+).
- **Diagnostic**: `ghg.co2_context / fossil_combustion_score / 
  activity_adjusted_co2` still emit, available to UI for "ODIAC says X" 
  captions and for offline validation scripts.

### Validation work (tracked as v1 deliverable, separate scope)
- Build `scripts/validate_co2_proxy.py`: pick 50-100 historical points 
  within 2020-2023, stratified across supplier types (power plant, 
  heavy industry, urban industrial, semi-rural, clean control). Compute 
  `ghg.co2.score` (ODIAC) and `ghg.core_audit_support` (live trio) at 
  each. Report Spearman ρ overall and by stratum.
- Expected findings: strong correlation in diffuse-emission locations 
  (urban, semi-industrial). Weaker correlation for CARMA point-source 
  locations — the live trio under-detects point-source CO₂. This 
  finding motivates explicit CARMA-overlap surfacing in v1.x.
- Report in methodology doc: "live CO₂ proxy achieves Spearman ρ = X 
  against ODIAC for diffuse locations and ρ = Y for point-source-
  proximate locations; the latter is mitigated by surfacing ODIAC's 
  standing-exposure layer alongside the live score."

### v1 UI follow-ups (P-05+, NOT scratch page)
- Show ODIAC as a distinct map layer with a vintage label.
- Update verbal summary templates: live CO₂ findings reference the 
  trio ("driven primarily by CH₄ / combustion / activity"); ODIAC 
  appears in a separate clause ("location sits within a high standing 
  fossil-CO₂ exposure zone, ODIAC 2023").

### v1.x — still relevant
- **CARMA-overlap flag**: now MORE important, since ODIAC's role is 
  explicitly to surface point-source proximity. The 10× clamp in the 
  relative_intensity formula remains a proxy until v1.x lands explicit 
  detection.

## M5.5c — ODIAC coverage window + data-type honesty (current)

### What changed
- `GhgIndicatorConfig` gained two optional fields:
  - `coverage_window: tuple[str, str] | None` — declares the
    indicator's data availability window. None means "always available"
    (CH₄, VIIRS); ODIAC carries `("2020-01-01", "2023-12-31")`.
  - `data_type: str` — `"satellite_observation"` (default; CH₄, VIIRS)
    or `"emissions_inventory_allocation"` (ODIAC). Surfaces in
    provenance so UI and audit trails can distinguish measured vs
    modelled values.
- `run_pillar` checks `coverage_window` before dispatching each
  indicator. Out-of-coverage indicators are skipped silently: None-
  filled keys, a provenance block with
  `skipped_reason="out_of_coverage"`, and NO entry in `_failures`.
  This is the operational fix for the bug where present-day screening
  generated noise about "no ODIAC monthly grids in 2026" in the UI.
- `run_pillar` tracks `attempted_keys` separately from
  `indicator_keys`. The "all failed → `PillarComputeError`" trigger
  uses `attempted_keys`, so a present-day run with only CO₂ selected
  (where CO₂ is silently skipped) no longer trips the pillar-wide
  failure.
- `compute_co2_snapshot` docstring leads with the inventory-vs-
  observation distinction. Provenance carries `data_type`,
  `data_source`, and `allocation_method` fields. The historical
  `n_months == 0` raise was removed (dead code after the coverage
  check moved upstream).
- Scratch page captions explicitly label ODIAC as "inventory estimate
  (not satellite-measured)" on the success path, and differentiate
  the "skipped" vs "failed" None paths via the provenance flag on the
  unavailable path.

### Why this matters
- **Operational**: stops calling ODIAC for date ranges where we know
  it has no data. Saves 4 EE round-trips per present-day GHG run.
- **Methodological honesty**: reviewers reading "1.2 million t CO₂/yr"
  in a report now have provenance-level clarity that the value was
  *allocated* from national statistics + CARMA + nightlights, not
  *observed* from space. Closes a real audit-defensibility gap.

### Display-only sub-aggregates flagged for v1.x review

Three CO₂-dependent sub-aggregates still compute when ODIAC succeeds:

- **`ghg.co2_context`** — pure alias of `ghg.co2.score`. Defensible.
  Used by the two below.
- **`ghg.fossil_combustion_score`** — `0.50·co2 + 0.30·combustion +
  0.20·activity`. *Mild* double-counting: VIIRS contributes both
  directly via `activity_score` and indirectly via ODIAC's
  nightlight-driven allocation. Worth reframing as a multi-source
  consensus check in v1.x with explicit attribution.
- **`ghg.activity_adjusted_co2`** — `0.70·co2 + 0.30·activity`.
  *Strong* double-counting: ODIAC's diffuse branch is partially
  nightlight-driven, so the 0.30 on `activity_score` is on top of
  the ~0.5 effective VIIRS weight already inside `co2_context`.
  The methodological case is weak. v1.x: either drop or reframe as
  diagnostic-only.

**In v1, nothing downstream consumes any of these three.** They
compute, they live in the payload, they're available for offline
validators and for future UI captions, but they don't feed any
aggregate. Harmless until removed. Tracking here so v1.x makes an
explicit decision rather than carrying them forward by inertia.

### Still deferred (unchanged from M5.5b list)
- CARMA-overlap flag
- JRC GSW long-term water (Nature pillar)
- EE round-trip batching
- IC_v5 confidence formula gap (§6.3)
- ODIAC vintage flag in `ghg.retrieval_inventory_quality`
- Schema_v2 §3.1 doc update (the `.anomaly` → `.relative_intensity`
  rename is live in code; doc edit still pending CLAUDE.md §8 guard)

## M5.6 — unified provenance schema (current)

### What changed
- New module `engine/core/provenance.py` defines the canonical
  provenance shape (11 fields, fixed order) plus the strict-validating
  `build_provenance()` constructor and two enums:
  `_ALLOWED_DATA_TYPES` (5 values) and `_ALLOWED_OBSERVATION_UNITS`
  (5 values). Full reference: `docs/provenance_schema.md`.
- Every pillar's config dataclass (`PollutantConfig`,
  `GhgIndicatorConfig`, `NatureIndicatorConfig`) gained `data_type` and
  `data_source` fields. All 19 v1 indicators across Air (9), GHG (3),
  Nature (7) now carry explicit metadata at the config layer.
- Every indicator's snapshot function (`compute_pollutant_snapshot`,
  `compute_ghg_indicator_snapshot`, `compute_co2_snapshot`, plus the
  seven Nature snapshot fns) now constructs provenance through
  `build_provenance(...)`. The previous ad-hoc dicts (varying in shape
  per pillar) are gone.
- The out-of-coverage skip path in `engine/ghg.py::run_pillar` also
  routes through `build_provenance`, with
  `observations={"count": 0, "unit": "monthly_grids"}`.
- M5.5b's `role_in_pillar="standing_exposure_context"` field on ODIAC
  provenance was dropped — `data_type="emissions_inventory_allocation"`
  carries the same information more honestly, and the "not in live
  composite" fact is encoded in `CORE_GHG_AUDIT_SUPPORT_WEIGHTS` itself.
- ODIAC's `n_months` moved into `observations.count`;
  `c_to_co2_factor` and `allocation_method` into `extra` and
  `method_note` respectively. No information loss.
- KBA's `compute_kba_proximity` gained a `time_range` parameter for
  provenance consistency; the user's request window is documented in
  the provenance block. When the function is called without a window
  (direct tests), provenance carries the sentinel `("static", "static")`.

### Why this matters
- **Audit defensibility.** A reviewer reading
  `_provenance.air.no2` sees the same 11 fields as
  `_provenance.ghg.co2` or `_provenance.nature.kba`. No pillar-specific
  switch statement in the audit UI; no chance of a key existing in one
  pillar's block and silently missing from another.
- **Honesty.** `data_type` makes the inventory-vs-observation
  distinction first-class. CAMS PM is tagged
  `gridded_model_output`; ODIAC is `emissions_inventory_allocation`;
  Dynamic World is `ml_classified_satellite`; KBA is
  `reference_dataset`. Reviewers calibrate evidentiary weight on the
  tag, not on free-text caveats they might miss.
- **Strict validation.** `build_provenance` raises `ValueError` for
  unknown `data_type` or `observations.unit` values at construction
  time. A typo can't slip into a payload silently.

### Test coverage
- `tests/test_provenance.py` — 8 unit tests for `build_provenance`
  (field order, defaults, validation paths, all-enum-values
  acceptance).
- `tests/test_air.py::TestProvenanceShape` — per-pollutant canonical-
  keys check (9 parametrised) plus 3 indicator-specific assertions
  (NO₂ flags satellite, PM2.5 flags model output, AOD carries
  bit-mask in extra).
- `tests/test_ghg.py::TestProvenanceShape` — CO₂ happy-path,
  out-of-coverage skip path, and direct `_format_result` tests for
  CH₄ and VIIRS.
- `tests/test_nature.py::TestProvenanceShape` — KBA happy path,
  static-sentinel path, plus a parametrised 7-indicator config
  metadata check.
- `tests/test_ghg_integration.py` — migrated to the new shape.

### Notes for v1.x
- **Observations counts.** Most non-CO₂ indicators pass
  `observations=None` because v1 doesn't track image counts through
  `six_step`. v1.x should plumb `n_used` through `six_step` so every
  provenance block can carry a non-None observations field.
- **Schema_v2 doc update.** Schema_v2 doesn't currently mention the
  provenance shape (it covers indicator IDs only). Either extend it or
  link to `docs/provenance_schema.md` from §6 ("Engine output shape").
  Still pending CLAUDE.md §8 confirmation to edit Schema_v2.

---

## Country supplier database integration (deferred M-P07)

P-07's third tab is disabled in v1. The Setup page exposes three input
modes — supply chain (from a loaded P-02 scope), ad hoc list, and
country supplier database. Only the first two are wired in v1; the
country-DB tab renders an informational placeholder + a disabled
"Coming in v1.x" button.

**v1.x integration targets.** Open Supply Hub for garments/textiles;
CARMA for power-plant emissions. Expand from there as datasets allow.

**Why this matters.** Policy Maker users gain a "scan every supplier
of type X in country Y" workflow ("every cement factory in Brazil",
"every coal plant in India") that v1 can't express. For MNC users it
unlocks a path beyond their own loaded chain — proactive screening of
adjacent supplier pools.

**Fix when picked up.** Add a country + sector selector to the disabled
tab, wire it to the supplier-DB adapter, and feed the resulting list
through the same `Supplier` dataclass + run path as the other two
modes. The 20-supplier cap may need to lift (or split into pages) for
country-scale lists; revisit alongside the parallel-execution work
below.

---

## CSV upload for ad hoc locations (deferred M-P07)

M-P07 ships textarea-paste as the only ad hoc input path. For lists of
~5-20 locations the textarea works well; beyond that, paste fidelity
gets brittle (Excel exports with quoted strings, BOM-prefixed UTF-8,
embedded newlines in names).

**Fix when picked up.** Add a drag-and-drop CSV uploader alongside the
textarea in `_render_ad_hoc_textarea`. Validate header row
(`name,lat,lon`), reuse the existing `_parse_ad_hoc` line validator
per row (returning the same `(suppliers, errors)` pair), surface the
same error expander. Practical list-size ceiling rises from ~20 to
~200 — at which point the 20-supplier cap becomes the limiting
factor, not the input path.

---

## Parallel batch execution (deferred M-P08)

P-07's run-section estimate is `~1 min/supplier`, which assumes
sequential execution (one `ScreeningRun` after the next). At the
v1 cap of 20 suppliers that's a ~20-minute wall-time for a full
batch. The setup page surfaces an info banner for batches of ≥ 10
suppliers warning the user to expect ~10+ minutes.

**Fix when picked up.** Parallelise via threadpool or asyncio in P-08's
runner, with EE rate-limit handling (TaskScheduler-style exponential
backoff on `ee.EEException` rate-limit codes). Each `ScreeningRun` is
already independent — no shared mutable state — so the parallelisation
is mostly a runner-side change. Expected wall-time drop is ~5-10× for
typical batches, putting a 20-supplier run under 5 minutes.

**Knock-on.** The "Estimated time" line in P-07's run section should
be recalibrated to the parallel estimate once P-08 lands the runner;
the constant `1` minute/supplier in `_render_run_section` is the
single hook to update.

## Controls inside redraw containers — widget-key collision pattern (architectural note)

**Two crashes this session, same root cause.** Streamlit widgets that
register a `key` argument cannot be safely re-rendered inside an
`st.empty()` container without changing the key — but changing the
key loses state between renders.

The pattern surfaced twice in the P-08 work:

1. **M-P08.2-FIX** — `st.radio(key="p08_rank_by")` was rendered
   inside the results container; the S2_Running progress callback
   re-rendered the radio per supplier completion → duplicate-key
   crash. Fix: split the radio out as a separate function called
   once outside the container; pass its result as an argument to
   the table renderer.

2. **M-P08.4-FIX** — `st.dataframe(key="p08_ranked_table",
   selection_mode="single-row")` was also re-rendered inside the
   results container. Adding `selection_mode` turned the dataframe
   from stateless display into a keyed widget. Fix: gate selection
   to S3_Results only (the table-in-S2 has no use for selection
   anyway).

**Architectural rule for future development:** any Streamlit widget
that takes a `key` argument MUST be rendered exactly once per page
render. Controls live ABOVE redraw containers; the container only
re-renders display elements (text, tables-without-keys, charts-
without-keys, plain markdown).

When this rule is unavoidable (a long-running batch needs an "edit
mid-run" control), the workaround is to gate the keyed widget to a
specific page state — the M-P08.4-FIX `enable_selection` parameter
pattern. Don't try generation-counter keys; widget state is lost
between renders, defeating the purpose.

---

## Verified ESG/regulatory alignment mappings (deferred M-P09)

M-P09 ships hand-authored ESG / regulatory alignment per indicator in
[demo/indicator_library.json](../demo/indicator_library.json), with a
top-of-page "indicative" caveat. The mappings draw on the obvious
frameworks (WHO AQ Guidelines, EU AAQD, EUDR, CBD GBF, TNFD, CSRD
ESRS, UN SDGs, GHG Protocol) but haven't been reviewed by a
domain expert.

**Fix when picked up.** Domain-expert review and verification of each
indicator's mapping. Possibly expand from the current
semicolon-separated text-string format to a structured taxonomy
(`{framework_id, article_reference, applicability_note}` per entry)
so the P-09 filter can be more precise — e.g. "EUDR Annex II
commodities" vs generic "EUDR". The P-09 `_collect_esg_terms` helper
splits on `;` today; a structured taxonomy would replace that with a
typed lookup.

---

## "Active in current workflow" toggle for P-09 (deferred M-P09)

Per Wireframes §P-09 spec, the Indicator Library should support a
toggle (C6) that dims indicators not in the current workflow's
selection. v1 skipped this: it couples the page to the
`screening_setup` / `prioritisation_setup` session state and adds
modest value on top of the search/filter pair already shipped.

**Fix when picked up.** Reactivate when the localStorage persistence
work (deferred for P-10) lands a stable notion of "current workflow"
across page loads — the toggle is only useful when "active in
workflow" survives navigation. At that point: add a third filter
control alongside search + ESG; when toggled on, dim cards whose
`indicator_id` isn't in the active setup's `indicators` list.

---

## M-COMPONENT-WEIGHTS — surface component-score exact weights in P-09 (deferred M-P09-COMPOSITES v2)

M-P09-COMPOSITES v2 surfaces **pillar follow-up priority** weights
live (those are owned by `c5_drilldown._AIR_FORMULA` / `_GHG_FORMULA`
/ `_NATURE_FORMULA`, which import from structured constants in
[engine/constants.py](../engine/constants.py)). For **component
scores** (e.g. `nature.vegetation_condition`,
`ghg.core_audit_support`), the weight dicts are also already in
`engine.constants` — `VEGETATION_CONDITION_WEIGHTS`,
`BIODIVERSITY_EXPOSURE_WEIGHTS`, `HABITAT_CONVERSION_WEIGHTS`,
`NATURE_QUALITY_ATTRIBUTION_WEIGHTS`, `CORE_GHG_AUDIT_SUPPORT_WEIGHTS`,
`GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS`, `AIR_POLLUTION_PROXY_WEIGHTS`.

So the constants exist; what's missing is the **wiring** that imports
them into `c5_drilldown`-style structured formula tuples and through
to `demo.indicator_library._resolve_live_formula`'s dispatch. v1 ships
component-score cards with a **conceptual inputs list** in the JSON
manifest plus a caption directing readers to the engine source.

**Fix when picked up.**

1. Extend [ui/components/c5_drilldown.py](../ui/components/c5_drilldown.py)
   (or a new sibling module) with `_FormulaTerm`-style tuples for each
   component score, mirroring the existing `_AIR_FORMULA` /
   `_GHG_FORMULA` / `_NATURE_FORMULA` build pattern. Import the weight
   dicts and pair them with display-name / payload-key bindings.
2. Extend
   [demo/indicator_library.py](../demo/indicator_library.py)::`_resolve_live_formula`'s
   `formula_for_aggregate` dispatch to include the 12 component-score
   IDs. Each returns a structured `{"formula", "weights"}` dict.
3. Drop the manifest's `inputs` field from the component-score entries
   (no longer needed once weights are live-sourced) — or keep it as a
   redundant readability aid; either choice is fine.
4. Drop the v1 *"Precise weights live in the engine source"* caption
   from the renderer's component-score branch — the formula + weights
   section now self-documents.
5. The existing canary test
   ([tests/test_indicator_library.py](../tests/test_indicator_library.py)::`TestDerivedEntries::test_pillar_aggregate_weights_match_c5_drilldown`)
   covers the lockstep guarantee for the new wiring automatically —
   just extend its parametrisation to include the 12 component-score
   IDs.

**Risk.** M-FOLLOWUP-FALLBACK's known-zero substitution logic touches
several compute functions (notably `compute_vegetation_condition` for
`nature.ndvi.negative_trend`); landing the constants exposure requires
careful regression testing to ensure the substitution semantics are
preserved end-to-end (engine output → c5_drilldown formula display →
library card display).

---

## Additional report templates — ESG / Portfolio screening (deferred M-P11)

M-P11.1 ships two templates: Policy audit report (Policy Maker) and
Supplier audit report (MNC). The wireframes spec describes more —
namely an **ESG / due-diligence report** (cross-sectoral, multi-pillar
narrative aimed at ESG officers) and a **Portfolio screening report**
(prioritisation-batch-focused, multi-supplier comparison framing).

**Fix when picked up.** Add new `ReportTemplate` entries to the
`_TEMPLATES` tuple in
[ui/components/p11_templates.py](../ui/components/p11_templates.py).
The user-type hard branch (`templates_for`) makes adding a template
visible to a specific role trivial; for cross-role templates, drop
the `user_type` filter or set it to a wildcard sentinel. Each new
template's `sections` tuple drives both M-P11.2 preview and M-P11.3
PDF rendering — define the section keys, then add the matching
renderers in the preview / PDF templates.

---

## Coverage-gap workflow on P-11 (deferred M-P11)

Wireframes §P-11 S4 describes a coverage-gap modal that fires when an
audit template is picked with a partial-coverage source (a screening
that ran fewer than the canonical 19 indicators, or a prioritisation
batch where indicators were deselected in P-07). v1 ships M-P11.1
without this — the partial-coverage status is implicit in the source's
saved payload, and M-P11.2's methodology section will note something
like *"Screening covered N of 19 indicators"*.

**Fix when picked up.** Detect partial coverage on source pick by
inspecting each chosen source's `screening_setup["indicators"]` /
`prioritisation_setup["indicators"]` vs `ALL_INDICATOR_IDS`. When any
source is partial, surface a modal (or inline warning) before the
**Preview** step with three options per the wireframes spec:

- **Run comprehensive screening for this target** — route to P-04
  pre-filled with the source's centre + all 19 indicators selected
  + radius from the source's setup.
- **Continue with partial coverage** — accept the gap and proceed to
  preview.
- **Cancel** — return to template selection without committing.

The "Run comprehensive" path is the integration point with P-04's
`scope` and `centre_metadata` plumbing — it should preserve the
report-build context so the user lands back on P-11 with the same
template selected after the comprehensive screening completes and is
saved.