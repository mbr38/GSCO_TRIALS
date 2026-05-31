# M-ODIAC-A1 — Closed Entry

**Milestone.** Remove ODIAC (fossil CO₂ context) as a named **driver** in the GHG verbal summary — the ODIAC analog of M-CH4-A1. ODIAC was demoted to standing-exposure reference data in M5.5b and does not feed the live GHG score, so naming it as the *driver* of a GHG severity finding misrepresented reference data as a severity signal.
**Status.** COMPLETE. Prose + one engine change to the verbal-summary candidate list; no scores changed, no seed regeneration.
**Branch.** `m-odiac-a1` (off `m-attrib-a2`).
**Date.** 31 May 2026.
**Origin.** Operator spotted the residual ODIAC driver role during M-ATTRIB-A2 Step B; scoped as a separate tiny milestone (operator decision, 31 May 2026).

---

## What changed

| File | Change |
|---|---|
| `engine/verbal_summary.py` | Removed `ghg.co2_context` from `_GHG_DOMINANT_CANDIDATES`; deleted its `_ghg_dominant_slots` branch. The two surviving live-trio terms (`combustion_proxy` 0.22, `activity_score` 0.11) keep their ordering. Weights are used only for relative ordering, so no rescaling. |
| `docs/Verbal_Summary_Templates_v1 (1).md` | §3.2 candidate table (ODIAC row removed + M-ODIAC-A1 note); §4.2 helper (co2 branch removed); §6.7 Hansen-clause note updated; §9 worked example (GHG now combustion-proxy driven). |
| `tests/test_verbal_summary.py` | Dominant-resolution, fallback, direction-stripping, and worked-example tests updated for the 2-candidate GHG set; obsolete `test_co2_uses_total_and_relative_intensity` removed. |

**Not changed (intentional):** ODIAC stays a reference-dataset surface — P-05 C5 reference card, P-11 reference row ("not used in composite score"), P-09 library entry (`ghg.co2.score`, `data_type=emissions_inventory_allocation`). Verified intact post-change. No engine scoring, composite weights, or seeds touched.

## Why this differs from (and is smaller than) M-CH4-A1

M-CH4-A1 removed CH₄ from **scoring** (composite renormalised, spatiotemporal anomaly, quality aggregates) and **regenerated all 5 seeds**. ODIAC was **already** out of scoring (M5.5b), so this milestone touches only the verbal-summary dominant-driver role. Consequence: **no score change, no seed regeneration** — only GHG prose at the 3 GHG-firing seeds changes.

## Regression (verified)

- ODIAC no longer named in any seed's GHG paragraph. ✓
- `template_ids` and all pillar/composite scores **unchanged** at all 5 seeds (verbal summary doesn't feed scoring). ✓
- GHG prose changed only at **brasilia, comodoro, norilsk** (low-band sapezal/suape name no driver, so unchanged): now "combustion proxy (NO₂ + CO)" driven. ✓
- ODIAC reference surfaces (C5 / P-11 / P-09) intact. ✓
- Full suite: **1917 passed, 28 skipped.** ✓

## New GHG prose at the seeds (post-change)

- brasilia — "…with combustion proxy (NO₂ + CO) as the main contributor (score 0.21, combined NO₂ + CO signal). The signal is within typical regional variability…"
- comodoro / norilsk — "…driven primarily by combustion proxy (NO₂ + CO) (score 0.64 / 0.65, combined NO₂ + CO signal)…"

## Flagged for operator (not applied — audit doc = no edits without confirmation)

**Audit-doc sync, `docs/Indicators_Audit_and_v1x_Roadmap.md` line 385.** Currently: *"ODIAC's 2+ year lag must be surfaced everywhere ODIAC contributes to display — verbal summary, KPI tiles, provenance."* Proposed: drop "verbal summary" from the dominant-driver sense, e.g. *"…surfaced everywhere ODIAC contributes to display — KPI tiles, provenance, and the P-09/C5/P-11 reference-dataset surfaces. ODIAC is no longer named as a dominant driver in the verbal summary (reference data does not drive severity prose), matching the CH₄ treatment (M-ODIAC-A1, 31 May 2026)."* A sync row analogous to the pending M-CH4-A1 row is also reasonable (could batch).
