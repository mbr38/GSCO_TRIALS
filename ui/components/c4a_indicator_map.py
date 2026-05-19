"""C4a — single-indicator map (M-UI-E.6).

Per-indicator visualisation registry. Each indicator gets its own
renderer because their natural visualisations differ fundamentally:
continuous z-rasters for atmospheric measurements (NO₂), vector
polygons for KBA proximity, categorical rasters for Dynamic World, etc.

v1 ships three representative renderers (NO₂, KBA, Dynamic World).
The remaining ~16 indicators each fall into one of those three
grammars; adding them is a v1.x exercise of registering an entry in
``_RENDERERS`` — see ``docs/v1x_followups.md``.

This module assumes Earth Engine has been initialised by the page that
imports it (``utils.ee_init.require_earth_engine``). Follows the
scratch page's geemap idioms verbatim: ``geemap.Map`` →
``add_basemap`` → ``addLayer`` → ``to_streamlit``. No streamlit-folium
wrapper.

Authority: docs/Wireframes_All_v4.md §P-05 C4a (revised M-UI-E.6 spec).
"""

# M-UI-E.6
from __future__ import annotations

import math
from typing import Callable, Sequence

import ee
import geemap.foliumap as geemap
import streamlit as st

from engine.air import AIR_POLLUTANT_CONFIG
from engine.nature import KBA_ASSET_ID


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_c4a_indicator_map(
    indicator_id: str,
    setup: dict,
    result: dict,
) -> None:
    """Dispatch to the registered renderer for ``indicator_id``.

    Unknown indicators surface the "not yet implemented" fallback so
    the page still renders something meaningful. Renderer exceptions
    are caught and surfaced as ``st.error`` — the EE round-trip is the
    likely failure mode and we want the rest of the page (header,
    indicator detail, action bar) to keep rendering.
    """
    renderer = _RENDERERS.get(indicator_id)
    with st.container(border=True):
        st.markdown("### Map")
        if renderer is None:
            _render_unsupported_indicator(indicator_id)
            return
        try:
            renderer(setup, result)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Map render failed: {exc}")


def _render_unsupported_indicator(indicator_id: str) -> None:
    st.info(
        f"Map view for `{indicator_id}` is not implemented in v1. "
        f"The numerical result below is complete; spatial visualisation "
        f"for this indicator lands in v1.x."
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _aoi_geom(centre: dict, radius_km: float) -> ee.Geometry:
    """``ee.Geometry.Point``-then-``.buffer`` AOI used throughout the engine."""
    return (
        ee.Geometry.Point([centre["lon"], centre["lat"]])
        .buffer(radius_km * 1000)
    )


def _zoom_for_radius_km(km: float) -> int:
    """Pick a Leaflet zoom level for ~``km`` visible across the map.

    Heuristic: km at zoom ``z`` ≈ ``156 / 2**(z - 7)``. Solving:
    ``z = 7 + log2(156 / km)``. Clamped to Leaflet's practical range.
    """
    if km <= 0:
        return 12
    z = 7 + math.log2(156 / km)
    return max(5, min(18, round(z)))


def _build_base_map(setup: dict) -> geemap.Map:
    """Centre on the AOI with a ~2× radius margin; draw the buffer outline.

    Returns a configured ``geemap.Map`` with a satellite basemap and
    the AOI buffer rendered as a red outline (same style the scratch
    page uses for the site buffer).
    """
    centre    = setup["centre"]
    radius_km = setup["radius_km"]
    zoom      = _zoom_for_radius_km(radius_km * 2)

    m = geemap.Map(center=[centre["lat"], centre["lon"]], zoom=zoom)
    m.add_basemap("SATELLITE")

    buffer = _aoi_geom(centre, radius_km)
    outline = (
        ee.FeatureCollection([ee.Feature(buffer)])
        .style(color="red", fillColor="00000000", width=2)
    )
    m.addLayer(outline, {}, "AOI buffer")

    # M-UI-E.6 polish — AOI centre marker is universal; every indicator
    # map should show what the screening was anchored on, so it lives on
    # the base map and renderers inherit it for free.
    m.add_marker(
        location=[centre["lat"], centre["lon"]],
        popup="AOI centre",
        icon_color="red",
    )
    return m


def _render_inline_legend(
    palette: Sequence[str],
    labels:  Sequence[str],
) -> None:
    """Render a row of small colour swatches with labels.

    M-UI-E.6 polish — replaces EE's overlaid ``add_colorbar`` so the
    legend sits next to the explanatory prose rather than floating on
    the satellite imagery. Caller chooses ordering and labels; we just
    lay them out in a column grid.
    """
    n = len(palette)
    assert len(labels) == n, "palette and labels must align"
    # 7-stop palettes (NO₂) get a single row; longer (DW's 9 classes)
    # wrap onto a 3-column grid.
    ncols = n if n <= 7 else 3
    cols = st.columns(ncols)
    for i, (colour, label) in enumerate(zip(palette, labels)):
        cols[i % ncols].markdown(
            f"<span style='display:inline-block;width:14px;height:14px;"
            f"background:{colour};margin-right:6px;vertical-align:middle;'>"
            f"</span>"
            f"<span style='vertical-align:middle;font-size:0.9em;'>"
            f"{label}</span>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Renderer 1 — NO₂ continuous z-score raster (Sentinel-5P TROPOMI)
# ---------------------------------------------------------------------------

def _render_no2_map(setup: dict, result: dict) -> None:
    """NO₂ TROPOMI mean composite over the screening window, expressed
    as a per-pixel z-score relative to the AOI buffer's spatial mean.

    Simplification vs the engine: the engine's anomaly uses an annular
    background ring (engine.core.buffers.background_ring). This view
    uses the buffer's own spatial mean as the reference, which is fast
    and good enough for visualising relative hotspots inside the AOI.
    The numeric anomaly/z values in the indicator detail card still
    come from the engine's ring-based computation — they do not have
    to match this layer pixel-for-pixel.
    """
    cfg       = AIR_POLLUTANT_CONFIG["no2"]
    centre    = setup["centre"]
    radius_km = setup["radius_km"]
    time_range = tuple(setup["time_range"])
    aoi = _aoi_geom(centre, radius_km)

    collection = (
        ee.ImageCollection(cfg.asset_id)
        .filterDate(time_range[0], time_range[1])
        .select(cfg.band)
    )
    mean_image = collection.mean().clip(aoi)

    stats = mean_image.reduceRegion(
        reducer=ee.Reducer.mean().combine(
            ee.Reducer.stdDev(), sharedInputs=True,
        ),
        geometry=aoi,
        scale=cfg.scale_m,
        maxPixels=int(1e9),
    )
    mean_val = ee.Number(stats.get(f"{cfg.band}_mean"))
    std_val  = ee.Number(stats.get(f"{cfg.band}_stdDev")).max(1e-12)
    z_image  = mean_image.subtract(mean_val).divide(std_val)

    vis = {
        "min": -3, "max": 3,
        # Diverging ColorBrewer RdBu_r 7-class — colour-blind safe.
        "palette": [
            "#2166ac", "#67a9cf", "#d1e5f0",
            "#f7f7f7",
            "#fddbc7", "#ef8a62", "#b2182b",
        ],
    }

    # M-UI-E.6 polish — pre-map context: prose + inline legend above
    # the visual, no colorbar floating on the satellite imagery.
    st.markdown(
        "**Sentinel-5P TROPOMI NO₂ column density**, mean composite "
        "over the screening window, expressed as the per-pixel z-score "
        "relative to the AOI's spatial mean. Positive values (warm "
        "colours) mark pixels with above-typical NO₂ for this AOI; "
        "negative values (cool colours) mark below-typical pixels. "
        "The scale is bounded at ±3 σ. "
        "*Spatial reference is the buffer itself, not the engine's "
        "annular background ring — see module docstring.*"
    )
    _render_inline_legend(
        palette=vis["palette"],
        labels=["−3σ", "−2σ", "−1σ", "0", "+1σ", "+2σ", "+3σ"],
    )
    st.write("")

    m = _build_base_map(setup)
    m.addLayer(z_image, vis, "NO₂ z-score (±3σ)")
    m.to_streamlit(height=500)


# ---------------------------------------------------------------------------
# Renderer 2 — KBA vector polygons + AOI centre marker
# ---------------------------------------------------------------------------

def _render_kba_map(setup: dict, result: dict) -> None:
    """KBA proximity — KBAs that intersect a ~5× radius bounding box.

    The 5× radius scoop is generous on purpose: when the nearest KBA
    is well outside the buffer, the user still wants to see it on the
    map. Engine stats (distance, overlap) read straight from the
    payload — no recomputation here.
    """
    centre    = setup["centre"]
    radius_km = setup["radius_km"]

    # Bounding box rather than a circular geometry — `filterBounds`
    # cooperates better with a rectangular envelope for vector data.
    extent = (
        ee.Geometry.Point([centre["lon"], centre["lat"]])
        .buffer(radius_km * 5_000)
        .bounds()
    )

    kbas = ee.FeatureCollection(KBA_ASSET_ID).filterBounds(extent)
    styled = kbas.style(color="green", fillColor="16a34a40", width=2)

    # M-UI-E.6 polish — pre-map context: prose + stats above the visual.
    # AOI centre marker is added by _build_base_map; no duplicate here.
    dist_km     = result.get("nature.kba.dist_km")
    overlap_pct = result.get("nature.kba.overlap_pct")
    dist_str    = f"{dist_km:.2f} km" if dist_km is not None else "—"
    overlap_str = f"{overlap_pct:.2f}%" if overlap_pct is not None else "—"
    st.markdown(
        "**Key Biodiversity Areas (BirdLife International)** within "
        "~5× the buffer radius. Green polygons mark the boundaries of "
        "designated areas; the red marker is the AOI centre, the red "
        "ring the screened buffer."
    )
    st.markdown(
        f"Nearest KBA: **{dist_str}** away. "
        f"Buffer overlap: **{overlap_str}**."
    )
    st.write("")

    m = _build_base_map(setup)
    m.addLayer(styled, {}, "Key Biodiversity Areas")
    m.to_streamlit(height=500)


# ---------------------------------------------------------------------------
# Renderer 3 — Dynamic World categorical land cover raster
# ---------------------------------------------------------------------------

# Class ordering matches DW's label values 0-8 (0=Water … 8=Snow/ice)
# so palette index == class label. Don't reorder without remapping
# either side.
_DW_CLASS_NAMES: tuple[str, ...] = (
    "Water", "Trees", "Grass", "Flooded vegetation", "Crops",
    "Shrub/scrub", "Built", "Bare", "Snow/ice",
)
_DW_CLASS_PALETTE: tuple[str, ...] = (
    "#419BDF", "#397D49", "#88B053", "#7A87C6", "#E49635",
    "#DFC35A", "#C4281B", "#A59B8F", "#B39FE1",
)


def _render_dw_map(setup: dict, result: dict) -> None:
    """Dynamic World V1 mode composite over the screening window."""
    centre    = setup["centre"]
    radius_km = setup["radius_km"]
    time_range = tuple(setup["time_range"])
    aoi = _aoi_geom(centre, radius_km)

    dw = (
        ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
        .filterDate(time_range[0], time_range[1])
        .filterBounds(aoi)
        .select("label")
    )
    mode = dw.mode().clip(aoi)

    # M-UI-E.6 polish — pre-map context: prose + dominant-class stat +
    # 9-class legend above the visual. No duplicate legend post-map.
    dominant   = result.get("nature.dw.dominant_class") or "—"
    class_conf = result.get("nature.dw.class_confidence")
    conf_str   = f"{class_conf:.0%}" if class_conf is not None else "—"
    st.markdown(
        "**Dynamic World V1 mode composite** over the screening window. "
        "Each pixel is classified into one of 9 land-cover classes; "
        "the colour palette follows Dynamic World's published convention."
    )
    st.markdown(
        f"Dominant class in the buffer: **{dominant}** "
        f"({conf_str} confidence)."
    )
    _render_inline_legend(
        palette=_DW_CLASS_PALETTE,
        labels=_DW_CLASS_NAMES,
    )
    st.write("")

    m = _build_base_map(setup)
    m.addLayer(
        mode,
        {"min": 0, "max": 8, "palette": list(_DW_CLASS_PALETTE)},
        "Dynamic World land cover",
    )
    m.to_streamlit(height=500)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Maps indicator IDs (the same canonical IDs P-04 / scratch page select)
# to renderers. Add more entries here as v1.x lands additional
# visualisations.
_RENDERERS: dict[str, Callable[[dict, dict], None]] = {
    "air.no2.score":              _render_no2_map,
    "nature.kba.proximity_score": _render_kba_map,
    "nature.dw.trees_pct":        _render_dw_map,
}
