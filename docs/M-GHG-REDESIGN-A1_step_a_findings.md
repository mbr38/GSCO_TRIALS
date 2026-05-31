# M-GHG-REDESIGN-A1 — Step A Reconnaissance Findings (GATE A)

**Date:** 31 May 2026
**Status:** recon complete; GATE A approved by operator (per-image data-access + anomaly-aggregate decisions taken — see §6).
**Scope:** GHG pillar VIIRS night-lights re-grammar (anomaly z-score → persistence-weighted ring-relative sustained contrast) + composite reweight (GATE B).

> This file persists the reconnaissance produced before any code change, per the
> spec's §1.5 mandatory-recon rule. It records ground truth about the *live*
> engine, not intended methodology. Where the spec disagreed with the code, the
> code wins and the disagreement is recorded in §5.

---

## 1. The live GHG scoring path

### 1.1 Composite (verbatim from `engine/constants.py:202`)
```python
CORE_GHG_AUDIT_SUPPORT_WEIGHTS = {
    "ghg.combustion_proxy":  0.815,   # Air NO₂/CO borrow (NOT VIIRS)
    "ghg.activity_score":    0.185,   # == ghg.viirs.score (1:1 passthrough)
}
```
Two terms only. Confirmed in `docs/Indicators_Computation_v4.md:243-245`
(`Core_GHG_Audit_Support_v1 = 0.815·Combustion_Proxy + 0.185·Activity_Score`).

- `Combustion_Proxy` (`ghg.combustion_proxy`) is **borrowed from the Air pillar**
  (`air.industrial_combustion_proxy = 0.60·NO₂ + 0.40·CO`), `engine/ghg.py:755`.
  It is **not** VIIRS-derived.
- `Activity_Score` (`ghg.activity_score`) is a 1:1 alias of `ghg.viirs.score`,
  `engine/ghg.py:774`. **This is VIIRS's only entry into the live composite,
  weight 0.185.**
- CH₄ was demoted to reference data (M-CH4-A1, 30 May 2026); ODIAC/CO₂ demoted to
  standing-exposure display-only (M5.5b). Neither scores.

### 1.2 Second VIIRS path — the spatiotemporal-anomaly aggregate
`ghg.viirs.z` → `compute_ghg_spatiotemporal_anomaly` (`engine/ghg.py:882`) →
`ghg.spatiotemporal_anomaly` → `ghg.audit_followup_priority` at weight **0.3125**
(`GHG_FOLLOWUP_WEIGHTS["anomaly"]`). After CH₄'s reference-data reclassification,
**VIIRS is the sole surviving contributor** to `ghg.spatiotemporal_anomaly`
(CO₂/ODIAC carries no `.z`). Dropping VIIRS `.z` collapses this aggregate.

## 2. VIIRS term computation & normalisation (confirmed)

VIIRS runs the **standard `six_step` z-score pipeline** (`engine/ghg.py:335`),
identical machinery to the air pollutants, on `NASA/VIIRS/002/VNP46A2` band
`Gap_Filled_DNB_BRDF_Corrected_NTL`. It produces:

- `score = to_score(site, bg_median, bg_std, k=3)`
  = `clamp((site − bg_median)/(3·σ_bg), 0, 1)` — `engine/core/normalisation.py:20`.
- `z = (site − bg_median)/bg_std` — `engine/core/repeatable_core.py:431`.

**Denominator:** `bg_std` is the **spatial std of the time-averaged background
ring** (NOT a 3-year temporal baseline as the doc text at IC §2.2 line 231
claims — doc/code drift to fix in §6). M-DIAG-A4 swapped this to a temporal σ for
the 8 air/gridded indicators but **explicitly excluded VIIRS**
(`engine/constants.py:1026`):
```python
CLIMATOLOGY_DENOMINATOR_EXCLUDED_INDICATORS = ("ghg.viirs",)
```
The exclusion comment (`constants.py:1014-1025`) and `docs/v1x_followups.md`
(lines ~10-28) both already diagnose the z-score grammar as wrong for VIIRS and
pre-describe the intended fix as a **"lit-frequency ↔ emission model … Until then
VIIRS severity should be read as a placeholder."** **This milestone is that fix.**
Recon therefore *confirms* the spec rather than contradicting it.

## 3. Per-timestep data availability (load-bearing, spec §1.2)

- **Per-timestep SITE values:** available in principle. `_server_side_hf`'s inner
  `per_image()` (`repeatable_core.py:682`) already reduces each image over the
  **site buffer** server-side (mean+count, day-bucketed), but collapses it to a
  scalar HF/n_valid before returning.
- **Per-timestep RING values:** **not computed anywhere** (grep confirms zero
  per-image ring reductions). The ring is reduced exactly once to a static
  `(bg_median, bg_std)`.
- The new contrast/persistence methodology needs per-image reductions over
  **both** site and ring → **new data access required.** Operator decision (§6):
  add a reusable per-image site+ring helper in `engine/core`.

## 4. Severity, confidence, docs

- **Severity:** VIIRS uses the **z-score grammar** (`ui/components/severity.py:138`;
  tile `ui/components/c4b_kpi_grid.py:177`): bands on `|ghg.viirs.z|` (≥2.0 High,
  ≥1.0 Concern). The headline tile metric is `ghg.viirs.score`, but the band is
  `.z`-driven. Dropping `.z` requires a new score-band grammar.
- **Confidence:** 4-term A1 formula (qa=0.85, n_valid=f(revisit), anomaly_strength
  =f(hf), spatial_context) × column-to-surface (`n_a` for VIIRS).
  `compute_indicator_confidence`, `engine/core/confidence.py:179`.
- **Windows:** presets 30d / 90d (default) / 6mo / 12mo / custom
  (`ui/components/analysis_window_picker.py:11`). VIIRS HF chunk = 90d.
- **Authoritative computation doc:** `docs/Indicators_Computation_v4.md`. v1.x
  master: `Indicators_Audit_and_v1x_Roadmap.md` (do not edit without confirmation).
- **Attributability voice (inherit for new copy):** *"A Concern or Severe severity
  means a local spatial contrast was detected, suggesting a site-attributable
  contribution worth investigating"* (IC §0.7 / M-ATTRIB-A2).

## 5. Contradictions spec ↔ code (recon wins)

| Spec assumption | Reality |
|---|---|
| VIIRS term named `Combustion_Proxy`/`Activity_Score`; composite has several non-VIIRS terms incl. a "NO₂/CO Combustion_Proxy" | `Combustion_Proxy` is the Air NO₂/CO borrow (not VIIRS). VIIRS = `Activity_Score` only. Composite is 2 terms (0.815 / 0.185). |
| VIIRS old weight cannot be assumed valid (implies large weight) | VIIRS already only 0.185 in the composite — but **also** solely drives `ghg.spatiotemporal_anomaly` (→ 0.3125 of follow-up priority). GATE B must weigh both paths. |
| "z-score / normalised against last 3 years background" | Code uses spatial-std of the current window, not a 3-year temporal baseline. Doc drift. |
| Per-timestep lit/contrast may be available | Per-image **site** computable; per-image **ring** is not — needs new access. |
| Exclusion constant gates VIIRS out of a temporal-denominator fix | Confirmed exactly. Becomes obsolete once VIIRS leaves `six_step`. |

## 6. Operator decisions taken at GATE A

1. **Per-image data access:** add a **new reusable per-image site+ring helper** in
   `engine/core` (VIIRS leaves `six_step` entirely).
2. **`ghg.spatiotemporal_anomaly` fate:** **decide at GATE B** — its retirement /
   re-pointing and the follow-up-priority reweight are part of the GATE B composite
   proposal. §2–§3 are implemented first; the full reweight is proposed after.

## 7. Implementation plan (§2–§3, against real code)

1. `engine/core/repeatable_core.py`: `per_image_site_ring_series(...)` — server-side,
   chunked per-image reduction over site buffer **and** background ring; returns the
   per-timestep `(iso_date, site_mean, ring_mean)` series to the engine.
2. `engine/ghg.py`: `compute_viirs_sustained_contrast(aoi, time_range, ee_client)` —
   per-timestep Michelson contrast & lit-mask → `contrast_over_lit_window`
   (high-percentile over lit timesteps) × `persistence_factor(persistence)`; new
   reduced measurement set; reframed confidence; provenance. Dispatcher branches
   `viirs` to this function (mirroring the `co2` branch).
3. `engine/constants.py`: new tunables (`VIIRS_PERSISTENCE_FLOOR`,
   `VIIRS_PERSISTENCE_FLOOR_DISCOUNT`, `VIIRS_LIT_CONTRAST_THRESHOLD`,
   `VIIRS_CONTRAST_PERCENTILE`), each `@parameter`-documented; retire the
   `CLIMATOLOGY_DENOMINATOR_EXCLUDED_INDICATORS` story.
4. `ui/components/severity.py` + `c4b_kpi_grid.py`: VIIRS score-band grammar.
5. Tests: five §2.3 behavioural cases on synthetic per-timestep inputs.
6. **GATE B:** composite reweight + `ghg.spatiotemporal_anomaly` fate.
7. Docs (`Indicators_Computation_v4.md`): new grammar, cross-pillar-divergence note,
   3-year-baseline drift fix, post-GATE-B weights.
