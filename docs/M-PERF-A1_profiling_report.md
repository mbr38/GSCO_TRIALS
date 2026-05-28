# M-PERF-A1 — Profiling report (Step A output)

*Captured 2026-05-28T16:17:56.195249+00:00 via `tools/m_perf_a1_profile.py`.*

## 1. Coverage

| AOI | Centre | Radius | Wall time | getInfo calls | Failures |
|---|---|---|---:|---:|---:|
| Sapezal 5 km (small inland) | (-13.5417, -58.7642) | 5.0 km | 18.9 s | 86 | 0 |
| Distrito Federal 43.1 km (large) | (-15.7808, -47.7968) | 43.1 km | 15.9 s | 86 | 0 |
| Rio de Janeiro coastal 20 km (M-TIER-A3 land mask) | (-22.9068, -43.1729) | 20.0 km | 184.7 s | 86 | 0 |

Spec PF16 named four behavioural corners (Sapezal, DF, coastal, cloudy). The cloudy/sparse AOI is omitted from this pass because M-FALLBACK-A1's climatology fallback path is not yet operational; re-add it once that milestone lands.

## 2. Top offenders — aggregate getInfo count across AOIs

| Rank | Module | Function | Total | Total seconds | sapezal_5km | distrito_federal_43_1km | rio_coastal_20km |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | `engine.air` | `compute_pollutant_snapshot` | 81 | 505.4 | 27 | 27 | 27 |
| 2 | `engine.core.ee_resilience` | `_wrapped_getInfo` | 54 | 99.6 | 18 | 18 | 18 |
| 3 | `engine.ghg` | `compute_ghg_indicator_snapshot` | 21 | 30.8 | 7 | 7 | 7 |
| 4 | `engine.ghg` | `compute_co2_snapshot` | 15 | 9.3 | 5 | 5 | 5 |
| 5 | `engine.nature` | `compute_ndvi_condition` | 15 | 12.0 | 5 | 5 | 5 |
| 6 | `engine.nature` | `compute_regional_loss_evidence` | 15 | 13.7 | 5 | 5 | 5 |
| 7 | `engine.nature` | `_dw_mode_histogram` | 12 | 12.7 | 4 | 4 | 4 |
| 8 | `engine.nature` | `compute_current_land_cover` | 9 | 20.5 | 3 | 3 | 3 |
| 9 | `engine.nature` | `compute_kba_proximity` | 9 | 6.8 | 3 | 3 | 3 |
| 10 | `engine.nature` | `compute_supplier_spatial_link` | 9 | 16.5 | 3 | 3 | 3 |
| 11 | `engine.nature` | `compute_forest_loss` | 6 | 3.6 | 2 | 2 | 2 |
| 12 | `engine.nature` | `compute_water_exposure` | 6 | 9.0 | 2 | 2 | 2 |
| 13 | `engine.nature` | `_ndvi_low_area_pct` | 3 | 1.3 | 1 | 1 | 1 |
| 14 | `engine.nature` | `compute_habitat_conversion` | 3 | 0.9 | 1 | 1 | 1 |

## 3. Per-AOI breakdown

### Sapezal 5 km (small inland)

- Baseline fixture: `tests/baselines/m_perf_a1/sapezal_5km.json`
- Wall time: 18.9 s
- getInfo calls: 86
- Failures (retried + reraised): 0

| Module | Function | Count | Seconds | Failures |
|---|---|---:|---:|---:|
| `engine.air` | `compute_pollutant_snapshot` | 27 | 43.8 | 0 |
| `engine.core.ee_resilience` | `_wrapped_getInfo` | 18 | 26.4 | 0 |
| `engine.ghg` | `compute_ghg_indicator_snapshot` | 7 | 3.7 | 0 |
| `engine.ghg` | `compute_co2_snapshot` | 5 | 2.7 | 0 |
| `engine.nature` | `compute_ndvi_condition` | 5 | 4.1 | 0 |
| `engine.nature` | `compute_regional_loss_evidence` | 5 | 3.4 | 0 |
| `engine.nature` | `_dw_mode_histogram` | 4 | 2.2 | 0 |
| `engine.nature` | `compute_current_land_cover` | 3 | 2.3 | 0 |
| `engine.nature` | `compute_kba_proximity` | 3 | 2.4 | 0 |
| `engine.nature` | `compute_supplier_spatial_link` | 3 | 1.6 | 0 |
| `engine.nature` | `compute_forest_loss` | 2 | 1.5 | 0 |
| `engine.nature` | `compute_water_exposure` | 2 | 1.5 | 0 |
| `engine.nature` | `_ndvi_low_area_pct` | 1 | 0.8 | 0 |
| `engine.nature` | `compute_habitat_conversion` | 1 | 0.4 | 0 |

### Distrito Federal 43.1 km (large)

- Baseline fixture: `tests/baselines/m_perf_a1/distrito_federal_43_1km.json`
- Wall time: 15.9 s
- getInfo calls: 86
- Failures (retried + reraised): 0

| Module | Function | Count | Seconds | Failures |
|---|---|---:|---:|---:|
| `engine.air` | `compute_pollutant_snapshot` | 27 | 36.8 | 0 |
| `engine.core.ee_resilience` | `_wrapped_getInfo` | 18 | 28.2 | 0 |
| `engine.ghg` | `compute_ghg_indicator_snapshot` | 7 | 2.0 | 0 |
| `engine.ghg` | `compute_co2_snapshot` | 5 | 2.6 | 0 |
| `engine.nature` | `compute_ndvi_condition` | 5 | 2.2 | 0 |
| `engine.nature` | `compute_regional_loss_evidence` | 5 | 2.5 | 0 |
| `engine.nature` | `_dw_mode_histogram` | 4 | 2.1 | 0 |
| `engine.nature` | `compute_current_land_cover` | 3 | 1.6 | 0 |
| `engine.nature` | `compute_kba_proximity` | 3 | 1.9 | 0 |
| `engine.nature` | `compute_supplier_spatial_link` | 3 | 2.1 | 0 |
| `engine.nature` | `compute_forest_loss` | 2 | 1.2 | 0 |
| `engine.nature` | `compute_water_exposure` | 2 | 0.5 | 0 |
| `engine.nature` | `_ndvi_low_area_pct` | 1 | 0.2 | 0 |
| `engine.nature` | `compute_habitat_conversion` | 1 | 0.2 | 0 |

### Rio de Janeiro coastal 20 km (M-TIER-A3 land mask)

- Baseline fixture: `tests/baselines/m_perf_a1/rio_coastal_20km.json`
- Wall time: 184.7 s
- getInfo calls: 86
- Failures (retried + reraised): 0

| Module | Function | Count | Seconds | Failures |
|---|---|---:|---:|---:|
| `engine.air` | `compute_pollutant_snapshot` | 27 | 424.8 | 0 |
| `engine.core.ee_resilience` | `_wrapped_getInfo` | 18 | 45.0 | 0 |
| `engine.ghg` | `compute_ghg_indicator_snapshot` | 7 | 25.0 | 0 |
| `engine.ghg` | `compute_co2_snapshot` | 5 | 4.0 | 0 |
| `engine.nature` | `compute_ndvi_condition` | 5 | 5.7 | 0 |
| `engine.nature` | `compute_regional_loss_evidence` | 5 | 7.8 | 0 |
| `engine.nature` | `_dw_mode_histogram` | 4 | 8.4 | 0 |
| `engine.nature` | `compute_current_land_cover` | 3 | 16.5 | 0 |
| `engine.nature` | `compute_kba_proximity` | 3 | 2.5 | 0 |
| `engine.nature` | `compute_supplier_spatial_link` | 3 | 12.8 | 0 |
| `engine.nature` | `compute_forest_loss` | 2 | 0.9 | 0 |
| `engine.nature` | `compute_water_exposure` | 2 | 7.0 | 0 |
| `engine.nature` | `_ndvi_low_area_pct` | 1 | 0.3 | 0 |
| `engine.nature` | `compute_habitat_conversion` | 1 | 0.2 | 0 |

## 4. Step B — batching candidates (to confirm)

The Step B plan picks the top N offenders from §2. Hypothesis from spec PF10 (to confirm against the table above):

- Nature's per-indicator reductions (7 main + regional_loss + spatial_link)
- The duplicate DW mode composites (habitat + spatial_link)
- Air's 9 per-pollutant six-step reductions

Each candidate should be assessed on (a) absolute count, (b) whether co-located reductions can combine into a single `ee.Dictionary`, (c) whether sharing crosses a function boundary (PF14 — pure call-consolidation only).
