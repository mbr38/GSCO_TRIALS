"""C9 — partial-coverage banner (M-UI-E.5).

Lists every indicator that didn't return a value, regardless of which
of the two failure paths produced the gap:

  1. Explicit per-indicator failures in ``_failures[<pillar>]``
     (raised by the engine and caught by ``orchestrator._run_one_pillar``).
  2. Silent coverage-window skips in
     ``_provenance.<pillar>.<indicator>.skipped_reason``
     (e.g. CO₂ outside ODIAC's 2020-2023 window).

The renderer short-circuits to a no-op when there's nothing to show —
callers can fire it unconditionally and let the banner decide.

No retry action in v1 — re-running individual indicators needs an
orchestrator entry point we don't have yet. Tracked in
``docs/v1x_followups.md``.

Authority: docs/Wireframes_All_v4.md §P-05 C9.
"""

# M-UI-E.5
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class _MissingIndicator:
    """One row in the partial banner."""

    pillar:        str
    indicator_id:  str
    reason:        str
    source:        str   # "failure" or "skipped"


# Canonical indicator slugs per pillar — used to scan provenance blocks
# for silent skips. Kept in sync with ``ui.components.c5_drilldown``'s
# dataset-key tuples.
_PILLAR_INDICATOR_SLUGS: dict[str, tuple[str, ...]] = {
    "air":    ("no2", "so2", "co", "hcho", "pm25", "pm10", "o3", "aai", "aod"),
    "ghg":    ("ch4", "co2", "viirs"),
    "nature": ("kba", "dw", "habitat", "forest_loss", "ndvi", "water", "recovery"),
}

# Translations for machine-readable skipped_reason codes. Unknown codes
# pass through as-is (same defensive pattern as c4b_kpi_grid).
_SKIPPED_REASON_PROSE: dict[str, str] = {
    "out_of_coverage": (
        "Data source's coverage window does not include the "
        "requested time range."
    ),
    # M-NATURE-DEFENSIVE — empty-result skip codes emitted by
    # engine.nature reducers when an EE reduction returns no usable
    # pixels. The Air-side ``no_cams_pixels`` code is registered for
    # parity even though Air's reducers currently route through
    # ``six_step`` (which raises ``IndicatorComputeError`` instead); the
    # entry future-proofs the UI against later defensive guards in
    # ``engine.air``.
    "no_dw_pixels": (
        "Dynamic World had no usable imagery for this AOI in the "
        "screening window — likely high cloud cover or no Sentinel-2 "
        "acquisitions."
    ),
    "no_hansen_pixels": (
        "Hansen forest-loss data has no coverage for this AOI."
    ),
    "no_modis_pixels": (
        "MODIS NDVI had no usable imagery for this AOI in the "
        "screening window."
    ),
    "no_cams_pixels": (
        "CAMS atmospheric data had no usable pixels for this AOI in "
        "the screening window."
    ),
    # M-AIR-GHG-DEFENSIVE — emitted by engine.core.repeatable_core.site_value
    # when the §0.2 site buffer reduces to no usable pixels. Distinct
    # from background_ring_no_data (which is about the ring outside
    # the buffer); these codes are about the buffer itself.
    "no_s5p_pixels": (
        "Sentinel-5P had no usable observations for this AOI in the "
        "screening window — likely high cloud cover or no overpasses."
    ),
    "no_maiac_pixels": (
        "MODIS MAIAC had no usable observations for this AOI — likely "
        "persistent cloud cover."
    ),
    "no_viirs_pixels": (
        "VIIRS had no usable observations for this AOI in the "
        "screening window."
    ),
    # M-OCEAN-RING — emitted by engine.core.repeatable_core.background_value
    # when the §0.2 background ring reduces to no usable pixels. Typical
    # cause: coastal AOIs whose ring lands over water (e.g. Rio de
    # Janeiro state at 281 km buffer → 562 km ring, largely Atlantic).
    # M-RING-UX — broadened to acknowledge cloud-cover / sparse-overpass
    # cause (Acre, deep Amazon) in addition to the water case.
    "background_ring_no_data": (
        "Background data unavailable — the area around the AOI either "
        "extends over water or has persistent cloud cover / sparse "
        "satellite overpasses (common for very large AOIs in tropical "
        "or polar regions). Try a smaller buffer or a region with "
        "better satellite coverage."
    ),
}

# Stable display order so the banner reads air → ghg → nature.
_PILLAR_ORDER: dict[str, int] = {"air": 0, "ghg": 1, "nature": 2}


def render_c9_partial_banner(
    payload:             dict,
    selected_indicators: set[str],
) -> None:
    """Render the partial-coverage banner.

    Banner-only — the per-indicator detail lives in the C4b KPI tiles
    (failed tiles carry their own "Why?" expander) and in the C5 drill-
    down panels. The banner's job is just to flag "something is partial"
    with a count, so the user knows to look for missing tiles below.

    M-P04 polish: only counts missing values for indicators the user
    actually selected — deselecting an indicator on P-04 is not a
    failure to report on P-05.
    """
    # M-UI-E.5 polish — list dropped; tiles + drill-downs already carry
    # the per-indicator detail, so the banner doesn't need to repeat it.
    missing = _collect_missing(payload, selected_indicators)
    if not missing:
        return

    n = len(missing)
    plural = "" if n == 1 else "s"
    st.warning(
        f"**Partial coverage** — {n} indicator{plural} did not return "
        f"a value. See the failed tiles below for details.",
    )


def _collect_missing(
    payload:             dict,
    selected_indicators: set[str],
) -> list[_MissingIndicator]:
    """Walk both failure paths and aggregate missing indicators.

    M-P04 polish: filters against ``selected_indicators`` — entries
    for indicators the user didn't select are skipped, since the
    "missing" framing only applies to indicators the user actually
    asked for. The full canonical selected ID (e.g.
    ``"air.no2.score"``) is reduced to its ``<pillar>.<slug>`` prefix
    for comparison with ``_failures`` and provenance keys.

    De-duplicates by ``indicator_id`` — when an indicator appears in
    both ``_failures`` and ``_provenance.<x>.skipped_reason``, the
    failure entry wins (it carries the engine's specific message).
    """
    # Build the set of indicator-prefix slugs the user selected.
    # selected_indicators carries full IDs like "air.no2.score";
    # _failures and provenance use "air.no2".
    selected_prefixes = {
        ".".join(ind.split(".")[:2]) for ind in selected_indicators
    }

    missing: dict[str, _MissingIndicator] = {}

    # Path 1 — explicit failures.
    failures = payload.get("_failures", {})
    for pillar, entries in failures.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            indicator_id = entry.get("indicator_id")
            if not indicator_id:
                continue
            if indicator_id not in selected_prefixes:
                continue
            reason = entry.get("reason") or "Failed (no reason recorded)."
            missing[indicator_id] = _MissingIndicator(
                pillar=pillar,
                indicator_id=indicator_id,
                reason=reason,
                source="failure",
            )

    # Path 2 — silent coverage-window skips via provenance.
    for pillar, slugs in _PILLAR_INDICATOR_SLUGS.items():
        for slug in slugs:
            indicator_id = f"{pillar}.{slug}"
            if indicator_id not in selected_prefixes:
                continue
            provenance = payload.get(f"_provenance.{pillar}.{slug}")
            if not isinstance(provenance, dict):
                continue
            skipped = provenance.get("skipped_reason")
            if not skipped:
                continue
            if indicator_id in missing:
                continue  # Already covered by an explicit failure.
            missing[indicator_id] = _MissingIndicator(
                pillar=pillar,
                indicator_id=indicator_id,
                reason=_SKIPPED_REASON_PROSE.get(skipped, skipped),
                source="skipped",
            )

    return sorted(
        missing.values(),
        key=lambda m: (_PILLAR_ORDER.get(m.pillar, 99), m.indicator_id),
    )
