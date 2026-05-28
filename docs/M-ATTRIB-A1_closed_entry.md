# M-ATTRIB-A1 — Closed entry

*Date: 28 May 2026. Branch: `m-attrib-a1`. Spec: `M-ATTRIB-A1_spec.md` v1.0.*

## Summary

Refactored the engine's attribution architecture across all three pillars to
cleanly separate **measurement quality** from **attributability**, ending the
methodological conflation that previously lived in `engine.nature`. Added a
new categorical attributability surface for habitat conversion (centroid
offset, Approach C), reframed `regional_loss_evidence` as reference data on
the M-UI-A6 Hansen card, renamed the Air and Nature measurement-quality
aggregates for honesty (with a dual-emit deprecation window for the Air ID),
and removed `nearby_source_isolation` from the GHG data-quality aggregate
(preserving the field for a future GHG attributability surface).

**Tests:** 1599 passed, 19 skipped (engine + UI). 55 new tests added across
`test_attributability.py`, `test_nature.py` (TestNatureMeasurementQuality +
TestSupplierSpatialLink), `test_pillar_confidence_rollup.py`,
`test_reference_datasets.py` (TestRegionalContextLine),
`test_habitat_attributability_ui.py`, `test_habitat_map_overlay.py`,
`test_habitat_attribution_pdf.py`, and `test_air.py` (TestMeasurementQualityRename).

## AT lock verification

- [x] **AT1.** Measurement quality and attributability separated.
  `compute_nature_measurement_quality` (renamed from
  `compute_nature_quality_attribution`) now contains measurement-quality terms
  only; `compute_supplier_spatial_link` is the categorical attributability
  surface. Regression: `tests/test_nature.py::TestNatureMeasurementQuality
  ::test_attribution_signals_not_in_aggregate`.

- [x] **AT2.** System-wide refactor confirmed. Air rename (Step C), GHG
  redirect (Step D), Nature reshape (Step E), Nature reframe (Step F), new
  attributability module (Step G) — all landed.

- [x] **AT3.** Categorical attributability per indicator implemented via
  `engine.core.attributability.compute_habitat_attributability` →
  `Literal["high","moderate","low","sparse"]`. Cite:
  [engine/core/attributability.py](engine/core/attributability.py).

- [x] **AT4.** One combined milestone — engine + UI + docs shipped together.

- [x] **AT5.** `regional_loss_evidence` reframed as reference data — emits
  `.ratio` + `.window` instead of `external_driver_screening`. Provenance.extra
  retains the raw flag for audit; `confidence_terms` removed. Cite:
  `engine.nature.compute_regional_loss_evidence`,
  `tests/test_regional_loss_evidence.py::TestRegionalLossEvidence`.

- [x] **AT6.** M-UI-A6 Hansen card regional-context line —
  `_regional_context_line(payload)` + `_ReferenceCardFields.regional_context`
  rendered between source and interpretation. Cite:
  `tests/test_reference_datasets.py::TestRegionalContextLine`.

- [x] **AT7.** Centroid-offset attributability (Approach C) implemented.
  `compute_supplier_spatial_link` builds the per-pixel DW natural→non-natural
  transition mask, computes the centroid via `pixelLonLat().updateMask`, and
  measures geodesic distance via `engine.core.attributability.haversine_km`.
  Cite: `tests/test_nature.py::TestSupplierSpatialLink`.

- [x] **AT8.** `supplier_spatial_link` is the sole attributability signal for
  habitat conversion. `regional_loss_evidence` no longer appears in the
  attributability function — it's purely reference data.

- [x] **AT9.** Map centroid marker + line rendering — `_habitat_overlay_elements`
  returns coloured `folium.Marker` + `folium.PolyLine`; high=green, moderate=amber,
  low=red, sparse=no render. Cite:
  `tests/test_habitat_map_overlay.py::TestOverlayElements`.

- [x] **AT10.** Hover tooltip on centroid — `_habitat_centroid_tooltip` text
  matches §5.2 format; folium Tooltip attached to the Marker. Cite:
  `tests/test_habitat_map_overlay.py::TestOverlayElements::test_marker_carries_hover_tooltip`.

- [x] **AT11.** C5 expander Low-only sub-section —
  `_render_habitat_attributability` opens "What's behind this attributability?"
  only when state == "low", with distance / direction / pixel count. Cite:
  `tests/test_habitat_attributability_ui.py::TestHabitatAttributabilityRows
  ::test_low_attributability_opens_expander` and
  `::test_moderate_does_not_open_low_expander`.

- [x] **AT12.** Bucket thresholds in `engine.constants` —
  `N_MIN_PIXELS_FOR_CENTROID=10`, `HABITAT_SPATIAL_LINK_HIGH_KM=1.0`,
  `HABITAT_SPATIAL_LINK_MOD_KM=3.0`. Flagged for calibration (Q-AT-1) with
  a scale-relativity note (the n_min counts pixels at the adaptive reduction
  scale, not DW's 10 m native). Boundary tests:
  `tests/test_attributability.py::TestHabitatAttributabilityBuckets`.

- [x] **AT13.** Nature aggregate renamed: `nature.quality_attribution` →
  `nature.measurement_quality`; `compute_nature_quality_attribution` →
  `compute_nature_measurement_quality`; `_FOLLOWUP_TERM_TO_ID` repointed.
  The followup-weight internal key "quality_attribution" is retained (its
  weight is unchanged per §4.1) but points at the new aggregate ID.

- [x] **AT14.** Nature weights renormalised to spec §4.2 first-pass: 0.35 /
  0.25 / 0.20 / 0.20 (sums to 1.0). Step B confirmed the renorm target after
  reconnaissance flagged that the spec's "before" values were inaccurate
  (current weights were 0.20/0.20/0.20/0.15/0.15/0.10, not the doc's
  0.30/0.20/0.20/0.20/0.10).

- [x] **AT15.** GHG `nearby_source_isolation` removed from
  `GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS`. Surviving 3 sub-scores renormalised
  to 0.34 / 0.33 / 0.33. `compute_nearby_source_isolation` still emits the
  field (reserved). Also removed from the limiting-factor prose map in
  `engine.verbal_summary` so C6 / verbal summary never name it as a
  measurement-quality limiting factor. Cite:
  `tests/test_pillar_confidence_rollup.py::TestGhgDqaSubScoreRecompute
  ::test_nearby_source_isolation_not_in_aggregate`.

- [x] **AT16.** Air renamed: `compute_attribution_confidence_score` →
  `compute_measurement_quality_score`. Dual-emit pattern in the function
  itself plus a module-level function alias for the old name. Both
  `air.measurement_quality_score` and `air.attribution_confidence_score`
  emitted with identical values for one milestone (Q-AT-3). All in-repo
  readers (orchestrator confidence ID, verbal summary, C3/C5/C6 UI,
  indicator-library manifest) migrated to the new ID. Cite:
  `tests/test_air.py::TestMeasurementQualityRename`.

- [x] **AT17.** Provenance fields are additive — all new spatial-link fields
  live in `provenance.extra.spatial_link_terms` (attributability_state,
  centroid_offset_km, centroid_lat, centroid_lon, n_change_pixels,
  n_min_pixels, direction). No top-level schema changes;
  `build_provenance(observations=None)` for the supplier_spatial_link block
  (the schema's allowed observation units are temporal — n_change_pixels
  lives in `extra` instead).

- [x] **AT18.** Strict-audit mode does not suppress attributability —
  `compute_supplier_spatial_link` runs unconditionally in `run_pillar` when
  habitat is selected, independent of any M-FALLBACK-A1 strict-audit gating
  (attributability is not measurement quality; strict-audit-mode disables
  substitution, not visual context).

- [x] **AT19.** Coordinated with M-WIND-A1 v2.0 — `ATTRIBUTABILITY_STATES`
  constant + `compass_direction` helper exposed from `engine.core.attributability`
  as the shared grammar M-WIND-A1 v2.0 will reuse. Map badge colours (green /
  amber / red) and hover-tooltip format follow the same pattern.

- [x] **AT20.** Threshold calibration flagged in code (`engine.constants`
  M-ATTRIB-A1 block) and in the closed-entry as Q-AT-1.

- [x] **AT21.** Sequenced before M-WIND-A1 v2.0. This milestone establishes
  the categorical-attributability + map-overlay pattern from scratch (the
  reconnaissance confirmed no prior hover/marker/line infrastructure existed).

- [x] **AT22.** M-UI-A6 Hansen card amended — added the regional-context
  line via `_ReferenceCardFields.regional_context`. Cite:
  `tests/test_reference_datasets.py::TestRegionalContextLine
  ::test_hansen_card_fields_carries_regional_context`.

## Step B reconciliation outcomes (locked decisions from the recon)

The Step A reconnaissance surfaced six mismatches with the spec. Each was
locked by user decision before Step C began:

1. **Centroid basis** — the per-pixel transition layer Approach C requires
   did not exist (the engine only computed buffer-level DW histograms). User
   chose to build the new EE pipeline; landed in `compute_supplier_spatial_link`.
2. **Nature renorm target** — spec §4.2 first-pass values (0.35/0.25/0.20/0.20).
3. **regional_loss_evidence in QA** — dropped entirely from
   `_NATURE_QA_INDICATOR_KEYS` (consistent with the reference-data reframing).
4. **Air dual-emit window** — 1 milestone.
5. **Map/hover infra** — confirmed built from scratch in this milestone; the
   spec's "reuse existing M-WIND-A1 v2.0 infra" framing was inverted (this
   milestone establishes; M-WIND-A1 v2.0 reuses).
6. **N_MIN scale** — flagged for calibration; spec literal value (10)
   shipped with a scale-relativity note.

## Documentation changes

Per the Step L user decision (28 May 2026): IC_v4 + Wireframes are edited;
the audit doc (`Indicators_Audit_and_v1x_Roadmap.md`) is **not** edited and
remains pending separate sign-off.

- `docs/Indicators_Computation_v4.md` — §2.3 GHG DQA 3-term formula; §3.3
  Nature_Measurement_Quality reshape + M-ATTRIB-A1 note; §7.5 reframed
  (Supplier_Spatial_Link as categorical attributability; External_Driver_Screening
  removed; regional_loss_evidence as reference ratio).
- `docs/Wireframes_All_v4.md` — C2 confidence-dot ID list updated;
  C4c map row notes the habitat attributability overlay; C5d Hansen card
  regional-context line; C5 habitat panel measurement-quality + attributability
  rows; Low expander sub-section.
- `docs/M-ATTRIB-A1_plain_language_explainer.md` — new stakeholder-facing
  explainer.
- `docs/M-ATTRIB-A1_closed_entry.md` — this file.
- **Pending separate sign-off:** `docs/Indicators_Audit_and_v1x_Roadmap.md`
  §9.3 v1.4 extension note (regional_loss_evidence reframing).
- **Pending separate sign-off:** `GSCO_v1x_TodoList.md` Path 3 entry / DONE mark.

## Follow-ups

- **Q-AT-1.** Calibration sweep for the 1 km / 3 km attributability
  thresholds and the Hansen ratio bands (< 0.5 / 0.5–2.0 / > 2.0), after
  first demo runs against Sapezal / Brasilia / a coastal AOI. The N_MIN_PIXELS
  scale-relativity (10 pixels at the adaptive scale, not native) is part of
  the same sweep.
- **C4b habitat tile.** Habitat conversion is not currently a C4b headline
  tile (the curated tile set deliberately excludes it). The map overlay
  renderer + dispatch wiring are in place, but habitat conversion is reachable
  on the map only if it becomes the active indicator via another surface.
  Adding a habitat tile is a small follow-up if reviewers want one-click
  access to the attributability overlay.
- **GHG `nearby_source_isolation` real implementation.** Reserved field;
  IC §7.2 spec is unchanged. Future attributability milestone to wire the
  satellite-only proxy.
- **Air `attribution_confidence_score` deprecation removal.** Remove the
  legacy ID emit + the `compute_attribution_confidence_score` module alias
  next milestone (1-milestone window per Q-AT-3).
- **Audit doc sync.** `Indicators_Audit_and_v1x_Roadmap.md` §9.3 needs an
  amendment note (regional_loss_evidence reframing); pending explicit
  sign-off to edit the audit doc.
