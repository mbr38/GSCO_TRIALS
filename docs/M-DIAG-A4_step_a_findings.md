# M-DIAG-A4 — Step A Reconnaissance Findings

*Version 1.0 — 31 May 2026. Reconnaissance only — no engine code changed; the `engine/` diff vs `main` is empty. Authority: `M-DIAG-A4_spec.md` v2.0 §5 Step A. Numerical baseline persisted at `analysis/m_diag_a4_baseline_seeds.json` (Step A item 6).*

This report answers the six Step A questions and surfaces the complications that the Step B operator gate must resolve **before** Phase 1 implementation begins.

---

## A1 — Shared code-path location (and a complication)

**Confirmed surface.** `bg_std` is computed in exactly one place: `engine/core/repeatable_core.py::_background_value_reduction` (lines 163–196), via

```python
img = ic.mean()                                   # time-average the windowed ring
reducers = median.combine(stdDev, sharedInputs)
img.reduceRegion(reducers, geometry=ring, ...)    # bg_std = SPATIAL stdDev of the time-mean field
```

This matches the M-DIAG-A3 §4 mechanism exactly: the std is a **spatial** spread over the ring of a **time-averaged** image — the wrong scale for the per-day temporal deviations it normalises.

**Complication (must be resolved at Step B).** The spec's §4.1 post-fix pseudocode assumes the climatology baseline can be dropped in "at `_background_value_reduction`". It cannot be a pure in-place swap, because that function only receives:
- `image_collection` **already filtered to the screening window** (`ic_window`, built in `six_step` lines 792–796), and
- the background `ring`.

It does **not** receive the *unfiltered* collection or the screening-window **start date** — both of which the trailing-climatology sample needs (`clim_start = screening_window_start − baseline_days`; `clim_end = screening_window_start`). So Phase 1 must thread the **unfiltered `image_collection`** and **`time_range`** down to a new denominator helper (e.g. `_climatology_bg_std(image_collection, aoi, band, time_range, scale)`), and `six_step` must call it. The spatial-median numerator (`bg_median`) is unaffected and stays where it is.

Net: the change is *localised* (one new helper + one call-site rewire in `six_step`), but it is **not** a one-line edit inside `_background_value_reduction`. The unfiltered collection is available in `six_step` (the `image_collection` parameter, before `ic_window` is derived).

## A2 — `max(90, screening_window_length)` implementation

Trivially available. `six_step` already has `time_range`, and `_window_days(time_range)` (line 329) returns the inclusive day count. The new logic is one line:

```python
baseline_days = max(90, _window_days(time_range) or 90)
```

The only work is **threading** `baseline_days` (or `time_range`) into the new denominator helper — see A1. No new constant strictly required, though a `CLIMATOLOGY_BASELINE_MIN_DAYS = 90` in `engine/constants.py` is the house style (no magic numbers in pillar/core code).

## A3 — Saved-trend `methodology_version` field

**Schema target:** `ui/components/trend_record.py::make_trend_entry` (lines 90–121) builds the `type="trend"` record as a plain dict (no dataclass). Add `"methodology_version": ENGINE_METHODOLOGY_VERSION` there.

**Render/banner target:** `ui/components/trend_view.py::render_saved_trend` (line 101) is where a re-opened trend is drawn — the stale-data banner comparison goes here: `record.get("methodology_version", 0) < ENGINE_METHODOLOGY_VERSION`.

**New constant:** `ENGINE_METHODOLOGY_VERSION` does not exist anywhere yet (grep-clean). Create it in `engine/constants.py` set to `1` (per §4.5; pre-M-DIAG-A4 records default to `0` → banner fires). Backward-compatible: the field is simply absent on the 5 current seeds and any pre-existing trend save, and `.get(..., 0)` triggers the banner.

**Note:** the 5 production seeds are all `type="screening"`, not `type="trend"` (verified). So `methodology_version` lands only on trend records; the screening seeds are versioned implicitly by regeneration (Phase 3 / DGC7). No saved-trend seed exists in `demo/saved_analyses/` to migrate.

## A4 — Re-selected controls (DGC6)

Spec-locked set: **Patagonia, Amazon (wet season), NZ South Island, Appalachia, retained Puerto Rico.** Still defensible vs the M-DIAG-A3 §7 caveat (3/5 original controls had transient absorbing-aerosol days). Two notes for Step B:
- **Patagonia** and **Amazon** coincide with existing *production-seed* AOIs (`wind_low_attribution_patagonia`, `high_priority_amazon`). The validation controls are independent clean windows, not the seed AOIs — but worth confirming the control windows are chosen for cleanliness, not reused from the seed setups.
- **Amazon wet season** is genuinely clean for absorbing aerosol only in the wet months; the control window dates must sit inside the wet season (≈ Dec–May) or it reintroduces the same biomass-burning contamination M-DIAG-A3 warned about.

These are **Phase 2** (live-EE) selections; Phase 2 cannot run without the `supply-chain-observatory` EE project + credentials (see "Execution constraint" below).

## A5 — Downstream `bg_std` consumer audit (DGC11) — **the key design decision**

`bg_std` is a **single value** computed once and consumed by **five** surfaces:

| # | Consumer | Location | Uses `bg_std` as |
|---|---|---|---|
| 1 | Aggregate `z` | `repeatable_core.anomaly_z_hf` L314 | `z = (site − bg_median) / bg_std` |
| 2 | Per-day HF detector | `repeatable_core._server_side_hf` L581 | per-day `z = (site_meanₜ − bg_median) / bg_std` → `is_hot` |
| 3 | Composite severity score | `core/normalisation.to_score` L36 | `score = raw / (k · bg_std)` |
| 4 | Trend severity / slope-σ | `core/trend.py` L216/227/422 | `slope_sigma = slope / bg_std` |
| 5 | Confidence `anomaly_strength` | `core/confidence.compute_anomaly_strength_term` | **indirect** — consumes `hf`, which is bg_std-derived (#2), not `bg_std` itself |

**The decision Step B must make explicit:** the spec's §0/§1 language ("the **per-day HF detector** uses a temporally-grounded denominator") describes consumer #2. But §4.2 ("only the underlying `bg_std` definition changes" → all 9 indicators inherit) and DGC7 (seed-composite movement expected) + DGC11 (audit severity/confidence shifts) describe a **global** replacement of the single `bg_std`, which moves consumers #1, #2, #3, **and** #4 — i.e. **the composite severity scores will move**, not just the per-day hot-day flags.

My reading of the spec as a whole (DGC7 "accept defensible movement", seed regeneration scoped in, DGC11 severity-shift audit) is that the **global replacement is intended**: `bg_std` becomes the temporal climatology std everywhere. But because the §0 framing repeatedly says "per-day HF detector," this should be **confirmed at Step B**, since the two readings differ sharply in blast radius:
- **Global (my reading):** severity scores (#3) and trend severity (#4) move → seed regen is load-bearing, DGC7/DGC11 are real work.
- **Per-day-only:** only `is_hot`/`hf` (#2) moves; `to_score`/aggregate-z/trend keep the spatial std → seeds barely move, DGC7/DGC11 nearly trivial, but the aggregate `z` and severity stay on the "wrong" denominator the diagnosis condemned.

I recommend **global** (it is the only reading consistent with the numerical-correctness framing in §0: if the spatial std is the wrong scale, it is wrong for `to_score` too). Flagging rather than assuming, per CLAUDE.md §9.

`to_score`, `anomaly_z_hf`, and `trend` all already guard `bg_std <= 0 → None`; the temporal std is ≥ 0 by construction, so the degenerate-path semantics are preserved.

## A6 — Numerical regression baseline (captured)

Persisted to `analysis/m_diag_a4_baseline_seeds.json`: per-seed, per-indicator `z`, `hf`, `score`, `confidence`, `site`, `background` across all 5 production seeds. This is the pre-fix snapshot for the Step E2 composite-stability comparison (DGC7). Headline pre-fix values (the surfaces the fix will move under the global reading):

- AAI per-day `hf` runs **0.36–0.84** across seeds (the over-firing the diagnosis flagged); aggregate `z` is small/negative (−1.56 … +0.15).
- Air severity scores presently driven by aggregate `z`/`to_score` (e.g. Norilsk NO₂ score 1.000 @ z 3.25; Patagonia AOD 0.644 @ z 1.93) — these are the scores at risk of "defensible movement" once `bg_std` becomes temporal.

---

## Execution constraints (not in the spec's Step A list, but blocking)

- **Phase 2 needs live Earth Engine.** Re-extracting AAI at the re-selected controls + the event set (D1/D2) requires the `supply-chain-observatory` EE project and (for any cross-check) Earthdata credentials, neither of which is in the repo/env. Phase 1 (implementation + engine-internal tests) and the Phase 3 *code* (banner, version field) can proceed offline; the **validation re-run and seed regeneration require EE access** the operator must supply or run.
- **Test baseline.** The spec cites "1898 from M-CH4-A1 baseline." The current tree has 86 test files; the absolute test count should be re-measured with `pytest --collect-only` at the start of Phase 1 so the "full suite passes" gate (C4) is anchored to the real number, not the spec's stale figure.

---

## Step B — decisions requested before Phase 1

1. **DGC11 / A5 — `bg_std` replacement scope:** global (all five consumers, severity moves) vs per-day-detector-only. *Recommend: global.*
2. **DGC1 / A1 — implementation surface:** confirm threading the unfiltered `image_collection` + `time_range` into a new `_climatology_bg_std` helper called from `six_step` (the spec's "edit `_background_value_reduction` in place" is not feasible as written).
3. **DGC6 / A4 — controls:** confirm the 5 control windows are independently clean (Amazon window inside wet season; controls not reused from seed setups).
4. **DGC9 / A3 — addendum location:** M-DIAG-A3 report in-file vs sibling `docs/M-DIAG-A3_addendum.md` (Q-DGC-C suggests sibling).
5. **Phase 2 spot-check indicators:** which 2–3 beyond AAI (spec §2.2 / D4). *Suggest O3 + AOD (highest control over-fire in M-DIAG-A3 §5) + NO₂.*
6. **Q-DGC-A — site-level vs ring-level climatology std:** spec suggests site-level for v1.x. Confirm.
7. **Q-DGC-B — `methodology_version` type:** numeric int + version-map doc (spec-suggested). Confirm.
8. **Q-DGC-D — regression-test event (DGC12):** Quebec 2023 wildfires vs a more recent event, pending Phase 2 data availability.
9. **Execution:** confirm who runs the live-EE Phase 2 re-extraction + Phase 3 seed regeneration, given EE credentials are not in-repo.
