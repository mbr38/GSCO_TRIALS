"""
Reference page: geemap + Earth Engine layer.

This page exists to validate the geemap + Streamlit + Earth Engine pipeline
end-to-end. It is NOT one of the P-01..P-11 pages from the wireframes — it's
a working reference you can keep, copy, or delete once the real indicator
pages are built on top of the same pattern.

Pattern to remember:
- Pages that DO touch Earth Engine       → use `import geemap.foliumap as geemap`
                                            and call `require_earth_engine()` first
"""

import streamlit as st

from utils.state import require_user_type, sign_out
from utils.ee_init import require_earth_engine

# ----------------------------------------------------------------------------
# Guards.
# ----------------------------------------------------------------------------
require_user_type()
require_earth_engine()   # <-- the only new line for EE-enabled pages

# Now safe to import geemap and ee — both rely on the EE singleton.
import ee
import geemap.foliumap as geemap

st.set_page_config(
    page_title="Earth Engine test — GSCO",
    page_icon="🛰️",
    layout="wide",
)

# ----------------------------------------------------------------------------
# Persistent nav.
# ----------------------------------------------------------------------------
nav_left, nav_right = st.columns([4, 1])
with nav_left:
    st.caption(
        f"Signed in as **{st.session_state.user_type_label}**  ·  "
        f"Session `{st.session_state.session_id}`"
    )
with nav_right:
    if st.button("Sign out", use_container_width=True):
        sign_out()
        st.switch_page("app.py")

st.divider()

# ----------------------------------------------------------------------------
# Page body.
# ----------------------------------------------------------------------------
st.title("Earth Engine integration test")

st.info(
    "This page proves that `geemap.foliumap` can render an Earth Engine "
    "raster inside Streamlit. The map below shows a Sentinel-2 true-colour "
    "composite of Cambridge over the last 90 days, cloud-filtered. "
    "Build the real result pages (P-05, P-06) on top of this pattern."
)

# ----------------------------------------------------------------------------
# Build a small Earth Engine demo: Sentinel-2 RGB composite over Cambridge.
# ----------------------------------------------------------------------------
@st.cache_data(show_spinner="Building Sentinel-2 composite…")
def build_s2_composite(centre_lat: float, centre_lon: float, days_back: int):
    """
    Return the components needed to render a Sentinel-2 composite.
    Cached so the EE compute graph is only built once per parameter set.
    """
    from datetime import datetime, timedelta

    aoi = ee.Geometry.Point([centre_lon, centre_lat]).buffer(20000)

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days_back)

    composite = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(start_date.isoformat(), end_date.isoformat())
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
        .median()
    )

    return {
        "image": composite,
        "vis_params": {
            "bands": ["B4", "B3", "B2"],
            "min": 0,
            "max": 3000,
            "gamma": 1.4,
        },
        "centre": [centre_lat, centre_lon],
    }


layer = build_s2_composite(centre_lat=52.205, centre_lon=0.119, days_back=90)

# ----------------------------------------------------------------------------
# Render with geemap.
# ----------------------------------------------------------------------------
m = geemap.Map(center=layer["centre"], zoom=11)
m.add_basemap("SATELLITE")
m.addLayer(layer["image"], layer["vis_params"], "Sentinel-2 (last 90 days)")
m.to_streamlit(height=500)

# ----------------------------------------------------------------------------
# Verification footer.
# ----------------------------------------------------------------------------
st.divider()
st.markdown(
    """
    **What this proves**

    - Earth Engine authenticates and initialises (`require_earth_engine()`).
    - `geemap.foliumap` renders an EE layer inline in Streamlit.
    - Streamlit's caching plays nicely with the EE compute graph.

    **The two patterns side by side**

    | Page type | Import | EE init |
    |---|---|---|
    | Setup / navigation pages | `import leafmap.foliumap as leafmap` | not needed |
    | Indicator result pages | `import geemap.foliumap as geemap` | call `require_earth_engine()` first |
    """
)
