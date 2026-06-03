# M-WEIGHTS-HARMONISE-A1 — Closed entry

*Date: 2 June 2026. Spec: inline (operator-provided).*

## Summary

Harmonised the three pillar follow-up priorities onto a single uniform shape
and unified the measurement-quality term across pillars. Every pillar follow-up
is now

```
Pillar_FollowUp = (1 − w_q)·Severity_core + w_q·MeasurementQuality
```

with a single shared `w_q = FOLLOWUP_QUALITY_WEIGHT = 0.20` across all three
pillars. Only the severity **core** differs by pillar — each retains its own
grammar (Air proxy/anomaly, GHG combustion/flaring, Nature
exposure/change/condition). This replaced the prior per-pillar
spurious-precision splits (Air `0.4375 / 0.3750 / 0.1875`; GHG `0.7273 /
0.2727`; Nature `0.30 / 0.30 / 0.25 / 0.15`), which were historical
renormalisations over removed terms and carried no scientific meaning.

The GHG measurement-quality term was implemented bottom-up (replacing the
placeholder routing), and the composite-confidence chain was unified so each
pillar feeds the `min(...)` with the same measurement-quality aggregate it uses
for its follow-up's quality term.

**Tests:** 2062 passed, 34 skipped (engine + UI). New: `TestHarmonisationInvariant`
(`test_followup_priority.py`) and `TestGhgMeasurementQuality` (`test_ghg.py`);
the parametrised follow-up canaries, C5/P-09/P-11 lock-step tests, and the
verbal-summary/orchestrator fixtures were updated to the two-level shape.

## Decisions (locked)

- **`w_q = 0.20`** — shared by intent, not coincidence: the fourth term means
  the same thing in every pillar (measurement quality = mean per-indicator
  confidence), so it carries the same weight everywhere.
- **GHG measurement quality: implemented (option a).** Computed bottom-up like
  Air/Nature, not deferred.
- **Nature severity core: decision (ii).** Clean effective values `0.30 / 0.30
  / 0.20 + 0.20` quality (core `0.375 / 0.375 / 0.250`), symmetric with Air,
  chosen over preserving the old `0.30 / 0.30 / 0.25` strand ratios. The only
  behavioural shift in Nature is `vegetation_condition`'s effective weight
  `0.25 → 0.20`.
- **GHG confidence chain unified.** The composite-confidence `min(...)`,
  the verbal-summary per-pillar confidence, and the C5 GHG drill-down all read
  `ghg.measurement_quality` (was `ghg.data_quality_attribution`). Air and Nature
  needed no change — their follow-up quality term and composite-confidence term
  were already the same aggregate; only GHG carried the split.
- **Legacy alias `air.attribution_confidence_score` retained.** Its retirement
  is deferred: it is now part of the legacy-ID back-compat layer
  (`test_legacy_id_fallback.py`, alongside `nature.quality_attribution`) that
  lets the screening loader read historical saved analyses, so removal is a
  standalone deprecation rather than a cleanup riding on this milestone.

## Target weights (as landed in `engine.constants`)

```
FOLLOWUP_QUALITY_WEIGHT = 0.20    # shared w_q

AIR_SEVERITY_CORE_WEIGHTS    = { proxy: 0.625, anomaly: 0.375 }       # = 0.50/0.30 ÷ 0.80
AIR_FOLLOWUP_WEIGHTS         = { severity_core: 0.80, quality: 0.20 }
                               → effective 0.50 proxy + 0.30 anomaly + 0.20 quality

CORE_GHG_AUDIT_SUPPORT_WEIGHTS = { combustion: 0.60, flaring: 0.40 }  # UNCHANGED
GHG_FOLLOWUP_WEIGHTS         = { core_support: 0.80, quality: 0.20 }

NATURE_SEVERITY_CORE_WEIGHTS = { biodiversity_exposure: 0.375,
                                 habitat_conversion:    0.375,
                                 vegetation_condition:  0.250 }
NATURE_FOLLOWUP_WEIGHTS      = { severity_core: 0.80, quality: 0.20 }
                               → effective 0.30 exposure + 0.30 conversion
                                          + 0.20 condition + 0.20 quality
```

The weights express **term ordering plus a uniform quality modifier**, not an
empirically fitted optimum — calibration is deferred (see `v1x_followups.md`).

## Task lock verification

- [x] **Task 1 — constants.** Four weight dicts rewritten; `FOLLOWUP_QUALITY_WEIGHT`
  and the two severity-core dicts added; module-level design comment explaining
  the uniform shape and the shared-by-intent `w_q`. `CORE_GHG_AUDIT_SUPPORT_WEIGHTS`,
  `GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS`, and `NATURE_MEASUREMENT_QUALITY_WEIGHTS`
  left unchanged per spec.
- [x] **Task 2 — Air.** `compute_air_audit_followup_priority` restructured to
  `0.80·severity_core + 0.20·measurement_quality`, computing the core via
  `_weighted_sum_strict` over `AIR_SEVERITY_CORE_WEIGHTS`. Follow-up term key
  renamed `confidence → quality`. Strict-None preserved (None core *or* None
  quality → None).
- [x] **Task 3 — Nature.** `compute_nature_followup_priority` restructured the
  same way over `NATURE_SEVERITY_CORE_WEIGHTS`; follow-up term key
  `quality_attribution → quality`. Strict-None preserved.
- [x] **Task 4 — GHG.** New `compute_ghg_measurement_quality`: survivor-mean of
  the **scored** GHG terms' per-indicator confidences — VIIRS flaring
  (`ghg.viirs.confidence`) and the combustion borrow (weighted NO₂/CO
  confidence via `INDUSTRIAL_COMBUSTION_PROXY_WEIGHTS`). CO₂/CH₄ are
  reference-only and excluded by construction. `compute_ghg_audit_followup_priority`
  → `0.80·core_support + 0.20·measurement_quality`; wired into `run_pillar`
  after the scored sub-aggregates and before the follow-up. Module docstring
  de-placeholdered.
- [x] **Confidence-chain unification.** `engine.orchestrator._PILLAR_CONFIDENCE_IDS`
  and `engine.verbal_summary._CONFIDENCE_KEY` switched the GHG term to
  `ghg.measurement_quality`. `ghg.data_quality_attribution` is unchanged and
  still computed/surfaced as the GHG data-quality breakdown (C5/C6/report) but
  no longer drives the composite minimum.
- [x] **Task 5 — naming.** Legacy alias retained with a TODO recording why
  removal is deferred (see Decisions). Public measurement-quality IDs unchanged
  (`air.measurement_quality_score`, `nature.measurement_quality`, new
  `ghg.measurement_quality`).
- [x] **Task 6 — tests.** Harmonisation invariant (all three follow-up dicts
  carry `quality == 0.20`; severity portion sums to `0.80`; no legacy
  spurious-precision literals in the follow-up dicts). GHG-quality tests:
  computed (not constant), `None` when both scored terms absent, VIIRS-only when
  the borrow is unresolved. Strict-None propagation tests kept green.
- [x] **Task 7 — docs.** `Indicators_Computation_v4.md` §1.3 / §2.3 / §3.3
  rewritten to the uniform formula with the one-line "ordering, not a fitted
  optimum" note; changelog bumped.

## UI / library consistency (lock-step surfaces)

- **C5 drill-down** (`ui/components/c5_drilldown.py`) — the follow-up formula
  breakdown shows the **effective** per-leaf weights for Air/Nature (severity
  portion × in-core weight, plus the 0.20 quality leaf); GHG stays a two-row
  `core_support / quality` table. The GHG headline confidence reads
  `ghg.measurement_quality`. `_build_formula` keeps its fail-loud import-time
  KeyError on key drift.
- **P-11 report appendix** (`ui/components/p11_sections.py`) — the composite-
  methodology section renders the effective per-term weights and states the
  shared two-level shape (`0.80·core + 0.20·quality`, `w_q = 0.20`).
- **Indicator library / P-09** — `ghg.measurement_quality` added as a
  derived component-score card (`demo/indicator_library.json` manifest entry +
  `INDICATOR_CONFIDENCE_FAMILY` classifier in `engine.constants`). It surfaces
  in place of `ghg.data_quality_attribution`, which leaves the derived
  catalogue (no longer a follow-up formula term).

## Regeneration

The seeded worked-example saved-analysis payloads (`demo/saved_analyses/`) were
regenerated for the affected aggregate layer only. Because this milestone
changed nothing below the pillar-aggregate level, the raw indicator values were
preserved and only the four affected aggregates per payload were recomputed with
the new engine functions, plus the new `ghg.measurement_quality` field
inserted: `air.audit_followup_priority`, `ghg.audit_followup_priority`,
`nature.followup_priority`, and `composite.overall_screening`.
`composite.confidence` recomputed identically (the binding minimum was unchanged).
A live Earth Engine re-run was deliberately **not** used — screening mode keys
its window to current data availability, so a re-run would have drifted the raw
values for reasons unrelated to this milestone.

## Documentation changes

- `docs/Indicators_Computation_v4.md` — §1.3 / §2.3 / §3.3 follow-up formulas
  rewritten to the uniform two-level shape; §2.3 records the bottom-up
  `GHG_Measurement_Quality` and the composite-confidence unification;
  changelog entry added at the top.
- `docs/M-WEIGHTS-HARMONISE-A1_closed_entry.md` — this file.
- The audit doc (`Indicators_Audit_and_v1x_Roadmap.md`) is **not** edited and
  remains pending separate sign-off (authority-pointer protocol).

## Follow-ups

- **Calibration of the harmonised weights.** The `w_q = 0.20`, the Air/Nature
  severity-core splits, and the GHG `0.60 / 0.40` core are first-pass orderings,
  not fitted values. A calibration sweep is deferred (`v1x_followups.md`).
- **`air.attribution_confidence_score` deprecation.** Retiring the legacy alias
  is a standalone deprecation: drop the loader back-compat fallback, migrate the
  baseline fixtures and seeded saves, then remove the dual-emit + module shim.
- **GHG two-output asymmetry vs Air.** Unchanged by this milestone and still
  deferred to v2 (see `M-VIIRS-REDESIGN-A1` §2.4 VR16): extending the
  severity/attributability split to Air's indicators would require Air-pillar
  composite recalibration.
