# M-ATTRIB-A2 — Closed Entry

**Milestone.** Air-pillar attributability framing — make explicit, across every Air-pillar user-facing surface, that severity measures **supplier-attributable anomaly against regional context**, not absolute pollution.
**Status.** COMPLETE. Prose + documentation only; no engine numerics changed.
**Branch.** `m-attrib-a2`.
**Date.** 31 May 2026.
**Spec.** `M-ATTRIB-A2_spec.md` (v1.0, 30 May 2026). Step A findings: `docs/M-ATTRIB-A2_step_a_findings.md`.

---

## Step B decisions locked (operator, 31 May 2026)

- **Framing applies per pillar** — the verbal summary is a single Air paragraph from a 15-cell grid, not per-indicator prose (Step A correction to spec §4.5). Per-indicator framing lives only in P-09.
- **PM₂.₅ + PM₁₀ in scope** → **9** Air indicators, not 7 (Step A confirmed both run the §0.2 z-score core; AT2-2 resolved in scope).
- **IC framing statement → §0.7.**
- **P-09 "What this measures" approved, Option 1 (no repetition):** one Air-tab callout carries the canonical framing; AOD is the anchor; the other 8 carry a single indicator-specific line each — no repeated cross-reference boilerplate.
- **ODIAC discovery (out of scope here):** operator noticed the GHG verbal summary still names demoted-reference ODIAC as the severity *driver*. Confirmed real (brasilia/comodoro/norilsk). Decision: handle as a **separate tiny milestone** (the ODIAC analog of M-CH4-A1); audit-doc line 385 sync **flagged for operator to apply**, not touched here. See "ODIAC follow-up" below. GHG verbal prose is therefore **unchanged** in M-ATTRIB-A2.

---

## Step C — what changed

| Step | Surface | File(s) | Change |
|---|---|---|---|
| C1 | AOD validation report | `docs/aod_pm25_validation.md` + `.docx` | §5.3 reframed ("orthogonal" → "tracks local spatial contrast — by design"); new §5.4 "Methodological framing"; docx re-exported (186 KB, 3 figures embedded). Findings unchanged; interpretation corrected. |
| C2 | Methodology doc | `docs/Indicators_Computation_v4.md` | New **§0.7 "Severity framing"**; §1 Air-pillar back-reference; §1.5 cross-reference to §0.7. |
| C3 | P-09 AOD anchor | `demo/indicator_library.json` | Full "What this measures" with validation citation. |
| C4 | P-09 other 8 + callout + plumbing | `demo/indicator_library.json`, `demo/indicator_library.py`, `ui/components/p09_library.py` | One-line framing per indicator (NO₂, SO₂, HCHO, CO, O₃, AAI, PM₂.₅, PM₁₀); Air-tab canonical callout (rendered once); new optional `what_this_measures` field threaded loader→dataclass→renderer, shown after Definition. |
| C5 | Verbal summary | `engine/verbal_summary.py`, `docs/Verbal_Summary_Templates_v1 (1).md` | All 15 Air templates (9 main + 6 fallback) reworded to site-vs-region framing; doc §6.1/§6.2/§9 synced. Normal states say "no anomalous local contribution detected", never "clean air". |
| C6 | P-11 report | `ui/components/p11_sections.py` | Methodology section gains an "attributability framing" paragraph (pillar-wide; covers partial-coverage reports). Pillar findings inherit the C5 verbal-summary changes automatically. |
| C7 | Engine skeleton | `docs/Engine_Module_Skeleton_v1 (1).md` | One-line severity-semantics note pointing to IC §0.7. |

**Tests:** `tests/test_verbal_summary.py` (worked example + two template-selection asserts updated for new phrasing; new `TestMAttribA2SeedProse` locking framing at all 5 seeds); `tests/test_indicator_library.py` (new parametrised `what_this_measures` coverage + AOD-anchor test).

---

## Step D — numerical regression (AT2-10 / R6)

Baseline: `tests/baselines/m_attrib_a2_prose_baseline.json` (captured pre-change in Step A).

- **All severity values, composite scores, confidence values, and verbal-summary `template_ids` byte-identical** before/after at all 5 production seeds. ✓
- **Air prose changed** to the new framing at all 5 seeds (string-match). ✓
- **GHG prose unchanged** (ODIAC deferred). ✓
- **No seed regeneration** (AT2-11) — scores didn't move. ✓
- **Full suite: 1908 passed, 28 skipped** (skips are EE-integration, no creds). ✓

---

## Closed-entry verification (AT2-1 … AT2-13)

- [x] **AT2-1** Named M-ATTRIB-A2; this file + branch `m-attrib-a2`.
- [x] **AT2-2** 9 Air indicators covered (7 core + PM₂.₅/PM₁₀, added at Step B per Step A z-score confirmation); cite P-09 entries + IC §0.7 list.
- [x] **AT2-3** Plain-language balanced tone; cite the §4.1 canonical text (P-09 Air-tab callout / IC §0.7).
- [x] **AT2-4** AAI included with current behaviour (M-DIAG-A4 unaffected); cite AAI's P-09 line.
- [x] **AT2-5** AOD is the anchor; cite the validation citation in AOD's P-09 entry + §5.4.
- [x] **AT2-6** AOD validation §5.3 reframed + §5.4 added; docx re-exported in the same commit.
- [x] **AT2-7** IC v4 single global framing statement at §0.7; per-indicator/§1.5 cross-reference.
- [x] **AT2-8** Verbal summary phrasings locked at Step B; cite §6.1/§6.2 + the 15 engine templates.
- [x] **AT2-9** P-11 inherits verbal-summary phrasing (no per-section copy); methodology paragraph added for PDF readers.
- [x] **AT2-10** No engine numeric changes; cite Step D regression pass.
- [x] **AT2-11** No seed regeneration; scores unchanged.
- [x] **AT2-12** M-UX-A1 parameter registry untouched.
- [x] **AT2-13** Step B phrasing review completed (operator approved A–F, 31 May 2026).

---

## Open items flagged for operator (not applied)

1. **Q-AT2-C — audit-doc row for M-ATTRIB-A2.** Documentation-only milestone; per CLAUDE.md the audit doc is not edited without explicit confirmation. Proposed row: *"M-ATTRIB-A2 — Air-pillar attributability framing (prose/docs only), 31 May 2026; severity = supplier-attributable anomaly; IC §0.7."* Could batch with the pending M-CH4-A1 row.

2. **ODIAC follow-up (separate milestone).** Remove `ghg.co2_context` from `_GHG_DOMINANT_CANDIDATES` + delete its slot formatter in `engine/verbal_summary.py`, mirroring M-CH4-A1's CH8. ODIAC is already out of scoring (M5.5b), so **no seed regeneration and no score change** — only GHG prose at brasilia/comodoro/norilsk changes (drops to combustion/activity driver or the no-dominant fallback). **Proposed audit-doc sync (operator to apply):** edit `docs/Indicators_Audit_and_v1x_Roadmap.md` line 385 — currently *"ODIAC's 2+ year lag must be surfaced everywhere ODIAC contributes to display — verbal summary, KPI tiles, provenance"* — to scope the verbal-summary *dominant-driver* role out, e.g.: *"…surfaced everywhere ODIAC contributes to display — KPI tiles, provenance, and the P-09/C5 reference-dataset surfaces. ODIAC is no longer named as a dominant driver in the verbal summary (reference data does not drive severity prose; see the ODIAC-analog milestone), matching the CH₄ treatment."*
