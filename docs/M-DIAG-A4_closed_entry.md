# M-DIAG-A4 — Closed Entry

*Climatology-baseline denominator (v2.0). Branch `m-diag-a4-fix` off `main`, 31 May 2026. Authority: `M-DIAG-A4_spec.md` v2.0; operator decisions 30–31 May 2026. Numerical-correctness framing (DGC13).*

---

## What shipped

The per-day / aggregate anomaly detector's denominator (`bg_std`) was the **spatial** standard deviation, across the 5–25 km background ring, of the **time-averaged** field — the M-DIAG-A3 H1c scale mismatch: a spatial scale normalising per-day *temporal* deviations. M-DIAG-A4 replaces it with the **temporal** σ of the site's per-day value series over a trailing clean prior period (`max(90, screening_window_length)` days, ending at the screening-window start). `bg_median` (the spatial median of the ring) is unchanged — only the normalisation **scale** becomes temporal.

This is a **numerical-correctness** fix (§0 / DGC13): the spatial std of a time-averaged field is the wrong scale to normalise per-day temporal deviations; the fix uses the right scale. Whether the post-fix detector catches more events than the pre-fix one is incidental to the justification.

**Global replacement (operator decision, 31 May 2026 / DGC11):** the single `bg_std` is consumed by the aggregate z, the per-day HF detector, the composite severity score (`to_score`), and the trend severity — all switch to the temporal denominator. Composite severity scores therefore move; seed regeneration (Phase 3) is load-bearing.

---

## Closed-entry verification (DGC1–14)

- [x] **DGC1** — window `max(90, screening_window_length)` trailing. `engine/core/repeatable_core.py::_climatology_window`; tests `tests/test_m_diag_a4_denominator.py::TestClimatologyWindow` (30→90, 90→90, 180→181, non-ISO→None).
- [x] **DGC2 (amended at E2)** — generic across the affected indicators via the shared `six_step` path; the override lives in `six_step` after site/bg resolution, no per-indicator code. **Scope narrowed from 9 → 8 by operator decision (Phase 3 / E2):** VIIRS is **excluded** (`CLIMATOLOGY_DENOMINATOR_EXCLUDED_INDICATORS`) — its temporal σ collapses at stably-lit sites, the mirror of the H1c spatial collapse. The 8 that take the temporal denominator: O3, AAI, AOD, NO₂, SO₂, CO, HCHO, CH₄ (CH₄ gets it though its severity isn't surfaced, per M-CH4-A1). See "VIIRS exclusion" below. Provenance threaded in both `engine/air.py` and `engine/ghg.py` `_format_result`.
- [x] **DGC3** — aggregation rule preserved. Single-hot-day unchanged; `anomaly_z_hf` / `_server_side_hf` HF semantics untouched. Chronic detection stays with M-TREND-A1/A2.
- [x] **DGC4** — M-FALLBACK-A1 reuse. The per-day climatology sample reuses the tested `engine.core.trend._server_side_day_means` server-side per-day reducer (site-level, Q-DGC-A) rather than re-deriving it. The per-country climatology *fixtures* are the wrong shape (country averages, not site day-by-day) — confirmed in Step A — so on-demand sampling is used, per the spec's DGC4 fallback.
- [x] **DGC5** — stale-data banner. `methodology_version` written by `ui/components/trend_record.py::make_trend_entry` (= `ENGINE_METHODOLOGY_VERSION`, numeric per Q-DGC-B); `is_stale_trend_record` predicate (missing → 0 → stale); `ui/components/trend_view.py::render_saved_trend` shows `STALE_TREND_BANNER`. Tests in `TestMethodologyVersion`.
- [x] **DGC6** — controls. Re-selected set verified in Step A (Patagonia, Amazon wet season, NZ South Island, Appalachia, retained Puerto Rico). Phase 2 live check exercised **Patagonia** (clean control) + **Quebec 2023 wildfire** (event); spot-check indicator **O3** per operator (§ below).
- [x] **DGC7** — composite stability per seed. All 5 seeds regenerated via `tools/regen_m_diag_a4_seeds.py`; before/after in `analysis/m_diag_a4_seed_stability.json`. Movements (original → post-fix, VIIRS excluded): Amazon 0.257→0.231 (−0.026), Brasília 0.308→0.275 (−0.033), **Norilsk 0.535→0.378 (−0.157)**, Patagonia 0.582→0.481 (−0.101), Suape 0.272→0.278 (+0.006). All **defensible** and mostly downward — the temporal denominator removes inflated false-hot scores; Norilsk (heaviest industrial, most inflated pre-fix) moves most, which is precisely the denominator collapse being corrected. No indefensible move remained after the VIIRS exclusion.
- [x] **DGC8** — M-DIAG-A1 numerator path untouched. `_server_side_hf`'s `mean_key` fix is unchanged; M-DIAG-A4 only replaces the denominator value, not the numerator reduction. `git diff` on the `_server_side_hf` reducer body is zero.
- [x] **DGC9 / DGC14** — M-DIAG-A3 addendum. **In-report** section appended to `docs/M-DIAG-A3_diagnosis_report.md` (operator choice), explicitly additive — the main report's conclusions are unchanged.
- [x] **DGC10** — z-threshold review. `ANOMALY_Z_THRESHOLD = 2.0` retained. The live probe + EE-gated regression test show it still separates the Quebec event (hf 0.18, ≥ 4 hot days) from the Patagonia control (hf 0.02) under the post-fix detector — an ~8× hf separation, vs the pre-fix collapse that left controls firing above events. The seed regen produced no degenerate severity at 2.0 (after the VIIRS exclusion). No retune needed for v1.x.
- [x] **DGC11** — confidence/severity side-effects audited. Step A consumer audit (`docs/M-DIAG-A4_step_a_findings.md` A5) enumerated all five `bg_std` consumers. `TestSixStepDenominatorOverride::test_global_replacement_reaches_composite_score` asserts the replacement reaches `to_score`. Confidence's `anomaly_strength` term consumes `hf` (bg_std-derived), not `bg_std` directly; its strict-None semantics are preserved (a σ of 0 strict-Nones z/hf/score via the existing `bg_std<=0` guards).
- [x] **DGC12** — regression test. `tests/test_m_diag_a4_regression_event.py` (EE-gated): AAI catches ≥ 4 hot days at Quebec 2023; event/control separation holds; temporal/spatial ratio > 2 at the control.
- [x] **DGC13** — numerical-correctness framing in closure. §0 + this document frame the fix as a scale correction, not an event-detection improvement.

---

## Files changed

**Engine**
- `engine/core/repeatable_core.py` — `_climatology_window`, `_temporal_std`, `_climatology_bg_std` (graceful-degrade with loud `RuntimeWarning`); `six_step` denominator override + `clim_denominator_extra` provenance.
- `engine/constants.py` — `CLIMATOLOGY_BASELINE_{MIN_DAYS,SPARSE_MIN_VALID_DAYS,MIN_COMPUTABLE_DAYS}`, `ENGINE_METHODOLOGY_VERSION = 1`.
- `engine/air.py`, `engine/ghg.py` — merge `clim_denominator_extra` into `provenance.extra`.

**UI**
- `ui/components/trend_record.py` — `methodology_version` field, `is_stale_trend_record`, `STALE_TREND_BANNER`.
- `ui/components/trend_view.py` — stale-data banner in `render_saved_trend`.

**Tests** — `tests/test_m_diag_a4_denominator.py` (20, synthetic), `tests/test_m_diag_a4_regression_event.py` (3, EE-gated), `tests/test_repeatable_core.py` (stub the denominator in the filterBounds-scope test). Full suite: 1936 passed / 28 skipped (offline).

**Docs / analysis** — `docs/M-DIAG-A4_step_a_findings.md`, `docs/M-DIAG-A3_diagnosis_report.md` (addendum), `docs/aai_firms_validation.md` (§10), this file; `analysis/m_diag_a4_baseline_seeds.json`, `analysis/m_diag_a4_validation_probe.{py,json}`, `analysis/m_diag_a4_seed_stability.json`; `tools/regen_m_diag_a4_seeds.py`.

---

## Phase 2 — live validation (spot-check: O3)

Post-fix engine, production code path (`compute_pollutant_snapshot` → `six_step`). Harness `analysis/m_diag_a4_validation_probe.py`:

| Case | indicator | spatial σ (old) | temporal σ (new) | ratio | hf |
|---|---|--:|--:|--:|--:|
| Patagonia control (clean) | AAI | 0.054 | 0.518 | 9.7× | 0.02 |
| Patagonia control (clean) | O3 | 0.501 | 22.92 | 45.7× | 0.09 |
| Quebec 2023 wildfire | AAI | 0.094 | 0.405 | 4.3× | 0.18 |

The 9.7× AAI control ratio sits inside M-DIAG-A3 §4's documented 2.2–14.2× inflation range; the temporal σ (0.518) matches §4's site-temporal-std range. Clean-control hf falls to 0.02 (from a pre-fix median of 0.33). O3 confirms the generic-collapse fix (D2). Full write-up: `docs/aai_firms_validation.md` §10.

---

## VIIRS exclusion (Phase 3 / E2, operator decision 31 May 2026)

The first seed regeneration surfaced that the temporal denominator **collapses for VIIRS night-lights**: a stably-lit site has near-zero *temporal* variance, so `bg_std_temporal` fell to 0.24–1.7 against a `bg_std_spatial` of 4–23, exploding VIIRS z (e.g. Sapezal 0.83 → 13.82) and saturating its score to 1.0 (severity High) at 3 of 5 seeds. This is the mirror of the H1c spatial collapse the milestone fixes — M-DIAG-A3 §5 foreshadowed it ("VIIRS … spatial std → 0 … the same H1c mechanism in its most extreme form").

Per DGC7 ("indefensible move → explicit operator decision"), this was surfaced. **Decision:** exclude VIIRS from the temporal swap (`CLIMATOLOGY_DENOMINATOR_EXCLUDED_INDICATORS = ("ghg.viirs",)`); VIIRS keeps its prior spatial-std denominator (unchanged behaviour). The deeper finding — neither a spatial nor a temporal z-score is the right anomaly model for a temporally-stable GHG-activity proxy — is filed for a **purpose-built VIIRS method** (lit-frequency ↔ GHG-emission correlation) in `docs/v1x_followups.md`. The 8 column/gridded indicators take the temporal denominator; the AAI/O3 validation is unaffected.

---

## Seed regeneration (Phase 3 / DGC7)

All 5 seeds regenerated against the post-fix engine (VIIRS excluded). Composite movements (original `main` → final), from `analysis/m_diag_a4_seed_stability.json`:

| Seed | composite before → after | Δ |
|---|--:|--:|
| Amazon (Sapezal, 5 km) | 0.257 → 0.231 | −0.026 |
| Distrito Federal (43 km) | 0.308 → 0.275 | −0.033 |
| Norilsk (10 km) | 0.535 → 0.378 | **−0.157** |
| Patagonia (10 km) | 0.582 → 0.481 | −0.101 |
| Suape (10 km) | 0.272 → 0.278 | +0.006 |

The movements are modest and mostly downward: the temporal denominator is generally larger than the collapsed spatial std for the air pollutants, so fewer per-day points cross the z-threshold and the inflated air scores moderate. **Norilsk** — the heaviest industrial site, whose air scores were most inflated by the spatial collapse (pre-fix NO₂ hf 0.675) — moves most (−0.157), which is exactly the inflation the milestone set out to remove (post-fix NO₂ hf 0.13). VIIRS values are unchanged from `main` (excluded per E2), confirming the exclusion is clean. Disposition: **accept defensible movement** (DGC7) — no indefensible move remained once VIIRS was excluded.

The fix's effect direction is **site-dependent**: at spatially-uniform sites the temporal σ ≫ spatial σ (scores fall, fewer spurious hot days). The earlier (VIIRS-included) regen showed the inverse for VIIRS — temporal σ collapses there — which drove the E2 exclusion above.

---

*Effort: Step A recon + Phase 1 (engine + tests) + Phase 2 (live validation) + Phase 3 (seed regen + docs). Aggregation rule preserved (DGC3); M-DIAG-A1 numerator path untouched (DGC8). Composes with M-ATTRIB-A2 (parallel, no overlap).*
