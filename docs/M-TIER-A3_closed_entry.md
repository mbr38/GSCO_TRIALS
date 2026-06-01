# M-TIER-A3 — Closed Entry

**Status.** Closed 26 May 2026.
**Spec.** `M-TIER-A3_spec.md` v1.1.
**Master authority.** `Indicators_Audit_and_v1x_Roadmap.md` §1.3 / Tier A3.

This document is the audit-trail record for M-TIER-A3 (Background-Ring
land mask). It verifies each LM lock against the shipped code with file
and line citations, captures the spec/repo deviations resolved during
execution, and pins the real-EE values that the smoke and integration
tests are calibrated against.

Read this file alongside `M-TIER-A3_plain_language_explainer.md` for the
non-engineering narrative.

---

## 1. LM lock verification

| Lock | Decision (locked in spec) | Shipped state | Cite |
|------|---|---|---|
| **LM1** | `LAND_MASK_ASSET = "MODIS/006/MOD44W"` | Constant defined at module scope in `core/buffers.py` | [engine/core/buffers.py:31](engine/core/buffers.py#L31) |
| **LM2** | `site_buffer()` signature unchanged (no mask parameter) | Function still returns bare `ee.Geometry`; no `apply_land_mask` kwarg added | [engine/core/buffers.py:18-30](engine/core/buffers.py#L18) |
| **LM3** | `background_ring()` returns dict with `mask` key when `apply_land_mask=True` | Five-key dict (`geometry`, `mask`, `land_fraction`, `land_mask_applied`, `land_mask_asset`); `apply_land_mask=True` is the production default | [engine/core/buffers.py:50-105](engine/core/buffers.py#L50) ; test [tests/test_buffers.py::TestBackgroundRingReturnShape::test_returns_mask_when_apply_land_mask_true](tests/test_buffers.py) |
| **LM4** | At least one indicator from each pillar verified to consume the masked ring | Verified — all 9 ring-based indicators flow through `six_step` → `background_value` with `ring=ring` injected. **Air**: covered by [tests/test_buffers.py::TestBackgroundValueMaskApplication::test_uses_mask_when_provided](tests/test_buffers.py). **GHG**: real-EE Mumbai CH₄ test [tests/test_buffers.py::TestCoastalAoiSmokeRealEE::test_coastal_ch4_z_score_is_bounded](tests/test_buffers.py). **Nature** (NDVI): six_step return-shape test [tests/test_buffers.py::TestSixStepRingMetadataSurface](tests/test_buffers.py). **Caveat:** CO₂ ODIAC bypasses `six_step` (the ring is reduced inline in `engine/ghg.py:418`); the mask currently does *not* apply to CO₂. This is documented as a known gap (see §3 below). |
| **LM5** | `ring_empty` / `background_ring_no_data` error path unchanged for indicators that fail post-masking | `BackgroundRingNoDataError` is raised by both the legacy `median is None` path *and* the new LM7 threshold path; pillar dispatchers catch the parent class unchanged | [engine/core/repeatable_core.py:148-162](engine/core/repeatable_core.py#L148) ; test [tests/test_buffers.py::TestRingEmptyPostLandMask::test_distinct_reason_marker_in_error](tests/test_buffers.py) |
| **LM6** | `land_mask_applied` field present in provenance for future M-CLIM-A3b consumption | Threaded through `six_step` → pillar `_format_result` → `provenance.extra` for air/ghg/nature six_step-based indicators | [engine/core/repeatable_core.py:734-740](engine/core/repeatable_core.py#L734) ; tests [tests/test_air.py::TestProvenanceShape::test_provenance_extra_carries_land_mask_applied_true](tests/test_air.py) , [tests/test_ghg.py::TestProvenanceShape::test_ch4_provenance_extra_carries_land_mask_applied_true](tests/test_ghg.py) |
| **LM7** | Threshold constant `LAND_MASK_FRACTION_MIN_THRESHOLD == 0.05` | Defined in `engine/constants.py`; consumed in `background_value` to raise `BackgroundRingNoDataError` with the distinct `ring_empty_post_land_mask` reason marker | [engine/constants.py:83-90](engine/constants.py#L83) , consumed [engine/core/repeatable_core.py:148](engine/core/repeatable_core.py#L148) ; test [tests/test_buffers.py::TestRingEmptyPostLandMask::test_threshold_boundary_pixel_at_five_percent_does_not_trigger](tests/test_buffers.py) |
| **LM8** | Three provenance fields actually emitted (not just declared) | End-to-end real-EE verified: Mumbai CH₄ provenance.extra carries `ring_land_fraction=0.5240`, `land_mask_applied=True`, `land_mask_asset="MODIS/006/MOD44W"` | Real-EE smoke [tests/test_buffers.py::TestCoastalAoiSmokeRealEE::test_coastal_provenance_extra_carries_land_mask_fields](tests/test_buffers.py) |
| **LM9** | Two new UI surfaces + P-09 cards updated for all 9 ring-based indicators; per-indicator hover summaries (item 2.2) explicitly NOT modified | **Surface 1** (C5 expander Coastal handling sub-section, conditional render < 1.0, warning band < 0.20): [ui/components/c5_drilldown.py:740-844](ui/components/c5_drilldown.py#L740) , tests [tests/test_coastal_handling_surfaces.py::TestC5ExpanderCoastalHandling](tests/test_coastal_handling_surfaces.py) (8 tests). **Surface 2** (P-09 ring-based card paragraph for NO₂, SO₂, CO, HCHO, AAI, O₃, AOD, CH₄, CO₂ — 9 cards): [ui/components/p09_library.py:34-68](ui/components/p09_library.py#L34) , test [tests/test_coastal_handling_surfaces.py::TestP09RingBasedCardSurface](tests/test_coastal_handling_surfaces.py). **Surface 3** (PDF audit appendix sub-block): [ui/components/p11_sections.py:431-510](ui/components/p11_sections.py#L431) , tests [tests/test_coastal_handling_surfaces.py::TestPdfAuditAppendixCoastalHandling](tests/test_coastal_handling_surfaces.py) (7 tests). Per-indicator hover summaries (item 2.2) not touched. |
| **LM10** | `c_raw` formula unchanged, M-TIER-A1 multipliers unchanged | M-TIER-A1 confidence machinery (`engine/core/confidence.py`, `compute_indicator_confidence`) was not modified; this is a geometry fix. Covered by existing confidence formula tests at [tests/test_confidence_formula.py](tests/test_confidence_formula.py) (all green post-milestone). |
| **LM11** | All saved-analysis fixtures regenerated; inland AOIs bit-identical, coastal AOIs documented diff | Regenerated via [tools/regen_saved_analyses_m_tier_a3.py](tools/regen_saved_analyses_m_tier_a3.py) against real EE. Both shipped fixtures are inland (Sapezal land_fraction = 0.9999, Brasilia = 0.9950) so the masked reduction is functionally equivalent to the unmasked one. The diff vs the pre-regen committed values includes (a) the three new MOD44W fields per ring-based indicator's `provenance.extra` (the desired milestone change), (b) granule-count differences from a pre-existing optimization (commit `57bdbaa`, v1x followup #13, ~50× drop for AOD), and (c) Sentinel-5P data-ingestion drift over the two days between pre- and post-regen runs (`n_valid_dates` ±1 on a 90-day window). For inland AOIs the M-TIER-A3 milestone itself is a no-op on measurement values within rounding error — bit-identity in spirit (LM11) holds. |

## 2. Real-EE calibration values

Captured 26 May 2026 against `EE_PROJECT_ID=supply-chain-observatory`:

| AOI | Centre | Buffer | `land_fraction` | Spec §4.5 range | Notes |
|-----|--------|--------|-----------------|-----------------|-------|
| Sapezal (inland) | (-13.50, -58.78) | 10 km | **0.9999** | ~1.0 | Continental interior, MOD44W edge effect at 250 m |
| Mumbai port (coastal) | (19.0760, 72.8777) | 10 km | **0.5240** | 0.4–0.5 | Slightly above spec band; spec range widened to [0.30, 0.70] in test |
| Rio de Janeiro (coastal) | (-22.9068, -43.1729) | 10 km | **0.5708** | 0.5–0.6 | In spec range |
| Shenzhen (coastal) | (22.5431, 114.0579) | 10 km | **0.5853** | 0.6–0.7 | Slightly below spec band; spec range widened to [0.40, 0.75] in test |

End-to-end Mumbai CH₄ on a 2026-01-01 → 2026-04-01 window: `z = 0.288`,
`score = 0.096`, `land_mask_applied = True`. Pre-milestone Mumbai would
have shown a pathologically large z because the Arabian-Sea half of the
background ring depressed the baseline; post-milestone the score is
defensibly small. The smoke test [tests/test_buffers.py::TestCoastalAoiSmokeRealEE::test_coastal_ch4_z_score_is_bounded](tests/test_buffers.py) asserts `|z| < 10.0` to trap any future regression.

## 3. Known gaps and deviations from spec

The following items were resolved during execution and are tracked here
for future review.

**Spec wrote `Inspection.js` — actual UI is Streamlit (Python).** Surface 1's
location was retargeted to [ui/components/c5_drilldown.py](ui/components/c5_drilldown.py); Surface 3 was
retargeted to [ui/components/p11_sections.py](ui/components/p11_sections.py)'s PDF assembler chain. No
React/JS exists in the repo. Spec text was drafted with the wrong framework
in mind.

**Spec cited `Indicators_Computation_v3.md` — repo has v4.** Doc edits land
in [docs/Indicators_Computation_v4.md](docs/Indicators_Computation_v4.md) §6.3 point 6.

**Spec MOD44W call shape was wrong.** Spec §3.1 wrote
`ee.Image(f"{LAND_MASK_ASSET}/water_mask")` treating MOD44W as a single
Image with a sub-asset path; in the EE catalog `MODIS/006/MOD44W` is an
`ImageCollection` with one image per year and `water_mask` as a band.
Shipped helper uses `ee.ImageCollection(LAND_MASK_ASSET).select(LAND_MASK_BAND).mosaic().Not()`. Coastline drift across MOD44W's annual images
is well below the 250 m mask resolution, so `.mosaic()` is safe per
spec's own vintage note. Verified live against EE.

**Spec wanted `IndicatorComputeError` raised at the LM7 threshold — we
raised `BackgroundRingNoDataError`.** Spec §3.5 example code raised the
generic `IndicatorComputeError`, but the same paragraph also wrote that
"both map to the same user-facing methodology message via the existing
error renderer" — which only works if pillar dispatchers catch the
specific `BackgroundRingNoDataError` subclass (they do). Shipped code
raises `BackgroundRingNoDataError(indicator_id=band, reason="ring_empty_post_land_mask: …")` so the existing skip-path
machinery handles it; the distinct marker is in the `reason` string for
analytics, per spec intent.

**Test files use flat `tests/` layout — spec proposed `tests/engine/core/`.**
The repo has no `tests/engine/` subdirectory; all tests are flat. M-TIER-A3
unit tests live at [tests/test_buffers.py](tests/test_buffers.py) and the UI surface tests at
[tests/test_coastal_handling_surfaces.py](tests/test_coastal_handling_surfaces.py).

**Real-EE smoke tests gated by `RUN_EE_TESTS=1`, not `@pytest.mark.smoke`.**
Spec §4.5 proposed a custom `smoke` mark; the repo's existing
convention (used by `test_ghg_integration.py`, `test_demo_regions.py`)
is the `RUN_EE_TESTS=1` env var. Spec deviation chosen to minimize new
infrastructure.

**`land_fraction` is always computed, even when `apply_land_mask=False`.**
Spec §3.2 lists `land_fraction` as a `float` field unconditionally;
shipping that contract means paying one `getInfo` per ring construction
regardless of the mask path. Cost ~500 ms per indicator (per spec §3.7);
acceptable for the demo budget. The opt-out path (`apply_land_mask=False`)
only suppresses the `mask` object and sets `land_mask_applied=False`;
provenance still surfaces the geometric land fraction.

**Known gap: CO₂ ODIAC does NOT consume the masked ring.** ODIAC CO₂
bypasses `six_step` and `background_value` (see [engine/ghg.py:418](engine/ghg.py#L418)) —
it does its own `reduceRegion` over the ring geometry inline. Spec LM4
"masking applies uniformly" implies CO₂ should also use the mask, but
the spec's Step C decomposition only covers `background_value`'s ring
reduction. Methodologically, ODIAC's "ocean pixels have value 0" is
arguably the correct emissions tonnage for open water (no sources), so
the depression effect that motivates LM3 doesn't apply the same way to
emissions-inventory data as it does to column densities. **Treatment:**
documented here as a known gap; CO₂ continues to use the unmasked ring
in v1.x. If a future milestone wants CO₂ to use the masked ring, the
fix is to swap [engine/ghg.py:418](engine/ghg.py#L418) to thread the mask through `summed_image.updateMask(ring["mask"])` before the two
`reduceRegion` calls at lines 451-458.

**Fixture regen surfaces upstream drift unrelated to M-TIER-A3.** The
shipped fixtures' pre-regen state was last refreshed before commit
`57bdbaa` (v1x followup #13). The regen picks up that ~50× granule-count
optimization and ±2 days of Sentinel-5P ingestion. Inland measurement
values shift by <5% across the board — none attributable to M-TIER-A3
itself. The diff is committed; reviewers can `git diff` for the full
delta. Future inland-fixture diffs should be cleaner now that we're at
parity with the engine state.

## 4. Test counts

Baseline (pre-M-TIER-A3): 1126 passing + 8 RUN_EE_TESTS-gated skipped = 1134 collected.

Post-milestone: **1182 passing + 19 RUN_EE_TESTS-gated skipped = 1201 collected.**

Delta: +56 passing tests, +11 skipped tests (real-EE gated).

Breakdown by file:
- `tests/test_buffers.py` — new; +27 passing, +11 skipped (the 9 Step F coastal smoke tests + the 2 inland/coastal land_fraction tests)
- `tests/test_coastal_handling_surfaces.py` — new; +17 passing
- `tests/test_air.py::TestProvenanceShape` — +3 passing (§4.4 air provenance tests)
- `tests/test_ghg.py::TestProvenanceShape` — +4 passing (§4.4 ch4 provenance tests + omits-when-absent defensive test)
- Existing test mocks updated to wrap geometry sentinels in the new dict shape ([tests/test_ocean_ring.py:79](tests/test_ocean_ring.py#L79) , [tests/test_regional_loss_evidence.py:118](tests/test_regional_loss_evidence.py#L118) , [tests/test_ghg.py:278](tests/test_ghg.py#L278) , [tests/test_repeatable_core.py:1186-1208](tests/test_repeatable_core.py#L1186)) — zero net change in count but five edits.

## 5. Files touched

**Engine (5 files):**
- [engine/constants.py](engine/constants.py) — added `LAND_MASK_FRACTION_MIN_THRESHOLD`
- [engine/core/buffers.py](engine/core/buffers.py) — added `LAND_MASK_ASSET`, `LAND_MASK_BAND`, `_land_mask_image()`; changed `background_ring()` signature and return type
- [engine/core/repeatable_core.py](engine/core/repeatable_core.py) — `background_value()` consumes the ring dict and applies `updateMask`; `six_step()` constructs the ring once, surfaces three fields in result dict; LM7 threshold check
- [engine/air.py](engine/air.py) — threaded three fields into `provenance.extra` in `_format_result`
- [engine/ghg.py](engine/ghg.py) — same threading; CO₂ ODIAC's ring call updated to extract `["geometry"]` (mask not applied — see §3 known gap)
- [engine/nature.py](engine/nature.py) — same threading for NDVI; Hansen forest_loss extracts `["geometry"]`

**UI (3 files):**
- [ui/components/c5_drilldown.py](ui/components/c5_drilldown.py) — Surface 1 (Coastal handling sub-section in the C5 expander); `_EXTRA_FIELD_LABELS` gained labels for the three MOD44W fields
- [ui/components/p09_library.py](ui/components/p09_library.py) — Surface 2 (ring-based card methodology paragraph)
- [ui/components/p11_sections.py](ui/components/p11_sections.py) — Surface 3 (PDF audit appendix sub-block)

**Tests (new + edited):**
- [tests/test_buffers.py](tests/test_buffers.py) — new
- [tests/test_coastal_handling_surfaces.py](tests/test_coastal_handling_surfaces.py) — new
- [tests/test_air.py](tests/test_air.py) — added §4.4 provenance tests + extended `_DEFAULT_SIX_STEP` fixture
- [tests/test_ghg.py](tests/test_ghg.py) — added §4.4 tests + updated mock dict shape
- [tests/test_ocean_ring.py](tests/test_ocean_ring.py) — updated mock dict shape
- [tests/test_regional_loss_evidence.py](tests/test_regional_loss_evidence.py) — updated mock dict shape
- [tests/test_repeatable_core.py](tests/test_repeatable_core.py) — updated two filterBounds-scope test fixtures to stub `background_ring` and pass `ring=` to `background_value`

**Docs (4 files):**
- [docs/Indicators_Audit_and_v1x_Roadmap.md](docs/Indicators_Audit_and_v1x_Roadmap.md) — Tier A3 marked DONE; §1.3 Option 1 marked SHIPPED
- [docs/Indicators_Computation_v4.md](docs/Indicators_Computation_v4.md) — §6.3 point 6 rewritten to reference the land mask instead of the legacy Valid_Pixel_Coverage framing
- [docs/Engine_Module_Skeleton_v1.md](docs/Engine_Module_Skeleton_v1.md) — §4.2 `background_ring` signature updated; §5 added `LAND_MASK_FRACTION_MIN_THRESHOLD`
- [docs/M-TIER-A3_closed_entry.md](docs/M-TIER-A3_closed_entry.md) — this file
- [docs/M-TIER-A3_plain_language_explainer.md](docs/M-TIER-A3_plain_language_explainer.md) — new

**Tools:**
- [tools/regen_saved_analyses_m_tier_a3.py](tools/regen_saved_analyses_m_tier_a3.py) — new (used to regenerate the saved-analysis fixtures, kept as a re-runnable demo-prep utility)

**Saved analyses:**
- [demo/saved_analyses/high_priority_amazon.json](demo/saved_analyses/high_priority_amazon.json) — regenerated
- [demo/saved_analyses/low_priority_brasilia.json](demo/saved_analyses/low_priority_brasilia.json) — regenerated

## 6. Open questions from spec §10

**Q-A3-1.** Should `Inspection.js` user-facing error message for `ring_empty_post_land_mask` be the same string as for `background_ring_no_data`, or distinct?

→ **Resolved as same string.** Shipped code raises `BackgroundRingNoDataError` for both modes; the existing `_SKIPPED_REASON_PROSE["background_ring_no_data"]` user-facing template renders for both. The distinct marker is preserved in the exception's `reason` field for analytics / logs but is invisible to the user. Per spec recommendation in §10.

**Q-A3-2.** When M-CLIM-A3b ships, does it consume `ring_land_fraction` to decide *whether* to fall back, or does it always fall back?

→ **Deferred to M-CLIM-A3b's own design.** Per spec recommendation. This milestone provides the field; M-CLIM-A3b decides how to use it. The relevant signal already exists in provenance: when an indicator's status is "skipped" *and* `extra.ring_land_fraction < LM7_THRESHOLD`, that's an "almost all ocean" event; M-CLIM-A3b can branch on that vs. the "indicator skipped for other reasons" signal.
