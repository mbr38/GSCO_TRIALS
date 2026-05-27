# M-UI-A5 — Closed-entry verification

**Date closed.** 28 May 2026.
**Scope delivered.** Multi-indicator map on P-05 (item 2.3b): the single-
indicator C4a renderers (M-UI-E.6) are lifted into the primary multi-indicator
P-05 view (C4c) at the C4b↔C5 anchor; the renderer registry is extended from 3
to all 14 scored tiles; the C4b "View on map →" affordance now sets the active
indicator; lazy session-scoped EE-tile caching; empty-base-map first state +
close-map control.

## Files touched

| File | Change |
|---|---|
| `ui/components/multi_map_state.py` | **new** — active-indicator + tile-cache state contract. Pure dict-injected helpers (`set/get/clear_active`, `sync_cache`, `cached_tile_url`, `cache_stats`) + `st.session_state` wrappers; owns `MAP_ANCHOR_ID` (breaks the c4a↔c4b cycle) |
| `ui/components/c4a_indicator_map.py` | rewritten — renderers refactored into `_LayerSpec` builders; **14-entry `_RENDERERS`** (parametric Air factory + bespoke CH₄/VIIRS/NDVI + preserved KBA/DW); cache-aware `_render_layer_spec`; new public `render_multi_indicator_map`; single-indicator `render_c4a_indicator_map` preserved (MV14) |
| `ui/components/c4b_kpi_grid.py` | `_map_link_html` (HTML `<a>`) → `_render_view_on_map` (`st.button`); dead `render_multi_indicator_map_anchor` stub removed; `MAP_ANCHOR_ID` re-imported from `multi_map_state`; scoped link-mimic CSS added to `_inject_tile_header_css` |
| `pages/05_Screening_Results.py` | multi-indicator view calls `render_multi_indicator_map(setup, result)` at the anchor (replaces the M-UI-A4 placeholder stub) |
| `tests/test_multi_map_state.py` | **new** — state machine + cache (hit/miss/run-id invalidation/active-clear), dependency-injected |
| `tests/test_c4a_indicator_map.py` | registry-14, reference-dataset exclusion, parametric-factory closure semantics, source-label/family, VIIRS+NDVI palette alignment |
| `tests/test_c4b_kpi_grid.py` | `_map_link_html` test → shared-anchor-id + "every tile `select_key` has a renderer" (MV8/MV16) |
| `docs/Wireframes_All_v4.md` | §P-05 component reference gains **C4c**; M-UI-A5 changelog entry |
| `docs/v1x_followups.md` | "extend the C4a registry" follow-up marked mostly-closed |
| `docs/M-UI-A5_plain_language_explainer.md`, `…_closed_entry.md` | **new** |

**Test status.** Full suite green — **1401 passed, 19 skipped** (pre-existing
skips; no new skips). EE-touching render path verified in the live app
(examiner-confirmed working) — not via pytest, per the C4a convention.

## Decisions taken (Step B reconciliation, 28 May 2026)

The reconnaissance surfaced three forks; all resolved to the recommended option:

- **R2 — affordance is an HTML hash-link, not a button (blocks MV16's premise).**
  An `<a href='#anchor'>` can scroll but can't set Streamlit session state. **Converted
  to `st.button(type="tertiary")`** — the codebase's own click→state pattern
  (M-UI-A2 abandoned HTML for `st.button`+`st.rerun()` for the same reason).
  Affordance text/position kept; scoped CSS restores the link look; a one-shot
  `scrollIntoView` JS replaces the lost hash-scroll.
- **MV11 cache depth.** Renderers coupled EE-compute and render. **Refactored
  into `_LayerSpec` builders + a cache-aware host** so `getMapId` is the cache
  boundary. NO₂ output is unchanged; the function *shape* changed (flagged
  against the spec's "bit-identical" wording, accepted).
- **R1 — Air config heterogeneous.** PM₂.₅/PM₁₀ are 44 km CAMS gridded model
  output; AOD is MODIS MAIAC with a QA-mask. **All 9 stay parametric (MV9)**:
  one `preprocess` branch covers AOD; PM carries a prose caveat (coarse grid).

**Note on tracking.** The spec names `GSCO_v1x_TodoList.md` as the master item
list, but that file is **not present in the repo**. Item 2.3b completion is
recorded here and in the `docs/v1x_followups.md` registry-coverage entry
instead; the absent master file is flagged for whoever owns it.

## MV-lock verification

- [x] **MV1** — Path A (EE Map Tiles via `getMapId`). Cite `c4a_indicator_map._get_tile_url` (`ee.Image(image).getMapId(vis)["tile_fetcher"].url_format`).
- [x] **MV2** — `geemap.foliumap` only; no new library. The cached tile-URL is re-attached via `folium.raster_layers.TileLayer` — `geemap.foliumap.Map` *is* a `folium.Map` (verified `issubclass`), so this introduces no new dependency.
- [x] **MV3** — No time slider. Each layer is a single mean composite over the screening window; no temporal control in the host or renderers.
- [x] **MV4** — Works for any global AOI. Renderers read `setup["centre"]/["radius_km"]/["time_range"]`; no AOI hard-coding. (Sapezal/Brasília/coastal regression is the live-app suite.)
- [x] **MV5** — Embedded at the anchor between C4b and C5: `pages/05_Screening_Results.py::_render_multi_indicator_view` calls `render_multi_indicator_map` immediately after `render_c4b_kpi_grid`.
- [x] **MV6** — No default raster on initial render. `render_multi_indicator_map` reads `active_map_indicator`, defaults `None` → `_render_empty_state` (base map only). Test: `test_active_defaults_to_none`.
- [x] **MV7** — Empty state shows base map **and** an instructional prompt (`st.info`). Q-MV-1 resolved to text (not a CSS overlay on the geemap iframe — recon A.10).
- [x] **MV8** — Tile-click drives the map; no separate switcher. `_render_view_on_map` (button) sets `active_map_indicator`; no dropdown/pill component exists. Test: `test_every_tile_select_key_has_a_map_renderer`.
- [x] **MV9** — Parametric for the 9 Air pollutants (`_make_air_pollutant_layer`); bespoke `_ch4_layer`/`_viirs_layer`/`_ndvi_layer`; KBA/DW preserved. Test: `test_registry_ships_fourteen_renderers`, `test_air_factory_returns_distinct_callables_per_key`.
- [x] **MV10** — Hansen + ODIAC excluded from `_RENDERERS`. Test: `test_reference_datasets_excluded_from_registry`.
- [x] **MV11** — Lazy session-scoped cache keyed per `(indicator, run_id)`; `getMapId` thunk fires only on miss; `run_id` change clears the cache. Tests: `test_first_render_is_a_miss_and_computes`, `test_second_render_same_indicator_is_a_hit_no_ee_call`, `test_new_run_invalidates_entire_cache`.
- [x] **MV12** — Soft stickiness: `active_map_indicator` lives in session state, so it survives normal reruns; cleared by the close button and by a screening rerun. Tests: `test_sync_cache_is_idempotent_within_a_run`, `test_new_run_clears_active_indicator`.
- [x] **MV13** — "✕ Close map" button present only when a layer is active (`_render_map_header`, top-right); single click clears, no modal.
- [x] **MV14** — Single-indicator inspection view unchanged: `render_c4a_indicator_map` keeps its container + "### Map" header + dispatch; reads no `active_map_indicator`. Test: `test_c4b`/`test_c4a` registry regression + the existing single-indicator path.
- [x] **MV15** — No pixel-value hover. No per-renderer hover handlers added.
- [x] **MV16** — Tile affordance enhanced (sets state + scrolls) with unchanged visible text/position; styling restored via scoped CSS. The state-set value is the tile `select_key`, which equals the renderer key — pinned by `test_every_tile_select_key_has_a_map_renderer`.

## Known follow-ups

- **M-UI-A6** — reference-dataset map treatment (Hansen, ODIAC) via an "open on map" affordance from the C5 cards (MV10 handoff).
- **Cache pre-warm (Q-MV-2)** — proactively warm BrasÍlia/Sapezal tiles at deploy so the first examiner click is instant.
- The empty-state base map and the AOI-outline layer re-fetch each render (only the indicator raster is cached, per §6.1 scope) — fine for the single small outline layer, revisit only if it shows up in profiling.
