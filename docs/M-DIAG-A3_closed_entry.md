# M-DIAG-A3 — Closed Entry

*Date: 30 May 2026. Spec: `docs/M-DIAG-A3_spec.md` v1.0. Master deliverable: `docs/M-DIAG-A3_diagnosis_report.md` v1.0. Audit trail: `analysis/m_diag_a3_*.{py,csv}` + `analysis/fig_m_diag_a3_*.png`. Evidence base reused (DGB2): `analysis/aai_firms_validation.csv`, `docs/aai_firms_validation.md`.*

## What this milestone was

Investigation milestone (diagnosis + recommendation, no fix) diagnosing the AAI `bg_std` denominator collapse surfaced by the AAI↔FIRMS validation (5/5 control false positives). Two-phase shape mirroring M-DIAG-A1, but on the **denominator** side. The diagnosis: a **spatial-vs-temporal scale mismatch (H1c)** — `bg_std` is the spatial std of the time-mean field, used to scale per-day temporal deviations — that is **genuine** (not computational) and **generic** (not AAI-specific). Recommended fix: an out-of-window climatological temporal baseline + a defined per-day→event aggregation rule; floor `bg_std` rejected; absolute-AAI gate as secondary only. Fix implementation deferred to M-DIAG-A4.

## Closed-entry verification (DGB1–DGB10)

- [x] **DGB1. Investigation only; no engine changes.** `git diff HEAD -- engine/` is empty. Only `docs/` + `analysis/` additions (+ the pre-existing, not-ours `.gitignore` edit, left untouched).
- [x] **DGB2. Reused AAI validation evidence, didn't re-extract.** D1 H1c, D3, and D4 all recompute on `analysis/aai_firms_validation.csv`. The only fresh probes are the small disambiguation runs the spec's §5 Step C explicitly allows (D1 ring-pixel distribution, D2 cross-indicator survey, D4 out-of-window climatology). Cite: `analysis/m_diag_a3_*.py`.
- [x] **DGB3. Cross-indicator probe was light-touch.** 8 sites × (9 air + CH₄ + VIIRS), a diagnostic survey, not a validation. Cite: report §5 + `m_diag_a3_d2_cross_indicator.csv`.
- [x] **DGB4. Three candidate fixes evaluated.** Floor / climatology / absolute gate, plus the within-window temporal proxy that motivated the out-of-window climatology run. Cite: report §7 table.
- [x] **DGB5. Recommendation made, not locked.** §8 leads with one recommendation, preserves ranked alternatives; §9 lists open questions for M-DIAG-A4; closure pending operator+supervisor confirm (operator confirmed Step E, 30 May 2026).
- [x] **DGB6. Instrumentation reverted at close.** None was added — no `provenance.extra` diagnostic fields, all probes external. Engine diff empty.
- [x] **DGB7. No production seeds regenerated.** `demo/saved_analyses/` untouched (no diff).
- [x] **DGB8. Engine numerator-side untouched.** `_server_side_hf` mean_key fix (M-DIAG-A1) and M-DIAG-A2 calibration unchanged — engine diff empty. M-DIAG-A1 regression locks (`tests/test_seeded_saves.py::TestMDiagA1RegressionLocks`) still pass.
- [x] **DGB9. Empirical floor value produced.** D3 sweep shows no floor separates; the smallest floor reaching ≤1 control FP is 1.0, which destroys 5/9 TP → floor rejected with a concrete value. Cite: report §6 + `m_diag_a3_d3_floor_sweep.csv`.
- [x] **DGB10. Cross-indicator findings inform fix generality.** D2 shows the collapse is generic (O3 ≥ AAI); §8 therefore favours a detector-level (generalising) fix over the AAI-specific absolute gate. Operator left the generic-vs-staged choice open for M-DIAG-A4 (Step E, 30 May 2026).

## Test impact

No engine or test files changed → behaviour unchanged by construction. Spot-checked the M-DIAG-A1 regression locks (the tests most relevant to the per-day HF path): pass. Full-suite count (`1890 + 35` per spec §6) is unaffected.

## Open questions handed to M-DIAG-A4

Per report §9: climatology window definition, the per-day→event aggregation rule (dominates the residual control FP), generic-vs-staged scope (operator left open), z-threshold recalibration, control-set quality re-selection, absolute-AAI co-gate value, and the `to_score`/confidence interaction.

## Notes

- **Q-DGB-A/B/C** answered in the report appendix (NDVI excluded but flagged for A4's generic scope; single recommendation with preserved alternatives; no instrumentation-revert commit needed since the engine diff is empty).
- A handful of untracked `analysis/` files (`extract.py`, `_recon_*`, `locked_locations.json`, `_final25_candidates.json`) are **not** M-DIAG-A3 artifacts and were left untouched.

---

*Reviewed against `M-DIAG-A3_spec.md` v1.0 — DGB1 through DGB10 all addressed. Diagnosis + recommendation: `docs/M-DIAG-A3_diagnosis_report.md`. Fix implementation: M-DIAG-A4 (to be drafted).*
