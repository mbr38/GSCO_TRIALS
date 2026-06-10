"""C4a / C4c — indicator map renderers (M-UI-E.6 → M-UI-A5).

Per-indicator spatial visualisation. Each scored indicator has a renderer
because their natural visualisations differ fundamentally: continuous
z-rasters for atmospheric measurements (the 9 Air pollutants + CH₄ + VIIRS),
a raw NDVI field for vegetation, vector polygons for KBA proximity, a
categorical raster for Dynamic World.

Two surfaces share these renderers (M-UI-A5):

  - **Single-indicator inspection** (``render_c4a_indicator_map``) — the
    lean P-05 variant when exactly one indicator was screened. Behaviour is
    unchanged from M-UI-E.6 (MV14).
  - **Multi-indicator map** (``render_multi_indicator_map``) — the primary
    P-05 visualisation, hosted at the anchor between C4b and C5. Starts on
    an empty base map; a tile's "View on map →" affordance sets the active
    indicator (MV8/MV16) and the raster renders here.

**Renderer shape (M-UI-A5).** Each renderer is a *layer builder* returning a
``_LayerSpec`` (the EE object + vis + prose + legend) rather than rendering
the map itself. A single host (``_render_layer_spec``) builds the base map,
fetches the layer's ``getMapId`` tile-URL **through the session cache**
(``multi_map_state.cached_tile_url`` — MV11), and draws it. This is what lets
a repeat click on the same indicator reuse the tiles with no EE round-trip.

**Registry (MV9).** The 9 Air pollutants share one parametric builder
(``_make_air_pollutant_layer`` reading ``AIR_POLLUTANT_CONFIG[key]``); CH₄,
VIIRS, and NDVI are bespoke (different asset families / grammars); KBA and DW
are preserved from M-UI-E.6. Hansen and ODIAC are reference datasets and stay
off the map (MV10) — they have no registry entry.

This module assumes Earth Engine has been initialised by the importing page
(``utils.ee_init.require_earth_engine``). Tile layers are added via folium
(``geemap.foliumap.Map`` is a ``folium.Map``) so a cached tile-URL can be
re-attached without re-calling ``getMapId``; no new map library is introduced
(MV2).

Authority: docs/Wireframes_All_v4.md §P-05 C4a/C4c; docs/M-UI-A5_spec.
"""

# M-UI-A5
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Sequence

import ee
import folium
import geemap.foliumap as geemap
import streamlit as st

from engine.air import AIR_POLLUTANT_CONFIG
from engine.ghg import GHG_INDICATOR_CONFIG
from engine.nature import KBA_ASSET_ID
from ui.components import multi_map_state as mms


# ---------------------------------------------------------------------------
# Layer spec — what a renderer returns (M-UI-A5)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _LayerSpec:
    """Everything needed to render one indicator layer, minus the base map.

    ``image`` is the EE object to tile (an ``ee.Image``, or a styled
    ``FeatureCollection`` — which ``.style()`` returns as an ``ee.Image``);
    ``vis`` is baked into the tiles by ``getMapId(vis)``. ``prose`` and the
    optional inline legend render *above* the map (M-UI-E.6 grammar — no
    colorbar floating on the imagery). ``extra_lines`` are stat / caveat
    markdown lines rendered between the prose and the legend.
    """

    layer_name: str
    image: object
    vis: dict
    prose: str
    legend_palette: Sequence[str] | None = None
    legend_labels: Sequence[str] | None = None
    extra_lines: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Shared helpers (unchanged from M-UI-E.6)
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

    Returns a configured ``geemap.Map`` with a satellite basemap, the AOI
    buffer rendered as a red outline, and the AOI centre marker. Shared by
    every renderer and the empty state so the map looks consistent
    regardless of which indicator (if any) is active.
    """
    centre    = setup["centre"]
    radius_km = setup["radius_km"]
    zoom      = _zoom_for_radius_km(radius_km * 2)

    # ee_initialize=False: the page already called require_earth_engine();
    # geemap's own initialiser uses a private ee.data attribute removed in
    # newer earthengine-api releases.
    m = geemap.Map(center=[centre["lat"], centre["lon"]], zoom=zoom, ee_initialize=False)
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
    the satellite imagery.
    """
    n = len(palette)
    assert len(labels) == n, "palette and labels must align"
    # ≤7-stop palettes get a single row; longer (DW's 9 classes) wrap onto
    # a 3-column grid.
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
# Visualisation grammars — palettes / vis params / prose
# ---------------------------------------------------------------------------

# Diverging ColorBrewer RdBu_r 7-class — colour-blind safe. Used by every
# z-score raster with a meaningful two-sided deviation (Air pollutants, CH₄).
_RDBU_R: tuple[str, ...] = (
    "#2166ac", "#67a9cf", "#d1e5f0", "#f7f7f7", "#fddbc7", "#ef8a62", "#b2182b",
)
_ZSCORE_LABELS: tuple[str, ...] = ("−3σ", "−2σ", "−1σ", "0", "+1σ", "+2σ", "+3σ")
_ZSCORE_VIS: dict = {"min": -3, "max": 3, "palette": list(_RDBU_R)}

# Single-ended sequential YlOrRd for VIIRS — only above-baseline is
# interesting (below-baseline is usually just "no activity"), so the palette
# runs 0 → +3σ rather than diverging (MV9 / §5.3).
_VIIRS_PALETTE: tuple[str, ...] = (
    "#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026",
)
_VIIRS_LABELS: tuple[str, ...] = ("0σ", "", "+1.5σ", "", "+3σ")
_VIIRS_VIS: dict = {"min": 0, "max": 3, "palette": list(_VIIRS_PALETTE)}

# Vegetation brown→green for NDVI — the natural NDVI range, low = bare /
# stressed, high = healthy vegetation (§5.4).
_NDVI_PALETTE: tuple[str, ...] = (
    "#a52a2a", "#d2b48c", "#ffffcc", "#c2e699", "#78c679", "#31a354", "#006837",
)
_NDVI_LABELS: tuple[str, ...] = ("−0.2", "0", "0.2", "0.4", "0.6", "0.8", "0.9")
_NDVI_VIS: dict = {"min": -0.2, "max": 0.9, "palette": list(_NDVI_PALETTE)}

# NDVI asset facts. ``NatureIndicatorConfig`` carries no ``band`` field
# (recon A.4); these mirror engine.nature's NDVI pipeline (MOD13Q1, ×1e-4 to
# physical NDVI — see engine/nature.py NDVI six-step, IC §3.1) so the map
# stays in step with the engine without importing private compute internals.
_NDVI_ASSET: str = "MODIS/061/MOD13Q1"
_NDVI_BAND: str = "NDVI"
_NDVI_SCALE_FACTOR: float = 0.0001

# Air pollutant display names + the measurement phrase used in the prose.
_AIR_DISPLAY: dict[str, tuple[str, str]] = {
    "no2":  ("NO₂", "column density"),
    "so2":  ("SO₂", "column density"),
    "co":   ("CO", "column density"),
    "hcho": ("HCHO", "column density"),
    "o3":   ("O₃", "total column"),
    "aai":  ("Absorbing Aerosol Index", "index"),
    "pm25": ("PM₂.₅", "surface concentration"),
    "pm10": ("PM₁₀", "surface concentration"),
    "aod":  ("Aerosol Optical Depth", "optical depth"),
}


def _air_source_label(pollutant_key: str) -> str:
    """Human asset-family label for the prose, per pollutant family (recon A.2)."""
    if pollutant_key in ("pm25", "pm10"):
        return "ECMWF CAMS"
    if pollutant_key == "aod":
        return "MODIS MAIAC"
    return "Sentinel-5P TROPOMI"


def _air_extra_lines(pollutant_key: str) -> tuple[str, ...]:
    """Per-family caveat lines (Step B: CAMS PM coarse-grid note; MAIAC QA)."""
    if pollutant_key in ("pm25", "pm10"):
        return (
            "_CAMS is a ~44 km global model grid; at typical AOI sizes the map "
            "shows the regional concentration field, not site-scale structure._",
        )
    if pollutant_key == "aod":
        return ("_Best-quality MAIAC retrievals only (AOD_QA-masked)._",)
    return ()


def _zscore_prose(source: str, name: str, phrase: str) -> str:
    """Shared z-score raster prose. ``no2`` reproduces the M-UI-E.6 text."""
    return (
        f"**{source} {name} {phrase}**, mean composite over the screening "
        f"window, expressed as the per-pixel z-score relative to the AOI's "
        f"spatial mean. Positive values (warm colours) mark pixels with "
        f"above-typical {name} for this AOI; negative values (cool colours) "
        f"mark below-typical pixels. The scale is bounded at ±3 σ. "
        f"*Spatial reference is the buffer itself, not the engine's annular "
        f"background ring — see module docstring.*"
    )


# ---------------------------------------------------------------------------
# EE image builders
# ---------------------------------------------------------------------------

def _zscore_image(
    asset_id: str,
    band: str,
    time_range: tuple[str, str],
    aoi: ee.Geometry,
    scale_m: float,
    preprocess: Callable[[ee.Image], ee.Image] | None = None,
) -> ee.Image:
    """Mean composite over ``time_range``, as a per-pixel z-score vs the AOI.

    Factored out of the M-UI-E.6 NO₂ renderer so the parametric Air builder
    and the CH₄ / VIIRS builders all share one implementation. ``preprocess``
    (e.g. MODIS MAIAC's AOD_QA mask) runs *before* band selection so it can
    read auxiliary QA bands — matching the engine's snapshot pipeline.
    """
    ic = ee.ImageCollection(asset_id).filterDate(time_range[0], time_range[1])
    if preprocess is not None:
        ic = ic.map(preprocess)
    ic = ic.select(band)
    mean_image = ic.mean().clip(aoi)

    stats = mean_image.reduceRegion(
        reducer=ee.Reducer.mean().combine(
            ee.Reducer.stdDev(), sharedInputs=True,
        ),
        geometry=aoi,
        scale=scale_m,
        maxPixels=int(1e9),
    )
    mean_val = ee.Number(stats.get(f"{band}_mean"))
    std_val  = ee.Number(stats.get(f"{band}_stdDev")).max(1e-12)
    return mean_image.subtract(mean_val).divide(std_val)


# ---------------------------------------------------------------------------
# Renderer 1 — parametric Air pollutant z-score raster (9 pollutants, MV9)
# ---------------------------------------------------------------------------

def _make_air_pollutant_layer(
    pollutant_key: str,
) -> Callable[[dict, dict], _LayerSpec]:
    """Factory returning a z-score-raster layer builder for one Air pollutant.

    Closes over ``pollutant_key`` and reads ``AIR_POLLUTANT_CONFIG[key]`` at
    render time. Covers all three Air families (recon A.2): the 7 Sentinel-5P
    gases, the 2 CAMS PM bands, and MODIS MAIAC AOD. The only family branch
    is ``cfg.preprocess`` (AOD's QA mask), threaded into ``_zscore_image``;
    PM's coarse 44 km grid is handled by a prose caveat, not a code path.
    """
    def _layer(setup: dict, result: dict) -> _LayerSpec:
        cfg = AIR_POLLUTANT_CONFIG[pollutant_key]
        aoi = _aoi_geom(setup["centre"], setup["radius_km"])
        z = _zscore_image(
            cfg.asset_id, cfg.band, tuple(setup["time_range"]),
            aoi, cfg.scale_m, cfg.preprocess,
        )
        name, phrase = _AIR_DISPLAY[pollutant_key]
        return _LayerSpec(
            layer_name=f"{name} z-score (±3σ)",
            image=z,
            vis=_ZSCORE_VIS,
            prose=_zscore_prose(_air_source_label(pollutant_key), name, phrase),
            legend_palette=_RDBU_R,
            legend_labels=_ZSCORE_LABELS,
            extra_lines=_air_extra_lines(pollutant_key),
        )

    return _layer


# ---------------------------------------------------------------------------
# Renderer 2 — CH₄ z-score raster (Sentinel-5P TROPOMI, GHG config) §5.2
# ---------------------------------------------------------------------------

def _ch4_layer(setup: dict, result: dict) -> _LayerSpec:
    """CH₄ column-averaged mixing ratio — same z-score grammar as Air, but
    reading from ``GHG_INDICATOR_CONFIG`` (recon A.3)."""
    cfg = GHG_INDICATOR_CONFIG["ch4"]
    aoi = _aoi_geom(setup["centre"], setup["radius_km"])
    z = _zscore_image(
        cfg.asset_id, cfg.band, tuple(setup["time_range"]), aoi, cfg.scale_m,
    )
    return _LayerSpec(
        layer_name="CH₄ z-score (±3σ)",
        image=z,
        vis=_ZSCORE_VIS,
        prose=(
            "**Sentinel-5P TROPOMI CH₄ column-averaged mixing ratio**, mean "
            "composite over the screening window, expressed as the per-pixel "
            "z-score relative to the AOI's spatial mean. Positive values mark "
            "pixels with above-typical methane; negative values mark "
            "below-typical pixels. The scale is bounded at ±3 σ."
        ),
        legend_palette=_RDBU_R,
        legend_labels=_ZSCORE_LABELS,
    )


# ---------------------------------------------------------------------------
# Renderer 3 — VIIRS nightlights z-score raster (single-ended) §5.3
# ---------------------------------------------------------------------------

def _viirs_layer(setup: dict, result: dict) -> _LayerSpec:
    """VIIRS nighttime lights — z-score raster with a single-ended palette
    (only above-baseline activity is interesting)."""
    cfg = GHG_INDICATOR_CONFIG["viirs"]
    aoi = _aoi_geom(setup["centre"], setup["radius_km"])
    z = _zscore_image(
        cfg.asset_id, cfg.band, tuple(setup["time_range"]), aoi, cfg.scale_m,
    )
    return _LayerSpec(
        layer_name="Nightlights z-score (0..+3σ)",
        image=z,
        vis=_VIIRS_VIS,
        prose=(
            "**VIIRS nighttime lights**, mean composite over the screening "
            "window, expressed as the per-pixel z-score relative to the AOI's "
            "spatial mean. Higher values mark pixels with above-typical "
            "anthropogenic activity. This is a proxy for industrial / urban "
            "activity, not a direct pollution measurement."
        ),
        legend_palette=_VIIRS_PALETTE,
        legend_labels=_VIIRS_LABELS,
    )


# ---------------------------------------------------------------------------
# Renderer 4 — NDVI raw vegetation field (MODIS MOD13Q1) §5.4
# ---------------------------------------------------------------------------

def _ndvi_layer(setup: dict, result: dict) -> _LayerSpec:
    """MODIS NDVI mean composite — the *raw* NDVI field (not the z-score
    deviation the C4b tile scores; complementary views, §5.4)."""
    aoi = _aoi_geom(setup["centre"], setup["radius_km"])
    time_range = tuple(setup["time_range"])
    ndvi = (
        ee.ImageCollection(_NDVI_ASSET)
        .filterDate(time_range[0], time_range[1])
        .filterBounds(aoi)
        .select(_NDVI_BAND)
        .mean()
        .multiply(_NDVI_SCALE_FACTOR)
        .clip(aoi)
    )
    return _LayerSpec(
        layer_name="NDVI (MOD13Q1)",
        image=ndvi,
        vis=_NDVI_VIS,
        prose=(
            "**MODIS NDVI vegetation index (MOD13Q1)**, mean composite over "
            "the screening window. Greener values indicate healthier "
            "vegetation; browner values indicate sparse or stressed "
            "vegetation. The scale is the natural NDVI range (~−0.2 to ~0.9)."
        ),
        legend_palette=_NDVI_PALETTE,
        legend_labels=_NDVI_LABELS,
        extra_lines=(
            "_The C4b NDVI tile scores the z-score deviation from the regional "
            "baseline; this map shows the raw NDVI field — complementary views._",
        ),
    )


# ---------------------------------------------------------------------------
# Renderer 5 — KBA vector polygons (preserved from M-UI-E.6)
# ---------------------------------------------------------------------------

def _kba_layer(setup: dict, result: dict) -> _LayerSpec:
    """KBA proximity — KBAs that intersect a ~5× radius bounding box.

    The 5× scoop is generous on purpose: when the nearest KBA is well outside
    the buffer, the user still wants to see it. Engine stats read straight
    from the payload — no recomputation.
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

    dist_km     = result.get("nature.kba.dist_km")
    overlap_pct = result.get("nature.kba.overlap_pct")
    dist_str    = f"{dist_km:.2f} km" if dist_km is not None else "—"
    overlap_str = f"{overlap_pct:.2f}%" if overlap_pct is not None else "—"
    return _LayerSpec(
        layer_name="Key Biodiversity Areas",
        image=styled,
        vis={},
        prose=(
            "**Key Biodiversity Areas (BirdLife International)** within ~5× "
            "the buffer radius. Green polygons mark the boundaries of "
            "designated areas; the red marker is the AOI centre, the red ring "
            "the screened buffer."
        ),
        extra_lines=(
            f"Nearest KBA: **{dist_str}** away. Buffer overlap: **{overlap_str}**.",
        ),
    )


# ---------------------------------------------------------------------------
# Renderer 6 — Dynamic World categorical land cover (preserved from M-UI-E.6)
# ---------------------------------------------------------------------------

# Class ordering matches DW's label values 0-8 (0=Water … 8=Snow/ice) so
# palette index == class label. Don't reorder without remapping either side.
_DW_CLASS_NAMES: tuple[str, ...] = (
    "Water", "Trees", "Grass", "Flooded vegetation", "Crops",
    "Shrub/scrub", "Built", "Bare", "Snow/ice",
)
_DW_CLASS_PALETTE: tuple[str, ...] = (
    "#419BDF", "#397D49", "#88B053", "#7A87C6", "#E49635",
    "#DFC35A", "#C4281B", "#A59B8F", "#B39FE1",
)


def _dw_layer(setup: dict, result: dict) -> _LayerSpec:
    """Dynamic World V1 mode composite over the screening window."""
    aoi = _aoi_geom(setup["centre"], setup["radius_km"])
    time_range = tuple(setup["time_range"])
    dw = (
        ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
        .filterDate(time_range[0], time_range[1])
        .filterBounds(aoi)
        .select("label")
    )
    mode = dw.mode().clip(aoi)

    dominant   = result.get("nature.dw.dominant_class") or "—"
    class_conf = result.get("nature.dw.class_confidence")
    conf_str   = f"{class_conf:.0%}" if class_conf is not None else "—"
    return _LayerSpec(
        layer_name="Dynamic World land cover",
        image=mode,
        vis={"min": 0, "max": 8, "palette": list(_DW_CLASS_PALETTE)},
        prose=(
            "**Dynamic World V1 mode composite** over the screening window. "
            "Each pixel is classified into one of 9 land-cover classes; the "
            "colour palette follows Dynamic World's published convention."
        ),
        legend_palette=_DW_CLASS_PALETTE,
        legend_labels=_DW_CLASS_NAMES,
        extra_lines=(
            f"Dominant class in the buffer: **{dominant}** ({conf_str} confidence).",
        ),
    )


# ---------------------------------------------------------------------------
# M-ATTRIB-A1 — habitat-conversion attributability overlay (§5.1/§5.2)
# ---------------------------------------------------------------------------

# Map indicator id for the habitat-conversion attributability overlay. This
# establishes the marker + line + hover-tooltip pattern that M-WIND-A1 v2.0
# reuses for Air attributability (AT19/AT21).
_HABITAT_MAP_KEY: str = "nature.habitat.conversion_score"

# AT9 — folium AwesomeMarkers icon colours (named, not hex) + matching line
# hex. Sparse renders nothing.
_ATTRIB_MARKER_ICON_COLOUR: dict[str, str] = {
    "high": "green", "moderate": "orange", "low": "red",
}
_ATTRIB_LINE_HEX: dict[str, str] = {
    "high": "#16a34a", "moderate": "#f59e0b", "low": "#dc2626",
}
_ATTRIB_STATE_LABEL: dict[str, str] = {
    "high": "High", "moderate": "Moderate", "low": "Low",
}


def _habitat_centroid_tooltip(state: str, offset_km, n_change) -> str:
    """§5.2 — hover tooltip text for the change-centroid marker."""
    dist = f"{offset_km:.1f}" if offset_km is not None else "?"
    label = _ATTRIB_STATE_LABEL.get(state, state)
    return (
        f"Habitat changes centred {dist} km from supplier — "
        f"{label} attributability. N = {n_change or 0} change pixels."
    )


def _habitat_overlay_elements(setup: dict, result: dict) -> list:
    """Build the folium elements for the habitat attributability overlay.

    Returns a coloured centroid `folium.Marker` (with hover tooltip) and a
    `folium.PolyLine` from the supplier centre to the centroid, both
    colour-coded by attributability state (AT9). Returns ``[]`` when the
    state is sparse / absent or no centroid was located — nothing renders.
    Split from the render path so the construction is unit-testable.
    """
    state = result.get("nature.habitat.attributability_state")
    if state not in _ATTRIB_MARKER_ICON_COLOUR:        # high / moderate / low only
        return []
    lat = result.get("nature.supplier_spatial_link.centroid_lat")
    lon = result.get("nature.supplier_spatial_link.centroid_lon")
    if lat is None or lon is None:
        return []
    offset = result.get("nature.supplier_spatial_link.centroid_offset_km")
    n_change = result.get("nature.supplier_spatial_link.n_change_pixels")
    centre = setup["centre"]
    tooltip = _habitat_centroid_tooltip(state, offset, n_change)

    marker = folium.Marker(
        location=[lat, lon],
        tooltip=tooltip,
        icon=folium.Icon(color=_ATTRIB_MARKER_ICON_COLOUR[state], icon="leaf"),
    )
    line = folium.PolyLine(
        locations=[[centre["lat"], centre["lon"]], [lat, lon]],
        color=_ATTRIB_LINE_HEX[state],
        weight=3,
        opacity=0.8,
        tooltip=tooltip,
    )
    return [marker, line]


def _habitat_overlay_prose(result: dict) -> str:
    """One-line explainer above the habitat attributability map."""
    state = result.get("nature.habitat.attributability_state")
    if state == "sparse":
        return (
            "**Habitat conversion — attributability.** Too few habitat-change "
            "pixels to locate a change centroid (sparse); no centroid is drawn."
        )
    if state in _ATTRIB_STATE_LABEL:
        offset = result.get("nature.supplier_spatial_link.centroid_offset_km")
        dist = f"{offset:.1f} km" if offset is not None else "—"
        return (
            "**Habitat conversion — attributability.** The coloured marker is "
            f"the centroid of detected natural→non-natural change ({dist} from "
            "the supplier); the line links it to the supplier coordinate. "
            "Colour = attributability (green/amber/red). This is context only — "
            "it does not enter the composite score."
        )
    return (
        "**Habitat conversion — attributability.** No attributability state "
        "available for this screening."
    )


def _render_habitat_attributability_map(setup: dict, result: dict) -> None:
    """Render the habitat-conversion attributability overlay (§5.1).

    Habitat conversion has no single raster layer (it's a DW class-delta
    aggregate), so this path draws the base map plus the centroid marker +
    supplier→centroid line + hover tooltip rather than a tile layer.
    """
    st.markdown(_habitat_overlay_prose(result))
    st.write("")
    m = _build_base_map(setup)
    # Supplier "label" on hover, parallel to the centroid marker (§5.1).
    centre = setup["centre"]
    folium.Marker(
        location=[centre["lat"], centre["lon"]],
        tooltip="Supplier coordinate",
        icon=folium.Icon(color="gray", icon="industry", prefix="fa"),
    ).add_to(m)
    for element in _habitat_overlay_elements(setup, result):
        element.add_to(m)
    m.to_streamlit(height=500)


# ---------------------------------------------------------------------------
# M-WIND-A1 v2.0 — wind attributability overlay (§6.1/§6.2)
# ---------------------------------------------------------------------------

# The five in-scope indicators (WA2): NO₂, SO₂, HCHO, AAI, AOD. Keyed by the
# canonical map indicator id (the .score variant) so dispatch can match the
# registry key directly. The base ID (e.g. "air.no2") is the provenance key.
_WIND_ATTRIBUTABILITY_MAP_KEYS: dict[str, str] = {
    "air.no2.score":  "air.no2",
    "air.so2.score":  "air.so2",
    "air.hcho.score": "air.hcho",
    "air.aai.score":  "air.aai",
    "air.aod.score":  "air.aod",
}

# WA12 — arrow colour scheme. Green / amber / red, matching the M-UI-A4 and
# M-ATTRIB-A1 severity grammar so the user reads "green = attribution OK,
# amber = caution, red = wind suggests external source".
_WIND_ARROW_HEX: dict[str, str] = {
    "high":     "#16a34a",
    "moderate": "#f59e0b",
    "low":      "#dc2626",
}

# WA17–WA19 — per-category hover copy. ``{speed}``, ``{ratio}``, ``{n_days}``
# get interpolated against the provenance numbers; the all-calm variant
# replaces the ratio line entirely.
#
# M-UI-WIND-TOOLTIP (29 May 2026) — tooltip text was getting cut off in
# the Leaflet hover bubble at the default ~200px max-width. Compressed
# from full sentences to a "Label — facts" idiom (~70 chars typical) and
# the rendering at `_wind_overlay_elements` now wraps the string in a
# folium.Tooltip with explicit max-width + white-space:normal so the
# wrap behaviour is deterministic.
_WIND_TOOLTIP_TEMPLATE_BY_STATE: dict[str, str] = {
    "high":     "<b>High attribution</b> — calm wind ({speed:.1f} m/s), symmetric ring (ratio {ratio:.2f}). {n_days} anomaly days.",
    "moderate": "<b>Moderate attribution</b> — {speed:.1f} m/s wind, ratio {ratio:.2f}. {n_days} anomaly days.",
    "low":      "<b>Low attribution</b> — wind suggests external sources. {speed:.1f} m/s, ratio {ratio:.2f}. {n_days} anomaly days.",
}
_WIND_TOOLTIP_ALL_CALM_TEMPLATE_BY_STATE: dict[str, str] = {
    "high":     "<b>High attribution</b> — all anomaly days calm (mean {speed:.1f} m/s). {n_days} anomaly days.",
    "moderate": "<b>Moderate attribution</b> — mostly calm. {speed:.1f} m/s. {n_days} anomaly days.",
    "low":      "<b>Low attribution</b> — wind suggests external sources. {speed:.1f} m/s. {n_days} anomaly days.",
}

# M-UI-WIND-TOOLTIP — explicit Leaflet tooltip style. Without this the
# default ~200-250px max-width truncated the longer "moderate"/"low"
# strings to a single ellipsised line. The white-space:normal flag is
# what lets the text wrap instead of clipping; max-width caps the bubble
# so it doesn't grow to span the viewport.
_WIND_TOOLTIP_STYLE: str = (
    "max-width:340px;"
    "white-space:normal;"
    "word-wrap:break-word;"
    "font-size:12px;"
    "line-height:1.35;"
    "padding:6px 8px;"
)

# Arrow length in kilometres, derived from the AOI buffer radius so the
# arrow always extends a little past the outline at any zoom level.
# Spec WA11 says "fixed visual length ~30 pixels at base zoom" — we keep
# this AOI-scaled so the user sees the arrow regardless of buffer size.
_WIND_ARROW_LENGTH_MULTIPLE: float = 2.0
_WIND_ARROW_MIN_LENGTH_KM:   float = 8.0


def _wind_overlay_provenance_extra(
    result: dict, indicator_id: str,
) -> dict | None:
    """Return the wind ``provenance.extra`` dict for ``indicator_id`` or None.

    Reads the canonical ``_provenance.air.{pollutant}`` block, drills into
    its ``extra`` field, and returns it. Returns None when the indicator is
    out of scope, the provenance block is missing, or the wind fields
    aren't present (e.g. a six_step bypass for a skipped pollutant).
    """
    base_id = _WIND_ATTRIBUTABILITY_MAP_KEYS.get(indicator_id)
    if base_id is None:
        return None
    prov = result.get(f"_provenance.{base_id}")
    if not isinstance(prov, dict):
        return None
    extra = prov.get("extra")
    if not isinstance(extra, dict):
        return None
    if "wind_attributability_state" not in extra:
        return None
    return extra


def _haversine_destination(
    centre: dict, bearing_deg: float, distance_km: float,
) -> tuple[float, float]:
    """Return ``(lat, lon)`` ``distance_km`` from ``centre`` along ``bearing_deg``."""
    earth_radius_km = 6371.0088
    lat0 = math.radians(centre["lat"])
    lon0 = math.radians(centre["lon"])
    angular_distance = distance_km / earth_radius_km
    bearing = math.radians(bearing_deg)
    lat = math.asin(
        math.sin(lat0) * math.cos(angular_distance)
        + math.cos(lat0) * math.sin(angular_distance) * math.cos(bearing)
    )
    lon = lon0 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat0),
        math.cos(angular_distance) - math.sin(lat0) * math.sin(lat),
    )
    return math.degrees(lat), math.degrees(lon)


def _format_wind_tooltip(extra: dict) -> str:
    """Build the hover-tooltip string from the wind ``provenance.extra`` dict."""
    state = extra.get("wind_attributability_state")
    speed = extra.get("wind_mean_speed_ms")
    ratio = extra.get("wind_mean_asymmetry_ratio")
    n_days = extra.get("wind_n_anomaly_days") or 0
    if state not in _WIND_ARROW_HEX:
        return ""
    if ratio is None:
        template = _WIND_TOOLTIP_ALL_CALM_TEMPLATE_BY_STATE[state]
        return template.format(
            speed=speed if speed is not None else 0.0, n_days=n_days,
        )
    template = _WIND_TOOLTIP_TEMPLATE_BY_STATE[state]
    return template.format(
        speed=speed if speed is not None else 0.0,
        ratio=ratio,
        n_days=n_days,
    )


def _wind_arrow_div_icon(colour_hex: str, bearing_deg: float):
    """SVG arrowhead marker rotated to ``bearing_deg`` (compass degrees).

    Used at the tip of the wind PolyLine. The marker is anchored at its
    centre so it sits exactly on the polyline endpoint when rotated.
    Bearing is converted to CSS-rotation degrees (CSS 0° points up = North,
    matches compass convention) — no conversion needed.
    """
    svg = (
        f"<div style=\"transform: rotate({bearing_deg}deg); transform-origin: 50% 50%;"
        f"width: 18px; height: 18px; line-height: 18px; text-align: center;\">"
        f"<svg width=\"18\" height=\"18\" viewBox=\"0 0 18 18\""
        f" xmlns=\"http://www.w3.org/2000/svg\">"
        f"<polygon points=\"9,0 16,16 9,12 2,16\" fill=\"{colour_hex}\""
        f" stroke=\"white\" stroke-width=\"1\" />"
        f"</svg></div>"
    )
    return folium.DivIcon(
        html=svg,
        icon_size=(18, 18),
        icon_anchor=(9, 9),
    )


def _wind_overlay_elements(setup: dict, result: dict, indicator_id: str) -> list:
    """Build the folium elements for the wind attributability overlay.

    Returns a ``folium.PolyLine`` shaft and a ``folium.Marker`` with a
    rotated SVG arrowhead, both colour-coded by ``wind_attributability_state``
    (WA11/WA12). Returns ``[]`` when the indicator is out of scope, the
    state is sparse, or wind direction is unavailable (all-calm anomaly
    days — spec §6.1 says "no arrow rendered" in the sparse case; for the
    all-calm-but-high case the wind has no direction so we skip the arrow
    too, surfacing the High state via the absence of an amber/red arrow
    per WA16).
    """
    extra = _wind_overlay_provenance_extra(result, indicator_id)
    if extra is None:
        return []
    state = extra.get("wind_attributability_state")
    if state not in _WIND_ARROW_HEX:        # high / moderate / low — sparse skipped
        return []
    bearing = extra.get("wind_mean_direction_deg")
    if bearing is None:
        # All-calm: no direction → no arrow. Hover tooltip on the C5
        # expander still surfaces the state; visual layer has nothing
        # meaningful to render.
        return []

    centre = setup["centre"]
    arrow_length_km = max(
        setup.get("radius_km", 0.0) * _WIND_ARROW_LENGTH_MULTIPLE,
        _WIND_ARROW_MIN_LENGTH_KM,
    )
    tip_lat, tip_lon = _haversine_destination(centre, bearing, arrow_length_km)
    tooltip_text = _format_wind_tooltip(extra)
    colour = _WIND_ARROW_HEX[state]

    # M-UI-WIND-TOOLTIP — wrap the string in folium.Tooltip with explicit
    # max-width + white-space:normal so longer "moderate"/"low" strings
    # wrap instead of clipping. `sticky=True` keeps the bubble open while
    # the cursor traces along the polyline (matters most for the shaft).
    # The text is interpreted as HTML by Leaflet (folium's Tooltip default),
    # so the templated <b>…</b> tags render as bold without further opts.
    def _make_tooltip() -> folium.Tooltip:
        return folium.Tooltip(
            tooltip_text,
            sticky=True,
            style=_WIND_TOOLTIP_STYLE,
        )

    shaft = folium.PolyLine(
        locations=[[centre["lat"], centre["lon"]], [tip_lat, tip_lon]],
        color=colour,
        weight=4,
        opacity=0.9,
        tooltip=_make_tooltip(),
    )
    head = folium.Marker(
        location=[tip_lat, tip_lon],
        icon=_wind_arrow_div_icon(colour, bearing),
        tooltip=_make_tooltip(),
    )
    return [shaft, head]


# ---------------------------------------------------------------------------
# Registry — 14 scored tiles (MV9). Keys == C4b tile select_keys, so the
# "View on map →" affordance can dispatch by the value it sets verbatim.
# Hansen + ODIAC are reference datasets and deliberately absent (MV10).
# ---------------------------------------------------------------------------

_RENDERERS: dict[str, Callable[[dict, dict], _LayerSpec]] = {
    # Air — one parametric builder per pollutant.
    "air.no2.score":  _make_air_pollutant_layer("no2"),
    "air.so2.score":  _make_air_pollutant_layer("so2"),
    "air.co.score":   _make_air_pollutant_layer("co"),
    "air.hcho.score": _make_air_pollutant_layer("hcho"),
    "air.o3.score":   _make_air_pollutant_layer("o3"),
    "air.aai.score":  _make_air_pollutant_layer("aai"),
    "air.pm25.score": _make_air_pollutant_layer("pm25"),
    "air.pm10.score": _make_air_pollutant_layer("pm10"),
    "air.aod.score":  _make_air_pollutant_layer("aod"),
    # GHG — bespoke.
    "ghg.ch4.score":   _ch4_layer,
    "ghg.viirs.score": _viirs_layer,
    # Nature.
    "nature.kba.proximity_score": _kba_layer,
    "nature.dw.trees_pct":        _dw_layer,
    "nature.ndvi.score":          _ndvi_layer,
}


# ---------------------------------------------------------------------------
# Rendering — shared dispatch + cache-aware layer host
# ---------------------------------------------------------------------------

def _render_unsupported_indicator(indicator_id: str) -> None:
    st.info(
        f"Map view for `{indicator_id}` is not implemented in v1. "
        f"The numerical result below is complete; spatial visualisation "
        f"for this indicator lands in v1.x."
    )


def _get_tile_url(image: object, vis: dict) -> str:
    """The Earth Engine round-trip: ``getMapId`` → XYZ tile-URL template.

    Isolated so the cache (``multi_map_state.cached_tile_url``) can call it as
    a thunk only on a miss, and so the rest of the module stays EE-free for
    unit tests.
    """
    map_id = ee.Image(image).getMapId(vis)
    return map_id["tile_fetcher"].url_format


def _current_run_id() -> str:
    """Cache key / invalidation signal — the screening's ``page_state.run_id``
    (recon A.8). Stable across reruns of one screening, fresh per screening.
    """
    state = st.session_state.get("page_state")
    return getattr(state, "run_id", "no-run") if state is not None else "no-run"


def _render_layer_spec(
    spec: _LayerSpec,
    setup: dict,
    indicator_id: str,
    run_id: str,
    *,
    result: dict | None = None,
    apply_overlays: bool = False,
) -> None:
    """Render prose + legend + base map + the (cached) indicator tile layer.

    M-WIND-A1 v2.0 — when ``apply_overlays=True`` (the multi-indicator path
    only; single-indicator inspection stays unchanged per WA25), the wind
    arrow overlay is added on top of the tile layer for the five in-scope
    indicators. ``result`` is required when ``apply_overlays`` is True so
    the wind ``provenance.extra`` block can be read.
    """
    st.markdown(spec.prose)
    for line in spec.extra_lines:
        st.markdown(line, unsafe_allow_html=True)
    if spec.legend_palette is not None:
        _render_inline_legend(spec.legend_palette, spec.legend_labels)
    st.write("")

    m = _build_base_map(setup)
    tile_url = mms.cached_tile_url(
        st.session_state, run_id, indicator_id,
        lambda: _get_tile_url(spec.image, spec.vis),
    )
    folium.raster_layers.TileLayer(
        tiles=tile_url,
        attr="Google Earth Engine",
        name=spec.layer_name,
        overlay=True,
        control=True,
        max_zoom=24,
    ).add_to(m)
    if apply_overlays and result is not None:
        for element in _wind_overlay_elements(setup, result, indicator_id):
            element.add_to(m)
    m.to_streamlit(height=500)


def _dispatch(
    indicator_id: str,
    setup: dict,
    result: dict,
    run_id: str,
    *,
    apply_overlays: bool = False,
) -> None:
    """Look up + render the layer for ``indicator_id``.

    Unknown indicators surface the "not yet implemented" fallback; renderer
    exceptions are caught and surfaced as ``st.error`` (the EE round-trip is
    the likely failure mode) so the rest of the page keeps rendering.

    M-WIND-A1 v2.0 — ``apply_overlays`` is True only on the multi-indicator
    map path (``render_multi_indicator_map``). The single-indicator
    inspection view (``render_c4a_indicator_map``) leaves it False so its
    behaviour is unchanged (WA25).
    """
    # M-ATTRIB-A1 (§5.1): habitat conversion has no raster layer — route it to
    # the attributability overlay (centroid marker + supplier→centroid line +
    # hover tooltip) instead of the cached-tile raster path.
    if indicator_id == _HABITAT_MAP_KEY:
        try:
            _render_habitat_attributability_map(setup, result)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Map render failed: {exc}")
        return

    builder = _RENDERERS.get(indicator_id)
    if builder is None:
        _render_unsupported_indicator(indicator_id)
        return
    try:
        spec = builder(setup, result)
        _render_layer_spec(
            spec, setup, indicator_id, run_id,
            result=result, apply_overlays=apply_overlays,
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"Map render failed: {exc}")


# ---------------------------------------------------------------------------
# Public entry point 1 — single-indicator inspection view (MV14, unchanged)
# ---------------------------------------------------------------------------

def render_c4a_indicator_map(
    indicator_id: str,
    setup: dict,
    result: dict,
) -> None:
    """Render the single-indicator inspection map (lean P-05 variant).

    Behaviourally unchanged from M-UI-E.6: a bordered container with a "Map"
    header and the indicator's raster. It opportunistically shares the
    session tile cache (MV14) but reads no ``active_map_indicator`` state, so
    this surface is unaffected by the multi-indicator state machine.
    """
    with st.container(border=True):
        st.markdown("### Map")
        _dispatch(indicator_id, setup, result, _current_run_id())


# ---------------------------------------------------------------------------
# Public entry point 2 — multi-indicator map (M-UI-A5, primary P-05 viz)
# ---------------------------------------------------------------------------

def render_multi_indicator_map(setup: dict, result: dict) -> None:
    """Host the multi-indicator map at the C4b↔C5 anchor (MV5).

    State machine (§4.2): reads ``active_map_indicator`` from session state.
    ``None`` → empty base map + prompt; an indicator id → that indicator's
    raster. A new screening (``run_id`` change) clears both the cache and the
    active indicator (handled in ``mms.sync_cache``, §4.6).
    """
    run_id = _current_run_id()
    mms.sync_cache(st.session_state, run_id)  # invalidate + clear active on new run
    active = mms.get_active_indicator()

    # Scroll anchor — the target every C4b "View on map →" affordance scrolls
    # to (MV16). Always present so the link works whether or not a layer is up.
    st.markdown(f"<div id='{mms.MAP_ANCHOR_ID}'></div>", unsafe_allow_html=True)

    with st.container(border=True):
        _render_map_header(active)
        if active is None:
            _render_empty_state(setup)
            return
        # M-WIND-A1 v2.0 — multi-indicator path opts into wind overlay for the
        # five in-scope indicators. Single-indicator inspection stays off (WA25).
        _dispatch(active, setup, result, run_id, apply_overlays=True)
        _render_cache_caption()

    # One-shot scroll-to-map after a tile click set the active indicator.
    if mms.consume_scroll():
        _emit_scroll_js()


def _render_map_header(active: str | None) -> None:
    """"Map" header; a top-right "✕ Close map" button when a layer is active
    (MV13, Q-MV-3 → above, top-right)."""
    if active is None:
        st.markdown("### Map")
        return
    title_col, close_col = st.columns([5, 1])
    title_col.markdown("### Map")
    with close_col:
        if st.button(
            "✕ Close map", key="close_multi_map", use_container_width=True,
        ):
            mms.clear_active_indicator()
            st.rerun()


def _render_empty_state(setup: dict) -> None:
    """Empty base map + instructional prompt (MV6/MV7; Q-MV-1 → text, not a
    fragile CSS overlay on the geemap iframe — recon A.10)."""
    st.info(
        'Click any indicator\'s "View on map →" link above to display its '
        "data here."
    )
    m = _build_base_map(setup)
    m.to_streamlit(height=500)


def _render_cache_caption() -> None:
    """Tiny cache-observability line (§6.5)."""
    stats = mms.cache_stats(st.session_state)
    st.caption(
        f"Map cache: {stats['hits']} hits · {stats['misses']} misses · "
        f"{stats['entries']} entries"
    )


def _emit_scroll_js() -> None:
    """Scroll the parent document to the map anchor (MV16).

    The hash-link scroll the affordance used pre-M-UI-A5 no longer applies
    (it's an st.button now), so we scroll explicitly. Best-effort, matching
    the prior affordance's honesty about in-page scrolling.
    """
    import streamlit.components.v1 as components

    components.html(
        f"<script>"
        f"const el = window.parent.document.getElementById('{mms.MAP_ANCHOR_ID}');"
        f"if (el) {{ el.scrollIntoView({{behavior: 'smooth', block: 'start'}}); }}"
        f"</script>",
        height=0,
    )
