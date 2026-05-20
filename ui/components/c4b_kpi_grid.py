"""C4b — KPI tile grid (M-UI-E.3, MNC primary visualisation).

12-tile grid: 9 air pollutants + 3 GHG indicators. Each tile shows the
indicator's display name, headline value with unit, an anomaly-direction
arrow (↑/↓/→) where the indicator has an anomaly concept, and a
confidence dot. Failed indicators render with a "Failed" badge and an
expander revealing the failure reason.

Nature has no tile here — its heterogeneous outputs (KBA distance,
Dynamic World dominant class, hectares lost, etc.) render in C5c.

C4b is the MNC primary visualisation per Wireframes §P-05. The Policy
Maker primary is C4a (hotspot map), which lands with M-UI-E.6 — until
then C4b renders for both user types.

Authority: docs/Wireframes_All_v4.md §P-05 C4b + Appendix C.2.
"""

# M-UI-E.3
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import streamlit as st

from ui.components.traffic_light import confidence_glyph


AnomalyDirection = Literal["up", "down", "flat", "none"]


@dataclass(frozen=True)
class _TileSpec:
    """Static spec for one tile. Dynamic values are read from the
    payload at render time.

    ``anomaly_key`` is ``None`` for indicators with no anomaly concept
    (ODIAC CO₂ is inventory-allocated, not an atmospheric measurement —
    matches engine.verbal_summary._ghg_dominant_slots's CO₂ branch).
    """

    display_name:   str
    pillar:         Literal["air", "ghg"]
    indicator:      str          # e.g. "no2", "ch4"
    value_key:      str          # full payload key, e.g. "air.no2.site"
    value_format:   str          # e.g. "{:.0f}"
    unit:           str          # display unit; "" for unitless indices
    anomaly_key:    str | None
    score_key:      str
    confidence_key: str


# Ordered list — the grid renders row by row in this order. Air first
# (9 tiles), then GHG (3). Within Air the order matches the dominant-
# contributor weights in engine/verbal_summary.py so the most decision-
# relevant pollutant lands first.
_TILES: tuple[_TileSpec, ...] = (
    _TileSpec("NO₂",   "air", "no2",  "air.no2.site",  "{:.0f}", "µmol m⁻²",
              "air.no2.anomaly",  "air.no2.score",  "air.no2.confidence"),
    _TileSpec("SO₂",   "air", "so2",  "air.so2.site",  "{:.0f}", "µmol m⁻²",
              "air.so2.anomaly",  "air.so2.score",  "air.so2.confidence"),
    _TileSpec("CO",    "air", "co",   "air.co.site",   "{:.0f}", "mmol m⁻²",
              "air.co.anomaly",   "air.co.score",   "air.co.confidence"),
    _TileSpec("HCHO",  "air", "hcho", "air.hcho.site", "{:.0f}", "µmol m⁻²",
              "air.hcho.anomaly", "air.hcho.score", "air.hcho.confidence"),
    _TileSpec("O₃",    "air", "o3",   "air.o3.site",   "{:.0f}", "DU",
              "air.o3.anomaly",   "air.o3.score",   "air.o3.confidence"),
    _TileSpec("PM₂.₅", "air", "pm25", "air.pm25.site", "{:.1f}", "µg m⁻³",
              "air.pm25.anomaly", "air.pm25.score", "air.pm25.confidence"),
    _TileSpec("PM₁₀",  "air", "pm10", "air.pm10.site", "{:.1f}", "µg m⁻³",
              "air.pm10.anomaly", "air.pm10.score", "air.pm10.confidence"),
    _TileSpec("AAI",   "air", "aai",  "air.aai.site",  "{:+.2f}", "",
              "air.aai.anomaly",  "air.aai.score",  "air.aai.confidence"),
    _TileSpec("AOD",   "air", "aod",  "air.aod.site",  "{:.2f}", "",
              "air.aod.anomaly",  "air.aod.score",  "air.aod.confidence"),
    _TileSpec("CH₄",              "ghg", "ch4",   "ghg.ch4.site",   "{:.0f}",  "ppb",
              "ghg.ch4.anomaly",  "ghg.ch4.score",  "ghg.ch4.confidence"),
    _TileSpec("CO₂ (ODIAC)",      "ghg", "co2",   "ghg.co2.mean",   "{:,.0f}", "t CO₂ yr⁻¹ per pixel",
              None,               "ghg.co2.score",  "ghg.co2.confidence"),
    _TileSpec("Nighttime lights", "ghg", "viirs", "ghg.viirs.site", "{:.1f}",  "nW cm⁻² sr⁻¹",
              "ghg.viirs.anomaly","ghg.viirs.score","ghg.viirs.confidence"),
)

# Values with |anomaly| below this read as no meaningful direction.
# Near-zero so most real signals get an arrow; only true zeros are flat.
_FLAT_ANOMALY_EPS = 1e-12

# Translations for the silent-skip path's machine-readable
# ``skipped_reason`` codes carried in ``_provenance.<pillar>.<indicator>``.
# Kept in lock-step with ``c9_partial_banner._SKIPPED_REASON_PROSE``.
_SKIPPED_REASON_TRANSLATIONS: dict[str, str] = {
    "out_of_coverage": (
        "Data source's coverage window does not include the "
        "requested time range."
    ),
    # M-NATURE-DEFENSIVE — see c9_partial_banner for the rationale.
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
    # M-OCEAN-RING — see c9_partial_banner for the rationale.
    "background_ring_no_data": (
        "Background ring (outside the AOI buffer) had no usable data — "
        "likely because the ring extends over water or outside the data "
        "source's coverage."
    ),
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_c4b_kpi_grid(payload: dict, selected_indicators: set[str]) -> None:
    """Render the C4b KPI tile grid.

    M-P04 polish: only tiles whose canonical ``score_key`` is in
    ``selected_indicators`` are rendered. Deselected indicators are
    omitted entirely — they're not failures, they were never asked
    for. When the user picked only non-tile indicators (e.g. just
    ``nature.*``), the whole grid no-ops.
    """
    visible_tiles = [
        tile for tile in _TILES
        if tile.score_key in selected_indicators
    ]
    if not visible_tiles:
        return

    with st.container(border=True):
        st.markdown("### Indicator values")
        cols_per_row = 4
        for row_start in range(0, len(visible_tiles), cols_per_row):
            row_tiles = visible_tiles[row_start:row_start + cols_per_row]
            columns = st.columns(cols_per_row)
            for col, tile in zip(columns, row_tiles):
                with col:
                    _render_tile(tile, payload)


# ---------------------------------------------------------------------------
# Per-tile rendering
# ---------------------------------------------------------------------------

def _render_tile(tile: _TileSpec, payload: dict) -> None:
    if _is_failed(tile, payload):
        _render_failed_tile(tile, payload)
    else:
        _render_value_tile(tile, payload)


def _is_failed(tile: _TileSpec, payload: dict) -> bool:
    """A tile is failed when its ``.score`` is ``None``.

    Catches all three failure paths:
    - Per-indicator failure (``_failures[pillar]`` entry).
    - ``coverage_window`` silent skip (e.g. CO₂ outside 2020-2023).
    - Pillar-wide failure (every key under the pillar is ``None``).
    """
    return payload.get(tile.score_key) is None


def _resolve_failure_reason(tile: _TileSpec, payload: dict) -> str:
    """Find the human-readable failure reason for a failed tile.

    Lookup order:
    1. ``_failures[pillar]`` list, matching on ``indicator_id``
       (which is ``<pillar>.<indicator>``, no measurement suffix —
       see ``engine.ids.make_id``).
    2. ``_provenance.<pillar>.<indicator>.skipped_reason``.
    3. Generic fallback.
    """
    failures = payload.get("_failures", {})
    pillar_failures = failures.get(tile.pillar, [])
    target_id = f"{tile.pillar}.{tile.indicator}"
    for entry in pillar_failures:
        if entry.get("indicator_id") == target_id:
            reason = entry.get("reason")
            if reason:
                return reason

    provenance = payload.get(f"_provenance.{tile.pillar}.{tile.indicator}", {})
    skipped = provenance.get("skipped_reason")
    if skipped:
        return _SKIPPED_REASON_TRANSLATIONS.get(skipped, skipped)

    return "Indicator did not return a value."


def _anomaly_direction(anomaly: float | None) -> AnomalyDirection:
    """Sign of the anomaly → ↑/↓/→. None → ``"none"``."""
    if anomaly is None:
        return "none"
    if abs(anomaly) < _FLAT_ANOMALY_EPS:
        return "flat"
    return "up" if anomaly > 0 else "down"


def _arrow_glyph(direction: AnomalyDirection) -> str:
    return {
        "up":   "↑",
        "down": "↓",
        "flat": "→",
        "none": "",
    }[direction]


def _arrow_colour(direction: AnomalyDirection) -> str:
    """Anomaly arrows carry direction, not severity, so they use a
    neutral palette — not the traffic-light colours from
    ``ui.components.traffic_light``. Severity lives in C3.
    """
    return {
        "up":   "#f59e0b",  # amber-500
        "down": "#3b82f6",  # blue-500
        "flat": "#9ca3af",  # grey-400
        "none": "#9ca3af",
    }[direction]


def _render_value_tile(tile: _TileSpec, payload: dict) -> None:
    """Success path — name + confidence dot, value + arrow, unit."""
    value = payload.get(tile.value_key)
    anomaly = payload.get(tile.anomaly_key) if tile.anomaly_key else None
    confidence = payload.get(tile.confidence_key)
    direction = _anomaly_direction(anomaly)
    arrow = _arrow_glyph(direction)
    arrow_colour = _arrow_colour(direction)
    glyph = confidence_glyph(confidence)

    value_str = (
        tile.value_format.format(value) if value is not None else "—"
    )

    with st.container(border=True):
        st.markdown(
            f"**{tile.display_name}**"
            f"<span style='float:right;font-size:1.1em;'>{glyph}</span>",
            unsafe_allow_html=True,
        )
        arrow_span = (
            f"<span style='color:{arrow_colour};font-size:1.1em;"
            f"margin-left:6px;'>{arrow}</span>"
            if arrow else ""
        )
        st.markdown(
            f"<div style='font-size:1.4em;font-weight:600;margin:4px 0;'>"
            f"{value_str}{arrow_span}</div>",
            unsafe_allow_html=True,
        )
        if tile.unit:
            st.markdown(
                f"<span style='font-size:0.85em;color:#6b7280;'>"
                f"{tile.unit}</span>",
                unsafe_allow_html=True,
            )


def _render_failed_tile(tile: _TileSpec, payload: dict) -> None:
    """Failure path — name + "Failed" badge, em-dash, expandable reason."""
    reason = _resolve_failure_reason(tile, payload)
    with st.container(border=True):
        st.markdown(
            f"**{tile.display_name}**"
            f"<span style='float:right;font-size:0.75em;color:#9ca3af;"
            f"background:#f3f4f6;padding:2px 6px;border-radius:3px;'>"
            f"Failed</span>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='font-size:1.4em;font-weight:600;margin:4px 0;"
            "color:#9ca3af;'>—</div>",
            unsafe_allow_html=True,
        )
        with st.expander("Why?"):
            st.caption(reason)
