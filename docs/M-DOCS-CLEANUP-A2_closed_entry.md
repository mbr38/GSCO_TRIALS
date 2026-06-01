# M-DOCS-CLEANUP-A2 — Closed Entry

**Status.** CLOSED — 1 June 2026.
**Type.** Bundled documentation + verification cleanup. No engine changes (defensive regression confirms).
**Branch.** `m-docs-cleanup-a2` off `main`.
**Spec.** `M-DOCS-CLEANUP-A2_spec.md` v1.0.

---

## 1. What landed

Three bundled cleanup deliverables plus one housekeeping note, one milestone:

1. **CS9 — IC v4 calibration-philosophy statement.** Landed the M-CALIBRATION-SWEEP-A1-flagged philosophy statement as a new standalone **§0.8 Calibration philosophy** in `docs/Indicators_Computation_v4.md`, immediately after §0.7 (Severity framing) and before §1.
2. **VR17 — IC v4 §2.3 combustion-proxy methodology paragraph.** Added the combustion_proxy borrow-architecture paragraph to §2.3 (Pillar aggregates), mirroring the engine + UI VR17 work already shipped under M-VIIRS-REDESIGN-A1.
3. **Item 17 — failing-test verification.** Resolved the long-carried carry-flag: the test **passes**. Carry-flag removed.
4. **DC6 — EDGAR scrap housekeeping.** Resolved as already-covered (no new edit); rationale recorded here for the historical record (DC10).

After this milestone the calibration philosophy is canonically documented, the combustion_proxy borrow architecture is fully documented (engine + UI + methodology paragraph), and the Item 17 question is resolved.

---

## 2. Step A reconnaissance findings (deltas from spec premises)

The spec carried several premises that Step A found to be partly stale. Recorded here because they materially shaped Step B:

- **CS9 was not greenfield.** A calibration-philosophy paragraph already existed inside §0.7 (landed by M-CALIBRATION-SWEEP-A1), covering the same ≤20% ceiling / sustained-vs-transient framing. Step B decision (operator): add the locked §4.1 wording as a *new standalone §0.8* and *trim* the existing §0.7 paragraph to a one-line cross-reference (resolves R7 / Q-DC-A). The concrete z-bands (Concern z≥1.0, High z≥2.0) and clean-control evidence live in `docs/M-CALIBRATION-SWEEP-A1_closed_entry.md` §C1, so trimming loses no audit detail.
- **Numbering.** §0 uses a numbered sub-section series (§0.1–§0.7); the spec's placeholder "§0.X" was realised concretely as **§0.8** to match that pattern. Title style matches the existing headers (e.g. "0.7 Severity framing").
- **VR17 target located.** The combustion component had no standalone prose paragraph — it lived only inside the §2.3 code-block comment (the M-GHG-REDESIGN-A1 weight lineage) plus a one-line mention in the §2.4 attributability coverage map (line ~417). The §4.2 paragraph lands cleanly as a new prose block after the §2.3 aggregate, with a back-reference to §2.4. Replaces nothing; supplements (Q-DC-B / R2 / R7 resolved).
- **Item 17 test was renamed.** The exact name `test_six_step_zero_valid_pixels_with_missing_key` no longer exists. It was renamed under M-DIAG-A1 work to `TestServerSideHfEEBugCoverage::test_server_side_hf_handles_zero_valid_pixels_with_missing_key` (`tests/test_repeatable_core.py:541`). That test **PASSES**.
- **EDGAR target file does not exist.** There is no `GSCO_v1x_TodoList.md` in the repo. The live v1.x roadmap is `docs/Indicators_Audit_and_v1x_Roadmap.md` (the authority doc CLAUDE.md forbids editing without confirmation), and EDGAR's v1.x rejection is *already documented there* (lines 381, 872, 908: "redundant with ODIAC… don't reopen for v1.x"). Step B decision (operator): **skip the new roadmap entry** — already covered; record the scrap rationale here only (DC5/DC6 reconciled, DC10).
- **No IC v4 docx.** `docs/Indicators_Computation_v4.md` has no `.docx` counterpart, so C5/R6 (re-export) is N/A.

---

## 3. Item 17 verification result

- **Procedure:** full suite via `pytest tests/ -v --tb=short`, captured at `analysis/m_docs_cleanup_a2_test_output.txt`.
- **Suite result:** **2022 passed, 34 skipped, 0 failed** (14 warnings, all pre-existing deprecation/EE-not-initialized noise).
- **Target test:** `tests/test_repeatable_core.py::TestServerSideHfEEBugCoverage::test_server_side_hf_handles_zero_valid_pixels_with_missing_key` → **PASSED**.
- **Outcome (DC4 binary):** PASSED → carry-flag resolved and removed. No fix-or-carry decision needed. The test's intent (M-DIAG-A1 EE combined-reducer key-shape coverage: `{band_mean, band_count}` not `{band}`) is fully exercised; see the docstring at `tests/test_repeatable_core.py:1370`.

---

## 4. EDGAR scrap — historical record (DC10)

EDGAR re-validation for the VIIRS redesign was **scrapped from v1.x** (operator decision, 1 June 2026). Rationale: ODIAC is the operational external benchmark for GHG; the VIIRS redesign was validated against operator-domain-knowledge ground truth at 17 AOIs (M-VIIRS-REDESIGN-A1 §D); the tool is positioned as a directional screening instrument where independent emissions-inventory precision is not critical-path for v1.x defensibility. Revisit if external-validation pressure emerges from stakeholders. No engine/doc work was done for EDGAR in this milestone; the rejection was already on record in `docs/Indicators_Audit_and_v1x_Roadmap.md` and `GEE_Database_List_v3.md §7`, so DC6's roadmap-line was satisfied without a new edit (DC5: no IC v4 caveat added).

---

## 5. Decision-criteria walk (DC1–DC10)

- **DC1 — Three deliverables bundled.** CS9 §0.8, VR17 §2.3 paragraph, Item 17 verification (+ EDGAR housekeeping) all landed in one milestone / one commit on `m-docs-cleanup-a2`.
- **DC2 — CS9 wording locked.** §0.8 carries the operator-approved §4.1 text verbatim; only the section number (§0.8) and placement were settled at Step B, not the wording.
- **DC3 — VR17 polish additive.** One new prose paragraph in §2.3; the pre-redesign weight lineage in the §2.3 code-block comment is unchanged (additive, mirroring M-DOCS-CLEANUP-A1 DC3).
- **DC4 — Item 17 binary outcome.** PASSED; carry-flag removed. Documented in §3 above.
- **DC5 — No external-validation caveat in IC v4.** None added. IC v4 diff scope is limited to §0.7 trim + new §0.8 + new §2.3 paragraph.
- **DC6 — EDGAR scrap in roadmap.** Reconciled as already-covered (`Indicators_Audit_and_v1x_Roadmap.md` + `GEE_Database_List_v3.md §7`); no new roadmap line, per Step B (the spec's target `GSCO_v1x_TodoList.md` does not exist).
- **DC7 — No engine touch.** `git diff engine/` is empty. (Unrelated pre-existing P-11 UI WIP in the working tree — `templates/p11/shell.html.j2`, `ui/components/p11_sections.py`, `ui/components/p11_templates.py` — was left untouched and is NOT part of this commit.)
- **DC8 — Branch + commit pattern.** Branch `m-docs-cleanup-a2` off `main`; single atomic commit (matches M-DOCS-CLEANUP-A1 DC10 precedent).
- **DC9 — Step B real but small.** Operator confirmed: CS9 placement (new §0.8 + trim line 126), EDGAR handling (skip — already covered). VR17 location and Item 17 outcome were determined by recon and needed no further choice.
- **DC10 — EDGAR scrap context in closure.** Recorded in §4 above for the historical record.

---

## 6. Test-plan verification

- [x] IC v4 §0.8 calibration-philosophy section present with operator-approved wording.
- [x] IC v4 §2.3 combustion paragraph updated per VR17 polish wording.
- [x] §0.7 calibration paragraph trimmed to a one-line cross-reference (no duplication).
- [x] Test verification output captured at `analysis/m_docs_cleanup_a2_test_output.txt`.
- [x] Item 17 test status documented (PASSED; carry-flag removed).
- [x] Defensive regression: full suite passes (2022 passed, 34 skipped, 0 failed; Item 17 passing).
- [x] EDGAR scrap rationale recorded (closure §4); no new roadmap line (Step B).
- [x] IC v4 docx re-export — N/A (no docx counterpart).
- [x] No engine code modified (`git diff engine/` empty).

---

## 7. Carried forward / out of scope

- ~~Stale phrase at IC v4 §0.7 ("VIIRS-based combustion-activity z") predates the M-GHG-REDESIGN-A1 re-grammaring (VIIRS is no longer a z-score).~~ **Fixed (follow-up, operator-confirmed):** §0.7 now reads "the VIIRS persistence-weighted sustained-contrast score — a site-vs-background-ring contrast, not a z-score, per M-GHG-REDESIGN-A1 §2.2a". Still no methodology change (framing-text only).
- Tier 7.6/7.7 audit-doc / spec-doc drift sweeps; auto-enrollment detector; sector-tagging closure debrief — carried.
- Regional-washout UX (item 14a) — separate scoping conversation.
- Pre-existing P-11 report-UI WIP in the working tree — not owned by this milestone.

---

*Closed 1 June 2026. Bundled cleanup: CS9 §0.8 philosophy + VR17 §2.3 combustion paragraph + Item 17 verification (PASSED) + EDGAR scrap housekeeping. No engine changes.*
