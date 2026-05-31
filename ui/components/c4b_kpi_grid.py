"""C4b — Indicator snapshot (M-UI-A4 redesign; MNC primary visualisation).

A severity-led indicator snapshot. Each tile leads with the **anomaly
magnitude** (z-score for atmospheric indicators; the natural metric for
Nature) and a **severity word + coloured dot** ("High" / "Concern" /
"Normal" / "Sparse data") computed locally by ``ui.components.severity``.
The raw site value is demoted to a secondary line (SR1).

Three severity *grammars* drive the tiles (SR7, spec v1.1):
  - **z-score** — 9 air pollutants + CH₄ + VIIRS + NDVI deviation
  - **DW categorical** — Dynamic World dominant class
  - **distance/overlap** — KBA proximity

Hansen forest loss and ODIAC CO₂ were removed from the headline grid in spec
v1.1 — they are reference datasets, not scored signals, and live in the C5
drill-down (their reference-dataset treatment is M-UI-A6's job).

By default only **critical** tiles render (severity ∈ {High, Concern},
SR2), topped up to a minimum of three (SR9); a "Show all indicators"
expander reveals the full grid (SR5 affordance + Normal/Sparse tiles).

Preserved from the prior C4b (M-UI-E.3): confidence dots (SR11), the
M-UI-A2 name-as-popover affordance (SR10), failure-tile handling (SR12),
selection-aware rendering (M-P04), and M-PARTIAL-CAVEAT compatibility.

Nature tiles now live here (SR4); the C5c "Nature details" deep-dive keeps
only the non-tileable outputs (SR13).

Authority: docs/M-UI-A4_spec; docs/Wireframes_All_v4.md §P-05 C4b;
docs/Indicator_ID_Schema_v2.md (canonical IDs).

NOTE on the filename: kept as ``c4b_kpi_grid.py`` (Q-A4-2 decision) though
the component is now an indicator *snapshot*, not a KPI grid.
"""

# M-UI-A4
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import streamlit as st

from ui.components.fallback_retry import (  # M-FALLBACK-A1 §5.3
    STRATEGY_SLIDING,
    STRATEGY_SPPY,
    apply_retry,
    is_retryable,
    reason_is_retryable,
)
from engine.core.trend import is_series_indicator
from ui.components.indicator_info import render_indicator_name_with_info
from ui.components.trend_view import set_active_trend
from ui.components.multi_map_state import (
    MAP_ANCHOR_ID,
    request_scroll,
    set_active_indicator,
)
from ui.components.severity import (
    Severity,
    is_critical,
    severity_categorical,
    severity_distance,
    severity_rank,
    severity_score_band,
    severity_zscore,
    zscore_direction,
)
from ui.components.traffic_light import confidence_glyph


Grammar = Literal["zscore", "score_band", "categorical", "distance"]

# ``MAP_ANCHOR_ID`` now lives in ``ui.components.multi_map_state`` (M-UI-A5):
# the multi-indicator map host renders the anchor and the C4b tiles scroll to
# it, so the shared id can't drift. Re-imported above; kept importable from
# here for backward compatibility.

# Minimum tiles shown in the default (critical) snapshot (SR9).
_MIN_SNAPSHOT_TILES: int = 3

# Reduced opacity for the "Show all" expander contents (SR5.5) — signals
# "less important" without hiding.
_EXPANDER_OPACITY: float = 0.85


# ---------------------------------------------------------------------------
# Tile spec — one polymorphic dataclass discriminated by ``grammar``
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _TileSpec:
    """Static spec for one tile. Dynamic values are read from the payload at
    render time. The ``grammar`` field selects the severity function and the
    layout variant.

    ``select_key`` is the canonical *selectable* indicator ID
    (``ui.components.p04_indicator_registry``) — it drives the M-P04
    selection filter and doubles as the M-UI-A2 popover ``indicator_id``.

    Failure detection (``_is_failed``) keys on the grammar's headline value,
    NOT on ``select_key``: e.g. ``nature.ndvi.score`` is routinely None in v1
    (depends on the not-yet-shipped trend engine) even when the NDVI z-score
    is present, so an NDVI tile must read its ``z_key`` to decide failure.
    """

    display_name:   str
    pillar:         Literal["air", "ghg", "nature"]
    indicator:      str                  # slug, e.g. "no2", "kba"
    grammar:        Grammar
    select_key:     str                  # selectable ID + M-UI-A2 id
    confidence_key: str | None

    # --- z-score grammar ---
    z_key:          str | None = None
    value_key:      str | None = None    # raw site value (secondary line)
    value_format:   str = "{:.0f}"
    unit:           str = ""
    background_key: str | None = None

    # --- score-band grammar (M-GHG-REDESIGN-A1; VIIRS sustained contrast) ---
    score_key:       str | None = None   # [0,1] component score (the headline)
    persistence_key: str | None = None   # lit fraction, for the secondary line
    score_format:    str = "{:.2f}"

    # --- categorical grammar ---
    scheme:             Literal["odiac", "dw"] | None = None
    category_key:       str | None = None   # ghg.co2.mean OR nature.dw.dominant_class
    class_confidence_key: str | None = None

    # --- distance grammar ---
    dist_km_key:    str | None = None
    overlap_pct_key: str | None = None

    # --- display extras ---
    centre_format:  str | None = None    # natural-metric centre format
    plain_language: str = ""             # framing line under the centre
    badge:          str | None = None    # e.g. Hansen "Reference dataset" note

    @property
    def provenance_key(self) -> str:
        return f"_provenance.{self.pillar}.{self.indicator}"


# Canonical order: air → ghg → nature (CLAUDE.md §7). Within Air, the order
# matches C5a / the P-04 registry. Nature order per spec §3.4 (KBA, DW,
# Hansen, NDVI). This is the order the "Show all" expander uses (SR5.4).
_TILES: tuple[_TileSpec, ...] = (
    # --- Air (z-score grammar) ---
    _TileSpec("NO₂", "air", "no2", "zscore", "air.no2.score", "air.no2.confidence",
              z_key="air.no2.z", value_key="air.no2.site", value_format="{:.0f}",
              unit="µmol m⁻²", background_key="air.no2.background"),
    _TileSpec("SO₂", "air", "so2", "zscore", "air.so2.score", "air.so2.confidence",
              z_key="air.so2.z", value_key="air.so2.site", value_format="{:.0f}",
              unit="µmol m⁻²", background_key="air.so2.background"),
    _TileSpec("CO", "air", "co", "zscore", "air.co.score", "air.co.confidence",
              z_key="air.co.z", value_key="air.co.site", value_format="{:.0f}",
              unit="mmol m⁻²", background_key="air.co.background"),
    _TileSpec("HCHO", "air", "hcho", "zscore", "air.hcho.score", "air.hcho.confidence",
              z_key="air.hcho.z", value_key="air.hcho.site", value_format="{:.0f}",
              unit="µmol m⁻²", background_key="air.hcho.background"),
    _TileSpec("PM₂.₅", "air", "pm25", "zscore", "air.pm25.score", "air.pm25.confidence",
              z_key="air.pm25.z", value_key="air.pm25.site", value_format="{:.1f}",
              unit="µg m⁻³", background_key="air.pm25.background"),
    _TileSpec("PM₁₀", "air", "pm10", "zscore", "air.pm10.score", "air.pm10.confidence",
              z_key="air.pm10.z", value_key="air.pm10.site", value_format="{:.1f}",
              unit="µg m⁻³", background_key="air.pm10.background"),
    _TileSpec("O₃", "air", "o3", "zscore", "air.o3.score", "air.o3.confidence",
              z_key="air.o3.z", value_key="air.o3.site", value_format="{:.0f}",
              unit="DU", background_key="air.o3.background"),
    _TileSpec("AAI", "air", "aai", "zscore", "air.aai.score", "air.aai.confidence",
              z_key="air.aai.z", value_key="air.aai.site", value_format="{:+.2f}",
              unit="", background_key="air.aai.background"),
    _TileSpec("AOD", "air", "aod", "zscore", "air.aod.score", "air.aod.confidence",
              z_key="air.aod.z", value_key="air.aod.site", value_format="{:.2f}",
              unit="", background_key="air.aod.background"),
    # --- GHG ---
    # M-CH4-A1 (30 May 2026): CH₄ removed from the headline severity grid —
    # reclassified as reference data (joins Hansen + ODIAC), per the GHG↔ODIAC
    # +OCO-2/OCO-3 validation (docs/ghg_odiac_validation.md §10: the CH₄
    # anomaly-z proxy fired at 1/25 sites at 5 km, 0/25 at 15 km). It now
    # renders as a muted reference card in the C5 drill-down, not a scored tile.
    # M-GHG-REDESIGN-A1 — VIIRS re-grammared to persistence-weighted ring-
    # relative sustained contrast. Severity now bands the [0,1] score
    # (score_band grammar), NOT a z-score (z dropped). The headline is the
    # sustained-contrast score; the secondary line surfaces lit-fraction
    # (persistence) and the site radiance.
    _TileSpec("Nightlights", "ghg", "viirs", "score_band", "ghg.viirs.score", "ghg.viirs.confidence",
              score_key="ghg.viirs.score", persistence_key="ghg.viirs.persistence",
              value_key="ghg.viirs.site", value_format="{:.1f}", unit="nW cm⁻² sr⁻¹",
              plain_language="sustained brightness vs. regional background"),
    # NOTE (spec v1.1): ODIAC CO₂ removed from the headline grid as a
    # reference dataset — it stays in the C5b GHG drill-down. M-UI-A6 owns
    # its reference-dataset treatment.
    # --- Nature ---
    _TileSpec("KBA", "nature", "kba", "distance",
              "nature.kba.proximity_score", "nature.kba.confidence",
              dist_km_key="nature.kba.dist_km", overlap_pct_key="nature.kba.overlap_pct",
              centre_format="{:.1f} km", plain_language="to nearest Key Biodiversity Area"),
    _TileSpec("Land cover", "nature", "dw", "categorical",
              "nature.dw.trees_pct", "nature.dw.confidence",
              scheme="dw", category_key="nature.dw.dominant_class",
              class_confidence_key="nature.dw.class_confidence",
              plain_language="dominant land-cover class (Dynamic World)"),
    # NOTE (spec v1.1): Hansen forest loss removed from the headline grid as a
    # reference dataset — it stays in the C5 Nature drill-down. M-UI-A6 owns
    # its reference-dataset treatment.
    _TileSpec("NDVI", "nature", "ndvi", "zscore",
              "nature.ndvi.score", "nature.ndvi.confidence",
              z_key="nature.ndvi.z", value_key="nature.ndvi.mean", value_format="{:.3f}",
              unit="NDVI", plain_language="vegetation vs regional baseline"),
)


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
    # M-AIR-GHG-DEFENSIVE — emitted by engine.core.repeatable_core.site_value
    # when the §0.2 site buffer reduces to no usable pixels.
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
    # M-OCEAN-RING / M-RING-UX — see c9_partial_banner for the rationale.
    "background_ring_no_data": (
        "Background data unavailable — the area around the AOI either "
        "extends over water or has persistent cloud cover / sparse "
        "satellite overpasses (common for very large AOIs in tropical "
        "or polar regions). Try a smaller buffer or a region with "
        "better satellite coverage."
    ),
}


# Severity → (dot CSS, word) for the badge (spec §5.1).
_SEVERITY_STYLE: dict[Severity, tuple[str, str]] = {
    # filled red dot
    "High":    ("background:#dc2626;border:1px solid #dc2626;", "High"),
    # filled amber dot
    "Concern": ("background:#f59e0b;border:1px solid #f59e0b;", "Concern"),
    # green *outline* dot (no fill)
    "Normal":  ("background:transparent;border:1.5px solid #16a34a;", "Normal"),
    # grey dot
    "Sparse":  ("background:#9ca3af;border:1px solid #9ca3af;", "Sparse data"),
}
_SEVERITY_WORD_COLOUR: dict[Severity, str] = {
    "High": "#dc2626", "Concern": "#f59e0b", "Normal": "#16a34a", "Sparse": "#9ca3af",
}


# ---------------------------------------------------------------------------
# Severity + failure resolution (pure — unit-tested)
# ---------------------------------------------------------------------------

def _tile_severity(tile: _TileSpec, payload: dict) -> Severity:
    """Compute the tile's severity by dispatching to the right grammar.

    A failed tile (``_is_failed``) is reported as ``"Sparse"`` for
    snapshot-filter purposes (SR12) — the renderer still draws the dedicated
    failure chrome, but the snapshot partition treats it as non-critical.
    """
    if _is_failed(tile, payload):
        return "Sparse"

    confidence = payload.get(tile.confidence_key) if tile.confidence_key else None
    provenance = payload.get(tile.provenance_key)

    if tile.grammar == "zscore":
        return severity_zscore(payload.get(tile.z_key), confidence, provenance)
    if tile.grammar == "score_band":
        return severity_score_band(payload.get(tile.score_key), confidence, provenance)
    if tile.grammar == "categorical":
        return severity_categorical(
            payload.get(tile.category_key), confidence, provenance,
            scheme=tile.scheme,
        )
    if tile.grammar == "distance":
        return severity_distance(
            payload.get(tile.dist_km_key), payload.get(tile.overlap_pct_key),
            confidence, provenance,
        )
    raise ValueError(f"unknown grammar: {tile.grammar!r}")  # pragma: no cover


def _headline_value(tile: _TileSpec, payload: dict):
    """The grammar's headline value — the one whose absence means 'failed'."""
    if tile.grammar == "zscore":
        return payload.get(tile.z_key)
    if tile.grammar == "score_band":
        return payload.get(tile.score_key)
    if tile.grammar == "categorical":
        return payload.get(tile.category_key)
    if tile.grammar == "distance":
        dist = payload.get(tile.dist_km_key)
        overlap = payload.get(tile.overlap_pct_key)
        return dist if dist is not None else overlap
    raise ValueError(f"unknown grammar: {tile.grammar!r}")  # pragma: no cover


def _is_failed(tile: _TileSpec, payload: dict) -> bool:
    """A tile is failed when its grammar's headline value is None.

    Unlike the prior C4b (which keyed on ``.score``), this reads the
    grammar's headline so NDVI — whose ``.score`` is routinely None in v1
    while its z-score is present — doesn't render as a permanent failure.
    """
    return _headline_value(tile, payload) is None


def _resolve_failure_reason(tile: _TileSpec, payload: dict) -> str:
    """Human-readable failure reason for a failed tile.

    Lookup order: ``_failures[pillar]`` (match on ``<pillar>.<indicator>``)
    → ``_provenance.<pillar>.<indicator>.skipped_reason`` → generic.
    """
    failures = payload.get("_failures", {})
    pillar_failures = failures.get(tile.pillar, [])
    target_id = f"{tile.pillar}.{tile.indicator}"
    for entry in pillar_failures:
        if entry.get("indicator_id") == target_id:
            reason = entry.get("reason")
            if reason:
                return reason

    provenance = payload.get(tile.provenance_key, {}) or {}
    skipped = provenance.get("skipped_reason")
    if skipped:
        return _SKIPPED_REASON_TRANSLATIONS.get(skipped, skipped)

    return "Indicator did not return a value."


# ---------------------------------------------------------------------------
# Snapshot partition (pure — unit-tested) — SR2, SR9
# ---------------------------------------------------------------------------

def _visible_tiles(selected_indicators: set[str]) -> list[_TileSpec]:
    """Tiles whose ``select_key`` is in the user's selection (M-P04)."""
    return [t for t in _TILES if t.select_key in selected_indicators]


def _snapshot_partition(
    tiles: list[_TileSpec], payload: dict,
) -> tuple[list[_TileSpec], list[_TileSpec], dict[str, Severity]]:
    """Split ``tiles`` into (default-visible snapshot, rest, severity map).

    Snapshot = critical tiles (severity ∈ {High, Concern}, SR2), sorted
    most-severe first, topped up to ``_MIN_SNAPSHOT_TILES`` (SR9) with the
    highest-severity non-critical tiles. The "rest" preserves canonical
    order for the "Show all" expander (SR5.4).
    """
    severities = {t.select_key: _tile_severity(t, payload) for t in tiles}

    critical = [t for t in tiles if is_critical(severities[t.select_key])]
    noncritical = [t for t in tiles if not is_critical(severities[t.select_key])]

    # Sort critical by severity (High before Concern); stable within a band.
    critical.sort(key=lambda t: severity_rank(severities[t.select_key]), reverse=True)

    snapshot = list(critical)
    if len(snapshot) < _MIN_SNAPSHOT_TILES:
        topup_pool = sorted(
            noncritical,
            key=lambda t: severity_rank(severities[t.select_key]),
            reverse=True,
        )
        needed = _MIN_SNAPSHOT_TILES - len(snapshot)
        snapshot.extend(topup_pool[:needed])

    snapshot_keys = {t.select_key for t in snapshot}
    rest = [t for t in tiles if t.select_key not in snapshot_keys]
    return snapshot, rest, severities


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_c4b_kpi_grid(payload: dict, selected_indicators: set[str]) -> None:
    """Render the C4b indicator snapshot.

    Only selected indicators render (M-P04). Critical tiles show by default;
    a "Show all indicators" expander reveals the rest (SR2/SR5). The section
    header surfaces the N-of-M filtering (SR5.4).
    """
    visible = _visible_tiles(selected_indicators)
    if not visible:
        return

    snapshot, rest, _ = _snapshot_partition(visible, payload)

    _inject_tile_header_css()

    with st.container(border=True):
        st.markdown(
            f"### Indicator snapshot &nbsp;"
            f"<span style='font-size:0.7em;color:#6b7280;font-weight:400;'>"
            f"{len(snapshot)} critical of {len(visible)} screened</span>",
            unsafe_allow_html=True,
        )
        _render_tile_grid(snapshot, payload)

        if rest:
            with st.expander("Show all indicators", expanded=False):
                st.markdown(
                    f"<div style='opacity:{_EXPANDER_OPACITY};'>",
                    unsafe_allow_html=True,
                )
                _render_tile_grid(rest, payload)
                st.markdown("</div>", unsafe_allow_html=True)


def _inject_tile_header_css() -> None:
    """Stop the tile *header* row (name + severity badge) from wrapping.

    The header uses the shared M-UI-A2 ``render_indicator_name_with_info``
    [4, 2] columns. Streamlit lays those columns out with ``flex-wrap: wrap``;
    when the severity badge ("Concern" / "Sparse data") is wider than its
    33%-basis column, the badge wraps to a second line, doubling the header
    height and pushing the tile's centre metric down — so tiles in the same
    row no longer align (the "+1.2σ" vs "7.3 km" mismatch). Forcing the
    per-tile header row to ``nowrap`` (and vertically centring it) keeps every
    header one line tall so the centres line up.

    Scoped to the C4b tile containers via their ``st-key-c4btile_*`` class
    (``st.container(key=...)``, Streamlit ≥ 1.39) so it can't affect the outer
    responsive grid columns or any other component's layout.
    """
    st.markdown(
        "<style>"
        # The header (name + badge) is the tile's first child: an
        # stLayoutWrapper containing the M-UI-A2 [4, 2] columns. Streamlit
        # renders that wrapper at a variable height (~30px for short tiles,
        # ~58px for others — a flex quirk involving the badge column),
        # shifting the centre metric down so tiles in a row don't align.
        # Clamp both the wrapper and its inner columns row to one line so
        # every header is the same height and the centres line up. `height`
        # is ignored by Streamlit's flex layout here; `max-height` clamps it.
        "[class*='st-key-c4btile_'] [data-testid='stLayoutWrapper'],"
        "[class*='st-key-c4btile_'] [data-testid='stHorizontalBlock']"
        "{flex-wrap:nowrap !important;align-items:center !important;"
        "min-height:0 !important;max-height:1.9rem !important;overflow:visible !important;}"
        # M-UI-A5 — the "View on map →" affordance is now an st.button (it has
        # to set session state; an <a> link can't). Strip the button chrome so
        # it reads like the prior blue text link (MV16: unchanged appearance).
        # Scoped to the per-tile button key so it can't touch other buttons.
        "[class*='st-key-viewmap_'] button"
        "{background:none !important;border:none !important;box-shadow:none !important;"
        "padding:0 !important;min-height:0 !important;height:auto !important;"
        "color:#2563eb !important;font-weight:400 !important;}"
        "[class*='st-key-viewmap_'] button:hover"
        "{text-decoration:underline !important;color:#1d4ed8 !important;}"
        "[class*='st-key-viewmap_'] button p"
        "{font-size:0.8em !important;margin:0 !important;}"
        "</style>",
        unsafe_allow_html=True,
    )


def _tile_container(tile: _TileSpec):
    """Bordered tile container with a per-tile key so the header-nowrap CSS
    (``_inject_tile_header_css``) can scope to C4b tiles only."""
    return st.container(border=True, key=f"c4btile_{tile.pillar}_{tile.indicator}")


def _render_tile_grid(tiles: list[_TileSpec], payload: dict) -> None:
    """Render ``tiles`` in a 4-column responsive grid."""
    cols_per_row = 4
    for row_start in range(0, len(tiles), cols_per_row):
        row_tiles = tiles[row_start:row_start + cols_per_row]
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
    elif tile.grammar == "zscore":
        _render_zscore_tile(tile, payload)
    else:
        _render_natural_metric_tile(tile, payload)


def _severity_badge_html(severity: Severity) -> str:
    """Coloured dot + severity word, right-aligned (SR1 — top-right).

    Uses inline-flex with ``align-items:center`` so the dot and the bold
    word share a vertical centre line — a plain ``vertical-align:middle`` on a
    fixed-size dot reads slightly low against bold text.
    """
    dot_css, word = _SEVERITY_STYLE[severity]
    colour = _SEVERITY_WORD_COLOUR[severity]
    mark = "?" if severity == "Sparse" else ""
    return (
        f"<span style='display:inline-flex;align-items:center;gap:5px;"
        f"white-space:nowrap;line-height:1;'>"
        f"<span style='flex:0 0 auto;width:10px;height:10px;border-radius:50%;"
        f"{dot_css}display:inline-flex;align-items:center;justify-content:center;"
        f"font-size:8px;color:white;'>{mark}</span>"
        f"<span style='color:{colour};font-weight:700;font-size:0.85em;'>"
        f"{word}</span></span>"
    )


def _render_view_on_map(tile: _TileSpec) -> None:
    """The 'View on map →' affordance (SR5 / MV8 / MV16).

    M-UI-A5: converted from an HTML hash-link to an ``st.button``. The old
    ``<a href='#anchor'>`` could scroll but couldn't set Streamlit session
    state (no round-trip), so it can't drive the multi-indicator map's active
    indicator — recon A.5 / R2. The button sets ``active_map_indicator`` to
    this tile's canonical ``select_key`` (which is exactly the map renderer
    key), requests a scroll to the map anchor, and reruns; the map host picks
    up the new active indicator on the next render. Styled to read like the
    prior text link via scoped CSS in ``_inject_tile_header_css`` so the
    visible affordance text and position are unchanged (MV16).

    Rendered with a per-tile key so the styling CSS can scope to it and so
    the (up to 14) buttons don't collide.
    """
    if st.button(
        "View on map →",
        key=f"viewmap_{tile.pillar}_{tile.indicator}",
        type="tertiary",
    ):
        set_active_indicator(tile.select_key)
        request_scroll()
        st.rerun()


def _render_view_trend(tile: _TileSpec) -> None:
    """The 'view trend →' affordance (M-TREND-A2 / UT7), a sibling of
    'View on map →'. Series indicators only — non-series tiles (KBA,
    Dynamic World, ODIAC CO₂, Hansen) carry no link and no substitute
    (decision-log U6). Sets the active trend indicator and routes to the
    dedicated P-06 trend page, which computes the trend on open.
    """
    if not is_series_indicator(tile.select_key):
        return
    if st.button(
        "View trend →",
        key=f"viewtrend_{tile.pillar}_{tile.indicator}",
        type="tertiary",
    ):
        set_active_trend(tile.select_key, tile.display_name)
        st.switch_page("pages/06_Trend_View.py")


def _confidence_line_html(confidence: float | None) -> str:
    glyph = confidence_glyph(confidence)
    return (
        f"<span style='font-size:0.8em;color:#6b7280;'>Confidence "
        f"<span style='font-size:1.1em;'>{glyph}</span></span>"
    )


_DIRECTION_ICON: dict[str, str] = {"above": "▲", "below": "▼", "near": "●"}


def _zscore_framing(direction: str) -> str:
    return {
        "above": "above regional baseline",
        "below": "below regional baseline",
        "near":  "near regional baseline",
    }[direction]


def _tile_header(tile: _TileSpec, severity: Severity) -> None:
    """Name (M-UI-A2 trigger) on the left, severity badge on the right."""
    render_indicator_name_with_info(
        display_name=tile.display_name,
        indicator_id=tile.select_key,
        key_prefix=f"c4b_{tile.pillar}",
        trailing_html=_severity_badge_html(severity),
    )


def _render_zscore_tile(tile: _TileSpec, payload: dict) -> None:
    """Z-score-style tile (spec §5.1): huge centred z, direction, raw values."""
    severity = _tile_severity(tile, payload)
    z = payload.get(tile.z_key)
    confidence = payload.get(tile.confidence_key) if tile.confidence_key else None
    direction = zscore_direction(z)

    with _tile_container(tile):
        _tile_header(tile, severity)

        z_str = f"{z:+.1f}σ" if z is not None else "—"
        st.markdown(
            f"<div style='font-size:2.4em;font-weight:700;padding:8px 0 0 0;"
            f"text-align:center;'>{z_str}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='text-align:center;font-size:0.85em;color:#6b7280;"
            f"margin-bottom:6px;'>{_DIRECTION_ICON[direction]} "
            f"{_zscore_framing(direction)}</div>",
            unsafe_allow_html=True,
        )

        st.markdown(_secondary_line_html(tile, payload), unsafe_allow_html=True)
        st.markdown(_confidence_line_html(confidence), unsafe_allow_html=True)
        _render_view_on_map(tile)
        _render_view_trend(tile)


def _secondary_line_html(tile: _TileSpec, payload: dict) -> str:
    """`Site X · Background Y unit`, or `Site X unit` when no background."""
    value = payload.get(tile.value_key) if tile.value_key else None
    bg = payload.get(tile.background_key) if tile.background_key else None
    unit = f" {tile.unit}" if tile.unit else ""
    if value is None:
        return "<span style='font-size:0.85em;color:#9ca3af;'>—</span>"
    site_str = tile.value_format.format(value)
    if bg is not None:
        bg_str = tile.value_format.format(bg)
        body = f"Site {site_str} · Background {bg_str}{unit}"
    else:
        body = f"Site {site_str}{unit}"
    return f"<span style='font-size:0.85em;color:#6b7280;'>{body}</span>"


def _render_natural_metric_tile(tile: _TileSpec, payload: dict) -> None:
    """Natural-metric tile (spec §5.2): KBA distance / Hansen % / DW class."""
    severity = _tile_severity(tile, payload)
    confidence = payload.get(tile.confidence_key) if tile.confidence_key else None
    centre, secondary = _natural_metric_centre_and_secondary(tile, payload)

    # DW class centre is a word — render slightly smaller than a number.
    centre_size = "1.7em" if tile.grammar == "categorical" and tile.scheme == "dw" else "2.4em"

    with _tile_container(tile):
        _tile_header(tile, severity)

        st.markdown(
            f"<div style='font-size:{centre_size};font-weight:700;padding:8px 0 0 0;"
            f"text-align:center;'>{centre}</div>",
            unsafe_allow_html=True,
        )
        if tile.plain_language:
            st.markdown(
                f"<div style='text-align:center;font-size:0.85em;color:#6b7280;"
                f"margin-bottom:6px;'>{tile.plain_language}</div>",
                unsafe_allow_html=True,
            )
        if secondary:
            st.markdown(
                f"<span style='font-size:0.85em;color:#6b7280;'>{secondary}</span>",
                unsafe_allow_html=True,
            )
        if tile.badge:
            st.markdown(
                f"<span style='font-size:0.72em;color:#9ca3af;background:#f3f4f6;"
                f"padding:1px 6px;border-radius:3px;'>{tile.badge}</span>",
                unsafe_allow_html=True,
            )
        st.markdown(_confidence_line_html(confidence), unsafe_allow_html=True)
        _render_view_on_map(tile)
        _render_view_trend(tile)  # no-op for non-series natural-metric tiles


def _natural_metric_centre_and_secondary(
    tile: _TileSpec, payload: dict,
) -> tuple[str, str]:
    """Return (centre_html, secondary_text) for a natural-metric tile."""
    if tile.grammar == "distance":
        dist = payload.get(tile.dist_km_key)
        overlap = payload.get(tile.overlap_pct_key)
        centre = tile.centre_format.format(dist) if dist is not None else "—"
        if overlap and overlap > 0:
            secondary = f"Buffer overlap: {overlap:.2f}%"
        else:
            secondary = "No buffer overlap"
        return centre, secondary

    if tile.grammar == "categorical" and tile.scheme == "dw":
        klass = payload.get(tile.category_key)
        centre = _DW_CLASS_LABELS.get(klass, klass) if klass else "—"
        cc = payload.get(tile.class_confidence_key) if tile.class_confidence_key else None
        secondary = f"Class confidence: {cc:.0%}" if cc is not None else ""
        return centre, secondary

    if tile.grammar == "score_band":
        # M-GHG-REDESIGN-A1 — headline is the [0,1] sustained-contrast score;
        # secondary surfaces lit-fraction (persistence) and the site radiance.
        score = payload.get(tile.score_key)
        centre = tile.score_format.format(score) if score is not None else "—"
        bits: list[str] = []
        persistence = payload.get(tile.persistence_key) if tile.persistence_key else None
        if persistence is not None:
            bits.append(f"Lit {persistence:.0%} of nights")
        site = payload.get(tile.value_key) if tile.value_key else None
        if site is not None:
            unit = f" {tile.unit}" if tile.unit else ""
            bits.append(f"Site {tile.value_format.format(site)}{unit}")
        return centre, " · ".join(bits)

    return "—", ""  # pragma: no cover


# DW slug → display label (mirrors c5_drilldown._DW_CLASSES labels).
_DW_CLASS_LABELS: dict[str, str] = {
    "trees": "Trees", "grass": "Grass", "crops": "Crops",
    "shrub_and_scrub": "Shrub/scrub", "flooded_vegetation": "Flooded veg.",
    "water": "Water", "built": "Built", "bare": "Bare", "snow_and_ice": "Snow/ice",
}


def _render_failed_tile(tile: _TileSpec, payload: dict) -> None:
    """Failure path (SR12): name + 'Failed' badge, em-dash, expandable reason.

    Restyled to match the new tile chrome. Counts as Sparse for the
    snapshot filter (handled in ``_tile_severity``).
    """
    reason = _resolve_failure_reason(tile, payload)
    failed_badge = (
        "<span style='font-size:0.75em;color:#9ca3af;"
        "background:#f3f4f6;padding:2px 6px;border-radius:3px;"
        "white-space:nowrap;display:inline-block;'>Failed</span>"
    )
    with _tile_container(tile):
        render_indicator_name_with_info(
            display_name=tile.display_name,
            indicator_id=tile.select_key,
            key_prefix=f"c4b_failed_{tile.pillar}",
            trailing_html=failed_badge,
        )
        st.markdown(
            "<div style='font-size:2.4em;font-weight:700;padding:8px 0 0 0;"
            "text-align:center;color:#9ca3af;'>—</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='text-align:center;font-size:0.85em;color:#9ca3af;"
            "margin-bottom:6px;'>no data available</div>",
            unsafe_allow_html=True,
        )
        with st.expander("Why?"):
            st.caption(reason)
            _render_retry_buttons(tile, payload)
        _render_view_on_map(tile)


def _render_retry_buttons(tile: _TileSpec, payload: dict) -> None:
    """M-FALLBACK-A1 §5.3 — fallback retry buttons on a failed tile.

    Shown only for a fallback-eligible indicator (six_step) whose failure is
    a sparse-coverage skip the fallback could plausibly recover. Each button
    triggers a patched re-screening of just this indicator, then reruns the
    page so the grid reflects the recovered value.
    """
    base_id = f"{tile.pillar}.{tile.indicator}"
    if not is_retryable(base_id):
        return
    provenance = payload.get(tile.provenance_key, {}) or {}
    if not reason_is_retryable(provenance.get("skipped_reason")):
        return

    st.caption("Try recovering this indicator with a fallback:")
    col_sppy, col_slide = st.columns(2)
    with col_sppy:
        if st.button(
            "Same-period-previous-year",
            key=f"c4b_retry_sppy_{base_id}",
            use_container_width=True,
        ):
            if apply_retry(base_id, STRATEGY_SPPY):
                st.rerun()
    with col_slide:
        if st.button(
            "Sliding lookback",
            key=f"c4b_retry_slide_{base_id}",
            use_container_width=True,
        ):
            if apply_retry(base_id, STRATEGY_SLIDING):
                st.rerun()
