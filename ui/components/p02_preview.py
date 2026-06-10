"""P-02 preview renderers (M-P02).

One function per scope mode. Each renders the scope's identifying
info + (for the two spatial modes) a small geemap preview. None mode
has no map — there's no AOI to render.

House map idioms match the scratch page and ``c4a_indicator_map``:
``geemap.Map`` → ``add_basemap`` → ``addLayer`` → ``to_streamlit``.
No ``streamlit_folium`` wrapper.

Authority: docs/Wireframes_All_v4.md §P-02; M-P02 design decisions.
"""

# M-P02
from __future__ import annotations

import math

import ee
import geemap.foliumap as geemap
import streamlit as st

from demo.regions import Region, country_boundary_fc, regions_for_country
from demo.scopes import SupplyChain


# ---------------------------------------------------------------------------
# Supply chain preview
# ---------------------------------------------------------------------------

def render_supply_chain_preview(chain: SupplyChain) -> None:
    """Render identity + node table + node-marker map."""
    col_meta, col_map = st.columns([1, 1])
    with col_meta:
        st.markdown(f"**{chain.name}**")
        st.markdown(f"Industry: *{chain.industry}*")
        st.markdown(f"Country: *{chain.country}*")
        st.markdown(f"Nodes: **{len(chain.nodes)}**")
        tiers = sorted({n.tier for n in chain.nodes})
        st.markdown(f"Tiers represented: {', '.join(tiers)}")
    with col_map:
        _render_chain_map(chain)

    st.divider()
    st.markdown("**Nodes in this chain**")
    rows = [
        {
            "Name":  n.name,
            "Tier":  n.tier,
            "Lat":   round(n.lat, 4),
            "Lon":   round(n.lon, 4),
            "Notes": n.notes or "",
        }
        for n in chain.nodes
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_chain_map(chain: SupplyChain) -> None:
    """Map view of a supply chain — one marker per node."""
    mean_lat = sum(n.lat for n in chain.nodes) / len(chain.nodes)
    mean_lon = sum(n.lon for n in chain.nodes) / len(chain.nodes)
    # ee_initialize=False: EE is already initialised by the page's
    # require_earth_engine() call; geemap's own initialiser reaches for a
    # private ee.data attribute removed in newer earthengine-api releases.
    m = geemap.Map(center=[mean_lat, mean_lon], zoom=5, ee_initialize=False)
    m.add_basemap("SATELLITE")
    for node in chain.nodes:
        m.add_marker(
            location=[node.lat, node.lon],
            popup=node.name,
        )
    m.to_streamlit(height=350)


# ---------------------------------------------------------------------------
# Region preview
# ---------------------------------------------------------------------------

def render_region_preview(region: Region) -> None:
    """Render identity + centroid/radius stats + map with buffer outline."""
    col_meta, col_map = st.columns([1, 1])
    with col_meta:
        st.markdown(f"**{region.name}, {region.country}**")
        st.markdown(
            f"Centroid: ({region.centroid_lat:.4f}, "
            f"{region.centroid_lon:.4f})"
        )
        st.markdown(
            f"Representative buffer: **{region.radius_km} km radius**"
        )
        if region.is_capped:
            st.info(
                f"This region is larger than the {region.radius_km} km "
                f"representative buffer (natural radius "
                f"{region.natural_radius_km} km). The screening will "
                f"cover a representative portion centred on the region's "
                f"centroid."
            )
        else:
            st.caption(
                "The buffer is sized to match the region's area; "
                "screening covers the whole region."
            )
    with col_map:
        _render_region_map(region)


def _render_region_map(region: Region) -> None:
    """Map view of a region — centroid marker + buffer outline."""
    m = geemap.Map(
        center=[region.centroid_lat, region.centroid_lon],
        zoom=_zoom_for_radius(region.radius_km),
        ee_initialize=False,  # see _render_chain_map note
    )
    m.add_basemap("SATELLITE")
    m.add_marker(
        location=[region.centroid_lat, region.centroid_lon],
        popup=region.name,
    )

    # Buffer outline — same FeatureCollection.style idiom the scratch
    # page + C4a renderer use. No fill, 2 px red stroke.
    buffer = (
        ee.Geometry.Point([region.centroid_lon, region.centroid_lat])
        .buffer(region.radius_km * 1000)
    )
    outline = (
        ee.FeatureCollection([ee.Feature(buffer)])
        .style(color="red", fillColor="00000000", width=2)
    )
    m.addLayer(outline, {}, "Representative buffer")
    m.to_streamlit(height=350)


def _zoom_for_radius(km: float) -> int:
    """Leaflet zoom for ~4× buffer-radius visible across the map.

    Mirrors the heuristic in
    ``ui/components/c4a_indicator_map._zoom_for_radius_km``. The
    Leaflet zoom range is clamped to a sane mid-band; we never need
    a continent-scale view here.
    """
    display_km = km * 4
    if display_km <= 0:
        return 8
    z = 7 + math.log2(156 / display_km)
    return max(3, min(18, round(z)))


# ---------------------------------------------------------------------------
# Country-regional preview
# ---------------------------------------------------------------------------

def render_country_regional_preview(country: str) -> None:
    """Regional-analysis preview — whole-country map, no region picked yet.

    No region is selected at scope time: this preview just establishes
    the country and shows the regions that can be inspected later (one
    marker per admin1 centroid). The single region (Inspect) or the
    multiple regions (Prioritisation) are chosen downstream on P-04/P-07.
    """
    regions = regions_for_country(country)

    col_meta, col_map = st.columns([1, 1])
    with col_meta:
        st.markdown(f"**Regional analysis — {country}**")
        st.markdown(f"Inspectable regions: **{len(regions)}**")
        st.caption(
            "No region is selected yet. You'll pick a single region to "
            "screen on the **Inspect** page, or several regions on the "
            "**Prioritisation** page. Each region screens at a buffer "
            "sized to its own area."
        )
    with col_map:
        _render_country_map(country, regions)


def _render_country_map(country: str, regions) -> None:
    """Country map — admin1 boundary outline + a marker per region centroid."""
    if regions:
        mean_lat = sum(r.centroid_lat for r in regions) / len(regions)
        mean_lon = sum(r.centroid_lon for r in regions) / len(regions)
        lat_span = max(r.centroid_lat for r in regions) - min(
            r.centroid_lat for r in regions
        )
        lon_span = max(r.centroid_lon for r in regions) - min(
            r.centroid_lon for r in regions
        )
        zoom = _zoom_for_span(max(lat_span, lon_span))
    else:
        mean_lat, mean_lon, zoom = 0.0, 0.0, 3

    m = geemap.Map(center=[mean_lat, mean_lon], zoom=zoom, ee_initialize=False)  # see _render_chain_map note
    m.add_basemap("SATELLITE")
    m.addLayer(country_boundary_fc(country), {}, f"{country} regions")
    for region in regions:
        m.add_marker(
            location=[region.centroid_lat, region.centroid_lon],
            popup=region.name,
        )
    m.to_streamlit(height=350)


def _zoom_for_span(span_deg: float) -> int:
    """Leaflet zoom so a lat/lon extent of ``span_deg`` fits comfortably.

    Mirrors the spirit of ``_zoom_for_radius`` but keyed on the angular
    spread of the region centroids rather than a buffer radius.
    """
    if span_deg <= 0:
        return 6
    z = round(math.log2(360 / max(span_deg, 0.1))) - 1
    return max(3, min(12, z))


# ---------------------------------------------------------------------------
# None-mode preview
# ---------------------------------------------------------------------------

def render_none_preview() -> None:
    """No-scope preview — explanatory text, no map."""
    st.info(
        "**No scope** — you'll configure each screening from scratch on "
        "the Inspect Setup page using free coordinates (or the geocoded "
        "search). This is the right choice for ad-hoc inspection of a "
        "single point that isn't part of a curated supply chain."
    )
    st.markdown(
        "On the next page (**Inspect Setup**), the Supplier and Region "
        "tabs will be hidden — only **Free coordinates** is available."
    )
