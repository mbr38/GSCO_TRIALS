# M-VIIRS-REDESIGN-A1 — Closed Entry

*Two-output VIIRS redesign. Branch `m-viirs-redesign-a1` off `main`, 1 June 2026. Authority: `M-VIIRS-REDESIGN-A1_spec.md` v1.2; Step A→B findings (`docs/M-VIIRS-REDESIGN-A1_step_a_findings.md`); operator confirmations 1 Jun 2026.*

---

## What shipped

The saturating `contrast·persistence` VIIRS grammar (M-GHG-REDESIGN-A1) is retired. VIIRS now produces **two distinct outputs** (VR1):

- **Flaring (severity)** → `ghg.viirs.score`, feeds the composite via `ghg.activity_score`. Absolute-anchored intense-source detector: fraction of site pixels brighter than `VIIRS_FLARING_ABS_THRESHOLD_NW` (≈100 nW/cm²/sr), normalised by `VIIRS_FLARING_SATURATION_FRAC`. **VR3 was refined from the spec's self-relative outlier to an absolute anchor** — the Step A→B distribution-check proved a self-relative median+3σ could not separate intense sources from rural lights (Appalachia-forest 0.031 ≈ Norilsk; no separating threshold); the absolute anchor does (operator: "intense source"; "directional tool").
- **Lit-contrast (attributability)** → `ghg.viirs.attributability_state` + siblings, Pattern A, **not** in composite or measurement-quality aggregate. Percentile of site median brightness within the ring's all-pixel (land-masked) distribution.

**Step D validation (production path, 17 AOIs):** tier means **High 0.39 > Mid 0.27 > Low 0.003** (monotonic — the old grammar had Mid > High); Comodoro flaring **0.64** (VR8); quiet max **0.0** incl. the old false-High Appalachia (VR9). Suite **1998 passed / 34 skipped**.

---

## Closed-entry verification (VR1–VR17)

- [x] **VR1** — two outputs from one indicator. Cite `engine.ghg.compute_viirs_two_output` (severity `ghg.viirs.score` + attributability `ghg.viirs.attributability_state`).
- [x] **VR2** — lit-contrast = percentile vs ring **all-pixel** distribution (`lit_contrast_percentile_from_counts` + the server-side ring `lt(site_median)` reduction).
- [x] **VR3 (refined)** — severity = absolute-anchored intense-source (NOT the spec's self-relative outlier — refined on Step A→B evidence + operator decision). `flaring_score_from_fraction`.
- [x] **VR4** — sustained-contrast grammar retired (deleted `_michelson_contrast`, `_persistence_factor`, `viirs_sustained_contrast_from_series`, `compute_viirs_sustained_contrast`). Cite commit `ee4210e`.
- [x] **VR5** — composite weights re-derived: `CORE_GHG_AUDIT_SUPPORT_WEIGHTS` = 0.40 flaring / 0.60 borrow (commit `2514c54`), per M-GHG-SANITY-A1 (borrow is the stronger ranker).
- [x] **VR6** — regional washout via standard attributability flag (Suape lit-contrast 0.74 → moderate; no special-case handling).
- [x] **VR7 / VR15** — attributability integration Pattern A: `compute_viirs_attributability` in `engine.core.attributability` (mirrors habitat); emits `ghg.viirs.attributability_state` + sibling metrics + `_provenance.ghg.viirs_lit_contrast`; NOT in composite; sparse-on-failure.
- [x] **VR8** — Comodoro regression: `test_m_viirs_redesign_regression.py::test_vr8_comodoro_fires_flaring` (≥0.30; live 0.64). 3 EE-gated tests pass live.
- [x] **VR9** — quiet-site guard: `test_vr9_quiet_sites_do_not_fire` (< 0.05; live all 0.0).
- [x] **VR11** — registry: 4 old VIIRS tunables retired (`VIIRS_LIT_CONTRAST_THRESHOLD`, `VIIRS_PERSISTENCE_FLOOR`, `_DISCOUNT`, `VIIRS_CONTRAST_PERCENTILE`); 6 new added first-pass (commits `71e2221`, `907912f`). Registry lint green.
- [x] **VR12** — Air borrow methodology unchanged; only its GHG composite weight changed (engine/air.py diff empty).
- [x] **VR13** — IC v4 §2.2a updated with the two-output grammar (old grammar marked superseded/historical).
- [x] **VR14** — composite stability inspectable per-component (`ghg.viirs.score` flaring + `ghg.combustion_proxy` borrow + their provenance/weights). Seed regen: see below.
- [x] **VR17 (engine)** — `_provenance.ghg.combustion_proxy` emitted (borrowed_from air.no2/air.co, per-pollutant scores, weight, contribution). Commit `2514c54`.

### Not yet done (carried as remaining follow-on)

- [ ] **VR10 / Step E seed regen** — 5 production seeds carry the old VIIRS keys (`.contrast`/`.persistence`) and pre-redesign composite; regenerate against the new engine and document per-seed movements (multi-band guardrail). **Pending** (needs EE run).
- [ ] **VR16** — the §2.X v1.x attributability coverage map (cross-pillar table + Air-vs-VIIRS asymmetry note). **Pending** (the §2.2a superseding block covers the VIIRS grammar; the full cross-pillar map is not yet written).
- [ ] **VR17 (UI)** — combustion_proxy C5 expander entry + deep-link to Air NO₂/CO; P-09 GHG methodology paragraph. **Pending** (engine provenance done; UI surfacing not yet).

---

## Files changed (engine + tests)

`engine/ghg.py` (new two-output path, retired grammar, VR17 provenance, dispatch), `engine/constants.py` (6 new constants, 4 retired), `engine/core/attributability.py` (`compute_viirs_attributability`). Tests: `test_viirs_sustained_contrast.py` (replaced with new pure-math tests), `test_m_viirs_redesign_regression.py` (new, EE-gated VR8/VR9), migrations in `test_ghg.py` / `test_ocean_ring.py` / `test_air_ghg_defensive.py`. Evidence: `analysis/m_viirs_redesign_a1_{distcheck,abscheck,validation}.{py,csv}`.

---

*Core engine redesign complete and validated (Step A–D); the remaining items (seed regen, §2.X coverage map, VR17 UI) are documented above as follow-on. `engine/air.py` and `engine/nature.py` untouched; M-ATTRIB-A1 / M-WIND-A1 grammars untouched (VIIRS joins as a peer attributability input).*
