# GSCO Environmental Tool — Indicator Provenance Schema (v15-field, M-V1x-RECONCILE)

**Purpose.** Every single-value indicator the engine computes emits a
`_provenance.<pillar>.<indicator>` block alongside its measurement values.
The block records *where the number came from* — which asset, which data
class, which time window, which observations were actually used, and the
v1.x epistemic tags (column-to-surface uncertainty, temporal mode,
sector-signal anomaly). This is the audit trail a reviewer reads to
decide whether a screening result is defensible.

**Authority.** This document is the canonical reference for the provenance
shape. It is consumed by:

- `engine/core/provenance.py::build_provenance` — the constructor, which
  validates against this schema at construction time.
- Per-pillar `compute_*_snapshot` functions in `engine/air.py`,
  `engine/ghg.py`, and `engine/nature.py`.
- P-05+ and P-11 UI — render provenance under the "where this number came
  from" panel and per-indicator audit lines.
- Offline validation scripts.

**Stability.** Adding a new field requires a doc update here, a schema
update in `engine/core/provenance.py`, and migration of every pillar's
call site. Adding a new value to any of the validated enums
(`_ALLOWED_DATA_TYPES`, `_ALLOWED_OBSERVATION_UNITS`,
`_ALLOWED_COLUMN_TO_SURFACE_UNCERTAINTY`, `_ALLOWED_TEMPORAL_MODES`)
requires updating the enum and this doc's reference tables.

---

## 1. The 15 canonical fields

Every provenance block carries these fields, in this order. Insertion order
is stable in Python 3.7+; downstream renderers rely on it. Eleven fields
trace back to M5.6; four (`indicator_id`, `column_to_surface_uncertainty`,
`temporal_mode`, `sector_signal_anomaly`) were added by M-V1x-RECONCILE
per `Indicators_Audit_and_v1x_Roadmap.md` §1.5 / §9.2 / §9.3.

| # | Field | Type | Required | Source | Description |
|---|---|---|---|---|---|
| 1 | `indicator_id` | `str` | yes | v1.x | Self-describing pillar.indicator key (e.g. `"air.no2"`, `"nature.regional_loss_evidence"`). Drives lookup-table defaults for `column_to_surface_uncertainty` and `temporal_mode`. |
| 2 | `asset_id` | `str` | yes | M5.6 | The EE asset ID (or external dataset path). |
| 3 | `band` | `str \| None` | yes | M5.6 | The band selected from the asset. `None` for vector / non-banded assets (e.g. KBA). |
| 4 | `data_type` | `str` (enum) | yes | M5.6 | One of the five categories in §2. |
| 5 | `data_source` | `str` | yes | M5.6 | Human-readable label, e.g. "Copernicus / ESA (Sentinel-5P TROPOMI)". |
| 6 | `native_scale_m` | `float` | yes | M5.6 | Asset's native pixel resolution in metres. 0 for vector data. |
| 7 | `method_note` | `str \| None` | yes | M5.6 | One-line free-text explanation of any per-indicator processing (PM modelled vs measured, CO₂ allocation method, etc). `None` when nothing notable. |
| 8 | `time_range` | `tuple[str, str]` | yes | M5.6 | The user-requested ISO date window. For static reference data (KBA), the sentinel `("static", "static")` is used. For standing-exposure indicators (Hansen via `regional_loss_evidence`), the fixed Hansen window. |
| 9 | `coverage_window` | `tuple[str, str] \| None` | yes | M5.6 | The asset's known data-availability window. `None` for indicators still actively updated (CH₄, VIIRS, MODIS). ODIAC carries `("2020-01-01", "2023-12-31")`. |
| 10 | `skipped_reason` | `str \| None` | yes | M5.6 | See §3 for the enumerated codes; `null` on the normal path. |
| 11 | `observations` | `{"count": int, "unit": str} \| None` | yes | M5.6 | How many of the asset's images / grids / composites were actually used. `None` when v1 doesn't track the count. See §4 for allowed `unit` values. |
| 12 | `column_to_surface_uncertainty` | `str` (enum) | yes | v1.x | One of `strong`, `moderate`, `moderate_weak`, `weak`, `n_a`. Auto-looked-up from `indicator_id` against the audit §1.5 per-gas table; explicit override allowed. See §5. |
| 13 | `temporal_mode` | `str` (enum) | yes | v1.x | `live_window` (reflects user's analysis window) or `standing_exposure` (cumulative / fixed-vintage; ODIAC, Hansen). Auto-looked-up by `indicator_id`. See §6. |
| 14 | `sector_signal_anomaly` | `bool \| None` | yes | v1.x | Always `null` in v1. Lights up with Tier C2 sector plumbing per audit §9.2 — fires only when (a) the supplier carries a sector tag AND (b) the satellite signal is inconsistent with the tag. Suppliers without sector tags generate `null`, preserving the metadata-bias rule. |
| 15 | `extra` | `dict[str, Any]` | yes | M5.6 | Indicator-specific overflow — see §7 escape-hatch policy. Always a dict (defaults to `{}`). |

---

## 2. The five `data_type` values

A reviewer reading provenance should understand from this tag alone how
much weight to give the value:

| `data_type` | Meaning | Example v1 indicators |
|---|---|---|
| `satellite_observation` | Direct atmospheric / radiance retrieval. Closest to "ground truth". | All seven Sentinel-5P pollutants (`air.no2 / so2 / co / hcho / o3 / aai`), `air.aod` (MODIS MAIAC), `ghg.ch4`, `ghg.viirs`, `nature.ndvi`, `nature.recovery` |
| `ml_classified_satellite` | Satellite imagery passed through an ML classification. Documented confusion matrices apply. | `nature.dw`, `nature.habitat`, `nature.water` (all Dynamic World) |
| `gridded_model_output` | Atmospheric / earth-system model output, **not** a direct measurement. Reviewers should know they're reading a model. | `air.pm25`, `air.pm10` (ECMWF CAMS) |
| `emissions_inventory_allocation` | Statistical totals down-scaled to a grid. Modelled allocation, not measured. | `ghg.co2` (ODIAC) |
| `reference_dataset` | Curated polygons / lookup data with no inference step. Authoritative but static. | `nature.kba` (BirdLife KBA), `nature.forest_loss` (Hansen post-demotion per audit §9.3), `nature.regional_loss_evidence` |

**Hansen's reclassification.** M-V1x-RECONCILE moved `nature.forest_loss`
from `ml_classified_satellite` to `reference_dataset` to match its
post-demotion treatment as a standing-exposure layer. It no longer
participates in live-window aggregates; the `reference_dataset` tag
tells reviewers to read it as standing context rather than live signal.

---

## 3. `skipped_reason` enumeration

`skipped_reason` is `null` on the normal path. When the engine silently
skips an indicator (out of coverage, no usable pixels, etc.) it
populates this field with one of the codes below. `engine.e1_reason`
maps these to user-readable text for the C9 partial banner and the C4b
failed-tile detail.

| Code | Meaning |
|---|---|
| `null` | Indicator computed successfully |
| `out_of_coverage` | User's `time_range` doesn't overlap the asset's `coverage_window` (ODIAC). |
| `background_ring_no_data` | Background ring overlaps ocean / lacks usable pixels. |
| `no_<asset>_pixels` | Site buffer has zero valid pixels after QA filtering. `<asset>` is `s5p`, `cams`, `maiac`, `viirs`, `odiac`, `dw`, or `hansen`. |
| `no_data_at_all` | All indicator inputs returned empty — AOI may be over water or outside coverage. |

---

## 4. The five `observations.unit` values

Required when `observations` is set. Reviewers shouldn't have to guess what
`count=3` means.

| `unit` | When to use |
|---|---|
| `daily_images` | Per-day retrievals (S5P, CAMS NRT, VIIRS, MODIS MAIAC daily granules). |
| `monthly_grids` | Monthly composites — ODIAC publishes monthly grids. |
| `annual_rasters` | Annual data — Hansen forest loss, `regional_loss_evidence`. |
| `16day_composites` | MODIS 16-day NDVI composites (MOD13Q1). |
| `static_snapshot` | Reference data with no time dimension — KBA polygons. Count is conceptually 1. |

---

## 5. The five `column_to_surface_uncertainty` values

Audit §1.5 / IC_v4 §1.5: TROPOMI measures total column density, not
surface concentration. The mapping is gas-dependent and is what this
tag captures. Auto-looked-up by `indicator_id`; non-column / non-air
indicators all default to `n_a`.

| Value | Meaning | Default for |
|---|---|---|
| `strong` | Reserved for future use; no v1 indicator carries this tag. | — |
| `moderate` | Short lifetime, most of column near surface, well-understood retrieval. | `air.no2`, `air.hcho` |
| `moderate_weak` | OK for near-source plumes; degrades quickly for aged / transported air masses. | `air.so2` |
| `weak` | Long lifetime; column dominated by background; supplier attribution loose. | `air.co`, `ghg.ch4` |
| `n_a` | Not a column retrieval, or framed as context (O₃ cap). | `air.o3`, `air.aai`, all `nature.*`, all `air.pm*` / `air.aod`, `ghg.co2` (inventory), `ghg.viirs` (radiance) |

The per-gas lookup table lives in
`engine/core/provenance.py::_COLUMN_TO_SURFACE_UNCERTAINTY`.

---

## 6. The two `temporal_mode` values

Audit §9.3: indicators either reflect the user's analysis window
(`live_window`) or describe a cumulative / fixed-vintage state
independent of the window (`standing_exposure`). Auto-looked-up by
`indicator_id`.

| Value | Meaning | Indicators in v1 |
|---|---|---|
| `live_window` | The numbers in the payload reflect the user's analysis time_range — they would change if the user picked a different window. | All `air.*`, `ghg.ch4`, `ghg.viirs`, `nature.kba`, `nature.dw`, `nature.habitat`, `nature.ndvi`, `nature.water`, `nature.recovery` |
| `standing_exposure` | Cumulative or fixed-vintage state. Re-running with a different time_range does not change the result. | `ghg.co2` (ODIAC 2020–2023 inventory), `nature.forest_loss` (Hansen cumulative since 2000), `nature.regional_loss_evidence` (fixed 5-year Hansen lookback) |

The standing-exposure lookup table lives in
`engine/core/provenance.py::_TEMPORAL_MODE`.

---

## 7. The `extra` escape hatch

`extra` exists for genuinely indicator-specific fields that don't fit any
canonical slot. Rules:

1. **Default to canonical fields first.** If a piece of information fits a
   canonical field (e.g. a calibration factor → `method_note`; a
   time-window → `time_range`), put it there. The canonical schema gets the
   benefit of strict validation and uniform UI rendering.
2. **Put genuinely indicator-specific info in `extra`.** Examples in v1:
   - `air.aod`: `{"aod_qa_bit_mask": "0xF00"}`
   - `air.pm25 / pm10`: `{"cams_min_valid_pct": 0.5}`
   - `ghg.co2`: `{"c_to_co2_factor": 3.667}`
   - `nature.kba`: `{"distance_decay_km": 10.0}`
   - `nature.habitat`: `{"baseline_time_range": (...), "baseline_years": 5, "conversion_saturation_pct": 0.10}`
   - `nature.ndvi`: `{"ndvi_negative_trend_threshold": -0.01}`
   - `nature.dw`: `{"composite_window_days": 90}`
   - `nature.regional_loss_evidence`: `{"buffer_loss_rate_m2_per_m2": ..., "ring_loss_rate_m2_per_m2": ..., "lookback_years": 5, "ratio_threshold": 2.0, "hansen_max_loss_year": 23}`
3. **Don't accumulate cruft.** If three or more indicators need the same
   `extra` key, promote it to a canonical field (doc update + schema update
   + migration).

---

## 8. Migration history

- **Pre-M5.6**: each pillar emitted ad-hoc provenance blocks of varying
  shape. Air had `{asset_id, time_range}`. GHG CO₂ had a rich custom block
  with `n_months`, `c_to_co2_factor`, `role_in_pillar`, etc. Nature
  indicators each had bespoke fields. Reviewer-facing UI would have needed
  a switch statement per indicator.
- **M5.6**: unified the shape under `build_provenance` (11 fields). The
  M5.5b-introduced `role_in_pillar` field on `ghg.co2` was dropped — its
  semantic content is now carried by `data_type`
  (`emissions_inventory_allocation` makes it obvious the value isn't a
  measurement). ODIAC's `n_months` moved into `observations.count` with
  unit `monthly_grids`; its `c_to_co2_factor` moved into `extra`.
- **M-V1x-RECONCILE (22 May 2026)**: expanded to 15 fields. Added
  `indicator_id` (self-describing pillar.indicator key, drives lookup-table
  defaults), `column_to_surface_uncertainty` (audit §1.5), `temporal_mode`
  (audit §9.3), `sector_signal_anomaly` (audit §9.2; v1 emits `null`,
  Tier C2 lights it up). Two new enums introduced
  (`_ALLOWED_COLUMN_TO_SURFACE_UNCERTAINTY`, `_ALLOWED_TEMPORAL_MODES`);
  two new lookup tables map `indicator_id` to per-indicator defaults.
  Hansen reclassified from `ml_classified_satellite` to `reference_dataset`
  per audit §9.3 v1.4.

---

## 9. Adding a new indicator

When you add a new single-value indicator to any pillar:

1. Set `data_type`, `data_source`, and (if non-default) `temporal_mode`
   on the indicator's config dataclass.
2. In the snapshot function, construct provenance via
   `engine.core.build_provenance(...)`, passing `indicator_id="<pillar>.<indicator>"`.
   **Do not write provenance dicts inline** — that bypasses schema
   validation.
3. If your indicator carries a non-default column-to-surface uncertainty,
   add its `indicator_id → uncertainty` mapping to the lookup table in
   `engine/core/provenance.py::_COLUMN_TO_SURFACE_UNCERTAINTY`. (The
   default is `n_a` — fine for almost all non-column-retrieval indicators.)
4. If your indicator has a finite data-availability window, set
   `coverage_window` on the config. `run_pillar`'s coverage check
   (`_time_range_in_coverage`) will pick it up automatically and skip the
   indicator silently when the user's `time_range` falls outside.
5. If the v1 code doesn't track the actual number of observations used,
   pass `observations=None` and leave a `TODO(v1.x)` comment.
6. Add a row to the per-pillar `TestProvenanceShape` parametrised tests
   in `tests/test_<pillar>.py`, and check `tests/test_provenance_shape.py`
   still passes (it walks every indicator in a real run and asserts the
   15-field shape).

---

*Document version 2.0 — M-V1x-RECONCILE (2026-05-22). Anchored to
`engine/core/provenance.py`.*
