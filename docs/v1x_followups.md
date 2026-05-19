# v1.x follow-ups

> **Scope.** This doc collects v1.x deferrals from across milestones, not
> just M5.5. The original "M5.5 follow-ups" header was retired when the
> list outgrew its origin; the M5.5/M5.5b/M5.5c/M5.6 sections below are
> preserved verbatim for historical context.

## Pillar-wide EE errors surface as raw server-side strings (M-UI-E.1)

Discovered during the P-05 smoke test of the `E1_AllFailed` path. Running
a screening at an ocean point (lat 0, lon -30) produces the user-facing
error `Dictionary.get: Dictionary does not contain key: 'label'` — the
raw EE server-side error from Dynamic World's `frequencyHistogram`
reducer when the buffer contains zero land pixels.

The bare `except Exception` in
`pages/05_Screening_Results.py::_run_engine_and_transition` correctly
routes to `E1_AllFailed` — that part works as designed. What's wrong is
that the engine's pillar modules don't catch `ee.EEException` and
re-raise as `PillarComputeError` with sensible context. v1 lets the raw
EE string bubble all the way to the UI.

**Fix.** Wrap pillar-wide EE-touching code in `try/except ee.EEException`
inside `engine/air.py`, `engine/ghg.py`, `engine/nature.py` and re-raise
as `PillarComputeError` with a context-aware message:
- Nature → *"No land cover detected in buffer — check AOI lies on land."*
- Air → *"No valid satellite observations in time range."*
- GHG → similar.

**v1 workaround.** Document in the user guide that the tool is for
land-based suppliers.

---

## Retry failed indicators from C9 (deferred M-UI-E.5)

The wireframes (§P-05 C9) describe a **"Retry failed indicators"**
action that re-runs only the failed indicator IDs from the partial-
coverage banner. Implementing it requires
`engine/orchestrator.py::run_pillar` to accept an `indicators=<subset>`
parameter and to compose subset results with the existing payload. v1
ships C9 in display-only form per Wireframes §P-08 precedent (partial
results accepted as-is).

**Scope when picked up.**
- Add `indicators` kwarg to each pillar's `run_pillar` so it only
  computes the listed slugs.
- Have the orchestrator merge the subset result into the existing
  `st.session_state.page_state.result` rather than rebuilding from
  scratch — preserves the values that did succeed on the first run.
- Add a "Retry" button to C9 wired to the new orchestrator entry
  point. Targeted at **v1.x**.

---

## Indicator map coverage — extend the C4a registry (deferred M-UI-E.6)

M-UI-E.6 ships three indicator-map renderers as a proof-of-pattern:
`air.no2.score`, `nature.kba.proximity_score`, `nature.dw.trees_pct`.
Each demonstrates one of three visualisation grammars: continuous
z-raster, vector polygons, categorical raster. Remaining indicators
all fall into one of those three grammars; adding them is a matter of
registering a new entry in
`ui/components/c4a_indicator_map.py::_RENDERERS`.

**Outstanding indicators by grammar.**

*Continuous z-raster (follow the NO₂ pattern).*
- `air.so2.score`, `air.co.score`, `air.hcho.score`, `air.o3.score`,
  `air.aai.score`, `air.aod.score`, `air.pm25.score`, `air.pm10.score`
  — all 8 use `AIR_POLLUTANT_CONFIG[slug]` for asset + band.
- `ghg.ch4.score` (Sentinel-5P CH₄), `ghg.viirs.score` (VIIRS nightlights),
  `ghg.co2.score` (ODIAC CO₂ — note coverage_window = 2020-2023).
- `nature.ndvi.score` (MODIS MOD13Q1).

*Vector polygons.* KBA is the only vector indicator in v1; no others
pending.

*Categorical / specialised.*
- `nature.habitat.natural_loss_ha` — before/after DW composite,
  highlighting natural→non-natural transitions.
- `nature.forest_loss.ha` — Hansen `lossyear` band, single-class binary
  raster filtered to the screening window.
- `nature.water.area_now_ha` — DW water class composite, similar to the
  DW renderer but filtered to a single class.

Each renderer is independent — pick up in **v1.x** as demand warrants.

---

## P-04 — activate Region and Supplier centre modes (deferred M-P04)

M-P04 ships P-04 with the Region and Supplier centre tabs disabled.
Both require a `supplyChain` object from P-02 (Scope Setup), which
isn't built yet. Activate them when P-02 lands by replacing the
informational tab content in `ui/components/p04_form.py` with the
real selectors per Wireframes_All_v4 §P-04 C1–C2.

---

## P-04 — add the time-range selector + Run Trend (deferred M-P04)

The time-range selector (C7) is hidden in screening mode per
Wireframes §P-04 C7; screening always uses the latest 90-day window.
It appears with P-06 (Trend View). When P-06 lands:

- Activate the Run Trend button in `ui/components/p04_form.py`.
- Show the time-range selector only when trend mode is selected.
- Route Run Trend → P-06 with `mode = "monitoring"` in `screening_setup`.

Targeted at the P-06 milestone, not strict v1.x.

---

## M5.5 follow-ups (original — do these when wiring ODIAC / CO₂)

## High priority
- **CARMA-overlap flag.** Add a sub-score / provenance flag that fires when 
  Site_Buffer overlaps a CARMA point source. Surface in limiting-factor 
  template as "CO₂ value influenced by reported power-plant allocation nearby."
- **VIIRS double-counting fix.** Either drop `ghg.activity_score` from 
  `Core_GHG_Audit_Support` when ODIAC is the CO₂ source, or reduce its weight 
  (currently 0.11) to acknowledge overlap with ODIAC's diffuse branch.

## Medium priority
- **Relabel `co2_anomaly` → `co2_relative_intensity`.** Background-ring 
  "anomaly" doesn't have the same physical meaning for ODIAC as for S5P. 
  Document σ_bg normalisation as an analytic choice, not a physical baseline.
- **Reconsider `Activity_Adjusted_CO₂`.** Triple-counts VIIRS. Either remove 
  from v1 or reframe as a diagnostic-only output.

## Documentation tier
- **Split `Spatial_Resolution_Suitability`** into CH4-specific and ODIAC-specific 
  sub-scores, OR update the limiting-factor template to mention both.
- **Default ODIAC to annual not monthly** for v1 (monthly has imposed 
  seasonality). Document the choice in IC docs.

## Cross-validation (not a v1 deliverable)
- Validate ODIAC `ghg.co2_context` against Climate TRACE for 5-10 known 
  large emitters before production.

## Engine performance — EE round-trip batching (v1.x)
M5b's Nature pillar issues many sequential `getInfo()` calls, which becomes 
the dominant runtime cost for full-screening mode and for P-08 batch runs.

- **`compute_kba_proximity` (engine/nature.py)** — currently issues 3–4 
  sequential EE round-trips (size check, distance, intersection area). 
  Combine into one server-side `ee.Dictionary` computation so the whole 
  KBA payload is a single `getInfo()`.
- **`compute_habitat_conversion` (engine/nature.py)** — same problem, 
  doubled. Calls `_dw_mode_histogram` twice (current + baseline window); 
  each call is itself a `getInfo()` plus a `.size().getInfo()` size check. 
  That's 4 round-trips for habitat conversion alone. Combine the two 
  histograms into one server-side call returning both windows in a single 
  Dictionary.
- **Knock-on impact.** With ~7 Nature indicators each doing similar 
  patterns, a single full screening run can issue 20–30 sequential EE 
  calls. P-08 batch mode (up to 30 nodes) compounds this. Target: cap 
  Nature at ≤ 10 round-trips per AOI.
- **`compute_co2_snapshot` (engine/ghg.py)** — issues 4 sequential 
  round-trips per AOI: `ic.size().getInfo()`, then three separate 
  `reduceRegion().get(band).getInfo()` calls (site sum, site mean, ring 
  mean). Same Dictionary-batching opportunity.

## M5.5 status (current)

### Completed in M5.5
- ODIAC asset ingested at `projects/supply-chain-observatory/assets/odiac`.
- `compute_co2_snapshot` implemented (relative-intensity model, not 
  six-step) — see engine/ghg.py.
- `co2_anomaly` renamed to `co2_relative_intensity` in engine code 
  (Schema_v2 §3.1 doc update is pending — see CLAUDE.md §8 confirmation 
  guard on the docs/ directory).
- `CORE_GHG_AUDIT_SUPPORT_WEIGHTS` rebalanced to reduce VIIRS 
  double-counting: `ghg.activity_score` 0.11 → 0.06, 
  `ghg.combustion_proxy` 0.22 → 0.27 (freed 0.05 redistributed). 
  Sum unchanged at 1.00.
- `CO2_TO_C_RATIO` constant (= 44/12) added to engine/constants.py with 
  inline comment explaining the molecular conversion.
- `engine/ids.py::CO2_MEASUREMENT_SUFFIXES` updated to the M5.5 7-key 
  set: `(mean, total, relative_intensity, trend, trend_p, confidence, 
  score)`.
- Scratch page renders CO₂ row in the GHG breakdown table with the 
  custom `mean` headline and an annualised-emissions caption.
- Synthetic-payload tests cover the score formula, the score 
  saturations, the C → CO₂ conversion arithmetic, the pixel-size guard, 
  and the empty-time-range failure path. Activated sub-aggregates 
  (`co2_context`, `fossil_combustion_score`, `activity_adjusted_co2`) 
  have happy-path tests.
- `tests/test_ghg_integration.py` added (skipped unless 
  `RUN_EE_TESTS=1`) — exercises ODIAC against the Ruhr Valley.

### Still deferred to v1.x
- **CARMA-overlap flag** — highest-leverage remaining ODIAC item. The 
  v1 score formula clamps `relative_intensity` at 10×, which is a 
  CARMA-overlap *proxy*; v1.x should detect overlap explicitly and set 
  `carma_overlap=True` in `_provenance.ghg.co2` so the limiting-factor 
  template can surface it.
- **`Activity_Adjusted_CO₂`** still triple-counts VIIRS by IC's own 
  reckoning. Kept active in v1 for completeness; v1.x should reframe 
  as diagnostic-only or remove.
- **JRC GSW long-term water** (Nature pillar) still pending IC docs.
- **EE round-trip batching** (engine performance section above) — 
  cross-pillar, including CO₂'s 4 round-trips per AOI.
- **IC_v5 confidence formula gap (§6.3)** — placeholder confidence 
  still flat 1.0 / 0.7 / 0.8 values across pillars.
- **ODIAC vintage flag** in `ghg.retrieval_inventory_quality` — ingest 
  added the asset, but the per-image `as-of` property isn't wired into 
  the quality sub-score yet.
- **Schema_v2 §3.1 doc update** — the rename from `.anomaly` to 
  `.relative_intensity` for CO₂ measurements is live in engine code 
  but the doc hasn't been edited (CLAUDE.md §8 requires explicit 
  confirmation to modify docs/).

## M5.5b — ODIAC demoted from live composite (current)

### What changed
- ODIAC removed from `CORE_GHG_AUDIT_SUPPORT_WEIGHTS`. The three live 
  signals (CH₄ + combustion proxy + activity score) rescaled by 1/0.61 
  to preserve relative proportions: 0.46 / 0.44 / 0.10.
- CO₂ snapshot still computes when ODIAC data is available (2020-2023). 
  Values still display (`ghg.co2.mean / total / relative_intensity / score`). 
  They no longer feed the live composite.
- The three CO₂-dependent sub-aggregates (`ghg.co2_context`, 
  `ghg.fossil_combustion_score`, `ghg.activity_adjusted_co2`) still 
  compute as display-only / diagnostic outputs.
- `_provenance.ghg.co2` carries `role_in_pillar="standing_exposure_context"` 
  so UI and offline validators can key on it.

### Why
- **Methodological**: ODIAC's 2+ year vintage lag means it cannot 
  drive a live signal. Including it in the live formula meant 
  present-day screening (e.g. May 2026) failed entirely. Removing it 
  makes the live formula honest about what data feeds it.
- **Defensibility**: Also resolves the VIIRS double-counting concern 
  (CO₂ formerly competed with VIIRS/Combustion via overlapping 
  coverage) and the "anomaly" framing problem (ODIAC's background-ring 
  isn't an atmospheric baseline). Both are now moot.

### What ODIAC still does in v1
- **Display**: standing-exposure context shown alongside the live GHG 
  composite (scratch page; will reappear in P-05+).
- **Diagnostic**: `ghg.co2_context / fossil_combustion_score / 
  activity_adjusted_co2` still emit, available to UI for "ODIAC says X" 
  captions and for offline validation scripts.

### Validation work (tracked as v1 deliverable, separate scope)
- Build `scripts/validate_co2_proxy.py`: pick 50-100 historical points 
  within 2020-2023, stratified across supplier types (power plant, 
  heavy industry, urban industrial, semi-rural, clean control). Compute 
  `ghg.co2.score` (ODIAC) and `ghg.core_audit_support` (live trio) at 
  each. Report Spearman ρ overall and by stratum.
- Expected findings: strong correlation in diffuse-emission locations 
  (urban, semi-industrial). Weaker correlation for CARMA point-source 
  locations — the live trio under-detects point-source CO₂. This 
  finding motivates explicit CARMA-overlap surfacing in v1.x.
- Report in methodology doc: "live CO₂ proxy achieves Spearman ρ = X 
  against ODIAC for diffuse locations and ρ = Y for point-source-
  proximate locations; the latter is mitigated by surfacing ODIAC's 
  standing-exposure layer alongside the live score."

### v1 UI follow-ups (P-05+, NOT scratch page)
- Show ODIAC as a distinct map layer with a vintage label.
- Update verbal summary templates: live CO₂ findings reference the 
  trio ("driven primarily by CH₄ / combustion / activity"); ODIAC 
  appears in a separate clause ("location sits within a high standing 
  fossil-CO₂ exposure zone, ODIAC 2023").

### v1.x — still relevant
- **CARMA-overlap flag**: now MORE important, since ODIAC's role is 
  explicitly to surface point-source proximity. The 10× clamp in the 
  relative_intensity formula remains a proxy until v1.x lands explicit 
  detection.

## M5.5c — ODIAC coverage window + data-type honesty (current)

### What changed
- `GhgIndicatorConfig` gained two optional fields:
  - `coverage_window: tuple[str, str] | None` — declares the
    indicator's data availability window. None means "always available"
    (CH₄, VIIRS); ODIAC carries `("2020-01-01", "2023-12-31")`.
  - `data_type: str` — `"satellite_observation"` (default; CH₄, VIIRS)
    or `"emissions_inventory_allocation"` (ODIAC). Surfaces in
    provenance so UI and audit trails can distinguish measured vs
    modelled values.
- `run_pillar` checks `coverage_window` before dispatching each
  indicator. Out-of-coverage indicators are skipped silently: None-
  filled keys, a provenance block with
  `skipped_reason="out_of_coverage"`, and NO entry in `_failures`.
  This is the operational fix for the bug where present-day screening
  generated noise about "no ODIAC monthly grids in 2026" in the UI.
- `run_pillar` tracks `attempted_keys` separately from
  `indicator_keys`. The "all failed → `PillarComputeError`" trigger
  uses `attempted_keys`, so a present-day run with only CO₂ selected
  (where CO₂ is silently skipped) no longer trips the pillar-wide
  failure.
- `compute_co2_snapshot` docstring leads with the inventory-vs-
  observation distinction. Provenance carries `data_type`,
  `data_source`, and `allocation_method` fields. The historical
  `n_months == 0` raise was removed (dead code after the coverage
  check moved upstream).
- Scratch page captions explicitly label ODIAC as "inventory estimate
  (not satellite-measured)" on the success path, and differentiate
  the "skipped" vs "failed" None paths via the provenance flag on the
  unavailable path.

### Why this matters
- **Operational**: stops calling ODIAC for date ranges where we know
  it has no data. Saves 4 EE round-trips per present-day GHG run.
- **Methodological honesty**: reviewers reading "1.2 million t CO₂/yr"
  in a report now have provenance-level clarity that the value was
  *allocated* from national statistics + CARMA + nightlights, not
  *observed* from space. Closes a real audit-defensibility gap.

### Display-only sub-aggregates flagged for v1.x review

Three CO₂-dependent sub-aggregates still compute when ODIAC succeeds:

- **`ghg.co2_context`** — pure alias of `ghg.co2.score`. Defensible.
  Used by the two below.
- **`ghg.fossil_combustion_score`** — `0.50·co2 + 0.30·combustion +
  0.20·activity`. *Mild* double-counting: VIIRS contributes both
  directly via `activity_score` and indirectly via ODIAC's
  nightlight-driven allocation. Worth reframing as a multi-source
  consensus check in v1.x with explicit attribution.
- **`ghg.activity_adjusted_co2`** — `0.70·co2 + 0.30·activity`.
  *Strong* double-counting: ODIAC's diffuse branch is partially
  nightlight-driven, so the 0.30 on `activity_score` is on top of
  the ~0.5 effective VIIRS weight already inside `co2_context`.
  The methodological case is weak. v1.x: either drop or reframe as
  diagnostic-only.

**In v1, nothing downstream consumes any of these three.** They
compute, they live in the payload, they're available for offline
validators and for future UI captions, but they don't feed any
aggregate. Harmless until removed. Tracking here so v1.x makes an
explicit decision rather than carrying them forward by inertia.

### Still deferred (unchanged from M5.5b list)
- CARMA-overlap flag
- JRC GSW long-term water (Nature pillar)
- EE round-trip batching
- IC_v5 confidence formula gap (§6.3)
- ODIAC vintage flag in `ghg.retrieval_inventory_quality`
- Schema_v2 §3.1 doc update (the `.anomaly` → `.relative_intensity`
  rename is live in code; doc edit still pending CLAUDE.md §8 guard)

## M5.6 — unified provenance schema (current)

### What changed
- New module `engine/core/provenance.py` defines the canonical
  provenance shape (11 fields, fixed order) plus the strict-validating
  `build_provenance()` constructor and two enums:
  `_ALLOWED_DATA_TYPES` (5 values) and `_ALLOWED_OBSERVATION_UNITS`
  (5 values). Full reference: `docs/provenance_schema.md`.
- Every pillar's config dataclass (`PollutantConfig`,
  `GhgIndicatorConfig`, `NatureIndicatorConfig`) gained `data_type` and
  `data_source` fields. All 19 v1 indicators across Air (9), GHG (3),
  Nature (7) now carry explicit metadata at the config layer.
- Every indicator's snapshot function (`compute_pollutant_snapshot`,
  `compute_ghg_indicator_snapshot`, `compute_co2_snapshot`, plus the
  seven Nature snapshot fns) now constructs provenance through
  `build_provenance(...)`. The previous ad-hoc dicts (varying in shape
  per pillar) are gone.
- The out-of-coverage skip path in `engine/ghg.py::run_pillar` also
  routes through `build_provenance`, with
  `observations={"count": 0, "unit": "monthly_grids"}`.
- M5.5b's `role_in_pillar="standing_exposure_context"` field on ODIAC
  provenance was dropped — `data_type="emissions_inventory_allocation"`
  carries the same information more honestly, and the "not in live
  composite" fact is encoded in `CORE_GHG_AUDIT_SUPPORT_WEIGHTS` itself.
- ODIAC's `n_months` moved into `observations.count`;
  `c_to_co2_factor` and `allocation_method` into `extra` and
  `method_note` respectively. No information loss.
- KBA's `compute_kba_proximity` gained a `time_range` parameter for
  provenance consistency; the user's request window is documented in
  the provenance block. When the function is called without a window
  (direct tests), provenance carries the sentinel `("static", "static")`.

### Why this matters
- **Audit defensibility.** A reviewer reading
  `_provenance.air.no2` sees the same 11 fields as
  `_provenance.ghg.co2` or `_provenance.nature.kba`. No pillar-specific
  switch statement in the audit UI; no chance of a key existing in one
  pillar's block and silently missing from another.
- **Honesty.** `data_type` makes the inventory-vs-observation
  distinction first-class. CAMS PM is tagged
  `gridded_model_output`; ODIAC is `emissions_inventory_allocation`;
  Dynamic World is `ml_classified_satellite`; KBA is
  `reference_dataset`. Reviewers calibrate evidentiary weight on the
  tag, not on free-text caveats they might miss.
- **Strict validation.** `build_provenance` raises `ValueError` for
  unknown `data_type` or `observations.unit` values at construction
  time. A typo can't slip into a payload silently.

### Test coverage
- `tests/test_provenance.py` — 8 unit tests for `build_provenance`
  (field order, defaults, validation paths, all-enum-values
  acceptance).
- `tests/test_air.py::TestProvenanceShape` — per-pollutant canonical-
  keys check (9 parametrised) plus 3 indicator-specific assertions
  (NO₂ flags satellite, PM2.5 flags model output, AOD carries
  bit-mask in extra).
- `tests/test_ghg.py::TestProvenanceShape` — CO₂ happy-path,
  out-of-coverage skip path, and direct `_format_result` tests for
  CH₄ and VIIRS.
- `tests/test_nature.py::TestProvenanceShape` — KBA happy path,
  static-sentinel path, plus a parametrised 7-indicator config
  metadata check.
- `tests/test_ghg_integration.py` — migrated to the new shape.

### Notes for v1.x
- **Observations counts.** Most non-CO₂ indicators pass
  `observations=None` because v1 doesn't track image counts through
  `six_step`. v1.x should plumb `n_used` through `six_step` so every
  provenance block can carry a non-None observations field.
- **Schema_v2 doc update.** Schema_v2 doesn't currently mention the
  provenance shape (it covers indicator IDs only). Either extend it or
  link to `docs/provenance_schema.md` from §6 ("Engine output shape").
  Still pending CLAUDE.md §8 confirmation to edit Schema_v2.