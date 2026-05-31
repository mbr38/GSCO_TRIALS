# M-PERF-A1 — Profiling report (Step A output)

*Captured 2026-05-31T17:11:38.991901+00:00 via `tools/m_perf_a1_profile.py`.*

## 1. Coverage

| AOI | Centre | Radius | Wall time | getInfo calls | Failures |
|---|---|---|---:|---:|---:|
| Sapezal 5 km (small inland) | (-13.5417, -58.7642) | 5.0 km | 94.7 s | 110 | 0 |
| Distrito Federal 43.1 km (large) | (-15.7808, -47.7968) | 43.1 km | 90.3 s | 108 | 0 |
| Rio de Janeiro coastal 20 km (M-TIER-A3 land mask) | (-22.9068, -43.1729) | 20.0 km | 250.1 s | 110 | 0 |

Spec PF16 named four behavioural corners (Sapezal, DF, coastal, cloudy). The cloudy/sparse AOI is omitted from this pass because M-FALLBACK-A1's climatology fallback path is not yet operational; re-add it once that milestone lands.

## 2. Top offenders — aggregate getInfo count across AOIs

| Rank | Module | Function | Total | Total seconds | sapezal_5km | distrito_federal_43_1km | rio_coastal_20km |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | `engine.air` | `compute_pollutant_snapshot` | 136 | 535.6 | 46 | 44 | 46 |
| 2 | `engine.core.repeatable_core` | `_process_chunk_for_server_side_hf` | 54 | 81.3 | 18 | 18 | 18 |
| 3 | `engine.ghg` | `compute_ghg_indicator_snapshot` | 36 | 34.5 | 12 | 12 | 12 |
| 4 | `engine.nature` | `compute_ndvi_condition` | 18 | 12.4 | 6 | 6 | 6 |
| 5 | `engine.nature` | `compute_regional_loss_evidence` | 15 | 8.7 | 5 | 5 | 5 |
| 6 | `engine.nature` | `_dw_mode_histogram` | 12 | 9.2 | 4 | 4 | 4 |
| 7 | `engine.nature` | `compute_current_land_cover` | 9 | 17.2 | 3 | 3 | 3 |
| 8 | `engine.nature` | `compute_kba_proximity` | 9 | 5.3 | 3 | 3 | 3 |
| 9 | `engine.nature` | `compute_supplier_spatial_link` | 9 | 8.4 | 3 | 3 | 3 |
| 10 | `engine.ghg` | `compute_co2_snapshot` | 6 | 2.1 | 2 | 2 | 2 |
| 11 | `engine.ghg` | `compute_viirs_sustained_contrast` | 6 | 235.0 | 2 | 2 | 2 |
| 12 | `engine.nature` | `compute_forest_loss` | 6 | 2.4 | 2 | 2 | 2 |
| 13 | `engine.nature` | `compute_water_exposure` | 6 | 7.8 | 2 | 2 | 2 |
| 14 | `engine.nature` | `_ndvi_low_area_pct` | 3 | 0.9 | 1 | 1 | 1 |
| 15 | `engine.nature` | `compute_habitat_conversion` | 3 | 1.0 | 1 | 1 | 1 |

## 3. Per-AOI breakdown

### Sapezal 5 km (small inland)

- Baseline fixture: `tests/baselines/m_perf_a1/sapezal_5km.json`
- Wall time: 94.7 s
- getInfo calls: 110
- Failures (retried + reraised): 0

| Module | Function | Count | Seconds | Failures |
|---|---|---:|---:|---:|
| `engine.air` | `compute_pollutant_snapshot` | 46 | 84.4 | 0 |
| `engine.core.repeatable_core` | `_process_chunk_for_server_side_hf` | 18 | 25.2 | 0 |
| `engine.ghg` | `compute_ghg_indicator_snapshot` | 12 | 6.3 | 0 |
| `engine.nature` | `compute_ndvi_condition` | 6 | 3.4 | 0 |
| `engine.nature` | `compute_regional_loss_evidence` | 5 | 2.0 | 0 |
| `engine.nature` | `_dw_mode_histogram` | 4 | 1.6 | 0 |
| `engine.nature` | `compute_current_land_cover` | 3 | 1.8 | 0 |
| `engine.nature` | `compute_kba_proximity` | 3 | 2.0 | 0 |
| `engine.nature` | `compute_supplier_spatial_link` | 3 | 1.7 | 0 |
| `engine.ghg` | `compute_co2_snapshot` | 2 | 0.5 | 0 |
| `engine.ghg` | `compute_viirs_sustained_contrast` | 2 | 62.9 | 0 |
| `engine.nature` | `compute_forest_loss` | 2 | 0.9 | 0 |
| `engine.nature` | `compute_water_exposure` | 2 | 0.7 | 0 |
| `engine.nature` | `_ndvi_low_area_pct` | 1 | 0.4 | 0 |
| `engine.nature` | `compute_habitat_conversion` | 1 | 0.5 | 0 |

### Distrito Federal 43.1 km (large)

- Baseline fixture: `tests/baselines/m_perf_a1/distrito_federal_43_1km.json`
- Wall time: 90.3 s
- getInfo calls: 108
- Failures (retried + reraised): 0

| Module | Function | Count | Seconds | Failures |
|---|---|---:|---:|---:|
| `engine.air` | `compute_pollutant_snapshot` | 44 | 83.0 | 0 |
| `engine.core.repeatable_core` | `_process_chunk_for_server_side_hf` | 18 | 21.5 | 0 |
| `engine.ghg` | `compute_ghg_indicator_snapshot` | 12 | 7.9 | 0 |
| `engine.nature` | `compute_ndvi_condition` | 6 | 3.3 | 0 |
| `engine.nature` | `compute_regional_loss_evidence` | 5 | 1.5 | 0 |
| `engine.nature` | `_dw_mode_histogram` | 4 | 1.8 | 0 |
| `engine.nature` | `compute_current_land_cover` | 3 | 2.2 | 0 |
| `engine.nature` | `compute_kba_proximity` | 3 | 1.3 | 0 |
| `engine.nature` | `compute_supplier_spatial_link` | 3 | 0.9 | 0 |
| `engine.ghg` | `compute_co2_snapshot` | 2 | 0.6 | 0 |
| `engine.ghg` | `compute_viirs_sustained_contrast` | 2 | 61.0 | 0 |
| `engine.nature` | `compute_forest_loss` | 2 | 0.5 | 0 |
| `engine.nature` | `compute_water_exposure` | 2 | 0.6 | 0 |
| `engine.nature` | `_ndvi_low_area_pct` | 1 | 0.2 | 0 |
| `engine.nature` | `compute_habitat_conversion` | 1 | 0.2 | 0 |

### Rio de Janeiro coastal 20 km (M-TIER-A3 land mask)

- Baseline fixture: `tests/baselines/m_perf_a1/rio_coastal_20km.json`
- Wall time: 250.1 s
- getInfo calls: 110
- Failures (retried + reraised): 0

| Module | Function | Count | Seconds | Failures |
|---|---|---:|---:|---:|
| `engine.air` | `compute_pollutant_snapshot` | 46 | 368.2 | 0 |
| `engine.core.repeatable_core` | `_process_chunk_for_server_side_hf` | 18 | 34.6 | 0 |
| `engine.ghg` | `compute_ghg_indicator_snapshot` | 12 | 20.3 | 0 |
| `engine.nature` | `compute_ndvi_condition` | 6 | 5.7 | 0 |
| `engine.nature` | `compute_regional_loss_evidence` | 5 | 5.2 | 0 |
| `engine.nature` | `_dw_mode_histogram` | 4 | 5.8 | 0 |
| `engine.nature` | `compute_current_land_cover` | 3 | 13.3 | 0 |
| `engine.nature` | `compute_kba_proximity` | 3 | 1.9 | 0 |
| `engine.nature` | `compute_supplier_spatial_link` | 3 | 5.8 | 0 |
| `engine.ghg` | `compute_co2_snapshot` | 2 | 1.0 | 0 |
| `engine.ghg` | `compute_viirs_sustained_contrast` | 2 | 111.1 | 0 |
| `engine.nature` | `compute_forest_loss` | 2 | 1.0 | 0 |
| `engine.nature` | `compute_water_exposure` | 2 | 6.5 | 0 |
| `engine.nature` | `_ndvi_low_area_pct` | 1 | 0.4 | 0 |
| `engine.nature` | `compute_habitat_conversion` | 1 | 0.3 | 0 |

## 4. Step B — batching candidates (to confirm)

The Step B plan picks the top N offenders from §2. Hypothesis from spec PF10 (to confirm against the table above):

- Nature's per-indicator reductions (7 main + regional_loss + spatial_link)
- The duplicate DW mode composites (habitat + spatial_link)
- Air's 9 per-pollutant six-step reductions

Each candidate should be assessed on (a) absolute count, (b) whether co-located reductions can combine into a single `ee.Dictionary`, (c) whether sharing crosses a function boundary (PF14 — pure call-consolidation only).
