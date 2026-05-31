# M-VIIRS-DIAG-A1 — Closed Entry

*Mixed-AOI VIIRS distribution diagnostic. Branch `m-viirs-diag-a1` off `main`, 1 June 2026. Authority: `M-VIIRS-DIAG-A1_spec.md` v1.0. Empirical diagnostic — no engine changes (DG10).*

---

## What this milestone found

The post-M-GHG-REDESIGN-A1 VIIRS score (`contrast_over_lit_window · persistence_factor`) was run across 12 AOIs in three industrial-intensity tiers (4 heavy + 4 middle + 4 quiet). **Verdict: SATURATION.** `persistence_factor` reaches 1.0 for every regularly-lit site (all 4 heavy, all 4 middle, and quiet Appalachia), so the score collapses to `contrast` alone, and `contrast` does not rank intensity (middle 0.78–0.97 overlaps/exceeds heavy 0.78–0.93). The P_FLOOR micro-sweep is **flat** — P_FLOOR is not the effective lever, because `persistence = 1.0 ≥ any P_FLOOR`. The proximate cause of the persistence saturation is the low `VIIRS_LIT_CONTRAST_THRESHOLD = 0.02`. Recommendation: VIIRS tunables enter the calibration-sweep scope, but redirected from P_FLOOR → lit-contrast threshold / contrast grammar / the purpose-built lit-frequency↔emission method filed in `docs/v1x_followups.md`. Evidence, not calibration values (DG7).

---

## Closed-entry verification (DG1–DG10)

- [x] **DG1** — Three-tier 12-AOI set (4 heavy + 4 middle + 4 quiet). Cite: report §2 table.
- [x] **DG2** — Heavy tier: Norilsk, Korba, Jamshedpur, Yanbu. Cite: §2 / `m_viirs_diag_a1_results.csv` `tier=heavy`.
- [x] **DG3** — Quiet tier: Patagonia, NZ South, Appalachia, Amazon-wet (the M-DIAG-A4-vetted clean set). Cite: §2 / CSV `tier=quiet`.
- [x] **DG4** — Middle tier confirmed at Step B (operator accepted): Ploiești, Pavlodar, Vadodara, Rondonópolis. Cite: §2 / CSV `tier=middle`.
- [x] **DG5** — Three metrics captured per AOI (`persistence_factor` [derived], `contrast`, `viirs_score`) + supporting `persistence`. Cite: CSV columns.
- [x] **DG6** — Decision criteria applied mechanically (saturation → working → ambiguous precedence) in `verdict()`; #heavy pf>0.85 = 4/4, #middle = 4/4 → saturation. Cite: report §3–§4.
- [x] **DG7** — Evidence + recommendation only; no calibration values locked. Cite: §6 ("specific values not proposed").
- [x] **DG8** — Production code path `compute_viirs_sustained_contrast`; no debug forks / instrumentation. Cite: probe imports.
- [x] **DG9** — Artefacts committed: `analysis/m_viirs_diag_a1_results.csv`, `…_pfloor_sweep.csv`, `…_plot_{persistence,contrast,score}.png`, probe `analysis/m_viirs_diag_a1_probe.py`, report `docs/M-VIIRS-DIAG-A1_report.md`, this file.
- [x] **DG10** — No engine touch: `git diff HEAD -- engine/ ui/` empty; full suite passes unchanged (see below).

---

## Step B locks (operator, 31 May 2026)

- Middle tier: my 4 proposals accepted (Ploiești, Pavlodar, Vadodara, Rondonópolis).
- AOI radius: 10 km. Window: 2025-09-01 → 2025-11-30 (settled 90 days, avoids VNP46A2 latency).
- P_FLOOR micro-sweep: **unconditional** (free — pure-math recompute on captured metrics).

## Q-DG answers

- **Q-DG-A** — micro-sweep run unconditionally (Step B). It came back flat, which is itself the key §5 finding.
- **Q-DG-B** — seed comparison included (§7 Q1): 4/5 seeds `persistence ≈ 1.0`, `score == contrast`; the Patagonia *seed* scores 0.96 vs a dark Patagonia point's 0.13 (placement sensitivity).
- **Q-DG-C** — the 12-AOI set overlaps two seeds (Norilsk, Patagonia) by design (DG2/DG3 named them); useful for anchoring to the original "lean High" observation rather than a problem.

## Per-AOI anomalies (Step D second output — operator: note in §7, hand to sweep)

- Appalachia ("quiet") scores 0.73 — a false High; the quiet tier is not reliably quiet under the current grammar.
- Patagonia seed (0.96) vs dark Patagonia point (0.13) — VIIRS is acutely placement-sensitive; the "quiet" seed AOI is not actually dark.

Both recorded in report §7 for the calibration sweep / demo-set work.

## Test impact

No engine or test files changed → behaviour unchanged by construction. Full suite run as the DG10 regression check: **see commit / run log** (expected 1957 passed / 31 skipped, offline). `git diff HEAD -- engine/ ui/` is empty.

---

*Diagnostic produced evidence + a recommendation for the calibration sweep's conditional VIIRS-tunables scope. It does not lock calibration values (DG7). The deeper "VIIRS needs a purpose-built method, not a threshold tweak" thread (foreshadowed in the M-DIAG-A4 closure and `v1x_followups.md`) is strengthened by this diagnostic but remains a sweep / future-milestone decision.*
