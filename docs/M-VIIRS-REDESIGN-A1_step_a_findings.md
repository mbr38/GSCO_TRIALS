# M-VIIRS-REDESIGN-A1 — Step A→B findings + locked design (checkpoint)

*1 June 2026. Branch `m-viirs-redesign-a1`. Step A recon + Step B locks complete and operator-confirmed; additive scaffolding landed (suite 1963 green). The core-grammar swap (rest of Step C) + Steps D/E are the focused follow-on. This doc carries the locked design + evidence so the next session resumes cleanly.*

---

## The key Step A→B finding (VR3 refined with evidence)

The spec's flaring grammar (VR3 = **self-relative** outlier, site median + 3σ) **was tested and fails** — it reproduces the saturation it was meant to fix. Distribution-check at the 17 AOIs (`analysis/m_viirs_redesign_a1_distcheck.csv`):

- tier means flaring(3σ): High 0.028, **Mid 0.033 > High**, Low 0.012 — no intensity ranking.
- **No separating threshold exists:** Appalachia-forest = 0.031 and Sapezal-town = 0.031 sit *above* Korba-steel (0.022) and Jamshedpur (0.021). A self-relative outlier-fraction measures distribution *shape*, not *level* — it throws away the absolute brightness that distinguishes a flare from a town.

**Operator decision (1 Jun): severity = "intense emissions source"; the tool is directional (guide auditing, not audit perfectly).** → VR3 refined from self-relative to **absolute-anchored**. Probe (`analysis/m_viirs_redesign_a1_abscheck.csv`):

- **`frac>100 nW` separates cleanly:** all quiet sites ≈0 (Appalachia **0.000**), intense sources 0.02–0.15 (Comodoro 0.064, Yanbu 0.15, Norilsk 0.034). Comodoro fires (VR8 ✓); quiet stay quiet (VR9 ✓).
- Caveats accepted as directional: doesn't perfectly *rank* (bright cities ≈ heavy industry); misses dim-NTL industry (Korba frac>100=0.003) — **but the Air borrow catches Korba (combustion_proxy 0.30)**. VIIRS-intensity and the borrow are complementary (VIIRS catches flares the borrow misses; borrow catches dim combustion VIIRS misses).

Lit-contrast (attributability) **works as-specced**: percentile vs ring all-pixel — High 0.97 / Mid 0.92 / Low 0.67; Suape (regionally embedded) 0.74 → moderate.

## Locked Step B decisions

| Item | Lock |
|---|---|
| Flaring grammar (VR3 refined) | **Absolute-anchored**: `viirs_flaring = min(frac_site_pixels_brighter_than_100nW / 0.10, 1.0)` |
| Lit-contrast (VR2) | Percentile of site median brightness within ring **all-pixel** (lit+dark, land-masked) distribution |
| Composite weights (VR5/B1) | **W_flaring 0.40 / W_borrow 0.60** (first-pass — borrow is the stronger ranker, ρ 0.85; VIIRS-intensity complements). Revisable. |
| Attributability bins (B2) | high ≥ 0.90, moderate ≥ 0.60, else low; sparse if ring < 20 lit px |
| Comodoro regression (VR8) | `viirs_flaring` fires (frac>100 ≈ 0.064 → score ~0.64) at patagonia_seed |
| Quiet guard (VR9) | `viirs_flaring` ≈ 0 at Patagonia-diag / NZ / Appalachia / Amazon |
| Edge case (B6/Q-VR-A) | lit-contrast vs ring **all-pixel** distribution (handles site-lit/ring-dark) |

New constants (landed, additive, first-pass): `VIIRS_FLARING_ABS_THRESHOLD_NW=100`, `VIIRS_FLARING_SATURATION_FRAC=0.10`, `VIIRS_MIN_SITE_PIXELS=10`, `MIN_RING_LIT_PIXELS=20`, `VIIRS_ATTRIBUTABILITY_HIGH_PCT=0.90`, `VIIRS_ATTRIBUTABILITY_MOD_PCT=0.60`.

## What's landed this session (verified, suite 1963 green)

- `engine/constants.py` — the 6 new constants above (additive).
- `engine/core/attributability.py` — `compute_viirs_attributability` (mirrors `compute_habitat_attributability`, VR15).
- Evidence probes: `analysis/m_viirs_redesign_a1_distcheck.{py,csv}`, `analysis/m_viirs_redesign_a1_abscheck.{py,csv}`.

## Remaining (focused follow-on) — the core-grammar swap + D/E

1. **C1** `compute_viirs_flaring(aoi, window, ee)` — server-side: `mean_img = ic.mean()`; `frac = mean_img.gt(100).reduceRegion(mean, site)`; `score = min(frac/0.10, 1)`; None if site pixels < 10. Emits `ghg.viirs.score` (= flaring) so `compute_activity_score`/composite wiring is preserved.
2. **C2** `compute_viirs_lit_contrast(aoi, window, ee)` — percentile = fraction of ring all-pixel (land-masked) dimmer than site median; → `compute_viirs_attributability` → emit `ghg.viirs.attributability_state` + siblings (`lit_contrast_percentile`, `ring_lit_pixel_count`, `site_brightness`) + `_provenance.ghg.viirs_lit_contrast`. Pattern A; NOT in composite.
3. **C5** Retire `compute_viirs_sustained_contrast`, `viirs_sustained_contrast_from_series`, `_persistence_factor`, `_michelson_contrast` (if unused), and the 4 old constants (`VIIRS_LIT_CONTRAST_THRESHOLD`, `VIIRS_PERSISTENCE_FLOOR`, `VIIRS_PERSISTENCE_FLOOR_DISCOUNT`, `VIIRS_CONTRAST_PERCENTILE`) — **migrate the old-grammar tests in lockstep**.
4. Confidence terms: `anomaly_strength` was fed by `persistence` (now gone) — decide replacement (e.g. flaring score, or n_valid-only). Note for the swap.
5. **C3/C6** composite: restructure `CORE_GHG_AUDIT_SUPPORT_WEIGHTS` to {viirs_flaring 0.40, combustion_proxy 0.60}; check `_FOSSIL_COMBUSTION_WEIGHTS` / `_ACTIVITY_ADJUSTED_CO2_WEIGHTS` (also use `ghg.activity_score`).
6. **C7/C8** VR8 Comodoro + VR9 quiet regression tests (EE-gated).
7. **VR17** combustion_proxy `_provenance.ghg.combustion_proxy` + C5 expander entry + P-09.
8. **Step D** 17-AOI validation report; **Step E** seed regen (VR10 guardrail), IC v4 §2.2a/§2.3 + VR16 coverage map, M-UX-A1 registry retire/add, closed-entry (VR1–17).

Branch `m-viirs-redesign-a1`. Engine diff so far is additive-only (no behaviour change — old grammar still live until the swap).
