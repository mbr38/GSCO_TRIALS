# M-DIAG-A1 — bg_std Behaviour Diagnosis Report

*Investigation milestone. Status: DRAFT (Step D in progress; pending Step E user review).*
*Date authored: 29 May 2026.*
*Authority pointer: M-DIAG-A1 spec (`docs/M-DIAG-A1_spec.md`, v1.0 — 28 May 2026).*
*Code state: instrumentation lives in `engine/core/repeatable_core.py`; one-line root-cause fix at `mean_key = f"{band}_mean"` in `_server_side_hf` was applied during this milestone (DG10 lifted on operator decision, 29 May 2026). Instrumentation reverts at Step F; the fix stays.*

---

## §1. Summary

The instrumentation built for this investigation did not reveal a bg_std behaviour issue. It revealed a **single-key bug** in `_server_side_hf` that had silently broken the per-day HF detector across every indicator since the M-TIER-A1 Step 8 server-side path landed. The combined `Reducer.mean().combine(Reducer.count(), sharedInputs=True)` reducer's `mean` output is suffixed as `{band}_mean` by Earth Engine to disambiguate it from `{band}_count`. The legacy code read the bare-band key `{band}`, hit the absent-key 0.0 default, and produced `site_mean = 0.0` for every granule. The per-day z then collapsed to `(0 − bg_median) / bg_std` — a function of the *background's* sign, not the site signal. AAI's negative bg_median made every day fire (the "tropical Moderate artefact"); every positive-bg_median pollutant produced hf=0 (the "Norilsk silence" and every other zero hf in production).

The spec's three candidate fix paths (A: calibrate threshold, B: fix bg_std, C: redesign detector) are all red herrings — they propose fixes to a detector that was never measuring what its name implies. The recommendation is the one-line key fix already applied in this milestone, plus a small follow-up (M-DIAG-A2) to validate the wind module's now-non-zero anomaly-day stream, audit other combined-reducer sites in the engine for the same class of bug, and re-tune any thresholds that were tacitly calibrated against the silently-zero detector.

## §2. Symptoms recap

Two symptoms surfaced during M-WIND-A1 v2.0 demo seeding (28 May 2026) and prompted this milestone:

**Symptom 1 — the AAI tropical Moderate artefact.** All three tropical seeds (Sapezal, Brasilia, Suape) returned `wind_attributability_state = "moderate"` for AAI with `N_anomaly_days = 88-89`. Essentially every day in a 90-day window fired as per-day z ≥ 2.0, even though the aggregate z was near zero. The original hypothesis (recorded in the M-DIAG-A1 spec and `engine/constants.py` Q-WA-1 comment, lines 596-617): AAI's `bg_std` collapses to near-zero at clean-air locations, so the per-day z denominator approaches zero.

**Symptom 2 — the Norilsk silence.** Norilsk NO₂ at site = 104.2 vs background = 67.4, aggregate z = 3.25 — a strong, real industrial signal — but the per-day HF detector fired *zero* anomaly days. The original hypothesis: the spatial bg_std (~11) was inflated by smelter plume contamination in the ring, raising the per-day threshold above what individual days could cross.

The spec's framing (DG1): one root-cause family — bg_std behaviour at the extremes of the conditions where the engine operates.

## §3. Method

### 3.1 Reconnaissance finding (and the first correction to the spec's mental model)

The spec describes investigating a "per-day bg_std distribution". The engine does not compute a per-day bg_std. There is one scalar `bg_std` per indicator-run: the spatial standard deviation of the time-averaged ring image (`image_collection.mean()` over the analysis window → `reduceRegion(stdDev)` over the land-masked annulus). That scalar is the denominator for both the aggregate z and the per-day HF detector. So DG8's "aggregate vs per-day" question reframes to **same denominator, different numerators** — and as it turned out, the per-day numerator was not what its variable name implied.

### 3.2 Instrumentation (Step B)

Per DG6, four diagnostic surfaces were added to `provenance.extra._diag_bg_std`:

| ID | Field(s) | Source | EE cost |
|---|---|---|---|
| D1 | `per_day_site_means: {iso_date: float}` | Augmented `per_image` in `_server_side_hf` — `aggregate_array("site_mean")` per chunk | none (rides existing getInfo) |
| D2 | `ring: {min, max, p10, p25, p50, p75, p90, p95, median, stdDev}` | Extended `_background_value_reduction` reducer with `percentile` + `minMax` | none (combined reducer) |
| D3 | `site_buf: {mean, min, max, p10, p50, p90}` | Extended `_site_value_reduction` reducer with `percentile` + `minMax` | none (combined reducer) |
| D4 | `plume_contam: {ring_p90_over_site_p90, ring_max_over_site_p90, ring_p90_over_site_mean}` | Client-side in `six_step` from D2 + D3 | none |

Plus the actual `bg_std`, `bg_median`, and `z_aggregate` were surfaced for cross-check. All diagnostics use temporary `_diag_*` keys reverted at Step F.

### 3.3 Seeds re-run (scope reduction at Step B.4)

The spec locked DG3 at 5 seeds (Sapezal, Brasilia, Suape, Comodoro, Norilsk). At Step B.4, with the diagnosis already legible from the first run's data, the operator reduced scope to **Sapezal + Norilsk** — the two extreme cases (clean tropical → AAI artefact; strong-source → Norilsk silence). The remaining three (Brasilia, Suape, Comodoro) are confirming-evidence seeds whose qualitative behaviour is already accounted for by the existing production seeds at `demo/saved_analyses/`. If §7's diagnosis or §8's recommendation calls for cross-AOI-scale evidence, a follow-up re-run is cheap (~10 min per fixture).

Outputs land in `demo/saved_analyses/diagnostic/{sapezal,norilsk}.json`. Production seeds at `demo/saved_analyses/*.json` were not overwritten (DG7 / R5).

Pillar coverage (DG2): Air (9 indicators), GHG (CH₄ + VIIRS), Nature (NDVI). DW, Hansen, ODIAC, KBA are excluded — they don't use the six-step pattern (no bg_std concept).

### 3.4 Analysis

`tools/m_diag_a1_analyse.py` reads the diagnostic JSONs and emits the §4 / §5 / §6 tables plus a `_summary.json`. Pure Python, no EE — re-runnable any time.

### 3.5 The root-cause probe

After the first instrumented re-run showed every `per_day_site_means` entry as exactly `0.0` for every (seed × indicator) cell, a small Earth-Engine probe (`/tmp/ee_reducer_key_probe.py`, ad-hoc) ran the same `Reducer.mean().combine(Reducer.count(), sharedInputs=True)` against a single S5P NO₂ image at Sapezal and printed the materialised dict keys. They are `{band}_mean` and `{band}_count` — no bare `{band}` key. The production code reads `reduction.get(band, 0.0)`, returns the 0.0 default, and the per-day site_mean is always silently zero. See §7.

---

## §4. Findings — bg_std behaviour

The bg_std column in the table below is what the engine actually computes. Once §7's bug is corrected the per-day detector reads the actual per-granule means, so any *residual* bg_std-related behaviour (rather than the bug's signature) is what this section is about.

### §4.1 — bg_std characterisation, Sapezal + Norilsk

| seed | indicator | site | bg_median | bg_std | cv=σ/|μ| |
|---|---|---|---|---|---|
| sapezal | air.no2 | 40.80 | 40.82 | 0.802 | 0.0196 |
| sapezal | air.so2 | 8.74 | 5.48 | 27.4 | 5.0 |
| sapezal | air.co | 27.2 | 27.5 | 0.407 | 0.0148 |
| sapezal | air.hcho | 121 | 106 | 12.5 | 0.118 |
| sapezal | air.o3 | 256 | 256 | 0.228 | 0.000889 |
| sapezal | **air.aai** | -0.65 | -0.647 | **0.0476** | 0.0735 |
| sapezal | air.aod | 67.2 | 76.3 | 17.1 | 0.224 |
| sapezal | ghg.ch4 | 1.90e3 | 1.91e3 | 15.5 | 0.00812 |
| sapezal | ghg.viirs | 3.52 | 0.15 | 4.05 | 27.1 |
| sapezal | nature.ndvi | — | 0.838 | 0.0722 | 0.0862 |
| norilsk | **air.no2** | **104** | 67.4 | 11.3 | 0.168 |
| norilsk | air.co | 32.0 | 31.7 | 0.877 | 0.0277 |
| norilsk | air.hcho | 46.1 | 39.9 | 3.58 | 0.0897 |
| norilsk | air.o3 | 446 | 444 | 1.08 | 0.00243 |
| norilsk | **air.aai** | -0.126 | 0.0136 | **0.0897** | 6.58 |
| norilsk | ghg.ch4 | 1.86e3 | 1.87e3 | 7.96 | 0.00426 |
| norilsk | ghg.viirs | 17.3 | 0.42 | 5.43 | 12.9 |
| norilsk | nature.ndvi | — | -0.0303 | 0.0145 | 0.478 |

**Interpretation.**

- **bg_std is small for some indicators in absolute terms.** AAI's bg_std lands at 0.048-0.090 (dimensionless), O₃ at 0.23-1.08 mol/m² ×scale, CO at 0.4-0.9. These are real reflections of how spatially uniform the time-averaged ring image is for the given indicator and AOI — not pathology. Coefficient-of-variation `cv = bg_std / |bg_median|` ranges from 10⁻⁴ (O₃ at Sapezal) to 27 (VIIRS at Sapezal, where bg_median is near zero and any noise dominates the ratio).
- **bg_std is not the symptom driver.** Once §7's bug is fixed, the per-day signal reads the actual per-granule mean — not a function of bg_median. Whether bg_std is small or large, the detector now responds to the real site-vs-ring contrast.
- **Plume contamination is not detectable in this data.** §6's cross-pillar pattern shows zero seeds where `ring_p90 ≥ site_p90` (the D4 proxy). Even at Norilsk — a textbook plume case — the smelter point dominates the site buffer enough that ring p90 stays well below site p90. The "plume contamination inflates bg_std" hypothesis (Norilsk silence Path B sub-option) is not supported by the diagnostic ring percentiles.

---

## §5. Findings — aggregate vs per-day

### §5.1 — Aggregate z vs per-day HF (post-fix)

| seed | indicator | z_aggr | hf | n_anom_days | per-day-z min | med | max | % ≥1.5 | % ≥2.0 | % ≥2.5 | disagreement |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sapezal | air.no2 | -0.028 | 0.412 | 35 | -30.7 | 0.66 | 17.4 | 47 | 41 | 38 | partial |
| sapezal | air.so2 | 0.119 | 0.260 | 13 | -7.6 | 0.57 | 12.7 | 30 | 26 | 20 | partial |
| sapezal | air.co | -0.854 | 0.343 | — | -32.3 | -2.77 | 20.5 | 39 | 34 | 34 | partial |
| sapezal | air.hcho | 1.18 | 0.352 | 25 | -18.8 | -0.02 | 16.0 | 35 | 35 | 32 | partial |
| sapezal | air.o3 | 0.342 | 0.472 | — | -47.0 | -2.28 | 61.4 | 47 | 47 | 46 | partial |
| sapezal | **air.aai** | -0.049 | **0.461** | 41 | -31.1 | 0.80 | 28.9 | 48 | 46 | 45 | partial |
| sapezal | air.aod | -0.530 | 0.333 | 11 | -2.05 | 0.25 | 7.0 | 33 | 27 | 21 | partial |
| sapezal | ghg.ch4 | -0.495 | 0.000 | — | -2.40 | -1.44 | -0.48 | 0 | 0 | 0 | agree (quiet) |
| norilsk | **air.no2** | **3.25** | **0.675** | 56 | -2.23 | 2.18 | 24.4 | 59 | 53 | 48 | **agree (strong)** |
| norilsk | air.co | 0.345 | 0.524 | — | -9.24 | 0.43 | 10.2 | 40 | 39 | 36 | aggr-quiet, per-day-saturated |
| norilsk | air.hcho | 1.75 | 0.747 | 65 | -4.34 | 1.21 | 10.2 | 46 | 38 | 36 | partial |
| norilsk | air.o3 | 1.62 | 0.578 | — | -62.2 | -0.90 | 102 | 44 | 43 | 42 | partial |
| norilsk | air.aai | -1.56 | 0.844 | 76 | -8.59 | -1.49 | 4.09 | 11 | 9 | 7 | partial |
| norilsk | ghg.ch4 | -1.18 | 0.167 | — | -6.85 | 0.05 | 4.11 | 17 | 17 | 17 | partial |

### §5.2 — Before/after delta (the fix's signature)

| seed × indicator | hf (production, pre-fix) | hf (post-fix) | n_anomaly_days (pre) | (post) |
|---|---|---|---|---|
| sapezal × air.aai | 1.000 | 0.461 | 89 | 41 |
| sapezal × air.no2 | 0.000 | 0.412 | 0 | 35 |
| sapezal × air.so2 | 0.000 | 0.260 | 0 | 13 |
| sapezal × air.hcho | 0.000 | 0.352 | 0 | 25 |
| sapezal × air.aod | 0.000 | 0.333 | 0 | 11 |
| norilsk × air.no2 | 0.000 | 0.675 | 0 | 56 |
| norilsk × air.aai | 0.000 | 0.844 | 0 | 76 |
| norilsk × air.hcho | 0.000 | 0.747 | 0 | 65 |

The signature is exactly what §7's mechanism predicts: pre-fix, hf was 1.0 only when bg_median was negative *and* the silent-zero numerator crossed the threshold; hf was 0.0 everywhere else. Post-fix, hf takes meaningful intermediate values across all indicators and seeds.

### §5.3 — DG8 verdict: is the disagreement a bug or a methodological distinction?

**It is a bug.** Before the fix, what looked like a methodological tension between the aggregate z and the per-day HF detector was an artefact of the per-day detector being effectively broken — the per-day numerator was constant 0, not the per-granule reduceRegion mean it was supposed to be. After the fix, the genuine cases of aggregate-vs-per-day disagreement that remain (e.g. `agree (strong)` at Norilsk NO₂; `aggr-quiet, per-day-saturated` at Norilsk CO) are real and load-bearing: the aggregate z and per-day HF *should* sometimes disagree because they measure related but distinct things (window-averaged contrast vs frequency of per-day spikes). The disagreement post-fix is no longer pathological.

---

## §6. Cross-pillar findings

| indicator | bg_std range | hf range (post-fix) | most common disagreement | seeds with plume contamination (ring_p90 ≥ site_p90) |
|---|---|---|---|---|
| air.no2 | 0.80…11.3 | 0.41…0.67 | partial | none |
| air.so2 | 27.4…27.4 | 0.26 | partial | none |
| air.co | 0.41…0.88 | 0.34…0.52 | partial | none |
| air.hcho | 3.58…12.5 | 0.35…0.75 | partial | none |
| air.o3 | 0.23…1.08 | 0.47…0.58 | partial | none |
| air.aai | 0.048…0.090 | 0.46…0.84 | partial | none |
| air.aod | 17.1 | 0.33 | partial | none |
| ghg.ch4 | 7.96…15.5 | 0.00…0.17 | agree (quiet) | none |
| ghg.viirs | 4.05…5.43 | n/a (HF not surfaced) | n/a | none |
| nature.ndvi | 0.015…0.072 | n/a (HF not surfaced) | n/a | none |

**Pillar pattern.** The same key-naming bug affected *every* indicator routed through `_server_side_hf` — Air, GHG.CH₄, GHG.VIIRS, Nature.NDVI. None of them is intrinsically more or less broken than the others; whether the symptom looked like "hf=0" or "hf=1" depended on the sign of the indicator's `bg_median`. GHG.CH₄ at Sapezal is the only indicator in this table whose post-fix hf is still 0 — and that's a real, defensible quiet-aggregate-quiet-per-day outcome (CH₄ at Sapezal is genuinely close to background; per-day max z is only −0.48).

**One pillar-specific observation worth flagging:** Nature.NDVI doesn't surface `hf` (the NDVI snapshot consumes the trend and inverted_anomaly fields instead), and GHG.VIIRS' `hf` is also not surfaced as a primary metric. So the **user-visible** impact of the bug was largely Air-pillar (the wind attributability surface) and CH₄ (via the methane snapshot's surfaced hf). NDVI and VIIRS quietly carried the bad numbers in their provenance but the UI didn't consume them.

---

## §7. Diagnosis

**Root cause (one line):** `_server_side_hf` reads the wrong key from a combined Earth Engine reducer.

In `engine/core/repeatable_core.py:604-622`:

```python
mean_count_reducer = ee.Reducer.mean().combine(
    reducer2=ee.Reducer.count(), sharedInputs=True,
)
mean_key  = band                  # ← bug
count_key = f"{band}_count"

def per_image(image):
    reduction = image.select(band).reduceRegion(reducer=mean_count_reducer, ...)
    count = ee.Number(reduction.get(count_key, 0))
    is_valid = count.gt(0)
    site_mean = ee.Number(
        ee.Algorithms.If(is_valid, reduction.get(mean_key, 0.0), 0.0)
    )
```

When `Reducer.mean()` is combined with another reducer via `sharedInputs=True`, EE auto-suffixes both reducers' outputs to disambiguate. The materialised dict keys are `{band}_mean` and `{band}_count` — confirmed by a live EE probe (`/tmp/ee_reducer_key_probe.py`, run 29 May 2026). There is no bare `{band}` key. So `reduction.get(band, 0.0)` returns the **0.0 default** for every granule, regardless of whether the image was valid.

The downstream consequence is mechanical: `site_mean = 0.0`, so

```
z = (0 - bg_median) / bg_std = -bg_median / bg_std
is_hot = z ≥ z_threshold (= 2.0)
       = (-bg_median / bg_std) ≥ 2.0
       = bg_median ≤ -2 * bg_std
```

For pollutants with positive bg_median (NO₂, SO₂, CO, HCHO, O₃, AOD at all five seeds; CH₄, VIIRS), is_hot is always False → hf = 0. For AAI at tropical seeds (negative bg_median, small bg_std → bg_median ≤ −2σ trivially), is_hot is always True → hf = 1.

**Why this stayed hidden:**

1. `_server_side_hf` lands on the boundary between the engine-side server reduction and the client-side per-day aggregation. The unit test that pins the chunk-result union (`test_server_side_hf_chunk_results_union_correctly_under_concurrency`) mocks `_process_chunk_for_server_side_hf` and never exercises the `per_image` closure against live EE. The `per_image` reducer key handling is therefore untested.
2. The bug's signature (hf=0 nearly everywhere, hf=1 only at a few negative-bg_median indicators) is *visually plausible* as a calibration outcome — clean rural and offshore air "should" be quiet; AAI at tropical seeds firing high is exactly what the engine's original authors of the wind module attributed to "a noise-floor pollutant".
3. The original `Reducer.mean()` standalone reducer (used by `_site_value_reduction` before this milestone) returns `{band: value}` — bare-band key. So copying that key-handling idiom into the combined-reducer path was an easy mistake to make. We hit the same trap during Step B of this milestone with the percentile-extended site reducer; the fix in `site_value()` and `_extract_site_diag_stats` to read `{band}_mean` as fallback was made before the smoke test, but didn't propagate retroactively to `_server_side_hf`.

**Why the "bg_std collapse" and "plume contamination" hypotheses both lined up *just well enough* to seem plausible:**

- The AAI artefact: AAI bg_median is sub-zero and `|bg_median| / bg_std` exceeds 2 at every tropical seed (cv=0.07-0.10, with bg_median itself sub-zero). So the bug fires at exactly the same locations where the "bg_std collapse" story predicted it would. False positive on the bg_std diagnosis.
- The Norilsk silence: NO₂ bg_median ≫ 2 × bg_std, so the silent-zero numerator can never cross the threshold from below. The "ring spatial std inflated by plume" story would have predicted the same hf=0 outcome via a different mechanism. False positive on the bg_std diagnosis.

Both red herrings were structurally consistent with their hypothesised mechanisms — which is why the original spec authors (and the M-WIND-A1 v2.0 demo seeders before them) reached them. The instrumentation built for this investigation killed both hypotheses by surfacing `per_day_site_means = 0.0` for every (seed × indicator × date) cell.

---

## §8. Recommendation

### 8.1 Chosen path: **Path D — one-line key correction (applied in this milestone)**

None of the spec's Paths A/B/C apply: there is nothing to calibrate, no bg_std to fix, no detector to redesign. The detector was *measuring zero* and lighting up only on sign-of-bg_median. The right fix is the one-line change to read the suffixed combined-reducer key:

```python
mean_key = f"{band}_mean"     # was: band
```

This has already landed in `engine/core/repeatable_core.py` (commit message will reference `M-DIAG-A1 §7 / §8.1`). The change is reverted out of *all* the temporary instrumentation at Step F, but the fix itself stays.

### 8.2 Evidence

§5.2's before/after delta is the single most compelling evidence. Sapezal AAI went from hf=1.000 to hf=0.461; Norilsk NO₂ from hf=0.000 to hf=0.675. Aggregate z values are unchanged (as expected — they use a different code path). Per-day z distributions now have realistic spread (Norilsk NO₂ per-day-z spans −2.23 to +24.4 with a median of +2.18, exactly the kind of variance industrial point-sources should produce). §7's live EE probe is the independent root-cause confirmation. §6 confirms the bug was pillar-agnostic — every indicator routed through `_server_side_hf` was affected.

### 8.3 What the chosen fix does NOT solve

- **Thresholds calibrated against the broken detector.** `ANOMALY_Z_THRESHOLD = 2.0`, `WIND_N_MIN_ANOMALY_DAYS = 5`, and the Q-AT-1 / Q-WA-1 thresholds in `engine/constants.py` were tacitly calibrated against a detector that nearly always returned hf=0. Now that hf takes meaningful intermediate values (0.26-0.84 in this data), the thresholds may need re-tuning. See §8.4 / M-DIAG-A2.
- **The "agree (quiet)" CH₄ behaviour at Sapezal.** CH₄ at Sapezal has aggregate z = −0.495 and post-fix hf = 0.000 with per-day-z max = −0.48. This is not a bug — it's genuinely quiet — but it does mean the methane snapshot's `hf` surface is structurally unable to flag anomalies when the entire window is below background. That was true before the fix too; the fix just makes the cases where CH₄ *should* flag actually flag.
- **The wind module's input validation.** During the post-fix Sapezal/Norilsk re-run, `air.aai` at Norilsk now produces 76 anomaly days (vs 0 pre-fix). The wind module's asymmetry-ratio calculation threw `ValueError: mean_asymmetry_ratio must be non-negative, got -1.488` and the wind block degraded to sparse via the existing `try/except` in `six_step` ([repeatable_core.py:1017-1035](engine/core/repeatable_core.py#L1017-L1035)). The graceful-degrade behaved correctly, but the wind module's asymmetry calculation should not be producing negative ratios in the first place. See §8.4 / M-DIAG-A2.
- **Downstream UI counts.** Any cached saved-analysis JSON that includes `hf`, `n_anomaly_days`, or `anomaly_dates_utc` from before the fix is stale. The five production demo seeds in `demo/saved_analyses/` carry stale data — they should be regenerated post-fix before any demo, or explicitly labelled as pre-fix evidence in the report's reference set (this milestone uses them only to demonstrate the bug's signature; post-fix demo regeneration is outside this milestone).

### 8.4 Subsequent fix-implementation milestone (proposed: M-DIAG-A2)

Rough scope, ~1-2 days:

1. **Audit other combined-reducer call sites in the engine** for the same class of bug. Specifically: any `reduceRegion` whose reducer is constructed by `Reducer.X().combine(Reducer.Y(), sharedInputs=True)` and whose result is read via `info.get(band)`. The Step B fix to `site_value()` + `_extract_site_diag_stats` already handles `_site_value_reduction`; this audit is for *other* `combine` patterns that haven't been touched in this milestone.
2. **Add an integration test that exercises `_server_side_hf`'s `per_image` against a live or carefully-mocked EE Image.** The current test mocks the chunker; the right fix is a smoke that runs one granule through `per_image` and asserts the `site_mean` attached to the feature equals the actual `reduceRegion(mean)` over a known pixel set.
3. **Fix the wind module's asymmetry-ratio validation** so a real negative ratio at AAI/Norilsk doesn't have to silent-degrade through the `try/except`. Either: (a) allow negative ratios and document the sign convention; (b) explicitly clamp to 0 with a warning; (c) check the upstream calculation for a sign error introduced by an absolute-value step. The post-fix Norilsk re-run is the first time AAI generated non-zero anomaly days, so this code path has never been exercised before.
4. **Re-tune the Q-WA-1 and ANOMALY_Z_THRESHOLD calibration sweep** that was deferred at M-WIND-A1 v2.0 close. With the per-day detector now functional, the threshold landscape will look entirely different — the 5-seed wind attributability buckets may all re-classify.
5. **Regenerate the 5 production demo seeds** in `demo/saved_analyses/` against the post-fix engine. Tactically defer this to whichever milestone is doing the next demo prep, but flag it so it doesn't get forgotten.
6. **Add a regression test locking in the post-fix hf values at the diagnostic seeds.** Specifically: a test asserting `air.no2.hf > 0.5` at Norilsk and `air.aai.hf < 0.7` at Sapezal (with reasonable tolerance — confirm exact thresholds against the §5.2 data). The bug stayed hidden because no test exercised the `per_image` path against real or realistic EE data; the integration test in item 2 covers the general case, but indicator-specific regression assertions at the two seeds with the strongest known signatures prevent silent regression of this specific bug. This is partially implicit in item 2 but worth surfacing as its own item.

### 8.5 Downstream consumers to coordinate with

- **M-WIND-A1 v2.0** — `wind_n_anomaly_days`, `wind_attributability_state`, `wind_mean_asymmetry_ratio`, `wind_mean_speed_ms`. All five wind in-scope indicators (NO₂, SO₂, HCHO, AAI, AOD) now see real anomaly-day samples for the first time. The Q-WA-1 calibration finding in `engine/constants.py` lines 596-617 ("none landed at state=low") needs revisiting — with the detector functional, several seeds will likely reclassify, and the calibration record should be updated to reflect the post-fix landscape.
- **item 1.4 (trend functionality)** — not yet built. Should be authored against the post-fix detector; the trend module should re-use the corrected `per_image` pattern as the template for per-date series sampling.
- **M-UI-A4 / M-UI-A1-SURFACE** — `hf` and `n_valid_dates` are surfaced in P-05 / P-06 / P-11. The numbers will change for every cached saved-analysis. Either invalidate the cache or regenerate seeds in the demo set before the next demo.
- **Air-pillar `compute_pollutant_snapshot`** — the `air.<pollutant>.hf` field now carries meaningful values for the first time. Any downstream code that treats hf=0 as "all clear" (rather than "no per-day spikes") will need its semantics revisited.
- **`engine.confidence.compute_anomaly_strength_term`** — consumes hf as one input. The post-fix hf distribution shifts the confidence formula's output; expect the per-indicator confidence scores to move (down, in cases where hf was artificially 0; up where hf was artificially 1 at AAI tropical seeds).
- **CH₄ snapshot** — `ghg.ch4.hf` is surfaced in the UI. CH₄ at Sapezal post-fix is hf=0.000 which is *genuinely* quiet; Norilsk CH₄ post-fix is hf=0.167 which is a real intermittent-anomaly signal. Both are now informative; before the fix neither was.

---

## §9. Open questions for the fix spec

**Q-DIAG-A2-1.** Whether to regenerate the 5 production demo seeds in this fix-implementation milestone or defer to the next demo-prep milestone. Argument for in-scope: the current production seeds carry a bug-shaped landscape and any demo run after the fix without regen will produce mismatched UI. Argument for deferring: M-WIND-A1 v2.0's seed regeneration was its own substantial undertaking; bundling it with M-DIAG-A2 risks scope creep.

**Q-DIAG-A2-2.** Whether the wind module's asymmetry-ratio negative-input path is a *bug in the asymmetry calculation* (sign error upstream of the ratio) or a *missing validation case* (real negative values are valid and the validator is wrong). The post-fix Norilsk AAI re-run is the only known-real reproducer; investigating requires running `compute_wind_attribution_extra` with the actual anomaly_dates_utc and inspecting the half-ring contrast calculation.

**Q-DIAG-A2-3.** Whether to extend the audit (M-DIAG-A2 §1) into a generic "combined-reducer key-naming lint" — a static check or a runtime warning when a reducer's output key isn't read by any downstream consumer. Probably out of scope for M-DIAG-A2 but worth flagging here.

**Q-DIAG-A2-4.** Whether to broaden the diagnostic re-run to the 3 deferred seeds (Brasilia, Suape, Comodoro) before the M-DIAG-A2 calibration sweep, or rely on the existing production seeds (pre-fix) plus the Sapezal/Norilsk post-fix data for the calibration. Cost is ~30 min of EE time; benefit is having a complete 5-seed post-fix data set for cross-AOI-scale calibration evidence.

**Q-DIAG-A2-5.** Whether the M-DIAG-A2 audit should include the *non*-`_server_side_hf` reduceRegion sites: e.g. ODIAC's pre-batching code, ODIAC's batched dict in `compute_co2_snapshot`, the Dynamic World categorical reductions in `engine.nature`. The bug pattern is specific to `mean().combine(...)`, but other combined-reducer patterns may have the same trap.

**Q-DIAG-A2-6.** Whether the post-fix hf regression test (item 6) should also assert sign invariants — e.g. that no indicator with positive `bg_median` produces `hf` exclusively at 0 or 1 across all seeds. This would catch the specific failure mode of this bug class generically (any future combined-reducer key bug would produce the same pathological signature). Suggest in scope for M-DIAG-A2.

---

## §9.A — Operator decisions on §9 open questions (Step E, 29 May 2026)

The following decisions were recorded by the operator at Step E review and lock the M-DIAG-A2 scope. They supersede the "open" framing in §9 above for the listed questions.

- **Q-DIAG-A2-1 (regenerate seeds): IN SCOPE for M-DIAG-A2.** Stale saved-analyses are a real downstream consequence; bundling regeneration with the calibration sweep keeps the fix coherent.
- **Q-DIAG-A2-2 (wind asymmetry negative input — bug or missing validation): INVESTIGATE in M-DIAG-A2.** Don't pre-judge. The §8.4 item 3 work is the investigation itself.
- **Q-DIAG-A2-3 (generic combined-reducer key-naming lint): OUT OF SCOPE for M-DIAG-A2.** Flag in `docs/v1x_followups.md`. Worth doing but doesn't block.
- **Q-DIAG-A2-4 (3 deferred seeds — re-run before M-DIAG-A2 or skip): CARRY INTO M-DIAG-A2's seed regeneration task.** The §5.2 before/after already covers the two extreme regimes; the other three would be confirming evidence at the cost of EE time.
- **Q-DIAG-A2-5 (audit beyond `_server_side_hf` — ODIAC, DW, etc.): IN SCOPE for M-DIAG-A2 item 1.** Broaden the audit to cover all `combine()` reducer patterns, not just `_server_side_hf`'s pattern. The bug class is the trap, not the specific function.

Q-DIAG-A2-6 was added at Step E and remains open (suggested in scope for M-DIAG-A2 per the question's own framing).

---

*Document version: DRAFT 0.1 — 29 May 2026. Authored against post-fix engine state (M-DIAG-A1 §7 / §8.1 fix lands in this milestone; instrumentation reverts at Step F). Cited numbers in §4-§6 come from `demo/saved_analyses/diagnostic/{sapezal,norilsk}.json`. Pre-fix evidence in §5.2 comes from the 5 production seeds at `demo/saved_analyses/`. Both sources are committed to the repo per Q-DG-1 (locked at Step A user approval). The 3 deferred seeds (Brasilia, Suape, Comodoro) were dropped from the diagnostic re-run set at Step B.4 operator decision; see §3.3 for the reasoning. Open question Q-DIAG-A2-4 covers whether to fold them in before M-DIAG-A2.*
