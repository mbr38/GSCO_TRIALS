# M-DOCS-CLEANUP-A1 — Closed Entry

**Status.** CLOSED — 31 May 2026.
**Type.** Documentation cleanup milestone. No engine changes.
**Branch.** `m-docs-cleanup-a1` off `main`.
**Spec.** `M-DOCS-CLEANUP-A1_spec.md` v1.0 (31 May 2026).

---

## 1. What shipped

Two paired documentation deliverables sharing one methodological foundation (the attributability framing from M-ATTRIB-A2 + the four shipped 30–31 May methodology milestones):

**Deliverable 1 — Audit-doc batch sync.** A new dated `## M-DOCS-CLEANUP-A1 methodology-sync register (31 May 2026)` section appended to `docs/Indicators_Audit_and_v1x_Roadmap.md`, carrying four sync rows (one per shipped milestone) plus a v1.7 version-footer bump.

**Deliverable 2 — AAI → FIRMS validation reframe.** A new additive `## §11 — Methodological reframe under attributability framing` section appended to `docs/aai_firms_validation.md`, with the docx re-exported.

No engine code, constants, seeds, or tests were modified.

---

## 2. Step A reconnaissance findings (notable)

The spec's hypothesised 7-column `Date | Indicator | Decision | Previous | New | Milestone | Evidence` audit-doc table **did not exist** (Risk R1 materialised). The existing ODIAC (§3.2) and Hansen (§4.4 / §9.3) demotion entries are *prose*, not rows. The only existing tabular milestone-decision register is the **`M-TREND-A1 supersedes-prior-doc register`** at the end of the doc. Per R1's mitigation, that register was adopted as the cleanest, most-recent template — the new register mirrors its shape (dated `##` header + intro sentence + table + version-footer bump).

Three cross-reference issues found at Step A and resolved at Step B:

1. **Missing evidence file.** `docs/M-GHG-REDESIGN-A1_closed_entry.md` (cited by spec §4.1 Row 4) does not exist — only `M-GHG-REDESIGN-A1_step_a_findings.md` is present. **Resolution (operator, Step B):** cite only the canonical spec doc `Indicators_Computation_v4.md` §2.2a + §2.3 for Row 4, avoiding the broken link.
2. **Wrong §-anchor for Row 1.** Spec said the CH₄ evidence was `ghg_odiac_validation.md §10`, but §10 there is "Response B — AOI widening". The CH₄→reference decision lives in §8 (option c). Row 1 cites `ghg_odiac_validation.md §8 + §10` and `M-CH4-A1_closed_entry.md`.
3. **Spec self-contradiction in Row 4.** Spec wrote "reweighted 0.60 VIIRS / 0.40 Activity_Score" — but VIIRS *is* the Activity_Score. The correct reweight per IC v4 §2.3 is **0.60·Activity_Score (VIIRS) + 0.40·Combustion_Proxy**; the register uses the correct figures.

The AAI doc runs §1–§8 then §10 (no §9); §11 is therefore the correct next section. §10 already carries a partial numerical-framing note — §11 was written additively to complete the *framing* reread and cross-reference §10.

The docx export command (from the AOD pattern) is `pandoc aai_firms_validation.md -o aai_firms_validation.docx`, **run from inside `docs/`** so the `../analysis/*.png` figure paths resolve (running from repo root drops the 3 figures and yields a 23 KB stub instead of the 687 KB figure-embedded docx).

---

## 3. Closed-entry verification (spec §7)

- [x] **DC1: Bundled in one milestone.** Both deliverables landed in a single commit on `m-docs-cleanup-a1`.
- [x] **DC2: Audit-doc additions follow existing row pattern.** New register mirrors the `M-TREND-A1 supersedes-prior-doc register` template (the cleanest existing tabular pattern; R1 mitigation applied). No new row format invented.
- [x] **DC3: AAI reframe is additive.** §11 section added; report body §1–§10 unchanged (diff is pure insertion — see DC5).
- [x] **DC4: Canonical framing source.** Both deliverables cite `Indicators_Computation_v4.md` §0.7 (the canonical supplier-attributability framing statement from M-ATTRIB-A2). No new framing prose invented.
- [x] **DC5: No rewrites, only additions.** `git diff --stat`: 43 insertions, 0 deletions across the two markdown files; docx is a binary re-export.
- [x] **DC6: Four audit-doc rows.** One each for M-CH4-A1, M-ATTRIB-A2, M-DIAG-A4 v2.0, M-GHG-REDESIGN-A1.
- [x] **DC7: AAI docx re-exported.** `docs/aai_firms_validation.docx` 683,747 → 686,920 bytes (figures embedded, +§11).
- [x] **DC8: No engine touch.** Test suite **1957 passed, 31 skipped** — identical to the spec's stated baseline. `git status` shows only `docs/` changed. The 5 production seeds are byte-identical by construction (no engine/constants/seed path touched).
- [x] **DC9: Step B is real.** Operator reviewed and locked: register format (new dated table), missing-evidence handling (cite IC v4 §2.2a/§2.3), commit pattern (single atomic). Open questions Q-DC-A (chronological order) and Q-DC-B (cross-reference §10 in §11) resolved to spec defaults.
- [x] **DC10: Branch + commit pattern.** Branch `m-docs-cleanup-a1` off `main`; single atomic commit (operator choice over the two-commit bisect option).

---

## 4. Test plan results (spec §6)

| Check | Result |
|---|---|
| Audit doc contains four new rows, one per milestone, following existing pattern | ✅ |
| AAI report contains §11 addendum matching Step B wording | ✅ |
| AAI docx re-exported and renders correctly (figures embedded) | ✅ 687 KB |
| Existing test suite passes unchanged (1957 / 31 skipped) | ✅ 1957 passed, 31 skipped |
| 5 production seeds byte-identical (defensive regression) | ✅ trivially — no engine path touched |
| All cross-references resolve | ✅ M-CH4-A1, ghg_odiac §8/§10, aod §5.3/§5.4, M-ATTRIB-A2, IC v4 §0.7/§2.2a/§2.3, M-DIAG-A4, M-DIAG-A3 addendum all verified present |

---

## 5. Follow-up noted (not in scope here)

- `docs/M-GHG-REDESIGN-A1_closed_entry.md` is absent despite the milestone having shipped (commit `643cf30`). The redesign is fully documented in `Indicators_Computation_v4.md` §2.2a/§2.3, so this is a working-doc gap, not a spec gap — worth writing a closed-entry for consistency with the other milestones.
- CLAUDE.md's authority pointer names the audit doc as "v1.5"; the doc footer is now at v1.7 (was v1.6 before this milestone). The §2 doc-version reference in CLAUDE.md drifts behind the audit doc's own footer — a candidate for the next spec-sync pass.

---

*Closed 31 May 2026. Documentation-only milestone. Both deliverables draw consistent framing language from `Indicators_Computation_v4.md` §0.7 (M-ATTRIB-A2's canonical attributability statement).*
