# M-GHG-SANITY-A1 — Closed Entry

*VIIRS absolute-intensity + Air-borrow sanity check. Branch `m-ghg-sanity-a1` off `main`, 1 June 2026. Authority: `M-GHG-SANITY-A1_spec.md` v1.0. Pre-redesign investigation — no engine changes (GS10).*

---

## What this milestone found

For 17 AOIs (12 M-VIIRS-DIAG-A1 + 5 production seeds), measured VIIRS absolute radiance (mean/median/sum, floor-masked + unmasked) vs the borrowed Air `combustion_proxy` vs expected GHG-intensity tiers. Headline:

- **The Air NO₂/CO borrow is the best GHG-intensity ranker measured** (Spearman ρ **0.85** vs expected tier; High 0.36 / Mid 0.10 / Low 0.03). It beats radiance-sum (0.78) and the current VIIRS score (0.52).
- **Absolute VIIRS radiance is a *presence* signal, not an *intensity* signal** — radiance-sum separates lit-from-dark (ρ 0.78, driven by wilderness ≈0) but doesn't rank High-vs-Mid; radiance-*mean* inverts (Mid 23.7 > High 21.8).
- **The two are complementary, not redundant** (borrow vs radiance-sum ρ 0.79, vs radiance-mean 0.31) — VIIRS uniquely catches flaring/activity the borrow misses (Patagonia-seed oil/gas region: VIIRS 0.96, borrow 0.10).

## Step D operator decision (1 Jun 2026)

**Option I — retain the Air borrow — and proceed to the VIIRS redesign.** Rationale confirmed with evidence: the borrow is the strongest intensity ranker (§6); VIIRS earns its place on the **presence/flaring** axis (the Comodoro oil/gas case VIIRS caught and the borrow missed). **Drop-VIIRS-entirely was considered and rejected** — it would collapse the GHG pillar to a re-badged Air signal (CH₄/ODIAC are reference-only, so the borrow would be the *only* scored GHG input) and lose flaring detection. Redesign direction: **VIIRS = presence/lit-contrast; Air borrow = intensity; fix VIIRS's saturating grammar.** Implementation is a **separate redesign milestone** (this check is investigation-only).

## Closed-entry verification (GS1–GS10)

- [x] **GS1** — 17 AOIs (12 diagnostic + 5 seeds). Cite: report §2/§3.
- [x] **GS2** — four radiance reducers captured (mean/median/sum + max attempted), floor-masked + unmasked. Cite: CSV columns. (`rad_max` returned null — flagged §8.)
- [x] **GS3** — `combustion_proxy` + `viirs_score` captured. Cite: CSV columns.
- [x] **GS4** — window 2025-09-01→11-30. Cite: §2.
- [x] **GS5** — 10 km radius (uniform; DF native 43 km flagged). Cite: §2.
- [x] **GS6** — expected tiers locked at Step B (incl. Patagonia-seed = Mid/oil-gas). Cite: §2/§3.
- [x] **GS7** — Spearman + rank-tables for analyses A/B/C. Cite: §4–§6.
- [x] **GS8** — report ended with evidence + options, **no** recommendation between them; the Option-I decision is the operator's, recorded above. Cite: report §7.
- [x] **GS9** — production code path + a minimal probe extension for raw radiance (documented). Cite: `analysis/m_ghg_sanity_a1_probe.py`.
- [x] **GS10** — no engine touch: `git diff main -- engine/` empty; full suite passes unchanged.

## Artefacts (committed)

`analysis/m_ghg_sanity_a1_probe.py`, `analysis/m_ghg_sanity_a1_results.csv`, `analysis/m_ghg_sanity_a1_analyses.png`, `docs/M-GHG-SANITY-A1_report.md`, this file.

## Hand-off to the redesign spec

The redesign should: (1) keep the Air borrow as the **intensity** signal (ρ 0.85); (2) re-grammar VIIRS as a **presence/lit-contrast + flaring** signal (fixing the saturation M-VIIRS-DIAG-A1 found); (3) preserve complementarity (don't collapse to one signal). Open items carried: `rad_max` probe fix; the site-vs-ring regional-washout blind spot affecting the borrow at lit-but-regional sites (Suape/DF); external validation via M-VIIRS-EDGAR-A1.

---

*Investigation only; no engine change (GS10). Operator chose Option I + redesign at Step D. Implementation deferred to a separate VIIRS-redesign milestone.*
