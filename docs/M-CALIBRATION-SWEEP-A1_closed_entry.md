# M-CALIBRATION-SWEEP-A1 — Closed Entry

*Calibration sweep. Branch `m-calibration-sweep-a1` off `main`, 1 June 2026. Authority: `M-CALIBRATION-SWEEP-A1_spec.md` v1.0; operator decisions 1 Jun 2026 (attribution re-frame, per-category dispositions). No engine value changed — this is a **"calibrated & confirmed"** outcome.*

---

## Headline

The sweep reviewed every in-scope threshold against evidence and **confirmed the current values — none changed.** The one category that needed action (VIIRS) turned out not to be threshold-tunable at all and was escalated to a method redesign. The real improvements for v1.x are **structural, not threshold tweaks.**

A load-bearing re-frame happened at Step B/C (operator, 1 Jun 2026): the tool's purpose is **attributing sustained pollution to a supplier over a user-selected window**, NOT catching transient events. The spec's "maximise event capture" philosophy (CS2) was re-interpreted accordingly — "events" = sustained, attributable, supplier-linked pollution (mines/refineries/smelters), not wildfires/dust. The calibration test set was rebuilt around known high-pollution industrial sites vs clean controls.

---

## Per-category dispositions (C1–C6)

| Cat | Threshold(s) | Disposition | Evidence / reason |
|---|---|---|---|
| **C1** | air `SEVERITY_BANDS.zscore` (global High 2.0 / Concern 1.0) | **Keep** | Industrial-vs-clean grid (`m_calibration_sweep_c1_attribution.csv`): at 1.0, **0/5 clean controls fire, 6/10 industrial fire**; no grid point hits ≥90%/≤20%; lowering to 0.5 only adds a curtailed smelter at the cost of a clean-site FP. Current cut already near-optimal. Bands are **global, not per-indicator** (operator chose not to restructure — in-scope). |
| **C2** | `HABITAT_SPATIAL_LINK_HIGH_KM` 1.0 / `_MOD_KM` 3.0 | **Keep** | No habitat-conversion ground-truth set in the calibration data (air-pollution events/controls only). 1/3 km are interpretable spatial judgments; defer to a dedicated Nature-attribution calibration if that test set is built. |
| **C3** | `HANSEN_LOSS_RATIO_THRESHOLD` 2.0 | **Keep** | Hansen is reference-data only (audit §9.3); the threshold drives only a non-headline audit-trail boolean. Tuning it changes nothing user-facing. |
| **C4** | `TREND_SIGNIFICANT_P` 0.05 / `TREND_WEAK_EMERGING_P` 0.10 / Theil-Sen K | **Keep** | Standard statistical conventions; operator elected to retain (Q-CS-B confirmatory path). Tier stays spec-mandated, sweep cited as confirming. |
| **C5** | M-FALLBACK confidence multipliers ×0.60 (SPPY) / ×0.75 (climatology) | **Keep** | Confidence *down-weights*, not severity/capture — not grid-calibratable against an event/control set. 0.60/0.75 are defensible trust-discount judgments. |
| **C6** | VIIRS tunables (`P_FLOOR`, `LIT_CONTRAST_THRESHOLD`, contrast central-tendency) | **Escalate — out of sweep scope** | M-VIIRS-DIAG-A1: P_FLOOR inert. This sweep (`m_calibration_sweep_c6_lit_sweep.csv`): raising `LIT_CONTRAST_THRESHOLD` 0.02→0.30 is **flat** (heavy mean 0.86, middle 0.89 at every value — middle never separates). No VIIRS tunable fixes the saturation; it's structural in the Michelson-contrast grammar. → purpose-built redesign (`v1x_followups.md`), a separate milestone. |

---

## Closed-entry verification (CS1–CS12)

- [x] **CS1** — scope adhered to; composite weights untouched (see CS4). VIIRS conditional scope resolved to "escalate," not tune.
- [x] **CS2** — maximise-event-capture philosophy applied, **re-framed to sustained-supplier-attribution** (operator, 1 Jun). Metric: industrial-fire rate at FP ≤ 20% on clean controls. Outcome: current band optimal; no change.
- [x] **CS3** — calibration set (industrial sites + clean controls) used; held-out evaluation moot (no value changed → engine identical to `main`, so held-out behaviour = production behaviour). Documented rather than run.
- [x] **CS4** — composite weights untouched (GHG 0.60/0.40 unchanged). Two escalations surfaced, not acted on: VIIRS redesign (C6); absolute-pollution-level emphasis (C1 — see note).
- [x] **CS5** — mixed mechanics: C1 grid-searched (industrial-vs-clean); C2–C5 hand-reviewed; all retained.
- [x] **CS6** — seed discipline: **no seeds regenerated** — no threshold value changed, so composites don't move. Multi-band guardrail not triggered.
- [x] **CS7** — re-validation: **none required** — no validation report's thresholds materially changed. AAI/AOD/GHG reports unaffected.
- [x] **CS8** — per-threshold operator approval: each category (C1–C6) approved individually 1 Jun 2026.
- [ ] **CS9** — calibration-philosophy documentation in IC v4 §0.X: **pending operator OK** (touches the authoritative `Indicators_Computation_v4.md`; per CLAUDE.md not edited without confirmation). Proposed statement: *"v1.x thresholds reviewed by M-CALIBRATION-SWEEP-A1 and retained; severity tuned for sustained supplier-attributable pollution at a ≤20% clean-site false-positive ceiling, not transient-event capture."*
- [x] **CS10** — held-out acceptance: N/A (no calibration delta to overfit).
- [x] **CS11** — branch `m-calibration-sweep-a1` off `main`.
- [x] **CS12** — closure narrative: this document.

---

## Escalations surfaced (not acted on — CS4)

1. **VIIRS needs a method redesign, not calibration** (C6). The contrast·persistence grammar saturates for any lit site and can't rank industrial intensity; no tunable helps. → purpose-built absolute-radiance / emissions-anchored method (filed in `v1x_followups.md`).
2. **Regional-embedding limit on the air severity *colour*** (C1). The z-anomaly severity tile measures *local contrast*, so a supplier in a uniformly-polluted region (e.g. Mpumalanga) shows "Normal" even when absolute pollution is high. **Resolved as a UX-emphasis note, not a gap:** the absolute level is already computed and displayed as the **"Site value"** metric in the screening drilldown ([indicator_detail.py:62](../ui/components/indicator_detail.py#L62)). Optional future UX: let absolute level influence the headline colour for regionally-embedded sites. No new signal/data needed.

---

## Artefacts (committed)

`analysis/m_calibration_sweep_c1_attribution.py` + `…_attribution.csv` + `…_grid.csv` (C1 industrial-vs-clean grid); `analysis/m_calibration_sweep_c1.py` + `…_zvalues.csv` + `…_grid.csv` (the initial event-framed grid that surfaced the re-frame); `analysis/m_calibration_sweep_c6.py` + `…_c6_lit_sweep.csv` (VIIRS lit-threshold gate). No engine or UI code modified — `git diff HEAD -- engine/ ui/` is empty.

---

*The sweep's honest result: v1.x thresholds are already defensible and were confirmed, not changed. The genuine v1.x improvements are structural (VIIRS redesign; optional absolute-level UX), surfaced as escalations. Composite weights untouched (CS4); statistical conventions retained (C4); reference-only and confidence-penalty thresholds retained (C3, C5).*
