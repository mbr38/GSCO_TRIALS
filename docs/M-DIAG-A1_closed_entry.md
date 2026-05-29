# M-DIAG-A1 — Closed entry

*Date: 29 May 2026. Spec: `docs/M-DIAG-A1_spec.md` v1.0. Master deliverable: `docs/M-DIAG-A1_diagnosis_report.md`.*

## Summary

Investigation milestone. The instrumentation built to characterise bg_std behaviour surfaced a **single-key bug** in `engine/core/repeatable_core.py::_server_side_hf` instead. The combined `Reducer.mean().combine(Reducer.count(), sharedInputs=True)` reducer's mean output is suffixed `{band}_mean` by Earth Engine to disambiguate from `{band}_count`. The legacy code read the bare-band key, hit the absent-key 0.0 default, and silently zeroed every per-day `site_mean` since the M-TIER-A1 Step 8 path landed. The per-day HF detector was effectively a sign-of-`bg_median` oracle for the entire engine lifetime: positive-bg_median pollutants produced `hf = 0` (the "Norilsk silence"); negative-bg_median AAI at tropical seeds produced `hf = 1` (the "AAI Moderate artefact").

**Outcome:** the spec's Paths A/B/C (calibrate threshold, fix bg_std, redesign detector) were all red herrings. The right fix was a one-line key correction (`mean_key = f"{band}_mean"`), applied in this milestone after operator authorisation lifted DG10. M-DIAG-A2 will pick up audit + calibration + seed regeneration (see §8.4 of the diagnosis report).

**Test posture post-fix:** 1808 passed, 28 skipped. One pre-existing test (`TestServerSideHfEEBugCoverage::test_server_side_hf_handles_zero_valid_pixels_with_missing_key`) had a mock fixture that encoded the same wrong key shape as production code (both were "wrong in the same way") and needed its mock dict corrected to the live EE shape. No real downstream consumer regressed.

## DG lock verification

- [x] **DG1. Investigation scope — single investigation covering both symptoms.** The diagnosis report (§7) shows both symptoms collapse to the same single-key bug. AAI tropical Moderate and Norilsk silence are not separate root causes; they are the same mechanism observed at opposite signs of `bg_median`. Cite: `docs/M-DIAG-A1_diagnosis_report.md` §7 "Why the 'bg_std collapse' and 'plume contamination' hypotheses both lined up just well enough to seem plausible."

- [x] **DG2. Pillar coverage — all pillars.** Air (9 indicators), GHG (CH₄ + VIIRS), Nature (NDVI) were threaded through the instrumented `_server_side_hf` / `six_step` path. The diagnosis surfaces that the bug class is pillar-agnostic — any indicator routed through `_server_side_hf` carries it (§6 of the report). DW / Hansen / ODIAC / KBA excluded by construction (no six-step / bg_std concept). Cite: `docs/M-DIAG-A1_diagnosis_report.md` §6.

- [x] **DG3. Existing seeds only — no new locations / no synthetic injection.** No new seed coordinates were added. The instrumentation re-ran against the 5 existing fixtures (Sapezal, Brasilia, Suape, Comodoro, Norilsk). Operator decision at Step B.4 trimmed the diagnostic re-run set from 5 to 2 (Sapezal + Norilsk) after the diagnosis became legible from the first instrumented re-run — see DG-related note below. Cite: `tools/m_diag_a1_rerun_seeds.py::_FIXTURES`.

- [x] **DG4. Deliverable shape — diagnosis report + recommended fix direction with rationale.** Delivered as `docs/M-DIAG-A1_diagnosis_report.md` (~620 lines, 9 sections). The recommendation in §8.1 names the path (one-line key correction), §8.2 cites the evidence, §8.3 acknowledges what the fix does NOT solve, §8.4 estimates the M-DIAG-A2 scope (6 items), §8.5 enumerates 6 downstream consumers.

- [x] **DG5. Output format — written markdown report at `docs/M-DIAG-A1_diagnosis_report.md`.** Structured per spec §6 (§1 summary → §2 symptoms recap → §3 method → §4 bg_std findings → §5 aggregate vs per-day → §6 cross-pillar → §7 diagnosis → §8 recommendation → §9 open questions). §5.2 includes the before/after delta table; §3.5 documents the root-cause probe. §9.A added at Step E to record operator decisions on Q-DIAG-A2-1 through Q-DIAG-A2-5.

- [x] **DG6. Instrumentation scope — temporary diagnostic fields in `provenance.extra`, reverted at milestone close.** The four diagnostic surfaces D1-D4 (per-day site means, ring percentiles, site percentiles, plume contamination ratios) landed as `provenance.extra._diag_bg_std`. At Step F, the percentile + minMax reducer extensions, the per-day site-mean aggregate, the 5th `ServerSideHfResult` field, the `_extract_*` + `_build_diag_bg_std_bundle` helpers, the `diag_bg_std` six_step return field, and the pillar `_format_result` plumbing were all reverted. Verification: `git diff main -- engine/` should show only the one-line `mean_key = f"{band}_mean"` change (plus the comment block above it) in `engine/core/repeatable_core.py::_server_side_hf` once the milestone is committed.

- [x] **DG7. Re-running existing seeds with instrumentation, into `demo/saved_analyses/diagnostic/`.** Diagnostic outputs landed at `demo/saved_analyses/diagnostic/{sapezal,norilsk}.json` and `_summary.json`. Production seeds at `demo/saved_analyses/*.json` were not overwritten. Cite: `tools/m_diag_a1_rerun_seeds.py::_OUTPUT_DIR`.

- [x] **DG8. Aggregate-vs-per-day question explicitly investigated.** §5.3 of the report names the verdict: the disagreement was a bug, not a methodological distinction. Pre-fix, what looked like a tension between aggregate z and per-day HF was an artefact of the per-day detector being effectively broken. Post-fix, the genuine disagreement cases that remain (e.g. `agree (strong)` at Norilsk NO₂, `aggr-quiet, per-day-saturated` at Norilsk CO) are real and load-bearing.

- [x] **DG9. Recommendation addresses all 3 paths (A/B/C) explicitly.** §8.1 of the report names each path and identifies that the chosen path (D, one-line key correction) is not in the original A/B/C set — exactly the contingency the spec authorised at DG9. The justification: there was no detector to recalibrate (A), no bg_std to fix (B), no detector to redesign (C). The detector was measuring zero.

- [x] **DG10. No implementation in this milestone (HARD LOCK) — LIFTED on operator authorisation 29 May 2026.** Recorded explicitly: at Step B+ the investigation surfaced a one-line production bug, not a methodology question. The operator (Step F handoff message) authorised the lift on the rationale that the diagnosis IS the fix in this case, deferring is artificial, and the change is "obvious-and-contained" (one line, no scope creep). The one-line fix landed in this milestone; the diagnosis report and all DG1-9 deliverables stand as written. The audit-trail visibility requirement (this paragraph) is the only DG10-related artefact carried into closure. Cite: operator message at Step E review; `docs/M-DIAG-A1_diagnosis_report.md` §8.1 "Path D" framing.

## Scope reductions logged during milestone

**Step B.4 — diagnostic re-run set trimmed from 5 to 2.** At operator decision (29 May 2026, during Step B.4 prompt-and-go cycle), the diagnostic re-run set dropped from {Sapezal, Brasilia, Suape, Comodoro, Norilsk} to {Sapezal, Norilsk} — the two extreme cases (clean tropical → AAI artefact; strong-source → Norilsk silence). Justification: with the diagnosis already legible from the first instrumented re-run, the remaining 3 seeds would be confirming evidence at ~30 min of additional EE time. Q-DIAG-A2-4 in §9 of the report carries them into M-DIAG-A2's seed regeneration task. The 3 deferred seeds' production data at `demo/saved_analyses/{low_priority_brasilia,wind_priority_suape,wind_low_attribution_patagonia}.json` remains in the repo and is cited in §5.2's before/after evidence (pre-fix shape).

## Production seed staleness note

The five **production** demo seeds at `demo/saved_analyses/*.json` carry pre-fix `hf`, `n_anomaly_days`, and `anomaly_dates_utc` values:

- `high_priority_amazon.json` (Sapezal)
- `low_priority_brasilia.json` (Brasilia)
- `wind_priority_suape.json` (Suape)
- `wind_low_attribution_patagonia.json` (Comodoro Rivadavia)
- `wind_low_attribution_norilsk.json` (Norilsk)

Consumers downstream of these values will see stale numbers. Known consumers (per §8.5 of the diagnosis report):

- M-UI-A4 severity counts (consume `hf`)
- M-WIND-A1 v2.0 wind attribution state (consumes `wind_n_anomaly_days`, `anomaly_dates_utc`)
- `engine.confidence.compute_anomaly_strength_term` (consumes `hf`)
- Air-pillar `compute_pollutant_snapshot` UI consumers of `air.<pollutant>.hf`
- CH₄ snapshot UI (`ghg.ch4.hf`)
- P-05 / P-06 / P-11 surfaced fields

**Regeneration is deferred to M-DIAG-A2 per operator decision Q-DIAG-A2-1** (in scope for M-DIAG-A2; bundle with the calibration sweep). Demos running between now and M-DIAG-A2 close will use stale numbers — the saved-analyses look the same; the visible inconsistency is between freshly-screened AOIs (post-fix detector) and previously-saved ones (pre-fix detector). Flag if a demo is scheduled in that window.

## Files touched (kept after revert)

- `engine/core/repeatable_core.py` — the one-line fix and the surrounding comment block at `_server_side_hf::mean_key = f"{band}_mean"`.
- `tests/test_repeatable_core.py` — `TestServerSideHfEEBugCoverage::test_server_side_hf_handles_zero_valid_pixels_with_missing_key` mock fixture corrected to use the live EE key shape, with an M-DIAG-A1 comment explaining what was wrong.
- `tools/m_diag_a1_rerun_seeds.py`, `tools/m_diag_a1_smoke.py`, `tools/m_diag_a1_analyse.py` — audit trail per Q-DG-1 (committed).
- `demo/saved_analyses/diagnostic/sapezal.json`, `demo/saved_analyses/diagnostic/norilsk.json`, `demo/saved_analyses/diagnostic/_summary.json` — audit trail per Q-DG-1 (committed).
- `docs/M-DIAG-A1_diagnosis_report.md` — the master deliverable.
- `docs/M-DIAG-A1_closed_entry.md` — this file.

## Files touched (reverted at Step F)

All purely-additive instrumentation:

- `engine/core/repeatable_core.py::_site_value_reduction` percentile + minMax extension
- `engine/core/repeatable_core.py::_background_value_reduction` percentile + minMax extension
- `engine/core/repeatable_core.py::site_value` band-key fallback (no longer needed once percentile reducer reverts)
- `engine/core/repeatable_core.py::_process_chunk_for_server_side_hf` per-day site-mean aggregate (returned to 3-tuple shape)
- `engine/core/repeatable_core.py::_server_side_hf` per_image `site_mean` Feature property + `diag_day_means` accumulator + per-day-site-means dict construction (3 return paths back to 4-arg `ServerSideHfResult`)
- `engine/core/repeatable_core.py::ServerSideHfResult` 5th `diag_per_day_site_means` field
- `engine/core/repeatable_core.py` `_extract_site_diag_stats`, `_extract_ring_diag_stats`, `_safe_ratio`, `_build_diag_bg_std_bundle` helpers
- `engine/core/repeatable_core.py::six_step` `_diag_site_stats` / `_diag_ring_stats` extraction + `diag_bg_std` return-dict entry
- `engine/air.py::_format_result`, `engine/ghg.py::_format_result`, `engine/nature.py::compute_ndvi_snapshot` `_diag_bg_std` provenance plumbing

## M-DIAG-A2 follow-up scope (locked at Step E)

Six items, per §8.4 of the diagnosis report, with operator decisions on each:

1. **Audit other combined-reducer call sites** — broadened to cover all `combine()` reducer patterns (operator: Q-DIAG-A2-5 IN SCOPE).
2. **Integration test exercising `per_image` against live or realistic EE**.
3. **Wind module asymmetry-ratio negative-input investigation** (operator: Q-DIAG-A2-2 INVESTIGATE; don't pre-judge bug-vs-validation).
4. **Re-tune Q-WA-1 / ANOMALY_Z_THRESHOLD calibration sweep**.
5. **Regenerate the 5 production demo seeds** (operator: Q-DIAG-A2-1 IN SCOPE; Q-DIAG-A2-4 fold the 3 deferred seeds into this task).
6. **Add a regression test locking in the post-fix hf values at the diagnostic seeds** (added at Step E review; partially implicit in item 2 but surfaced as its own item).

Q-DIAG-A2-3 (generic combined-reducer key-naming lint) is OUT OF SCOPE for M-DIAG-A2 per operator decision; a v1.x followup note has been added to `docs/v1x_followups.md`.

Q-DIAG-A2-6 (sign invariants in the regression test) remains open; suggested in scope for M-DIAG-A2 per the question's own framing.

## Outstanding work

- **Draft the M-DIAG-A2 spec** as the natural next milestone. Confirm direction with operator before writing.
- **GSCO_v1x_TodoList.md location** — operator's handoff referenced this file (asking to mark item 1.7 done and flag M-DIAG-A2 as next). I could not locate it in the repository at `find . -name "GSCO_v1x_TodoList.md"` or equivalent. Flagged for operator clarification: either the file lives outside the repo (private project tracker) and the update is operator-side, or the file lives at a different path I missed.

---

*Reviewed against `M-DIAG-A1_spec.md` v1.0 — DG1 through DG10 all addressed above. DG10 explicitly lifted during the milestone with audit-trail documentation here. Test suite: 1808 passed, 28 skipped post-fix (1807 before the test mock correction). Diagnosis report: `docs/M-DIAG-A1_diagnosis_report.md`.*
