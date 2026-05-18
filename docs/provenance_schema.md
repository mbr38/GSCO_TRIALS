# GSCO Environmental Tool — Indicator Provenance Schema (M5.6)

**Purpose.** Every single-value indicator the engine computes emits a
`_provenance.<pillar>.<indicator>` block alongside its measurement values.
The block records *where the number came from* — which asset, which data
class, which time window, which observations were actually used. This is the
audit trail a reviewer reads to decide whether a screening result is
defensible.

**Authority.** This document is the canonical reference for the provenance
shape. It is consumed by:

- `engine/core/provenance.py::build_provenance` — the constructor, which
  validates against this schema at construction time.
- Per-pillar `compute_*_snapshot` functions in `engine/air.py`,
  `engine/ghg.py`, and `engine/nature.py`.
- P-05+ UI (forthcoming) — renders provenance under "where this number came
  from" panels.
- Offline validation scripts.

**Stability.** The schema is fixed in v1. Adding a new field requires a doc
update here, a schema update in `engine/core/provenance.py`, and migration
of every pillar's call site. Adding a new `data_type` or `observations.unit`
value requires updating `_ALLOWED_DATA_TYPES` / `_ALLOWED_OBSERVATION_UNITS`
and this doc's reference tables.

---

## 1. The 11 canonical fields

Every provenance block carries these fields, in this order. Insertion order
is stable in Python 3.7+; downstream renderers rely on it.

| # | Field | Type | Required | Description |
|---|---|---|---|---|
| 1 | `asset_id` | `str` | yes | The EE asset ID (or external dataset path). |
| 2 | `band` | `str \| None` | yes | The band selected from the asset. `None` for vector / non-banded assets (e.g. KBA). |
| 3 | `data_type` | `str` (enum) | yes | One of the five categories in §2. |
| 4 | `data_source` | `str` | yes | Human-readable label, e.g. "Copernicus / ESA (Sentinel-5P TROPOMI)". |
| 5 | `native_scale_m` | `float` | yes | Asset's native pixel resolution in metres. 0 for vector data. |
| 6 | `method_note` | `str \| None` | yes | One-line free-text explanation of any per-indicator processing (PM modelled vs measured, CO₂ allocation method, etc). `None` when nothing notable. |
| 7 | `time_range` | `tuple[str, str]` | yes | The user-requested ISO date window. For static reference data (KBA), the sentinel `("static", "static")` is used when no real window is meaningful. |
| 8 | `coverage_window` | `tuple[str, str] \| None` | yes | The asset's known data-availability window. `None` for indicators still actively updated (CH₄, VIIRS, MODIS). ODIAC carries `("2020-01-01", "2023-12-31")`. |
| 9 | `skipped_reason` | `str \| None` | yes | `"out_of_coverage"` when the dispatcher silently skipped this indicator (M5.5c); `None` on the normal path. |
| 10 | `observations` | `{"count": int, "unit": str} \| None` | yes | How many of the asset's images / grids / composites were actually used. `None` when v1 doesn't track the count. See §3 for allowed `unit` values. |
| 11 | `extra` | `dict[str, Any]` | yes | Indicator-specific overflow — see §4 escape-hatch policy. Always a dict (defaults to `{}`). |

---

## 2. The five `data_type` values

A reviewer reading provenance should understand from this tag alone how
much weight to give the value:

| `data_type` | Meaning | Example v1 indicators |
|---|---|---|
| `satellite_observation` | Direct atmospheric / radiance retrieval. Closest to "ground truth". | All seven Sentinel-5P pollutants (`air.no2 / so2 / co / hcho / o3 / aai`), `air.aod` (MODIS MAIAC), `ghg.ch4`, `ghg.viirs`, `nature.ndvi`, `nature.recovery` |
| `ml_classified_satellite` | Satellite imagery passed through an ML classification. Documented confusion matrices apply. | `nature.dw`, `nature.habitat`, `nature.water` (all Dynamic World); `nature.forest_loss` (Hansen) |
| `gridded_model_output` | Atmospheric / earth-system model output, **not** a direct measurement. Reviewers should know they're reading a model. | `air.pm25`, `air.pm10` (ECMWF CAMS) |
| `emissions_inventory_allocation` | Statistical totals down-scaled to a grid. Modelled allocation, not measured. | `ghg.co2` (ODIAC) |
| `reference_dataset` | Curated polygons / lookup data with no inference step. Authoritative but static. | `nature.kba` (BirdLife KBA) |

---

## 3. The five `observations.unit` values

Required when `observations` is set. Reviewers shouldn't have to guess what
`count=3` means.

| `unit` | When to use |
|---|---|
| `daily_images` | Per-day retrievals (S5P, CAMS NRT, VIIRS, MODIS MAIAC daily granules). |
| `monthly_grids` | Monthly composites — ODIAC publishes monthly grids. |
| `annual_rasters` | Annual data — Hansen forest loss. |
| `16day_composites` | MODIS 16-day NDVI composites (MOD13Q1). |
| `static_snapshot` | Reference data with no time dimension — KBA polygons. Count is conceptually 1. |

---

## 4. The `extra` escape hatch

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
3. **Don't accumulate cruft.** If three or more indicators need the same
   `extra` key, promote it to a canonical field (doc update + schema update
   + migration).

---

## 5. Migration history

- **Pre-M5.6**: each pillar emitted ad-hoc provenance blocks of varying
  shape. Air had `{asset_id, time_range}`. GHG CO₂ had a rich custom block
  with `n_months`, `c_to_co2_factor`, `role_in_pillar`, etc. Nature
  indicators each had bespoke fields. Reviewer-facing UI would have needed
  a switch statement per indicator.
- **M5.6**: unified the shape under `build_provenance`. The
  M5.5b-introduced `role_in_pillar` field on `ghg.co2` was dropped — its
  semantic content is now carried by `data_type`
  (`emissions_inventory_allocation` makes it obvious the value isn't a
  measurement). ODIAC's `n_months` moved into `observations.count` with
  unit `monthly_grids`; its `c_to_co2_factor` moved into `extra`. No
  information loss.

---

## 6. Adding a new indicator

When you add a new single-value indicator to any pillar:

1. Set `data_type` and `data_source` on the indicator's config dataclass.
2. In the snapshot function, construct provenance via
   `engine.core.build_provenance(...)`. **Do not write provenance dicts
   inline** — that bypasses the schema validation.
3. If your indicator has a finite data-availability window, set
   `coverage_window` on the config. `run_pillar`'s coverage check
   (`_time_range_in_coverage`) will pick it up automatically and skip the
   indicator silently when the user's `time_range` falls outside.
4. If the v1 code doesn't track the actual number of observations used,
   pass `observations=None` and leave a `TODO(v1.x)` comment.
5. Add a row to the per-pillar `TestProvenanceShape` parametrised tests
   in `tests/test_<pillar>.py`.

---

*Document version 1.0 — M5.6 (2026-05-18). Anchored to
`engine/core/provenance.py`.*
