# M-PERF-A1 — Step A findings + Step B runbook

> Static reconnaissance complete (Claude Code, 28 May 2026). The
> EE-touching parts of Step A (profile + baseline capture) have not
> been run yet — they require user-side EE credentials. This doc is
> the durable handoff. The measured profile report lands at
> `docs/M-PERF-A1_profiling_report.md` once `tools/m_perf_a1_profile.py`
> finishes.

---

## 1. What's in place now

| Asset | Role | File |
|---|---|---|
| Resilience module | retry/backoff + thread-safe call counter + idempotent wrapper installer | `engine/core/ee_resilience.py` |
| App-side install | `app.py` delegates to the module (single line — no inline patching) | `app.py` |
| Unit tests | 32 tests covering predicate, retry behaviour, exhaustion, thread-safety, counter, idempotence | `tests/test_ee_resilience.py` |
| Profile + baseline script | runs the 3 regression AOIs, dumps `tests/baselines/m_perf_a1/*.json`, writes the measured report | `tools/m_perf_a1_profile.py` |

The wrapper composes as `timing-log → retry → original getInfo` — so
the existing `[ee_timing]` log captures total wall-time *including*
retries, which is the right observability default (PF6 commentary).

## 2. Static reconnaissance findings

### 2.1 getInfo chokepoint (Step A.1)

There is a single chokepoint: `ee.ComputedObject.getInfo` is monkey-
patched at app boot. Every `.getInfo()` in the codebase — pillar code,
core helpers, GAUL region loader, tests — routes through it. No user-
code wraps `getInfo` directly, so the new resilience wrapper at
`engine/core/ee_resilience.py:install_getinfo_wrapper` covers
everything for free, including future M-WIND-A1 v2.0 ERA5 fetches
(PF17 — pillar-agnostic placement).

### 2.2 Composition with the existing timing wrapper (Step A.2)

The pre-milestone wrapper in `app.py:141-176` logged elapsed wall time
to `[ee_timing]` and used the `_GSCO_WRAPPED` marker for idempotence
across Streamlit reruns. The new resilience module:

- Preserves the same `[ee_timing]` log format (no log-scraping regression).
- Preserves the `_GSCO_WRAPPED` marker (no nested wrappers).
- Adds retry/backoff *inside* the timing log so the log line reflects
  total elapsed time including any retries (correct observability).

### 2.3 Tenacity availability (Step A.3)

`tenacity 9.1.4` is already installed in the venv — it's a transitive
dependency of `streamlit` and `plotly`. No `requirements.txt` change
is strictly necessary, but pinning it explicitly is recommended at
Step F if we end up shipping. The retry decorator uses
`tenacity.wait_exponential_jitter` (full jitter) with the constants
locked in `ee_resilience.py`:

```python
_RETRY_BASE_S = 1.0
_RETRY_MULTIPLIER = 2.0
_RETRY_MAX_ATTEMPTS = 5
_RETRY_MAX_WAIT_S = 30.0
```

These match spec PF6. Adjust at Step B if the profiling-time 429
observations suggest different ceilings.

### 2.4 EE error signatures (Step A.5)

`ee.data.computeValue` (which `ComputedObject.getInfo` calls) wraps
`googleapiclient.errors.HttpError` into `ee.EEException` carrying
`HttpError._get_reason()` as the message. The status code does **not**
survive the wrap — the EE client throws away everything except the
reason string. Consequence: the `_is_retryable` predicate must
inspect the message text, not a status attribute.

The predicate matches (case-insensitive) any of:
- 429 family: `429`, `too many requests`, `rate limit`,
  `quota exceeded`, `user rate limit`, `resource_exhausted`
- 5xx family: `500`, `502`, `503`, `504`, `internal server error`,
  `bad gateway`, `service unavailable`, `gateway timeout`,
  `deadline exceeded`
- EE transient: `computation timed out` (HTTP 400 + this message
  is the timeout described in `engine/core/repeatable_core.py:416`)

Hard exclusions: `IndicatorComputeError`, `PillarComputeError`, any
non-`ee.EEException` (PF5 — retry is for transport-level transients,
not pillar logic failures).

### 2.5 Important caveat — EE library already retries 5xx

`_execute_cloud_call` passes `num_retries=MAX_RETRIES=5` to
googleapiclient by default. googleapiclient retries HTTP 5xx with
exponential backoff but **not 429**. Consequences:

- **429**: this milestone's retry layer is the *only* retry path. Big win.
- **5xx**: our retry compounds with the library's. Worst case ~25
  attempts over ~150 s. Bounded; rare; the spec PF5 still mandates
  the coverage.
- **Computation timed out**: the library doesn't retry these (HTTP
  400 + message string). Our wrapper does.

### 2.6 Parallelism layout (composes with M-PERF-PARALLEL / 3.4)

`tenacity`'s retry state is per-call (closure-local on the decorated
function), not module-level. Concurrent invocations from different
worker threads do not share state. Verified by
`tests/test_ee_resilience.py::TestConcurrentRetryStateIsolated`.

The worker pools the retry layer composes with:

| Stage | Workers | Code |
|---|---:|---|
| Cross-pillar Air ∥ Nature | 2 | `engine/orchestrator.py:149` |
| Air per-pollutant | 4 (`_AIR_MAX_PARALLEL_WORKERS`) | `engine/air.py:889` |
| GHG per-indicator | 3 (`_GHG_MAX_PARALLEL_WORKERS`) | `engine/ghg.py:1108` |
| Nature per-indicator | 6 (`_NATURE_MAX_PARALLEL_WORKERS`) | `engine/nature.py:2097` |
| HF chunk-level (in Air) | `_SERVER_SIDE_HF_MAX_CONCURRENCY` | `engine/core/repeatable_core.py:570` |

PF12 — batched reductions still dispatch through these pools; nothing
in this milestone removes parallelism. Batching reduces calls
*within* a task; parallelism runs tasks concurrently.

### 2.7 Existing tests (Step A.6)

`tests/test_ghg_integration.py` is the existing real-EE harness
pattern: module-level `pytest.mark.skipif` gated on `RUN_EE_TESTS=1`
+ a fixture that calls `ee.Initialize(project=...)`. Step E's
tolerance-based regression harness will follow the same gating so
synthetic-payload tests keep running fast.

## 3. Static enumeration of getInfo call sites (Step A.4 hypothesis)

These are the calls visible in the source. The hypothesis below is
the spec PF10 candidate list — the measured profile will confirm,
correct, or rerank.

| Pillar | Function | getInfo calls per AOI (hypothesis) |
|---|---|---:|
| Nature | `compute_current_land_cover` | 2 — `frequencyHistogram` + `class_confidence` |
| Nature | `compute_habitat_conversion` | ≥1 — transition reductions |
| Nature | `compute_supplier_spatial_link` | 2 — transition count + centroid |
| Nature | `compute_kba_proximity` | 3 — `.size`, `.distance`, `.area` |
| Nature | `compute_forest_loss` | 2 — lossyear + ring area |
| Nature | `compute_regional_loss_evidence` | 1-2 |
| Nature | `compute_ndvi_condition` | 1+ (via `repeatable_core`) |
| Nature | `compute_water_exposure` | 1+ |
| Nature | `compute_recovery_signal` | 1+ |
| Air | `compute_pollutant_snapshot` × 9 pollutants | each routes through `six_step` — chunked path multiplies |
| Air `core` | `six_step` per-chunk reductions | N chunks × pollutants |
| GHG | `compute_co2_snapshot` / `compute_ch4_snapshot` / `compute_viirs_activity` | ~3-4 each |
| `core/buffers` | `background_ring` land-fraction reduce | 1 per pillar (3 per screening) |
| `core/adaptive_scale` | `adaptive_scale_m` area reduce | 1 per indicator |

The DW-mode duplicate (PF10): `compute_current_land_cover` and
`compute_habitat_conversion` both build `ic.select("label").mode()`
for the current window. M-PERF-PARALLEL (3.4) made them run
concurrently, but they still each compute the mode composite. Step B
decides whether to share it (more saving, more coupling) or leave
the concurrent-duplicate status quo (PF10 default = leave).

## 4. Runbook — how to produce the measured Step A output

```bash
# 1. Make sure EE is authenticated (already configured for the Streamlit app)
export EE_PROJECT_ID=<your-project>
# (or: source .env, or rely on the existing earthengine token)

# 2. Run the profiler against all three regression AOIs (~15–25 min total)
python tools/m_perf_a1_profile.py

# 3. Inspect:
#    - tests/baselines/m_perf_a1/sapezal_5km.json
#    - tests/baselines/m_perf_a1/distrito_federal_43_1km.json
#    - tests/baselines/m_perf_a1/rio_coastal_20km.json
#    - docs/M-PERF-A1_profiling_report.md   ← the measured ranking
```

Each `tests/baselines/m_perf_a1/<aoi>.json` contains the full
`ScreeningRun` payload (the golden fixture for the Step E tolerance
harness), plus the per-AOI profile snapshot and wall-time.

The combined `docs/M-PERF-A1_profiling_report.md` ranks call sites
across all three AOIs (the "top offenders" table the Step B plan is
keyed off).

To re-run a single AOI:
```bash
python tools/m_perf_a1_profile.py --aoi sapezal_5km
```
(this skips the combined report — re-run with `--aoi all` to refresh it).

## 5. Regression-AOI coverage gap

Spec PF16 names four behavioural corners (Sapezal, DF, coastal,
cloudy). The cloudy/sparse corner is omitted from this milestone
because M-FALLBACK-A1's climatology fallback path is not yet
operational — exercising the sparse path now would produce a
baseline that's about to change. Add the fourth AOI once that
milestone lands; the regression harness is built to accept a
4-AOI matrix without code change.

## 6. What to do after the profiler finishes (Step B handoff)

Review `docs/M-PERF-A1_profiling_report.md` and confirm:

- **Top N offenders to batch.** The hypothesis is "top by total count"
  — but a row whose seconds-per-call is high may be worth batching
  even at a lower rank.
- **DW-mode duplicate (PF10 / §4.3).** Decide: share the mode
  composite across `compute_current_land_cover` +
  `compute_habitat_conversion` (more saving, more coupling), or leave
  the concurrent-duplicate status quo.
- **Tolerance epsilon (PF4 / Q-PF-1).** Default is `1e-6` relative
  (`1e-9` absolute). Adjust if any baseline value sits suspiciously
  close to a categorical threshold.
- **Backoff schedule (PF6 / Q-PF-3).** Default 1 s base / ×2 / 5
  attempts / 30 s cap. Reduce if the profiler hits frequent retries.

Once those are locked, I move to Step D (targeted batching, one
offender at a time, regression after each).
