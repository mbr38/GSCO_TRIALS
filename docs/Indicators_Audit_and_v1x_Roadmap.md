# GSCO Environmental Tool — Indicators Audit & v1.x Roadmap

**Purpose.** Per-indicator audit answering three questions for each entry in the v1 indicator set:

1. **What's missing for v1.x** — values, terms, or fields that v1 explicitly defers.
2. **How to make the current value more accurate** — calibration, filtering, cross-referencing, or methodological upgrades that are defensible for a screening tool.
3. **How to make the data-quality / confidence layer more complete inside the tool.**

**Anchored to.** `Indicators_Computation_v3.md`, `Indicator_ID_Schema_v1.md`, `GEE_Database_List_v3.md`, `Engine_Module_Skeleton_v1.md`, `v1x_followups.md` (uploaded), `Final_Indicators_List.pdf`, `Indicators_Full_Research.pdf`.

**What this document is NOT.** It is not a request for new scope. Most items below are either (a) already namespaced in `Indicator_ID_Schema_v1.md` §8, (b) listed in `v1x_followups.md`, or (c) explicitly rejected in `GEE_Database_List_v3.md` §7. The goal is to consolidate, prioritise, and surface scientific-soundness gaps.

**Scoping principle.** This is a *screening tool*. Per PLFS_v4: it flags suppliers for human follow-up; it does not estimate verified Scope 1/2/3 emissions, nor does it produce regulatory-grade air-quality measurements. Every upgrade below is judged against that bar, not against a research-grade atmospheric inventory bar.

---

## 0. Audit framework

Each indicator gets a card with five fields:

| Field | Meaning |
|---|---|
| **v1 state** | What is currently computed in the engine. |
| **Q1 — v1.x value gaps** | Terms or fields the v1 formula explicitly sets to zero, rescales around, or skips. |
| **Q2 — accuracy levers** | Calibration, filtering, or cross-referencing improvements that strengthen the value without changing the science. |
| **Q3 — data-quality gaps** | Confidence-side limitations: what the user sees vs what the engine actually knows. |
| **Defensibility verdict** | Whether the current v1 indicator can stand up to an ESG / academic reviewer as-is. |

Three verdict tiers:

- **Defensible** — current v1 implementation is publishable as a screening indicator with the documented caveats.
- **Defensible with explicit caveats** — works as long as the limitations are surfaced; the engine must not let the user forget them.
- **Methodologically incomplete** — should not ship in current form without v1.x work, OR is currently shipping with a placeholder that should be flagged.

The placeholder verdict, "**Methodologically incomplete**", currently applies to exactly **two** items in v1: the §6.3 confidence formula and the trend engine (`engine/core/trend.py`). Everything else is at "Defensible" or "Defensible with explicit caveats".

## 0.5 Formula notation guide

Pillar-aggregate formulas in this document use a three-state convention so the reader can distinguish design intent from current implementation from end-state:

- **`*_REFERENCE`** — the canonical formula as written in `Final_Indicators_List.pdf` and `Indicators_Computation_v3.md`. Includes all terms, no rescaling.
- **`*_v1`** — the formula the engine actually computes today. Reflects M5.5b's ODIAC demotion, Rule 1 rescaling for deferred terms, and the M-FOLLOWUP-FALLBACK known-zero substitution where the trend engine isn't yet live.
- **`*_post_v1x`** — the formula after the v1.x roadmap below lands. Reflects Sector_Match scrap (§9.2), Hansen demotion (§9.3 v1.4), and Tier C1 wind activation.

When the reference, v1, and post-v1.x forms are identical, only one is shown.

The Rule 1 rescale comes from `Indicators_Computation_v3.md §7.1` — deferred terms are set to zero and the remaining weights are renormalised by dividing by their sum, preserving the [0, 1] output range and keeping cross-supplier comparisons fair.

---

## 1. Cross-cutting issues that affect every indicator

Before walking the indicator list, five cross-cutting items dominate. Fixing these has more leverage than any per-indicator change.

### 1.1 The §6.3 confidence formula is a placeholder (CRITICAL)

**Current state (v1x_followups line 417-418).** Confidence is reported as flat values per pillar — roughly `1.0 / 0.7 / 0.8` — disconnected from the actual data quality of the run. This means every confidence dot in the UI, every "data quality moderate" caption, and every `composite.confidence = min(...)` cross-pillar result is currently uninformative.

**Why this is the single most important fix.** The verbal-summary templates (`Verbal_Summary_Templates_v1.md`) explicitly condition the prose on `composite_confidence_bucket ∈ {high, moderate, low}`. If the underlying number is a placeholder, the prose tier is also a placeholder. The "data quality" framing is the main scientific-defensibility hook the tool has against the (correct) critique that satellite proxies have known limitations.

**v1.x fix.** Replace the placeholder with the formula `Indicators_Computation_v3.md §0.2 Step 6` describes:

```
Confidence = f(QA, N_valid, anomaly_strength, spatial_context, wind)
```

Concretely, for v1.x (without wind data):

```
Conf_indicator = w_qa · QA_score                  # 0.30 — sensor QA bits / SCL classes / DW probability
              + w_n · clamp(N_valid / N_target, 0, 1)   # 0.25 — image count vs target
              + w_strength · clamp(|Z|/3, 0, 1)         # 0.20 — anomaly strength as confidence in the deviation
              + w_spatial · valid_pixel_pct             # 0.25 — fraction of buffer that produced a usable value
```

The four weights sum to 1.0; wind is held out at zero per the Rule 1 rescaling pattern (`Indicators_Computation_v3.md §7.1`). Each indicator type defines its own `QA_score`, `N_target`, and `valid_pixel_pct`. These quantities are already available in the engine — they are produced by the `repeatable_core` and `buffers` modules — but they are not currently composed into a real confidence score.

**Effort.** ~1 week of engine + tests. Zero new GEE assets. Zero new dependencies.

### 1.2 The trend engine (`engine/core/trend.py`) is missing (HIGH)

**Current state (v1x_followups line 263-296).** `engine/core/repeatable_core.py` returns `_trend = None` because `engine/core/trend.py` has not landed. Downstream, `engine/nature.compute_vegetation_condition` substitutes `0.0` for `nature.ndvi.negative_trend` (under the M-FOLLOWUP-FALLBACK known-zero pattern), so the 0.25 weight on `Negative_Vegetation_Trend` in `Vegetation_Condition_v1` contributes nothing. The same pattern applies to every other `*.trend` ID in the system.

**Impact.** In Screening mode this is bounded — `Trend_Score := 0` is the documented design (`Indicators_Computation_v3.md §1.3` for Air, §2.3 for GHG). But the 0.20 weight on `GHG_Trend` and on `Air_Trend_Score` is also dead-weight in screening, and the 0.25 weight on `Negative_Vegetation_Trend` inside `Vegetation_Condition` *is* meant to be live in screening mode. That term is currently zero.

**More importantly.** Trend mode (P-06) cannot ship at all without `trend.py`. The current v1 build is single-mode (screening only) because of this gap.

**v1.x fix.** Land `engine/core/trend.py` with Theil-Sen slope + Mann-Kendall p-value per `Indicators_Computation_v3.md §0.3`. The two algorithms are well-established (NumPy + SciPy implementations exist), so this is engineering work, not research. Once landed:

- Remove the M-FOLLOWUP-FALLBACK known-zero substitution from `engine.nature`.
- Activate the `Trend_Score` term in each pillar's follow-up priority.
- Unblock P-06 (Trend View).

**Effort.** ~1-2 weeks engine + tests + P-06 wiring.

### 1.3 Background ring methodology for coastal & sparse-coverage AOIs (HIGH)

**Current state (v1x_followups line 208-260).** When the background ring contains no usable pixels (coastal AOIs with ring over ocean; or tropical/polar AOIs where ring overpass density is too sparse), the affected indicators emit `None` and surface as Failed in C4b or trigger E1_AllFailed. The user message has been polished — they now see a clear "ring over water / sparse coverage" caption — but the indicator value itself is lost.

**Two v1.x options exist, documented in v1x_followups:**

- **Option 1 — Land-mask the ring.** ✅ **SHIPPED (M-TIER-A3, 26 May 2026).** Intersects the background ring with MOD44W v6 (250 m static water mask) before reducing. Cheap. Fixes coastal cases; below the 5% land-fraction threshold the existing `BackgroundRingNoDataError` skip path fires with the distinct `ring_empty_post_land_mask` reason marker. Does not fix sparse-coverage cases (M-CLIM-A3b will).
- **Option 2 — Regional climatology fallback.** When the ring has no usable pixels, fall back to a pre-computed regional median + σ for the same band (e.g. national-mean S5P NO₂ for the AOI's country). Methodologically the right answer; fixes both cases. Requires per-indicator climatology fixtures and a vintage story.

**Recommendation.** Option 1 is shipped. Option 2 (M-CLIM-A3b) remains a v1.x-late milestone: it needs roughly one climatology fixture per pollutant × per country, plus a "fallback used" provenance flag so the user knows the z-score is regional-climatology-based. Composition with M-TIER-A3 is already wired: M-CLIM-A3b triggers off the post-masking `ring_empty_post_land_mask` event, reading `provenance.extra.land_mask_applied` to decide whether to fall back.

### 1.4 Spec-doc drift (LOW but worth knowing)

Documented drifts between live code, this audit, and the canonical spec docs:

- **CAMS band names** (v1x_followups line 93-98). Legacy names `particulate_matter_2.5um` / `particulate_matter_10um` still appear in `Indicators_Computation_v3.md` §1.1; the live names are `particulate_matter_d_less_than_25_um_surface` / `particulate_matter_d_less_than_10_um_surface`. The engine is correct; the spec docs need refresh.
- **CO₂ measurement rename** (v1x_followups line 422-425). `.anomaly` → `.relative_intensity` is live in `engine/ghg.py` but not in `Indicator_ID_Schema_v1.md` §3.1.
- **Schema_v2 §6 doesn't mention provenance shape** (v1x_followups line 629-632). M5.6 landed an 11-field provenance schema but the public schema doc still describes indicator IDs only.
- **Provenance schema growth from §9 notes.** The v1.x roadmap adds three new provenance fields beyond M5.6's 11: `column_to_surface_uncertainty` (§1.5), `temporal_mode` (§9.3), and a `sector_signal_anomaly` flag (§9.2). Final schema is 14 fields. Worth aligning during the spec-sync milestone.
- **`GHG_Data_Quality_Attribution_v1` rescaling correction.** An earlier audit version showed weights of `0.30 / 0.24 / 0.24 / 0.12` with rescale factor `1/0.85`; these are mathematically inconsistent (sum to 0.90, not 1.0; correct factor is `1/0.75`). The corrected formula is in §3.4. Worth verifying against `engine.constants.GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS`.
- **`Core_GHG_Audit_Support` weight lineage.** The engine's post-M5.5b rescale by `1/0.61` (producing 0.46 / 0.44 / 0.10) implies pre-rescale weights that don't exactly match the canonical Final_Indicators_List.pdf reference. Live output is correct; documentation lineage needs reconciliation. See §3.4 for the trace.
- **§9.2 deprecation of `ghg.sector_match`.** Remove from `Indicator_ID_Schema_v1.md §8` reserved-for-v1.x namespace; remove the corresponding row from `Verbal_Summary_Templates_v1.md §5.2` limiting-factor lookup.
- **§9.3 v1.4 Habitat_Conversion update.** New formula (0.40 / 0.27 / 0.22 / 0.11; Forest_Loss removed). Update in `Indicators_Computation_v3.md §3.3` and the matching summaries in `Final_Indicators_List.pdf` and `Indicators_Full_Research.pdf`.

These are housekeeping. Bundle into a single "spec sync" milestone in v1.x.

### 1.5 Vertical column density vs surface concentration framing (MEDIUM)

**The science.** Every gas indicator in the Air and GHG pillars consumes a Sentinel-5P band of the form `*_column_number_density` or `column_volume_mixing_ratio_dry_air`. These are **vertical column densities (VCDs)** — the integrated number of molecules in a vertical column from the surface to the top of the atmosphere. ESG and health frameworks (WHO AQG, EU AAQD, ESRS E2, GRI 305-7) are written in **surface concentration** units (µg m⁻³, ppb at breathing height). Converting VCD → surface concentration is non-trivial; it depends on boundary-layer height (BLH), vertical profile shape of the gas, background atmospheric column, and atmospheric stability.

**This is already documented as a weak assumption.** `Indicators_Computation_v3.md §5.2 AP1`: *"TROPOMI column densities are a proxy for surface concentrations — Weak for SO₂ and CO, moderate for NO₂."* `Indicators Full Research.pdf` (TROPOMI section) makes the same point with the additional warning that simple linear conversions like `PM2.5 = a·AOD + b` are "usually too weak for a serious tool."

**How v1 partially mitigates this already.** Worth foregrounding because these design choices are real defensibility wins:

1. **The Z-score / anomaly framing.** When the engine computes `Z = (P_site − P_background) / σ_background`, both `P_site` and `P_background` are VCDs measured under the same atmospheric conditions on the same days. BLH, vertical profile, and background-column contributions cancel out to first order. This is the reason satellite-based hotspot screening works at all without explicit surface conversion.
2. **The "context, not measurement" framing in PLFS_v4.** The tool flags suppliers for follow-up; it does not quantify Scope 1 emissions or surface concentrations. Unit labels (µmol m⁻², ppb, mol m⁻²) are honest about being column / volume-mixing-ratio quantities, not surface units.
3. **The O₃ cap at 0.5** (`Indicators_Computation_v3.md §1.3`). Total-column O₃ is dominated by the stratospheric component (~90% of the column); the cap acknowledges that surface O₃ stress cannot be inferred directly from the satellite column.

**Per-gas column-to-surface uncertainty.** The summary table below drives the v1.x provenance field recommendation:

| Gas | Column → surface | Why |
|---|---|---|
| **NO₂** | Moderate | Short lifetime (~hours); ~75-90% of the tropospheric column is in the boundary layer over urban/industrial sites. Anomaly framing absorbs most of the bias. |
| **SO₂** | Moderate-to-weak | Similar to NO₂, but stack plumes can be injected into the upper BL or above, decoupling column from surface. |
| **CO** | Weak | ~2-month lifetime; well-mixed through the troposphere. Most of the column is in the free troposphere, not the BL. |
| **HCHO** | Moderate | Lifetime ~hours in daylight; mostly BL when locally produced. |
| **O₃** | N/A for surface inference | Total column dominated by stratosphere. Already capped at 0.5 and framed as "regional air-quality stress context" — keep as is. |
| **AAI** | N/A | Dimensionless aerosol index, not a concentration. |
| **CH₄** | Weak by design | ~9-year lifetime; column dominated by ~1900 ppb global background. Local enhancement is a small fraction of the total. |
| **PM₂.₅ (CAMS)** | Already in surface units (µg m⁻³) | CAMS produces a surface PM₂.₅ field directly using a full meteorological model. The pixel-size issue dominates here, not the column-vs-surface issue. |
| **AOD** | Column quantity by design | Optical depth of the whole atmospheric column. Not meant to be surface. |

**v1.x fix — make the weakness visible and quantified, not eliminate it.** Three additions, in order of leverage:

1. **Add a `column_to_surface_uncertainty` field to per-indicator provenance.** Categorical: `low` / `moderate` / `weak` / `not_applicable` per the table above. Set once per gas at engine init; no runtime cost. Surfaces the AP1 assumption to the user without cluttering the verbal summary.
2. **Boundary-layer height awareness in the confidence formula.** ERA5 provides `boundary_layer_height` (`ECMWF/ERA5/HOURLY` — corrected 24 May 2026 from `ECMWF/ERA5_LAND/HOURLY`; ERA5-Land's 150-band surface/soil/snow/lake catalogue does not carry `boundary_layer_height`. BLH is an atmospheric variable on the full ERA5 product. Discovered during Tier C2 pre-spec investigation). When BLH during the analysis window is unusually low or high relative to the local climatology, the confidence on column → surface inference should drop. This bundles naturally with the wind work in Tier C — same dataset, same pipeline, marginal additional cost.
3. **A dedicated "atmospheric column screening" caption near the unit labels in C4a / C4b** (one place, not the verbal summary). Single short string per gas indicator card that names the quantity correctly. Wireframes can decide placement; the engine just needs to expose the field.

**What v1.x SHOULD NOT try.**

- **Compute a VCD-to-surface conversion in the engine.** This is exactly the trap the Indicators_Full_Research note warns about. The serious version (BLH + vertical profile + RH + temperature + wind + season + local emissions) is what GEOS-CF and CAMS already do, and they ship the surface field directly. For surface PM₂.₅ the tool already uses CAMS. For gases, the right answer is to remain in VCD units and frame outputs as atmospheric column screening rather than surface concentration estimation.
- **Pretend the conversion is solved by a constant scaling factor.** Per the research file: published-wrong even for the simplest cases.
- **Drop O₃ further.** The 0.5 cap is the right mitigation; the 0.10 weight inside `Air_Pollution_Proxy_Score` is small enough that the column-vs-surface concern doesn't dominate the pillar score, and dropping O₃ entirely would forfeit a useful regional-stress signal that has independent value (regional photochemistry, secondary pollutant context).

---

## 2. Air Pollution pillar — per-indicator audit

### 2.1 NO₂ (`air.no2.*`)

**v1 state.** Sentinel-5P OFFL `NO2_column_number_density`, repeatable core method, 7 measurements (site, background, anomaly, z, hf, confidence, score). Strongest pillar signal — facility-attributable, daily revisit, well-validated TROPOMI product.

**Q1 — v1.x value gaps.** None at the indicator level. The pillar-level gaps that affect NO₂ scoring are:
- `Wind_Consistency` in `Attribution_Confidence_Score` (deferred per §7.1; ERA5 wind).
- Trend score (zeroed in screening mode by design; engine-blocked in trend mode).

**Q2 — accuracy levers.**
- **OFFL vs NRTI selection.** §5.2 AP4 flags NRTI as weaker than OFFL. The engine should prefer OFFL and only fall back to NRTI for dates within the last ~5 days when OFFL is not yet published. Surface NRTI usage in provenance.
- **QA filtering.** Standard TROPOMI NO₂ practice is to mask pixels with `qa_value < 0.75` before averaging. Whether the engine currently does this is worth checking against `engine/core/repeatable_core.py`; if not, it's the single highest-leverage filtering change.
- **Stratospheric column subtraction.** The `NO2_column_number_density` band is the total column; the tropospheric column (`tropospheric_NO2_column_number_density`) is more directly tied to surface emissions. Most facility-attribution literature uses the tropospheric band. **Recommendation.** Switch v1.x to the tropospheric band; document the change in the spec doc.
- **Cross-reference.** No external cross-reference needed for v1.x — NO₂ is the most-trusted TROPOMI product and CAMS PM only loosely correlates.

**Q3 — data-quality gaps.** The §6.3 confidence formula gap (§1.1 above) applies. NO₂-specific quality signals already available but not yet composed into confidence:
- `valid_pixel_pct` after QA filtering.
- `N_valid` (number of cloud-free overpasses in the 90-day composite).
- Pixel-buffer ratio (1 km buffer with 7×5.5 km TROPOMI pixel is one pixel — the C9 warning fires correctly per `Indicators_Computation_v3.md §6.3`).
- Column-vs-surface uncertainty: **moderate** per §1.5; tag in provenance. NO₂ is the most favourable case for column-to-surface inference among the v1 gases (short lifetime, BL-bound source), so the moderate tag is honest rather than penalising.

**Defensibility verdict.** **Defensible.** NO₂ is the strongest single indicator in the tool; the proxy literature is extensive and the TROPOMI product is mature.

---

### 2.2 SO₂ (`air.so2.*`)

**v1 state.** Sentinel-5P OFFL `SO2_column_number_density`, same six-step method as NO₂.

**Q1 — v1.x value gaps.** Same as NO₂ — no indicator-level gaps. Pillar-level wind / sector deferrals apply.

**Q2 — accuracy levers.**
- **Strong sensitivity to QA filtering.** TROPOMI SO₂ has a higher noise floor than NO₂. The `qa_value` mask threshold matters more here — common practice is `qa_value > 0.50` for SO₂ (not the 0.75 used for NO₂). Worth checking the engine.
- **Volcanic signal contamination.** SO₂ from volcanic plumes will appear as a positive anomaly. v1 has no filter for this. For known volcanic regions (Indonesia, Italy, Iceland, Hawaii, Kamchatka, Andes) the provenance block should surface a "volcanic-region" flag — a simple bounding-box check against a static list of active volcanoes, computed once per AOI.
- **Episodic nature.** §5.2 AP1: SO₂ is episodic; 90-day means can hide spikes. A "fraction of days above 2σ" (i.e. `HF` itself) is more informative than the mean for SO₂. The score formula already uses `Z` via the repeatable core, so this is partially addressed; surfacing `HF` as a primary user-visible field (not just an internal value) would help.

**Q3 — data-quality gaps.** SO₂ valid-pixel coverage in clean regions is often very low (most pixels filtered). The confidence formula must reflect this; the placeholder doesn't. Column-vs-surface uncertainty: **moderate-to-weak** per §1.5 — stack-injected plumes can sit in the upper BL or above, partly decoupling column from surface. Tag in provenance and let the confidence formula draw on the BLH term when ERA5 lands (Tier C).

**Defensibility verdict.** **Defensible with explicit caveats.** The "sulphur-heavy activity" framing is correct; the caveat is that SO₂ is the noisiest TROPOMI product and a single-supplier SO₂ flag should never be acted on without follow-up.

---

### 2.3 CO (`air.co.*`)

**v1 state.** Sentinel-5P OFFL `CO_column_number_density`, six-step method. CO is long-lived (lifetime ~2 months) and more regional than facility-specific.

**Q1 — v1.x value gaps.** None at the indicator level.

**Q2 — accuracy levers.**
- **Regional transport contamination.** §5.2 AP2: CO is the most transport-prone of the v1 pollutants. The current mitigation — using CO inside `Smoke / Dust / Regional Transport Score` and subtracting from CH₄ via `Fire_or_Regional_Transport_Risk` — is correct, but CO's standalone z-score may flag biomass-burning regions as supplier anomalies. The v1.x answer is `Wind_Consistency` (ERA5) to identify whether the elevated CO is upwind-originated.
- **CO column-to-surface coupling is weak.** Per §1.5: CO's ~2-month lifetime means it's well-mixed through the troposphere; most of the column is free-tropospheric, not in the boundary layer. No filter change recommended (the assumption is structural to the dataset), but this needs the `column_to_surface_uncertainty = weak` tag in provenance more than any other v1 gas.

**Q3 — data-quality gaps.** §6.3 confidence formula gap. CO-specific: very few QA-rejected pixels (CO is one of the better-retrieved TROPOMI products), so `valid_pixel_pct` will be near 1.0 — but that *high* coverage is misleading when the CO signal is regional rather than local. Confidence should be downweighted when the local Z is small while the buffer-wide CO mean is high (i.e. the supplier is inside a regional CO plume). The column-to-surface weak tag (§1.5) should also drag the confidence down on absolute terms.

**Defensibility verdict.** **Defensible with explicit caveats.** Frame CO as "regional combustion / fire proxy" in the UI, never as facility-specific.

---

### 2.4 HCHO (`air.hcho.*`)

**v1 state.** Sentinel-5P OFFL `tropospheric_HCHO_column_number_density`, six-step method.

**Q1 — v1.x value gaps.** None at the indicator level.

**Q2 — accuracy levers.**
- **HCHO is a chemistry product, not an emissions product.** HCHO is produced by atmospheric oxidation of VOCs from many sources — biogenic emissions, biomass burning, and industrial VOC release. The "VOC / photochemical pollution context" framing in §1.2 captures this correctly. No filter change recommended.
- **Strong seasonality.** HCHO is highly seasonal (correlates with photochemical activity and temperature). The same-month seasonality baseline (`Indicators_Computation_v3.md §0.6`) is listed as "optional for the air-pollution datasets where seasonality is weaker"; **for HCHO it should be on by default in v1.x**, same as for NDVI. This is a one-line config change.

**Q3 — data-quality gaps.** TROPOMI HCHO has a higher noise floor than NO₂. `qa_value > 0.50` is standard. v1.x confidence formula should incorporate the QA filter pass rate. Column-vs-surface uncertainty: **moderate** per §1.5 — when HCHO is locally produced via photochemistry it's largely BL-bound, but biomass-burning HCHO can sit at altitude.

**Defensibility verdict.** **Defensible with explicit caveats.** The "VOC oxidation / fire / biogenic activity proxy" framing in `Indicators_Full_Research.pdf` "Best interpretation" table is the right caveat to surface.

---

### 2.5 O₃ (`air.o3.*`)

**v1 state.** Sentinel-5P OFFL `O3_column_number_density`, six-step method, **score capped at 0.5** because O₃ is a secondary pollutant (per `Indicators_Computation_v3.md §1.3`).

**Q1 — v1.x value gaps.** None.

**Q2 — accuracy levers.**
- **The 0.5 cap is correct.** O₃ is not directly emitted; treating it as context (not a primary score) is methodologically sound.
- **Total column vs tropospheric.** O₃ total column is dominated by the stratospheric column. The product available in GEE is total column. For regional air-quality stress, this is acceptable as a screening proxy; for any quantitative claim it would be wrong. The "regional air-quality stress indicator" framing in `Indicators_Full_Research.pdf` is correct.

**Q3 — data-quality gaps.** §6.3 placeholder. The column-vs-surface issue is already mitigated by the 0.5 cap (§1.5 also confirms this); no further provenance tag needed beyond `column_to_surface_uncertainty = not_applicable` (because the score isn't trying to infer surface concentration in the first place).

**Defensibility verdict.** **Defensible.** The cap and the framing handle the methodological weakness correctly. Keep O₃ at its current 0.10 weight inside `Air_Pollution_Proxy_Score` — it carries useful information about regional photochemical stress and secondary-pollutant context that the other gases don't, and the column-vs-surface concern is already absorbed by the cap.

---

### 2.6 AAI (`air.aai.*`)

**v1 state.** Sentinel-5P OFFL `absorbing_aerosol_index`, dimensionless, six-step method.

**Q1 — v1.x value gaps.** None.

**Q2 — accuracy levers.**
- **AAI is sensitive to dust and smoke specifically** (UV-absorbing aerosols). Using it inside `Smoke / Dust / Regional Transport Score` is correct.
- **Negative values are physically meaningful** (scattering aerosols). The current normalisation `clamp((X_site - X_bg) / (k·σ_bg), 0, 1)` for "higher = worse" drops negative anomalies. This is correct for AAI scoring — we only care about elevated absorbing aerosol — but the raw value should still be reported even when negative.

**Q3 — data-quality gaps.** §6.3 placeholder.

**Defensibility verdict.** **Defensible.**

---

### 2.7 PM₂.₅ & PM₁₀ (CAMS) (`air.pm25.*`, `air.pm10.*`)

**v1 state.** CAMS NRT, bands `particulate_matter_d_less_than_25_um_surface` and `particulate_matter_d_less_than_10_um_surface` (after the M-CAMS-BAND-FIX rename), ×10⁹ to convert kg m⁻³ → µg m⁻³.

**Q1 — v1.x value gaps.**
- **Spec-doc drift on band names.** Live code is correct; `Indicators_Computation_v3.md §1.1` still shows the legacy names. Fix in the next spec-doc bump.
- **`PM_or_Aerosol_score` fallback path.** Already implemented: falls back to AAI-only when CAMS coverage <50% of buffer or site mean is null (`Indicators_Computation_v3.md §1.2`). This is a working v1 mechanism, not a gap.

**Q2 — accuracy levers.**
- **The pixel-size problem is structural.** CAMS PM at ~44.5 km resolution is bigger than any v1 buffer except the 50/100 km regional ones. §5.2 AP3 already flags this as "weak — always frame as modelled regional context". The pixel-size warning in §6.3 catches this. **No filter change can fix CAMS pixel size; framing is the answer.**
- **Cross-reference with MAIAC AOD.** v1.x option: when MAIAC AOD is available for the same date, use it as a sanity check on CAMS PM. The Chiang Mai PM₂.₅ study (in the `Indicators_Full_Research.pdf` Source 11 image, MLR with AOD + CO + NO₂) shows that AOD + CO + NO₂ together predict ground-truth PM₂.₅ with R ~ 0.8. This is **a cross-reference, not a replacement** — we are not in the business of training our own MLR globally, but if CAMS PM and AOD diverge significantly (e.g. CAMS shows elevated PM₂.₅ but AOD is clean), the confidence should drop. A heuristic divergence flag is defensible in v1.x without becoming an ML pipeline.

**Q3 — data-quality gaps.**
- **Vintage of CAMS NRT.** CAMS NRT has a ~1-day lag and routinely undergoes back-revisions. Provenance should record the production timestamp.
- **Pixel size vs buffer should drive confidence directly.** When the buffer is 5 km and the pixel is 44 km, the supplier-specific signal is zero — what's being measured is the regional pixel. This should result in `Conf_PM2.5 ≪ 1.0` regardless of valid-pixel coverage. The §6.3 confidence formula must include a `pixel_size / buffer_size` term for PM specifically (and for CH₄ in the GHG pillar).

**Defensibility verdict.** **Defensible with explicit caveats.** The caveat must be aggressively surfaced: "PM₂.₅ here is modelled regional context, not a measurement at your supplier."

**PM₂.₅ / PM₁₀ at sub-CAMS-pixel buffers.** The CAMS Near-Real-Time PM₂.₅ and PM₁₀ assets used in v1 (`ECMWF/CAMS/NRT`, bands `particulate_matter_d_less_than_25_um_surface` / `_10_um_surface`) have a 44.5 km native pixel. The engine sub-pixel guardrail at `engine/air.py:251-261` raises `IndicatorComputeError` when the analysis buffer radius is below this scale, with the message "site buffer (N km) smaller than pm25/pm10 native pixel (44.5 km)". Both demo sites (Sapezal at 5 km, Brasilia at 43.1 km) trip this guardrail; PM₂.₅ and PM₁₀ are dropped from the Air pillar at these AOIs and the E4 fallback (`compute_pm_or_aerosol`, `formula='fallback_aai_only'`) uses Aerosol Index alone. This is intentional v1 design — there is no spatial contrast at sub-pixel resolution. If a future version replaces CAMS NRT with a higher-resolution PM dataset (e.g. EAC4 at finer scale, or a regional reanalysis), this guardrail's threshold should be revisited. Documented per `v1x_followups.md` followup #4 investigation, 24 May 2026.

---

### 2.8 AOD (`air.aod.*`)

**v1 state.** MODIS MAIAC `Optical_Depth_055`, masked by `AOD_QA` bits 8-11. Marked **optional** in `Indicators_Computation_v3.md §1.1`.

**Q1 — v1.x value gaps.** None. It is optional by design.

**Q2 — accuracy levers.**
- **MAIAC QA mask is multi-layered.** v1 masks bits 8-11; v1.x could check additional bits (cloud, snow/ice, adjacency). Diminishing returns.
- **Daily AOD has high variability.** A 90-day mean is essential.

**Q3 — data-quality gaps.** §6.3 placeholder. Pixel size (~1 km MAIAC) is fine even at 1 km buffer.

**Defensibility verdict.** **Defensible.** AOD is a well-validated product; treating it as optional is correct because PM₂.₅ + AAI cover similar ground.

---

### 2.9 Pillar aggregates — Air

**v1 state.**

```
Air_Pollution_Proxy_Score = 0.30·NO₂ + 0.20·SO₂ + 0.15·CO + 0.15·HCHO
                          + 0.10·PM_or_Aerosol + 0.10·O₃_context

Air_Pollution_Audit_FollowUp_Priority =
    0.35·Air_Pollution_Proxy_Score
  + 0.30·SpatioTemporal_Anomaly_Score
  + 0.20·Trend_Score                (= 0 in Screening mode)
  + 0.15·Attribution_Confidence_Score
```

**Q1 — v1.x value gaps.**
- **`Trend_Score = 0` in screening mode is by design.** No gap.
- **`Trend_Score` is engine-blocked in trend mode** (§1.2 above). This is the gap.
- **`Attribution_Confidence_Score` is currently a placeholder** (§1.1 above). Same gap as confidence everywhere else.

**Q2 — accuracy levers.** The pillar weights themselves were set qualitatively from `Indicators_Full_Research.pdf` ranking work. They are defensible but not empirically calibrated. A v1.x sensitivity analysis (run the screening at a stratified sample of 50 sites, vary each weight by ±0.05, plot rank-order stability) would let the project claim "weights are within their stability envelope." This is the kind of analysis ESG reviewers expect.

**Q3 — data-quality gaps.** Confidence formula gap.

**Defensibility verdict.** **Defensible** once §1.1 lands. The pillar formula is consistent with ESRS E2 / GRI 305-7 framing per `Indicators_Computation_v3.md §1.2` note on `Industrial Air Pollution Burden Score`.

---

## 3. GHG pillar — per-indicator audit

### 3.1 CH₄ atmospheric (`ghg.ch4.*`)

**v1 state.** Sentinel-5P OFFL `CH4_column_volume_mixing_ratio_dry_air`, six-step method, ppb units.

**Q1 — v1.x value gaps.** None at the indicator level. Pillar-level: `Wind_Consistency` for plume attribution.

**Q2 — accuracy levers.**
- **TROPOMI CH₄ has known historical gaps** (per `GEE_Database_List_v3.md` table row). Coverage is patchy at high latitudes and over dark surfaces. The valid-pixel filter handles this passively.
- **CH₄ is well-mixed and the 1 ppb anomaly is hard to detect at the supplier scale.** §5.3 GHG3 already flags this. The "screening only, never quantification" framing is correct.
- **The CH₄_Context_Adjusted sub-aggregate** (CH₄ − 0.2 × Fire_or_Regional_Transport_Risk) is methodologically sound. The 0.2 multiplier is a calibration not a physical constant; documenting it as a tunable is fine. v1.x: when FIRMS lands, the multiplier increases to ~0.4 on confirmed-fire dates (`Indicators_Computation_v3.md §7.3` last paragraph).
- **Cross-reference with TROPOMI plume detection products.** Outside scope for v1; commercial CH₄ products (Kayrros, GHGSat) exist but are not in GEE.

**Q3 — data-quality gaps.** §6.3 placeholder. CH₄-specific: pixel size (~7×5.5 km) is bigger than 1-5 km buffers, so confidence at small buffers should drop hard. Same logic as PM₂.₅. Column-vs-surface uncertainty: **weak by design** per §1.5 — the long lifetime and ~1900 ppb global background mean a local enhancement is a small fraction of the column. Tag in provenance.

**Defensibility verdict.** **Defensible with explicit caveats.** "Methane hotspot screening" per the `Indicators_Full_Research.pdf` "Best interpretation" table is the right framing.

---

### 3.2 Fossil CO₂ context (`ghg.co2.*`) — ODIAC

**v1 state.** ODIAC fossil-fuel CO₂ emissions, uploaded asset at `projects/supply-chain-observatory/assets/odiac`. Coverage window 2020-2023 (declared in `coverage_window` per M5.5c).

**Critical change in current v1: ODIAC has been DEMOTED from the live composite** (per `v1x_followups.md` M5.5b, line 427-486). The Core_GHG_Audit_Support weights have been rescaled to drop ODIAC: 0.46·CH₄ + 0.44·Combustion_Proxy + 0.10·Activity_Score (sum = 1.0). ODIAC still computes and displays as "standing exposure context" alongside the live composite, but does not feed the live score.

**Q1 — v1.x value gaps.**
- **CARMA-overlap flag (`v1x_followups.md` line 406-410).** The score formula clamps `relative_intensity` at 10× as a CARMA-overlap proxy. v1.x should detect point-source overlap explicitly and set `carma_overlap=True` in provenance so the limiting-factor template can surface "CO₂ value influenced by reported power-plant allocation nearby."
- **Atmospheric XCO₂ (OCO-2/3).** Already considered and rejected in `GEE_Database_List_v3.md §7`. The rejection holds — XCO₂ is too coarse and gappy to add screening value above ODIAC. Do not reopen.
- **ODIAC vintage flag in `ghg.retrieval_inventory_quality` (`v1x_followups.md` line 419-421).** The per-image `as-of` property is set on the asset but not yet wired into the data-quality sub-score.

**Q2 — accuracy levers.**
- **Cross-validate against Climate TRACE (`v1x_followups.md` line 459-472).** Build `scripts/validate_co2_proxy.py`: pick 50-100 historical points within 2020-2023, stratified across supplier types, compute `ghg.co2.score` and `ghg.core_audit_support` (live trio) at each, report Spearman ρ overall and by stratum. **This is the single highest-leverage v1.x item from the project's defensibility standpoint** because it produces a quotable validation number ("our live trio achieves ρ = X against ODIAC for diffuse locations and ρ = Y for point-source-proximate locations").
- **EDGAR.** Already considered and rejected (`GEE_Database_List_v3.md §7`). Adds redundancy with ODIAC; larger lag; sector allocation adds complexity. Don't reopen for v1.x.
- **Reframe the display-only sub-aggregates (`v1x_followups.md` line 527-549).** `ghg.fossil_combustion_score` and especially `ghg.activity_adjusted_co2` triple-count VIIRS. They should be reframed as diagnostic-only or removed in v1.x.

**Q3 — data-quality gaps.**
- **The vintage lag is the dominant quality issue.** ODIAC's 2+ year lag must be surfaced everywhere ODIAC contributes to display — verbal summary, KPI tiles, provenance. M5.5c put `data_type="emissions_inventory_allocation"` in provenance, which is excellent.
- **CARMA overlap should surface in confidence too**, not just as a flag. A buffer that overlaps a CARMA point source has a high `ghg.co2.score` that is *expected* (it's just reading what CARMA said); the supplier-specific signal in that score is correspondingly low.

**Defensibility verdict.** **Defensible** in its current v1 demoted role (standing exposure context, not live signal). The demotion + provenance + cross-validation script together make this one of the more carefully-handled indicators in the tool.

---

### 3.3 VIIRS nighttime-light activity (`ghg.viirs.*`)

**v1 state.** VIIRS Black Marble `NASA/VIIRS/002/VNP46A2`, `Gap_Filled_DNB_BRDF_Corrected_NTL` band, six-step method, nW cm⁻² sr⁻¹.

**Q1 — v1.x value gaps.** None at the indicator level.

**Q2 — accuracy levers.**
- **VIIRS sees urban spillover, traffic, gas flaring, sports stadiums, and many non-industrial sources** (§5.3 GHG4). Treating it as an "activity proxy" not an "emissions signal" is correct.
- **Gas-flaring-specific layer.** A gas-flaring-only VIIRS product exists (the Skytruth / NOAA VIIRS Nightfire dataset is the canonical reference). Adding it would let the tool flag flaring-heavy GHG contexts specifically. Not in GEE native, would require ingestion. Worth flagging for v1.x consideration but not first-priority.
- **VIIRS double-counting with ODIAC's diffuse branch.** Already resolved by the M5.5b demotion (ODIAC out of live composite; VIIRS now carries 0.10 weight without overlap concern). No further fix needed.

**Q3 — data-quality gaps.** §6.3 placeholder. VIIRS-specific: cloud cover and lunar illumination affect quality; the Gap_Filled product handles most of this but the QA flags should feed confidence.

**Defensibility verdict.** **Defensible** with the "activity proxy, not emissions signal" caveat.

---

### 3.4 Pillar aggregates — GHG

**Reference formulas** (canonical, from `Final_Indicators_List.pdf` / `Indicators_Computation_v3.md` §2.3):

```
Core_GHG_Audit_Support_REFERENCE =
    0.35·CO₂_Context + 0.25·CH₄_Hotspot_Signal + 0.20·Combustion_Proxy
  + 0.10·Activity_Score + 0.10·High_GWP_Sector_Risk
                                                       (sums to 1.00)

GHG_Data_Quality_Attribution_REFERENCE =
    0.25·Temporal_Coverage + 0.20·Spatial_Resolution_Suitability
  + 0.20·Retrieval_or_Inventory_Quality + 0.15·Wind_Consistency
  + 0.10·Sector_Match + 0.10·Nearby_Source_Isolation
                                                       (sums to 1.00)

GHG_Audit_FollowUp_Priority_REFERENCE =
    0.40·Core_GHG_Audit_Support + 0.25·GHG_SpatioTemporal_Anomaly
  + 0.20·GHG_Trend + 0.15·GHG_Data_Quality_Attribution
                                                       (sums to 1.00)
```

**Live v1 formulas (post-M5.5b ODIAC demotion):**

```
Core_GHG_Audit_Support_v1 =
    0.46·CH₄_Hotspot_Signal + 0.44·Combustion_Proxy + 0.10·Activity_Score
                                                       (sums to 1.00)
  Method: ODIAC's CO₂_Context term excluded (demoted to standing exposure
          per M5.5b); High_GWP_Sector_Risk excluded (deferred to v1.x);
          three live signals rescaled by 1/0.61 per the engine's
          CORE_GHG_AUDIT_SUPPORT_WEIGHTS constant (cited in v1x_followups
          M5.5b paragraph).

  Note: the implied engine source weights (CH₄, Combustion, Activity
        summing to 0.61 before rescale) do not exactly match the
        canonical Final_Indicators_List.pdf reference values
        (which would imply 0.55, not 0.61). The engine's working weights
        likely include an earlier rescale that excluded High_GWP_Sector_Risk
        at engine init. Worth verifying during the §1.4 spec-sync milestone;
        the live composite output is correct; the documentation lineage
        is what needs reconciliation.

GHG_Data_Quality_Attribution_v1 =
    0.33·Temporal_Coverage + 0.27·Spatial_Resolution_Suitability
  + 0.27·Retrieval_or_Inventory_Quality
  + 0.13·Nearby_Source_Isolation
                                                       (sums to 1.00)
  Method: Wind_Consistency (0.15) deferred to Tier C1a;
          Sector_Match (0.10) scrapped per §9.2;
          remaining four terms rescaled from 0.75 via factor 1/0.75.

GHG_Audit_FollowUp_Priority unchanged from reference.
```

> **Correction note.** A prior version of this audit showed `GHG_Data_Quality_Attribution_v1` weights as `0.30 / 0.24 / 0.24 / 0.12` with rescale factor `1/0.85`. Those values do not sum to 1.0 (they sum to 0.90) and the rescale factor was incorrect (the deferred terms summed to 0.25, so the correct factor is `1/0.75`, not `1/0.85`). The values above are the methodologically correct rescaling assuming the canonical reference weights are correct. Worth verifying against `engine.constants.GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS` during the v1.x spec-sync milestone (§1.4).

**Q1 — v1.x value gaps.**
- **High_GWP_Sector_Risk (`ghg.high_gwp_sector_risk`).** Reserved in `Indicator_ID_Schema_v1.md §8`. Requires sector input (deferred to v1.x post-P-02 sector-tagging work).
- **Wind_Consistency (`ghg.wind_consistency`).** Reserved. Requires ERA5 wind (Tier C1a).
- **Sector_Match (`ghg.sector_match`).** **Deprecated** per §9.2 — not deferred, scrapped from the confidence formula on metadata-bias grounds. Surviving conceptually as a standalone provenance flag.
- **Nearby_Source_Isolation (`ghg.nearby_source_isolation`).** Currently a v1 satellite proxy (per `Indicators_Computation_v3.md §7.2`) is computed but exposed only as an internal sub-score, not as a public indicator ID. v1.x should expose it.
- **Temporal_Coverage, Spatial_Resolution_Suitability, Retrieval_or_Inventory_Quality.** All currently placeholders inside the confidence formula gap (§1.1 above). The constants exist (per `v1x_followups.md` line 783-784: `GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS`), but the live values feeding them are not yet computed.

**Q2 — accuracy levers.** The v1.x roadmap for GHG is the most active in the codebase (M5.5 → M5.5b → M5.5c → M5.6 are all GHG iteration). The next steps are documented in v1x_followups — CARMA overlap, validation script, reframe-or-remove the display-only sub-aggregates.

**Q3 — data-quality gaps.** All four `GHG_Data_Quality_Attribution` sub-scores need real computation. This is bundled into the §1.1 confidence formula fix.

**Post-v1.x end-state formula** (after Tier C1a wind lands; for reference):

```
GHG_Data_Quality_Attribution_post_v1x =
    0.28·Temporal_Coverage + 0.22·Spatial_Resolution_Suitability
  + 0.22·Retrieval_or_Inventory_Quality + 0.17·Wind_Consistency
  + 0.11·Nearby_Source_Isolation
                                                       (sums to 1.00)
  Method: Sector_Match scrapped per §9.2; its 0.10 weight redistributed
          proportionally across the other five terms.
```

**Defensibility verdict.** **Defensible** post-M5.5b for the live composite (CH₄ + combustion + activity), provided the standing-exposure ODIAC layer is honestly labelled. The CARMA-overlap flag is the gating v1.x item for point-source-heavy locations.

---

## 4. Nature / Land pillar — per-indicator audit

### 4.1 KBA proximity / overlap (`nature.kba.*`)

**v1 state.** Vector distance from supplier point to `projects/ee-kbas-in-gee/assets/current`, intersect with Site_Buffer for overlap. Formula:

```
KBA_Proximity_or_Overlap = max(overlap_pct/100, exp(−dist_km/10))
```

**Q1 — v1.x value gaps.** None at the indicator level.

**Q2 — accuracy levers.**
- **The 10 km decay constant is calibrated.** A 7 km distance gives 0.50; a 20 km distance gives 0.14. This is a reasonable decay but it's a choice, not a physical constant. Worth documenting and exposing as a tunable.
- **No EE round-trip batching yet (`v1x_followups.md` line 358-361).** `compute_kba_proximity` issues 3-4 sequential `getInfo()` calls. v1.x: combine into one server-side `ee.Dictionary` computation. This is performance, not accuracy.
- **KBA dataset accuracy is moderate** (§5.4 N3). Polygons drawn from many source surveys with varying precision. No client-side fix.

**Q3 — data-quality gaps.** §6.3 placeholder. KBA-specific: the dataset is static-ish (updated every 6 months per `GEE_Database_List_v3.md` row 17), so `Temporal_Coverage` is always full. The dominant confidence factor is polygon precision, which is unobservable from the data. Use `data_type="reference_dataset"` in provenance (already in place per M5.6).

**Defensibility verdict.** **Defensible.** This is one of the cleanest indicators in v1.

---

### 4.2 Dynamic World land-cover composition (`nature.dw.*`)

**v1 state.** 90-day mode composite over Site_Buffer; per-class areas and percentages for 9 classes; dominant-class mean probability for confidence.

**Q1 — v1.x value gaps.** None.

**Q2 — accuracy levers.**
- **Dynamic World is ML-classified satellite** (`data_type="ml_classified_satellite"` per M5.6). The class probabilities are well-validated globally but confusion exists in arid landscapes, dry crops, and post-fire scars (§5.4 N1).
- **The fixed natural / non-natural class mapping** (`Indicators_Computation_v3.md §3.5`) is a methodological choice. Documenting `flooded_vegetation` as natural (correct) and `water` as semi-natural context (correct, not counted as habitat) is good practice.
- **The `flooded_vegetation → water` borderline check** (NDVI drop check before counting as habitat loss) is a sophisticated mitigation. Keep it.
- **Sentinel-2 BSI / NDBI confirmation** for bare-ground and built-up classes (per `Indicators_Computation_v3.md §3.1`). Marked "optional"; in v1 it may not be wired. v1.x: turn on by default for high-stakes habitat-conversion calls.

**Q3 — data-quality gaps.** §6.3 placeholder. `DynamicWorld_Class_Confidence` (mean class probability over Site_Buffer) is already produced per IC §3.3 and used inside `Nature_Quality_Attribution`. This is the one place in v1 where the data-quality formula is more mature than the rest.

**Defensibility verdict.** **Defensible.**

---

### 4.3 Habitat conversion (`nature.habitat.*`)

**v1 state.** Compare current 90-day composite vs baseline 90-day composite from `HABITAT_BASELINE_YEARS = 5` years earlier; per-class transition areas; `annualised_rate = converted_area_ha / 5`. The 10% saturation calibration (`CONVERSION_SATURATION_PCT`) is the right defensive choice. For the formula's pillar-level expression (current v1 form with Hansen still present, plus the post-v1.4 form with Hansen removed), see §4.8.

**Q1 — v1.x value gaps.** User-tunable baseline window (currently locked to 5 years).

**Q2 — accuracy levers.**
- **EE round-trip batching (`v1x_followups.md` line 363-368).** `compute_habitat_conversion` does 4 round-trips. Combine into one server-side call.
- **Cross-reference with Hansen forest loss** as confidence-side context, *not* as a live composite term. Post-§9.3 v1.4, Hansen contributes via `regional_loss_evidence` inside `External_Driver_Screening` rather than directly into `Habitat_Conversion`. The two methodologies should still broadly agree on the woody-cover-loss subset; large divergence remains a useful internal quality flag.
- **The 5-year baseline is aligned with ESRS E4 and TNFD 5-year reporting horizons.** This is a defensible choice; do not weaken it without need.

**Q3 — data-quality gaps.**
- **`Seasonal_Comparability`** sub-score (§3.3) already handles month-offset comparisons. Good.
- **`Supplier_Spatial_Link`** (§7.5) — confidence-side check on whether change pixels cluster near the supplier point. Already specified.
- **`External_Driver_Screening`** (§7.5) — fire / drought / regional-loss exclusion. Specified.

All three are part of `Nature_Quality_Attribution`. Whether they are **actually live** in the engine (vs documented in the spec but placeholder-valued) is the same question that applies to every data-quality sub-score in v1 — this is bundled into the §1.1 fix.

**Defensibility verdict.** **Defensible.**

---

### 4.4 Forest loss (Hansen) (`nature.forest_loss.*`)

**v1 state.** Hansen `lossyear` band ≥ baseline year, within Site_Buffer. Annual update; v1 uses `UMD/hansen/global_forest_change_2024_v1_12`.

**Status update (v1.4 §9.3).** Hansen forest loss has been **demoted** from the live `Habitat_Conversion` composite by analogy with the M5.5b ODIAC demotion. It survives in two scoped roles: (a) as an input to `regional_loss_evidence` inside `External_Driver_Screening`, with a fixed 5-year lookback; (b) as a standing reference layer in the Indicator Library (P-09). Provenance carries `temporal_mode = "standing_exposure"` and `data_type = "reference_dataset"`. See §9.3 for the full reasoning and updated `Habitat_Conversion` formula.

**Q1 — v1.x value gaps.** None at the indicator level. The 0.10 weight previously carried in `Habitat_Conversion` has been redistributed across the four DW-based terms per §9.3 v1.4.

**Q2 — accuracy levers.** Hansen is well-validated and widely cited. No filter change needed. The dataset's known issue is plantation cycles being detected as loss; after demotion this caveat is low-stakes because the indicator is now framed as cumulative historical context rather than current-period loss.

**Q3 — data-quality gaps.** §6.3 placeholder. Hansen-specific: annual update cadence means the most recent loss-year may be missing for the first few months of a calendar year. Provenance should record which Hansen vintage is in use.

**Defensibility verdict.** **Defensible** in its demoted role. Strongest use is inside `regional_loss_evidence` where the buffer/ring comparison uses the same Hansen window on both sides — the annual cadence is a feature there, not a liability.

---

### 4.5 NDVI (`nature.ndvi.*`)

**v1 state.** Sentinel-2 SR Harmonized, B8/B4 normalised difference, masked by SCL classes 3, 8, 9, 10, 11 plus Dynamic World built/water/bare mask. Six-step method on monthly medians.

**Q1 — v1.x value gaps.**
- **`nature.ndvi.negative_trend` is currently None** because `engine/core/trend.py` has not landed (§1.2 above). This blocks `Vegetation_Condition` from carrying its 0.25 trend weight.

**Q2 — accuracy levers.**
- **NDVI < 0.3 as the "low vegetation" threshold is biome-dependent** (§5.4 N4). A deciduous forest in winter naturally falls below 0.3. Mitigations:
  - The `Low_Vegetation_Area_pct` formula only counts pixels inside the natural-cover mask (per §3.2 sub-formula breakdown), which addresses the crop-cycle case.
  - The seasonal baseline (§0.6) is on by default for NDVI, which addresses the winter case.
  - For v1.x, consider switching the 0.3 threshold to a **biome-aware threshold** — i.e. the local median NDVI for the dominant Dynamic World natural class, minus some delta. This is methodologically tighter but adds complexity. **Recommendation: ship a calibrated biome-aware threshold as a v1.x extension; default the v1 fixed 0.3 to "good enough for screening" with the caveat documented.**
- **Cross-reference with MODIS NDVI/EVI 16-day (MOD13Q1) for longer-history trend.** Already in `GEE_Database_List_v3.md` row 14. Used selectively in v1 (per `Engine_Module_Skeleton_v1.md` Nature pillar likely).

**Q3 — data-quality gaps.** §6.3 placeholder. NDVI-specific quality signals: cloud-mask pass rate, Dynamic World natural-class purity, seasonal alignment with baseline. These exist as `Valid_Pixel_Coverage`, `Cloud_or_Observation_Quality`, and `Seasonal_Comparability` in `Nature_Quality_Attribution`.

**Defensibility verdict.** **Defensible** for the snapshot metrics; **Methodologically incomplete** for the trend metric until `trend.py` lands.

---

### 4.6 Bare-ground / Built-up expansion (`nature.bare.*`, `nature.built.*`)

**v1 state.** Dynamic World "bare" / "built" class change between baseline and current; optional Sentinel-2 BSI / NDBI confirmation.

**Q1 — v1.x value gaps.** Whether BSI/NDBI confirmation is wired in v1 or marked "optional and skipped". Worth verifying against `engine/nature.py`.

**Q2 — accuracy levers.**
- **Bare-ground is the most ambiguous DW class** (§5.4 N1, and `Indicators_Computation_v3.md §3.4`). Confuses dry soil, rock, construction sites, post-fire scars. Adding BSI confirmation reduces false positives.
- **Built-up is the most permanent and most attributable** subtype. Less ambiguity. NDBI confirmation is optional.

**Q3 — data-quality gaps.** §6.3 placeholder.

**Defensibility verdict.** **Defensible with explicit caveats** for bare-ground (the ambiguity must be surfaced); **Defensible** for built-up.

---

### 4.7 Water / Flooded vegetation exposure (`nature.water.*`)

**v1 state.** Dynamic World classes "water" and "flooded_vegetation"; distance to nearest water.

**Q1 — v1.x value gaps.**
- **JRC GSW long-term water (Nature pillar)** — flagged in `v1x_followups.md` line 414 as "still pending IC docs." GSW is the canonical long-term surface water dataset; it would replace or supplement DW's water class for the historical baseline.

**Q2 — accuracy levers.** DW water class is good for current state but noisy on seasonal water bodies. GSW would add a stable historical baseline.

**Q3 — data-quality gaps.** §6.3 placeholder.

**Defensibility verdict.** **Defensible**; GSW integration is a nice-to-have, not a must-have.

---

### 4.8 Pillar aggregates — Nature

**Reference formulas** (canonical, from `Final_Indicators_List.pdf` / `Indicators_Computation_v3.md` §3.3):

```
Biodiversity_Exposure_REFERENCE =
    0.40·KBA_Proximity_or_Overlap + 0.30·Sensitive_LandCover_Presence
  + 0.20·Water_or_FloodedVegetation_Exposure + 0.10·Buffer_Sensitivity
                                                       (sums to 1.00)

Habitat_Conversion_REFERENCE =
    0.35·Natural_Habitat_Loss_% + 0.25·Natural_to_Built_%
  + 0.20·Natural_to_Bare_% + 0.10·Forest_Loss_%
  + 0.10·Annualised_Conversion_Rate
                                                       (sums to 1.00)

Vegetation_Condition_REFERENCE =
    0.35·Inverted_NDVI_SpatioTemporal_Anomaly
  + 0.20·Inverted_EVI_SpatioTemporal_Anomaly
  + 0.20·Negative_Vegetation_Trend
  + 0.15·Low_Vegetation_Area_pct
  − 0.10·Recovery_Signal
                                                       (positive weights sum
                                                        to 0.90 by design;
                                                        Recovery is a separate
                                                        negative-direction signal
                                                        subtracting up to 0.10)

Nature_Quality_Attribution_REFERENCE =
    0.20·Valid_Pixel_Coverage + 0.20·Cloud_or_Observation_Quality
  + 0.20·DynamicWorld_Class_Confidence + 0.15·Seasonal_Comparability
  + 0.15·Supplier_Spatial_Link + 0.10·External_Driver_Screening
                                                       (sums to 1.00)

Nature_FollowUp_Priority_REFERENCE =
    0.30·Biodiversity_Exposure + 0.30·Habitat_Conversion
  + 0.25·Vegetation_Condition + 0.15·Nature_Quality_Attribution
                                                       (sums to 1.00)
```

**Live v1 formulas:**

```
Biodiversity_Exposure_v1 =
    0.444·KBA_Proximity_or_Overlap + 0.333·Sensitive_LandCover_Presence
  + 0.222·Water_or_FloodedVegetation_Exposure
                                                       (sums to 1.00)
  Method: Buffer_Sensitivity (0.10) deferred to v1.x (requires sector
          input); remaining three terms rescaled from 0.90 via 1/0.90.
          Three-decimal precision shown so displayed weights sum cleanly;
          engine stores at full float precision.

Vegetation_Condition_v1 =
    0.45·Inverted_NDVI + 0.25·Negative_Vegetation_Trend
  + 0.20·Low_Vegetation_Area_pct − 0.10·Recovery_Signal
                                                       (positive weights sum
                                                        to 0.90, preserving the
                                                        reference formula's total
                                                        positive weight)
  Method: EVI term (0.20) absorbed into NDVI per IC §7.4 — EVI is strongly
          correlated with NDVI; the merged weight is now 0.45. The remaining
          weight is split into trend and low-veg area. Recovery stays at
          −0.10 as an independent positive-direction signal.
          Negative_Vegetation_Trend currently returns None and is
          substituted as 0.0 per the M-FOLLOWUP-FALLBACK pattern (blocked
          by missing trend engine §1.2 above). The 0.25 weight is dead in
          v1 until A2 lands.

Habitat_Conversion_v1 (current pre-§9.3-v1.4) =
    0.35·Natural_Habitat_Loss_% + 0.25·Natural_to_Built_%
  + 0.20·Natural_to_Bare_% + 0.10·Forest_Loss_%
  + 0.10·Annualised_Conversion_Rate
                                                       (sums to 1.00)
  Method: full reference formula; no rescaling applied in current v1.

Nature_Quality_Attribution_v1 — same as reference (no deferrals).

Nature_FollowUp_Priority_v1 — same as reference.
```

**Post-§9.3 v1.4 formula (after Hansen demotion):**

```
Habitat_Conversion_post_v1x =
    0.40·Natural_Habitat_Loss_% + 0.27·Natural_to_Built_%
  + 0.22·Natural_to_Bare_% + 0.11·Annualised_Conversion_Rate
                                                       (sums to 1.00)
  Method: Forest_Loss_% removed (Hansen demoted to standing exposure +
          regional_loss_evidence input only per §9.3); 0.10 weight
          redistributed proportionally across the four DW-based terms.
```

**Q1 — v1.x value gaps.**
- **`nature.buffer_sensitivity`** reserved (`Indicator_ID_Schema_v1.md §8`). Requires sector input. The 0.10 weight on `Biodiversity_Exposure` is currently rescaled per the live v1 formula above.
- **`Negative_Vegetation_Trend`** blocked by missing trend engine (§1.2).
- **`nature.forest_loss.*` demoted from live composite** per §9.3 v1.4. Survives in `regional_loss_evidence` and as standing reference in the Indicator Library.

**Q2 — accuracy levers.** Same sensitivity-analysis recommendation as for Air pillar: vary each pillar weight by ±0.05, check rank-order stability across a 50-site sample. Defensibility hook for ESG reviewers.

**Q3 — data-quality gaps.** The full `Nature_Quality_Attribution` (Valid_Pixel + Cloud + DW_Class_Confidence + Seasonal_Comparability + Supplier_Spatial_Link + External_Driver_Screening) is specified in the IC doc but likely placeholder-valued in v1 outside of DW_Class_Confidence. This is the largest data-quality gap in the Nature pillar specifically and bundles into the §1.1 fix.

**Defensibility verdict.** **Defensible** with the explicit caveat that vegetation trend is currently zero-weighted in screening (which is fine) AND that the data-quality sub-scores beyond DW class confidence are placeholders.

---

## 5. Cross-pillar composite

**v1 state.**

```
Overall_Screening_Score = ⅓·Air + ⅓·GHG + ⅓·Nature
composite.confidence = min(Air_Conf, GHG_Conf, Nature_Conf)
```

**Q1 — v1.x value gaps.** Sector-aware weighting deferred. The equal ⅓ default is correct for screening; sector-weighted variants come post-P-02 sector-tagging.

**Q2 — accuracy levers.** None at the cross-pillar level beyond the per-pillar items.

**Q3 — data-quality gaps.** `composite.confidence = min(...)` is the right framing (conservative; one weak pillar drops the composite). But the pillar-level confidences are placeholders today, so the composite confidence is also a placeholder. Bundles into §1.1.

**Defensibility verdict.** **Defensible** structurally; will be **Defensible** in numerical output once §1.1 lands.

---

## 6. The v1.x prioritised roadmap

Combining the per-indicator audit above and the items in `v1x_followups.md`, the v1.x work has six tiers ordered by leverage. **Each tier completes before the next is scoped**, to avoid the trap of starting many indicators and finishing none.

### Tier A — Scientific integrity (BLOCKERS for v1.x defensibility)

**A1. §6.3 confidence formula** (cross-cutting issue §1.1). Replace flat 0.7/0.8 placeholders with the QA + N_valid + anomaly_strength + spatial_context formula. ~1 week. Unblocks every confidence dot, the verbal summary tiering, and `composite.confidence`. **The single most important v1.x item from a defensibility standpoint.**

**A2. `engine/core/trend.py`** (cross-cutting issue §1.2). Theil-Sen + Mann-Kendall. ~1-2 weeks. Unblocks P-06, Vegetation_Condition's 0.25 trend weight, and every `*.trend` ID. Also removes the M-FOLLOWUP-FALLBACK known-zero substitution.

**A3. Background-ring fallback Option 1 — land mask** ✅ **DONE (26 May 2026, M-TIER-A3).** Intersect background ring with global land mask (MOD44W v6, 250 m) before reducing. Real-EE verified at Sapezal (land_fraction 0.9999), Mumbai (0.524), Rio (0.571), Shenzhen (0.585); coastal CH₄ z-scores bounded post-mask. Three new `provenance.extra` fields (`ring_land_fraction`, `land_mask_applied`, `land_mask_asset`) thread through air/ghg/nature pillars. Below the LM7 threshold (`< 0.05` land) the existing `BackgroundRingNoDataError` skip path fires with the distinct `ring_empty_post_land_mask` reason marker. Sparse-coverage AOIs still routed to skip path — climatology fallback (M-CLIM-A3b, audit §1.3 Option 2) remains the open v1.x-late composition partner.

**Outcome of Tier A.** Every existing v1 indicator emits a defensible value, a defensible confidence, and a defensible trend (in trend mode). No new datasets. No new dependencies. **This is the foundation for everything below.**

---

### Tier B — Cross-validation (DEFENSIBILITY for supervisor / reviewers)

**B1. `scripts/validate_co2_proxy.py`** (`v1x_followups.md` M5.5b line 459-472). Stratified sample of 50-100 historical points, compute the live trio + ODIAC score at each, report Spearman ρ by stratum. **Produces a quotable number** for any thesis defence: "the live trio achieves ρ = X against the independent ODIAC source for diffuse locations and ρ = Y for point-source-proximate locations."

**B2. CARMA-overlap flag** (`v1x_followups.md` line 406-410). Replaces the 10× clamp proxy in `ghg.co2.relative_intensity` with explicit point-source detection. Surfaces in the limiting-factor verbal-summary template. Closes the "we know this is a point source we just don't say so" gap.

**B3. Sensitivity analysis on pillar weights.** Run the screening at 50 stratified sites, vary each weight by ±0.05, plot rank-order stability. Produces another quotable defensibility number ("rank-order is preserved within the documented weight envelope").

**Outcome of Tier B.** The tool produces three independent defensibility statements: (a) confidence formula is real, (b) live trio is calibrated against ODIAC at known emitters, (c) weights are inside their stability envelope. This is the floor for academic / supervisor defence.

---

### Tier C — High-value new context (UNLOCKS deferred indicators)

**C1. ERA5 wind integration.** Per `GEE_Database_List_v3.md §7` and `Indicator_ID_Schema_v1.md §8`. This is the largest single methodological upgrade in the v1.x roadmap and unlocks three distinct things, split here as C1a / C1b / C1c so they can be scoped independently.

**C1a — `ghg.wind_consistency` sub-score (HIGH leverage, LOW risk).** The deferred 0.15 weight inside `GHG_Data_Quality_Attribution_v1`. Tells the user: "the days on which an anomaly was detected were also days with wind direction consistent with the supplier being upwind of the buffer." If wind was blowing the plume *away* from the buffer, a positive anomaly is less likely to be supplier-attributable and the confidence drops. Implementation:

```
1. For each anomaly day (Z ≥ ANOMALY_Z_THRESHOLD):
   a. Pull ERA5 u10/v10 wind components averaged over the supplier point.
   b. Compute mean wind direction during the satellite overpass window
      (~13:30 local time for Sentinel-5P).
2. wind_consistency_per_day = 1 if the buffer lies downwind of the supplier;
   else 0 (or graded by angular alignment for non-binary scoring).
3. Wind_Consistency = mean(wind_consistency_per_day across anomaly days)
```

**Per-gas wind sensitivity — drives which indicators get the term first.** Not every gas benefits equally; the indicator-level priority for `Wind_Consistency` rollout is:

| Gas | Wind sensitivity | Reasoning |
|---|---|---|
| **NO₂** | **High** | Short lifetime (~hours); plumes are directional and visible in satellite imagery. The Canadian oil-sands TROPOMI study (Griffin et al. 2019) cited in `Indicators_Full_Research.pdf` literally maps plume directionality. |
| **SO₂** | **High** | Same short-lifetime logic; SO₂ stack plumes are typically even more directional than NO₂. |
| **CH₄** | **Moderate** | Long lifetime means wind dispersion is less directional, but anomaly-day attribution still benefits (this is the namespaced `ghg.wind_consistency` use case). |
| **AAI / smoke / dust** | **Moderate** | Smoke and dust plumes are highly directional; wind explains the transport patterns the `Smoke / Dust / Regional Transport Score` is meant to capture. |
| **CO** | **Moderate-to-weak** | Long lifetime; regional transport dominates over local wind direction. Wind still helps identify whether elevated CO is upwind-originated (per CO Q2 above), but the local supplier-attribution payoff is smaller. |
| **HCHO** | **Moderate** | Short lifetime, but photochemical production fuzzes the directionality. |
| **O₃** | **N/A** | Secondary pollutant; wind doesn't attribute it to a source. Skip. |
| **CAMS PM** | **N/A** | CAMS uses ERA5 wind internally as part of the meteorological forcing. Do not second-guess it. |

Roll out `Wind_Consistency` for NO₂ + SO₂ + CH₄ + AAI in C1a; defer the others.

**C1b — Boundary-layer height awareness in the confidence formula (MEDIUM leverage, LOW risk).** ERA5 also provides `boundary_layer_height`. When the BLH during the analysis window is unusually low or high relative to the local climatology, the confidence on column → surface inference should drop (per §1.5 above). Bundles naturally with C1a — same dataset, same ingestion pipeline, marginal additional cost. Improves the honesty of every gas indicator's confidence score, particularly for SO₂ and CH₄ where stack injection / vertical mixing can decouple column from surface.

**C1c — Directional buffer construction (HIGH leverage, MEDIUM risk).** Instead of a symmetric circle around the supplier, construct an asymmetric AOI that extends further downwind than upwind — typically ~10-20 km downwind, ~2-5 km upwind, with the Background_Ring biased away from the supplier's downwind sector. This is a real methodological upgrade because industrial plumes routinely drift 5-20 km downwind (`Indicators_Computation_v3.md §6.3` point 3) and a symmetric 5 km buffer misses the plume entirely on steady-wind days.

But the methodological cost is real: it complicates cross-supplier comparison (Buffer A is shaped differently from Buffer B), the verbal summary, and the reporting. It also requires a *stable* mean wind direction over the analysis window, which is only reliably true in some climates (trade winds, monsoon flow) and not others (mid-latitude variable weather).

**Recommendation.** Ship C1a + C1b in v1.x as a single milestone (low complexity, high defensibility). Treat C1c as a deeper extension that needs its own methodology section in the IC spec doc; not a v1.x lift unless C1a+C1b reveal that the symmetric buffer is masking signal in a way C1c demonstrably fixes.

**C2. Sector input plumbing** (post-P-02 sector tagging). Unlocks:
- `ghg.high_gwp_sector_risk` (additive prior-information term in Core_GHG_Audit_Support).
- `nature.buffer_sensitivity` (in Biodiversity_Exposure).
- The new standalone "sector-signal anomaly" flag in provenance (per §9.2) — informational, not in any score or confidence arithmetic.

Note: `ghg.sector_match` is **NOT** unlocked by this tier; it's deprecated per §9.2. The post-v1.x end-state formulas (visible in §3.4 and §4.8) reflect this. The original Final_Indicators_List.pdf v1.1+ row is not fully restored — Sector_Match stays scrapped on methodological grounds; Hansen stays demoted per §9.3 v1.4.

**C3. FIRMS active-fire integration** (currently the satellite-only proxy `Fire_or_Regional_Transport_Risk` is used). Increases the 0.20 multiplier on CH₄_Context_Adjusted to ~0.40 on confirmed-fire dates.

**Outcome of Tier C.** Every deferred indicator namespaced in `Indicator_ID_Schema_v1.md §8` is live. The tool is functionally complete to the v1 spec.

---

### Tier D — Per-indicator calibration upgrades (REFINEMENTS)

Pickable in any order; each is a small, well-bounded change.

| Item | Indicator(s) | Effort |
|---|---|---|
| Switch NO₂ to `tropospheric_NO2_column_number_density` band | `air.no2.*` | 1-2 days |
| Turn on same-month seasonality for HCHO | `air.hcho.*` | hours |
| Volcanic-region flag for SO₂ | `air.so2.*` | 1 day |
| Pixel-size term in confidence for PM₂.₅ and CH₄ | `air.pm25.*`, `air.pm10.*`, `ghg.ch4.*` | bundled with A1 |
| AOD–CAMS PM divergence flag | `air.pm25.*` | 2-3 days |
| Biome-aware low-NDVI threshold | `nature.ndvi.*` | 1 week (most expensive in tier) |
| Default-on BSI/NDBI confirmation for bare/built | `nature.bare.*`, `nature.built.*` | 2-3 days |
| Hansen forest-loss vintage surfacing in provenance | `nature.forest_loss.*` | hours |

**Outcome of Tier D.** Marginal accuracy gains where defensible; no scope creep.

---

### Tier E — Performance & UX hygiene (NICE TO HAVE)

**E1. EE round-trip batching** (`v1x_followups.md` line 354-376). Combine sequential `getInfo()` calls into single `ee.Dictionary` payloads. Target: cap Nature pillar at ≤10 round-trips per AOI. ~1 week.

**E2. `verify_bands.py` smoke script** (`v1x_followups.md` line 103-105). CI step that lists every pollutant's band and asserts it's present in the asset's current band catalogue. Prevents the next CAMS-style upstream drift from taking a user-bug-report cycle to surface.

**E3. Pillar-wide `ee.EEException` wrapping** (`v1x_followups.md` line 41-66). Re-raise as `PillarComputeError` with context-aware messages.

**E4. Retry failed indicators from C9** (`v1x_followups.md` line 109-127).

**Outcome of Tier E.** Tool is faster, more robust, more debuggable.

---

### Tier F — Optional new datasets (DEFER decisions)

**F1. JRC GSW long-term water for Nature pillar** (`v1x_followups.md` line 414). Adds historical-water baseline. Low priority.

**F2. Climate TRACE facility emissions for cross-validation** (already considered in `GEE_Database_List_v3.md §7`). Not as a live signal; only as a validation source if B1 turns up issues that ODIAC alone can't diagnose.

**F3. Gas-flaring-specific VIIRS Nightfire layer** (mentioned in §3.3 above). Niche.

**Everything else listed in `GEE_Database_List_v3.md §7` stays rejected**: EDGAR (redundant with ODIAC), OCO-2/3 (too coarse), and so on. Do not reopen these without a use case.

---

## 7. What this means for the demo and the supervisor conversation

Three statements the tool can defensibly make today, **after Tier A completes**:

1. *"Every indicator value reported by the tool comes with a real per-indicator confidence score derived from QA flags, valid-pixel coverage, observation count, and anomaly strength — not a placeholder."* This is Tier A1.
2. *"Trend analysis uses Theil-Sen slope with Mann-Kendall significance testing, robust to the heavy-tailed outliers in TROPOMI / CAMS time series."* This is Tier A2.
3. *"Coastal and sparse-coverage AOIs no longer silently fail; the background ring is land-masked and indicators emit defensible z-scores even when the ring intersects ocean."* This is Tier A3.

Three further statements available **after Tier B completes**:

4. *"The live GHG composite has been cross-validated against ODIAC at 50+ known emitters across supplier types; the Spearman correlation is X for diffuse locations and Y for point-source-proximate locations, motivating the explicit CARMA-overlap surfacing."*
5. *"The pillar weights have been sensitivity-tested; rank order across the supplier set is preserved within the documented weight envelope."*
6. *"Point-source overlap is explicitly flagged in the ODIAC standing-exposure layer; the user never confounds 'high CO₂ because CARMA says so' with 'high CO₂ because the satellite signal is elevated.'"*

Two further statements available **after Tier C1 completes** (ERA5 wind + BLH):

7. *"For the wind-sensitive gases (NO₂, SO₂, CH₄, AAI), every anomaly day is checked against ERA5 wind direction at satellite-overpass time; days when the wind was blowing the plume away from the buffer drop the supplier-attribution confidence accordingly. This is the `ghg.wind_consistency` term that the v1 formula explicitly held out per the §7.1 rescaling rule."*
8. *"The tool reports atmospheric column densities, not surface concentrations, and surfaces a per-gas column-to-surface uncertainty tag (low / moderate / weak / not applicable) in provenance — calibrated against gas lifetime and boundary-layer behaviour. Boundary-layer height anomalies from ERA5 feed the confidence formula so the user knows when the column-vs-surface assumption is under additional stress."*

These eight statements together are what gets the tool past a reasonable supervisor review. Tier A and Tier B are the floor; Tier C1 is the strongest single addition that meaningfully changes the science of what the tool reports.

---

## 8. What this audit does NOT recommend

For completeness — items reviewed and not recommended for v1.x:

- **Building an internal ML layer** (e.g. an MLR for PM₂.₅ ground-truth). Out of scope for a screening tool. The PM₂.₅ ground-truth study cited in `Indicators_Full_Research.pdf` Source 11 (β0 + β1·AOD + β2·CO + β3·NO₂) is locale-specific (Chiang Mai) and not generalisable globally without per-region training data. The right cross-reference is heuristic divergence flagging (D7), not model training.
- **Computing a VCD → surface concentration conversion in the engine.** Per §1.5 and the warning in `Indicators_Full_Research.pdf`: any simple linear conversion (e.g. `PM2.5 = a·AOD + b`) is published-wrong; the serious version requires BLH + vertical profile + RH + temperature + wind + season + local emissions and is what GEOS-CF / CAMS already do. For surface PM₂.₅ the tool already uses CAMS. For gases, the right answer is to remain in VCD units and tag the column-to-surface uncertainty in provenance.
- **Directional buffer construction (C1c) as a v1.x ship item.** The methodology is sound but the cross-supplier comparability cost is real and it depends on a stable mean wind direction over the analysis window, which isn't reliably true in all climates. Defer until C1a + C1b reveal a specific case where the symmetric buffer is masking signal a directional buffer would catch.
- **Dropping O₃ or reducing its 0.10 weight.** The 0.5 cap already absorbs the stratospheric-dominance / column-vs-surface concern; the 0.10 weight is small enough not to dominate the pillar score; and O₃ carries useful regional-photochemistry information no other v1 gas provides.
- **OCO-2/3 XCO₂.** Rejected in `GEE_Database_List_v3.md §7` for good reasons (coarse, gappy, well-mixed gas → weak facility attribution). Holds.
- **EDGAR.** Rejected for redundancy with ODIAC. Holds.
- **More buffer radii.** The 1 / 5 / 10 / 25 / 50 / 100 km logarithmic progression is well-reasoned (`Indicators_Computation_v3.md §6.2`). Adding more options would invite over-tuning.
- **Lowering the anomaly Z threshold from 2 back to 1.** The v3 raise to Z ≥ 2 is correct; it matches atmospheric-science convention and makes HF a meaningful "fraction of genuinely anomalous observations." Holds.

---

## 9. Follow-up notes

Refinements and corrections to the main audit, captured as iteration notes rather than rewrites. Each note targets a specific section of the main audit and clarifies, narrows, or corrects it.

### 9.1 Note on §2.1 — the tropospheric-band recommendation is NO₂-only

The main audit (§2.1) recommends switching to `tropospheric_NO2_column_number_density` and implies similar moves may apply to other gases. Walking the bands gas-by-gas tightens this to a NO₂-only recommendation.

| Gas | Stratospheric component significant? | Separate tropospheric band in GEE? | v1.x action |
|---|---|---|---|
| **NO₂** | Yes (natural stratospheric NO₂; varies with latitude / season) | Yes — `tropospheric_NO2_column_number_density` | **Switch to tropospheric band.** |
| **HCHO** | No (short lifetime; stratosphere negligible) | Already on tropospheric band — `tropospheric_HCHO_column_number_density` (confirmed in `Inspection.js` FP_DATASETS registry and `AirQuality.js`) | **No change.** Already correct. |
| **SO₂** | Effectively no (lifetime too short for stratospheric residence except after major volcanic eruptions) | No separate tropospheric band — `SO2_column_number_density` *is* effectively tropospheric | **No change.** No band switch available or needed. |
| **CO** | Trace amounts only (from CH₄ oxidation in upper atmosphere) | No separate tropospheric band — `CO_column_number_density` is dominantly tropospheric | **No change.** |
| **O₃** | Dominantly stratospheric (~90% of total column) | Separate tropospheric ozone product (`O3_tcl`) exists but is methodologically different (Level 3, higher noise, lower coverage, different GEE feed structure) | **No change.** The existing mitigations (0.5 cap + "regional air-quality stress" framing) handle the column-vs-surface concern adequately at the screening tier; switching to L3 tropospheric ozone would change the indicator's character and reduce coverage for marginal accuracy gain. Consistent with the prior decision to keep O₃ as-is. |
| **CH₄** | The product is a column-averaged volume mixing ratio (ppb), not a column density. No tropospheric variant exists in the same form. | N/A | **No change.** The column-vs-surface concern for CH₄ is structural (long lifetime, ~1900 ppb background); addressed via the `column_to_surface_uncertainty = weak` tag in provenance (§1.5), not via a band switch. |
| **AAI** | Dimensionless UV radiance ratio — not a column density at all | N/A | **No change.** Concept does not apply. |

**Net effect on the v1.x roadmap.** The "Switch NO₂ to tropospheric band" line in Tier D stays. No new Tier D entries are added for the other gases. The §2.4 HCHO Q2 bullet about "tropospheric band already in use" should be made explicit in the HCHO card text on the next spec-doc bump.

### 9.2 Note on §3.4 — scrapping Sector_Match from the confidence formula

The main audit treats `Sector_Match` as a deferred-to-v1.x term namespaced in `Indicator_ID_Schema_v1.md §8`. On reconsideration this is wrong. **Sector_Match should be scrapped from the confidence formula entirely**, not deferred. The reasoning is methodological, not just operational.

**The bias mechanism.** `Sector_Match` requires user-provided sector tagging. Sector tagging will be patchy across any real supplier list — many coordinates will have no sector tag. When that happens, the Rule 1 rescale (set the term to 0, renormalise the other weights to sum to 1.0) silently encodes the assumption that "no sector data = full confidence in observation." This is not true. Two suppliers with identical satellite signals would then get different confidence scores purely because one has metadata completeness and the other doesn't. That is a metadata-completeness bias, not a data-quality judgement.

**Why this is different from High_GWP_Sector_Risk.** `High_GWP_Sector_Risk` is an additive upward correction on the score — it represents "the satellites are blind to your sector's dominant gases, so we add prior-information risk." Absence means "we add nothing," which is the correct conservative default. The Rule 1 rescale works cleanly here. By contrast, `Sector_Match` is a *cross-checking* term: it compares prior (sector) against observation (satellite signal). Absence of the prior means the cross-check cannot run; there is no clean default value, because zero implies "low consistency" and one implies "high consistency" and neither is true when the input is missing.

**General principle.** Any confidence-formula term that requires user-supplied metadata of variable completeness will introduce metadata-driven variance into the confidence score. Such terms should not live in the confidence arithmetic. They can fire as **standalone flags in provenance** without the arithmetic problem. Terms that depend on data the tool always produces itself (valid-pixel coverage, QA flags, BLH from ERA5) are safe in the confidence formula because the inputs are universally available.

**Concrete v1.x action.**

1. **Remove `Sector_Match` from `GHG_Data_Quality_Attribution` entirely.** Redistribute the 0.10 weight across the remaining five terms, post-Tier-C wind (so wind is live):

| Sub-score | Original weight | After scrap-and-redistribute |
|---|---|---|
| `Temporal_Coverage` | 0.25 | 0.28 |
| `Spatial_Resolution_Suitability` | 0.20 | 0.22 |
| `Retrieval_or_Inventory_Quality` | 0.20 | 0.22 |
| `Wind_Consistency` | 0.15 | 0.17 |
| `Nearby_Source_Isolation` | 0.10 | 0.11 |
| `Sector_Match` | 0.10 | — (removed) |
| **Total** | **1.00** | **1.00** |

2. **Remove `ghg.sector_match` from `Indicator_ID_Schema_v1.md §8`.** Make it explicit that this indicator ID has been deprecated pre-implementation.

3. **Update `Verbal_Summary_Templates_v1.md §5.2`** to drop the `Sector_Match` row from the GHG limiting-factor lookup.

4. **Add a standalone "sector-signal anomaly" flag in provenance** that fires only when both (a) the supplier has a sector tag and (b) the satellite signal is inconsistent with the tag (e.g. a software-tagged supplier showing heavy-industry NO₂ + SO₂ + CO signatures). The flag is informational — it does not enter any score or confidence arithmetic. Suppliers without sector tags simply don't generate the flag, so there is no metadata-completeness bias.

5. **Keep `High_GWP_Sector_Risk`** in `Core_GHG_Audit_Support`. The reasoning above shows why this term is not affected by the same critique.

**Implication for Tier C.** Tier C2 ("Sector input plumbing") shrinks. It still unlocks `ghg.high_gwp_sector_risk` and `nature.buffer_sensitivity`, plus enables the new standalone sector-signal anomaly flag. It no longer unlocks `ghg.sector_match` (deprecated). Update the Tier C2 description accordingly when the next planning cycle starts.

### 9.3 Note on §4.4 — demote Hansen from the live Habitat_Conversion composite

The main audit (§4.4) treats Hansen forest loss as a live contributor to `Habitat_Conversion` with a 0.10 weight. Earlier follow-up work (§9.3 v1.2 / v1.3) attempted to reconcile Hansen's annual cadence with the engine's 90-day default via a Strategy B / C switch. **v1.4 supersedes that approach: Hansen is demoted from the live composite entirely**, by direct analogy with the M5.5b demotion of ODIAC in the GHG pillar.

**Why this is the right move.** Three problems collapse at once:

1. **Temporal-mismatch problem.** Hansen's annual cadence required engine logic to decide when to use a windowed sum versus a standing cumulative. Once Hansen leaves the live composite, that decision goes away — the live composite has no Hansen to reconcile.
2. **Plantation-cycle false positives.** Hansen's known weakness in rubber / palm / managed-timber regions (where harvest cycles register as "loss") would have driven false elevated scores for suppliers in Southeast Asia, West Africa, and parts of South America. Demotion contains this — Hansen is reframed as cumulative historical context, where plantation cycles are honest as "regional turnover" rather than dishonest as "current deforestation."
3. **Most-recent-year noise.** The 2024 release's least-reliable year (2024 itself) contributed disproportionately under the B/C switch logic. Cumulative 5-year averaging dilutes this naturally without engine workarounds.

**The methodological symmetry with ODIAC.** M5.5b demoted ODIAC because its 2+ year vintage couldn't drive a "live" signal honestly; ODIAC survives as standing exposure context with `temporal_mode = "standing_exposure"`. Hansen is demoted for an analogous reason — its annual cadence can't drive a live-window signal honestly — and survives identically. Treating Hansen and ODIAC symmetrically across pillars makes the tool's design easier to explain.

**What Hansen continues to do post-demotion.** Two things, both well-scoped:

1. **Standing-reference layer in the Nature pillar.** Available alongside the live results, presented with `data_type = "reference_dataset"` and `temporal_mode = "standing_exposure"` provenance. Same UI treatment as ODIAC post-M5.5b: a value, no separate temporal-window label on the card. Surfaces in the Indicator Library (P-09) with the cumulative loss footprint and the Hansen vintage used.
2. **`regional_loss_evidence` input inside `External_Driver_Screening`.** This is the strongest use of Hansen — the buffer-vs-ring comparison is internally consistent because both sides use the same Hansen window. Hansen's annual cadence is a strength here (stable, consistent) rather than a liability.

**v1.x UI treatment (M-UI-A6, 28 May 2026).** The standing-reference role above is now realised in the P-05 drill-down (C5) as a dedicated "Reference datasets" sub-section, applied **symmetrically to Hansen and ODIAC** (the M5.5b ODIAC demotion gets the same surface). Each is shown as a muted card — cumulative loss % (Hansen) or annual emissions intensity (ODIAC), plus vintage and source — carrying the badge "Reference dataset — not used in composite score", with no severity reading and no confidence dot. The cards link to the P-09 Indicator Library entry; the Hansen card's footnote names its `regional_loss_evidence` contribution explicitly. M-UI-A6 itself changed **UI only** — vintage is derived in the UI from existing provenance (Hansen from the asset_id year, ODIAC from the coverage window), no engine field added. See `M-UI-A6_closed_entry.md`. The headline-grid removal that precedes this is M-UI-A4 v1.1.

**Engine reconciliation (M-V1x-STANDING-WINDOW, 28 May 2026).** A follow-up that brings the engine into line with the standing-exposure intent above. Previously `compute_forest_loss` masked Hansen `lossyear` to the **user's analysis window**, and `compute_co2_snapshot` filtered ODIAC to the user's window (with `run_pillar` skipping ODIAC entirely when out of coverage). For any present-day window that meant Hansen reported 0 (the latest Hansen loss year is 2023; a 2026 window masks to a year with no data) and ODIAC was always skipped — the opposite of "latest available standing exposure." The engine now reads both from **fixed windows independent of the analysis window**: Hansen over the most recent `HANSEN_LOOKBACK_YEARS` loss years (2019–2023), matching `compute_regional_loss_evidence`; ODIAC over its latest coverage year (2023). This is the §9.3-lines-982/1002 behaviour, now implemented rather than aspirational. **Consequence:** demo saved-analysis fixtures (`demo/saved_analyses/*.json`) were regenerated against live Earth Engine on 28 May 2026 — they now carry real standing-exposure values (e.g. Sapezal: Hansen 0.13% / 9.96 ha cumulative, ODIAC 48 t CO₂ yr⁻¹ per pixel; Brasília: Hansen 0.56% / 3243 ha, ODIAC 1888) instead of the old window-bounded `forest_loss.pct = 0` / `co2.mean = None`. The regen also refreshed `ghg.viirs.z` (M-UI-A4 emitted-set addition), so VIIRS now classifies normally rather than as a stale-fixture failure.

**`regional_loss_evidence` spec post-demotion.**

```
hansen_lookback_years = most recent 5 available Hansen loss years
                        (e.g. 2020-2024 with the Hansen 2024 release)

buffer_loss_rate = sum(hansen[y] in Site_Buffer for y in lookback) / area_buffer
ring_loss_rate   = sum(hansen[y] in Background_Ring for y in lookback) / area_ring

regional_loss_evidence = 1.0 if ring_loss_rate > 2 × buffer_loss_rate else 0.0
```

The 5-year lookback is fixed, independent of the user's analysis window. Both sides use the same years. The `2×` threshold from `Indicators_Computation_v3.md §7.5` is preserved. No B/C switch needed; no `hansen_mode` provenance needed.

**Habitat_Conversion redistribution.** The 0.10 weight previously on `Forest_Loss_%` redistributes proportionally across the four remaining (Dynamic World-based) terms:

| Term | v1 weight | Post-demotion weight |
|---|---|---|
| `Natural_Habitat_Loss_%` | 0.35 | 0.40 |
| `Natural_to_Built_%` | 0.25 | 0.27 |
| `Natural_to_Bare_%` | 0.20 | 0.22 |
| `Forest_Loss_%` | 0.10 | — (removed) |
| `Annualised_Conversion_Rate` | 0.10 | 0.11 |
| **Total** | **1.00** | **1.00** |

The relative emphasis is preserved (natural-loss dominant, rate term small). Detection of deforestation events is not lost — Dynamic World's `trees` class captures it via the natural-loss and forest-related contributions, at finer spatial resolution (10 m) and with more recent updates.

**Concrete v1.x changes.**

1. **Remove Hansen from `Habitat_Conversion`**; apply the redistributed weights above. Update the formula in `Indicators_Computation_v3.md §3.3` and the matching reference in `Indicators Full Research.pdf` / `Final Indicators List.pdf` summary.
2. **Tag Hansen with `temporal_mode = "standing_exposure"` and `data_type = "reference_dataset"`** in provenance, mirroring ODIAC's post-M5.5b treatment.
3. **`regional_loss_evidence` uses a fixed 5-year Hansen lookback always.** No B/C switch logic, no `hansen_mode` provenance field, no partial-year-attribution caveats.
4. **Standing reference layer in Indicator Library (P-09).** Hansen card displays cumulative loss across the lookback, vintage name, lookback span. No separate temporal label needed because the framing makes the standing-exposure mode self-evident.
5. **Verbal summary integration.** When a supplier scores high on both `nature.habitat.*` (live, DW-driven) and Hansen's standing cumulative loss is also high, the template can honestly note "Dynamic World shows recent habitat conversion in the analysis window, and Hansen records sustained forest-loss context in the surrounding region over the most recent 5 years — two independent signals agreeing across cadences."
6. **Plantation-cycle caveat is now low-stakes.** Because Hansen no longer drives the live score, plantation-region false positives don't materially affect ranking. The caveat can be documented in the Indicator Library card text without further engine work.

**What the `temporal_mode` framework still does.** The `live_window` vs `standing_exposure` distinction remains valid as a provenance concept. ODIAC and Hansen are the two v1 members of `standing_exposure`; everything else is `live_window`. The framework absorbs future mixed-cadence datasets cleanly without UI changes.

**Effort estimate.** Smaller than the B/C switch approach. Formula updates in three spec docs + weight constant change + `regional_loss_evidence` simplification + Indicator Library P-09 card text + provenance tagging. ~1-2 days of engine + spec sync. No wireframe changes.

**What this does NOT do.** It does not scrap Hansen. The cross-validation, External_Driver_Screening, and standing-reference roles all survive. The change is narrowly scoped to removing Hansen from the live composite.

---

*Document version 1.5 — May 2026. Anchored to `Indicators_Computation_v3.md`, `Indicator_ID_Schema_v1.md`, `GEE_Database_List_v3.md`, `Engine_Module_Skeleton_v1.md`, `Indicators_Full_Research.pdf`, `Inspection.js`, `AirQuality.js`, and the uploaded `v1x_followups.md`. v1.1 added §1.5 (column-vs-surface concentration framing) and expanded Tier C1 into C1a / C1b / C1c with per-gas wind sensitivity detail. v1.2 appended §9 follow-up notes: §9.1 narrows the tropospheric-band switch to NO₂ only and confirms HCHO is already correct; §9.2 scraps Sector_Match from the confidence formula on metadata-bias grounds and replaces it with a standalone provenance flag. v1.3 revised §9.3 (B/C switch logic, Strategy A dropped). v1.4 superseded v1.3 §9.3 with a Hansen demotion approach by analogy with the M5.5b ODIAC demotion. **v1.5 sweeps the document for formula consistency**: §0.5 (formula notation guide) added; §3.4 (GHG pillar aggregates) rewritten with Reference / Live v1 / Post-v1.x three-state pattern and a correction note on the prior `1/0.85` rescaling error; §4.8 (Nature pillar aggregates) likewise expanded with reference + v1 + post-v1.4 forms; §4.3 and §4.4 updated to reflect Hansen demotion; Tier C2 corrected to remove `ghg.sector_match` from the unlocking list; §1.4 spec-doc-drift expanded with the formula corrections and the three new provenance fields v1.x adds. Treat as a working scoping document, not a spec doc — when items here land, the canonical spec docs absorb the changes.*
