# M-PERF-A1 — Closed entry

*Date: 28 May 2026. Spec: `M-PERF-A1_spec.md` v1.0. Authority: this entry
verifies the locked PF1–PF17 decisions; the user-side regression run
(`RUN_EE_TESTS=1 python -m pytest tests/test_m_perf_a1_regression.py`)
is the final categorical-invariance gate.*

## Summary

Two-part milestone delivered.

**Part A — Retry/backoff resilience layer (item 3.5, done).** Single
chokepoint at `engine/core/ee_resilience.py::install_getinfo_wrapper`
replaces the inline timing wrapper that lived in `app.py`. Composes
`timing-log → tenacity retry → original getInfo` so `[ee_timing]` log
lines reflect total wall-time including retries (correct observability).
Retry predicate matches HTTP 429 / 5xx / EE-specific "Computation timed
out" via message-substring inspection (EE drops status codes during the
`HttpError → EEException` translation). Backoff: 1 s base, ×2 multiplier,
5 attempts, 30 s cap, full jitter. 34 unit tests under
`tests/test_ee_resilience.py`. Wind's M-WIND-A1 v2.0 ERA5 fetches inherit
the layer for free (pillar-agnostic placement).

**Part B — Targeted batching (item 3.1 partial).** Two batches landed in
separate atomic commits:

1. `engine/ghg.py::compute_co2_snapshot` — 4 → 1 `getInfo` (n_months +
   site_sum + site_mean + ring_mean combined into one `ee.Dictionary`).
2. `engine/core/repeatable_core.py::six_step` (no-fallback branch) —
   `site_value` + `background_value` reductions combined into one
   `ee.Dictionary`. Covers all 9 air pollutants + GHG CH4/VIIRS + Nature
   NDVI. Achieved via new `_site_value_reduction` / `_background_value_reduction`
   helpers + `_precomputed=` kwarg on the two public functions so the
   fallback path (which re-calls them with different ICs across SPPY
   windows) keeps its existing call shape.

Measured baseline (Step A profile): 86 `getInfo` calls per AOI across the
three regression AOIs (Sapezal 5 km, Distrito Federal 43.1 km, Rio
coastal 20 km). Expected post-batch: ~71 per AOI (~17% reduction).
Final number gated on the user's regression-harness run.

**`_server_side_hf` batching explicitly deferred** — Step B's Tier-1
named it, but lifting `bg_median` / `bg_std` from Python floats to
server-side `ee.Number` refs (so HF could combine with site+bg in one
dict) crossed PF14's "pure call-consolidation only" lock and introduced
real categorical-flip risk on `hf` / `n_valid_dates` for boundary cases.
Logged as a follow-up in `docs/v1x_followups.md` (M-PERF-A1 status
section) with the ~13% additional reduction available.

**Tests.** 1659 passed, 27 skipped (synthetic suite). 34 new tests under
`tests/test_ee_resilience.py`. 10 new comparator unit tests under
`tests/test_m_perf_a1_regression.py`; 9 EE-gated regression tests (3
AOIs × 3 categories) fire when `RUN_EE_TESTS=1`. Updated mocks in
`tests/test_ghg.py`, `tests/test_six_step_fallback.py`,
`tests/test_repeatable_core.py`, `tests/test_buffers.py` to handle the
batched `ee.Dictionary` call shape.

## PF lock verification

- [x] **PF1. Targeted scope — top offenders only.** Two batches shipped
  (CO2 standalone + six_step site+bg); HF batching deferred with
  documented rationale; Nature `compute_kba_proximity` /
  `compute_habitat_conversion` left in backlog per PF13. Cite:
  `docs/v1x_followups.md::M-PERF-A1 status`.

- [x] **PF2. Tolerance-based determinism (continuous outputs).** Relative
  `1e-6` / absolute `1e-9`. Cite:
  `tests/test_m_perf_a1_regression.py::_REL_TOL` /
  `::_continuous_within_tolerance`.

- [x] **PF3. Categorical-invariance HARD LOCK.** Severity, attributability
  state, sparse flag, skipped_reason, bool, None — all asserted exactly
  via `_diff_payloads`'s `categorical_flip` / `added_path` /
  `removed_path` kinds. Cite:
  `tests/test_m_perf_a1_regression.py::TestDiffComparator
  ::test_bool_is_categorical_not_continuous` and
  `::test_none_vs_value_flagged_as_categorical`.

- [x] **PF4. Tolerance value documented.** Constants at the top of
  `tests/test_m_perf_a1_regression.py` (`_REL_TOL = 1e-6`,
  `_ABS_TOL = 1e-9`). Step B confirmation logged in the spec choice doc.

- [x] **PF5. Retry trigger conditions.** Predicate matches 429 / 5xx /
  EE transient timeouts; rejects 4xx-non-429, auth errors,
  `IndicatorComputeError`, `PillarComputeError`, non-`EEException`. Cite:
  `engine/core/ee_resilience.py::_is_retryable` +
  `tests/test_ee_resilience.py::TestRetryablePredicate`.

- [x] **PF6. Backoff schedule.** `_RETRY_BASE_S = 1.0`,
  `_RETRY_MULTIPLIER = 2.0`, `_RETRY_MAX_ATTEMPTS = 5`,
  `_RETRY_MAX_WAIT_S = 30.0`; full-jitter via
  `tenacity.wait_exponential_jitter`. Cite:
  `engine/core/ee_resilience.py` top-of-module +
  `tests/test_ee_resilience.py::TestRetryBehaviour::test_backoff_wait_is_capped`.

- [x] **PF7. Per-call retry granularity.** Retry decorator wraps the
  innermost `original(self, *args, **kwargs)` call inside
  `install_getinfo_wrapper`; tenacity state is closure-local. Cite:
  `engine/core/ee_resilience.py::install_getinfo_wrapper`.

- [x] **PF8. Thread-safety.** Concurrent retries don't share state.
  Verified by
  `tests/test_ee_resilience.py::TestConcurrentRetryStateIsolated
  ::test_concurrent_calls_independent_state` (two threads with disjoint
  failure patterns). Profile counter uses a single `threading.Lock`;
  verified by `tests/test_ee_resilience.py::TestProfileCounter
  ::test_counter_concurrent_increments` (8 threads × 250 records each).

- [x] **PF9. Profiling-first.** Step A profile ran before any batching
  via `tools/m_perf_a1_profile.py`; produced
  `tests/baselines/m_perf_a1/*.json` (3 AOIs) and
  `docs/M-PERF-A1_profiling_report.md` (ranking). Both batches target
  measured top-of-table call sites.

- [x] **PF10. Batching candidates confirmed by profiling.** Air's
  `compute_pollutant_snapshot` (27 calls/AOI) was the dominant offender,
  confirming spec's PF10 hypothesis; six_step batching covers the air
  + ghg + nature indicators that flow through it. DW-mode duplicate
  decision: leave concurrent-duplicated per PF10 default (1-call extra
  cost vs. coupling two functions — not worth it).

- [x] **PF11. `ee.Dictionary` batching mechanism.** Both batches use
  `ee.Dictionary({...}).getInfo()` for server-side composition. Cite:
  `engine/ghg.py` compute_co2_snapshot body +
  `engine/core/repeatable_core.py::six_step` no-fallback branch.

- [x] **PF12. Composes with M-PERF-PARALLEL (3.4).** Batched reductions
  still dispatch through the per-pillar `ThreadPoolExecutor` pools; no
  pool sizing changed. Cite: `engine/orchestrator.py:149` (Stage-1
  Air∥Nature), `engine/air.py:889`, `engine/ghg.py:1108`,
  `engine/nature.py:2097` — all unchanged. Regression test
  `test_getinfo_call_count_not_inflated` asserts call count is
  monotonically non-increasing under batching, defending against
  accidental serial re-introduction.

- [x] **PF13. Remaining batching left in backlog.** `compute_kba_proximity`,
  `compute_habitat_conversion`, and `_server_side_hf` (deferred separately)
  remain. Cite: `docs/v1x_followups.md::M-PERF-A1 status::Remaining
  backlog`.

- [x] **PF14. No formula / threshold / weight / method changes.** Both
  batches are pure call-consolidation: identical reducer kinds, identical
  scales, identical geometries. The site_value / background_value
  post-processing (incl. SiteBufferNoDataError /
  BackgroundRingNoDataError raises) runs on the materialized inner dicts
  via the `_precomputed=` kwarg, preserving the exact failure shape.

- [x] **PF15. Baseline captured before batching.** Step A profile ran
  with the un-batched code (commit prior to batch #1); golden fixtures
  at `tests/baselines/m_perf_a1/*.json`. The regression harness in Step
  E asserts against those exact files.

- [x] **PF16. Four regression AOIs.** Three covered (Sapezal,
  Distrito Federal, Rio coastal); cloudy/sparse AOI deferred until
  M-FALLBACK-A1's climatology fallback path lands (documented in
  `docs/M-PERF-A1_step_a_findings.md::5 Regression-AOI coverage gap`
  and in the profile report's §1 note). Three of four corners is the
  practical coverage we have; spec PF16 accepts adding the fourth later.

- [x] **PF17. Retry layer is generic for wind reuse.** Wrapper is
  pillar-agnostic — installed at `ee.ComputedObject.getInfo` level via
  the single module-level monkey-patch. M-WIND-A1 v2.0's ERA5 fetches
  go through the same chokepoint with zero additional code. Cite:
  `engine/core/ee_resilience.py::install_getinfo_wrapper` (no
  pillar-specific predicates in the body).

## Regression-harness run — 28 May 2026

Three AOIs, 9 tests, 150 s wall.

| Assertion | Sapezal | DF | Rio | Outcome |
|---|---|---|---|---|
| Continuous within 1e-6 (PF4) | PASS | PASS | PASS | Floats stable under `ee.Dictionary` reorder |
| Call count not inflated (PF12 / §6.4) | PASS | PASS | PASS | Batching strictly reduced round-trips |
| Categorical exact (PF3) | PASS¹ | PASS¹ | PASS¹ | ¹ after harness fix below |

¹ First run flagged 66 false-positive "categorical" diffs per AOI, all of
the shape `_meta.time_range` and `_provenance.<indicator>.time_range`
being a Python tuple in the live run vs a JSON list in the baseline.
Root cause: `_walk_leaves` recursed into `list` but treated `tuple` as a
leaf, so the JSON-loaded baseline (no tuple type) walked a different
path-set than the live `ScreeningRun` output. **No science output
changed** — the continuous and call-count tests, which are insensitive
to container-type representation, both passed first time. Fix:
`isinstance(obj, (list, tuple))` in
`tests/test_m_perf_a1_regression.py::_walk_leaves` + a regression unit
test (`test_tuple_and_list_treated_identically`). Re-run after the fix:
all categorical assertions pass.

## Outstanding work

- **HF batching follow-up.** Logged in `docs/v1x_followups.md`. Future
  milestone (M-PERF-A2?) revisits with a dedicated PF14-compatible
  approach.

- **Profiling-attribution defect fix.** Step A profile's rank-2
  `engine.core.ee_resilience._wrapped_getInfo` bucket (18 calls/AOI) was
  the stack-walker self-counting; fixed in
  `engine/core/ee_resilience.py::_attribute_call` with regression test
  `tests/test_ee_resilience.py::TestAttributionWalkerSkipsOwnModule`.
  Re-running the profiler is optional (no plan change) — the next
  capture will redistribute those 18 calls into their real helper
  buckets.

---

*Reviewed against `M-PERF-A1_spec.md` v1.0 — PF1 through PF17 all
verified above. Wider test suite: 1659 passed, 27 skipped (synthetic
suite). EE-touching regression: 9 tests, gated on `RUN_EE_TESTS=1`.*
