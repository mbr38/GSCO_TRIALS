"""Developer scratch page — Air pillar (Milestone 3a debug UI).

Throwaway debugging UI, NOT part of the user-facing wireframes. Calls
engine.air.compute_pollutant_snapshot from the browser so we can visually
verify the engine returns sensible numbers before the real result pages
(P-05+) exist. Delete once P-05 lands.

Filename is 99_ so Streamlit's alphabetical page ordering keeps this at
the bottom of the sidebar, separated from the real P-01..P-11 pages.

Streamlit page rules (CLAUDE.md §7): imports → set_page_config → guards →
EE init → EE-dependent imports.
"""

from datetime import date, timedelta

import streamlit as st

from utils.state import require_user_type, sign_out
from utils.ee_init import require_earth_engine

st.set_page_config(
    page_title="Engine scratch — GSCO",
    page_icon="🧪",
    layout="wide",
)

require_user_type()
require_earth_engine()

import ee
import geemap.foliumap as geemap

from engine.air import AIR_POLLUTANT_CONFIG, compute_pollutant_snapshot
from engine.constants import BACKGROUND_RING_MAX_KM, BACKGROUND_RING_RADIUS_MULTIPLE
from engine.core.buffers import background_ring, site_buffer
from engine.exceptions import IndicatorComputeError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PRESETS: dict[str, tuple[float, float] | None] = {
    "Mid-Atlantic (clean reference)": (0.0, -30.0),
    "Ruhr Valley (industrial)":       (51.4566, 7.0117),
    "São Paulo (urban)":              (-23.5505, -46.6333),
    "Custom":                         None,
}

_DEFAULT_PALETTE = ["black", "blue", "purple", "cyan", "green", "yellow", "red"]

# Per-pollutant map viz params, in NATIVE units (the layer is built directly
# from the raw asset, before air.py's scale_factor is applied). Loosely tuned
# for visibility — adjust as needed.
_VIZ_PARAMS: dict[str, dict] = {
    "no2":  {"min": 0.0,   "max": 0.00015, "palette": _DEFAULT_PALETTE},
    "so2":  {"min": 0.0,   "max": 0.0005,  "palette": _DEFAULT_PALETTE},
    "co":   {"min": 0.02,  "max": 0.06,    "palette": _DEFAULT_PALETTE},
    "hcho": {"min": 0.0,   "max": 0.0003,  "palette": _DEFAULT_PALETTE},
    "o3":   {"min": 0.12,  "max": 0.155,   "palette": _DEFAULT_PALETTE},
    "aai":  {"min": -1.0,  "max": 2.0,     "palette": _DEFAULT_PALETTE},
    "pm25": {"min": 0.0,   "max": 7.5e-8,  "palette": _DEFAULT_PALETTE},
    "pm10": {"min": 0.0,   "max": 1.5e-7,  "palette": _DEFAULT_PALETTE},
    "aod":  {"min": 0.0,   "max": 0.5,     "palette": _DEFAULT_PALETTE},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_preset() -> None:
    """Preset selector callback: copy the chosen coords into lat/lon state."""
    coords = _PRESETS[st.session_state.scratch_preset]
    if coords is not None:
        st.session_state.scratch_lat, st.session_state.scratch_lon = coords


def _fmt(value: float | None, decimals: int = 3) -> str:
    return "—" if value is None else f"{value:.{decimals}f}"


# Session-state defaults for the sidebar widgets.
st.session_state.setdefault("scratch_preset", "Mid-Atlantic (clean reference)")
st.session_state.setdefault("scratch_lat", 0.0)
st.session_state.setdefault("scratch_lon", -30.0)


# ---------------------------------------------------------------------------
# Page chrome
# ---------------------------------------------------------------------------

st.warning(
    "Developer scratch page — not part of the user-facing tool. "
    "Delete when P-05 lands."
)
st.title("Engine scratch — Air pillar")

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


# ---------------------------------------------------------------------------
# Sidebar inputs
# ---------------------------------------------------------------------------

with st.sidebar:
    st.subheader("Location")
    st.selectbox(
        "Quick presets",
        list(_PRESETS.keys()),
        key="scratch_preset",
        on_change=_apply_preset,
    )
    lat = st.number_input(
        "Latitude",
        min_value=-90.0, max_value=90.0,
        key="scratch_lat", format="%.4f",
    )
    lon = st.number_input(
        "Longitude",
        min_value=-180.0, max_value=180.0,
        key="scratch_lon", format="%.4f",
    )

    st.subheader("AOI")
    radius_km = st.slider("Radius (km)", min_value=1, max_value=50, value=5)

    st.subheader("Pollutant + time range")
    pollutant = st.selectbox("Pollutant", list(AIR_POLLUTANT_CONFIG.keys()))
    today = date.today()
    start_date = st.date_input("Start date", value=today - timedelta(days=93))
    end_date = st.date_input("End date", value=today - timedelta(days=3))


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

cfg = AIR_POLLUTANT_CONFIG[pollutant]
centre = {"lat": lat, "lon": lon}
background_km = min(BACKGROUND_RING_RADIUS_MULTIPLE * radius_km, BACKGROUND_RING_MAX_KM)
time_range = (start_date.isoformat(), end_date.isoformat())

left_col, right_col = st.columns([3, 2])

with left_col:
    site_geom = site_buffer(centre, radius_km)
    ring_geom = background_ring(centre, radius_km)
    layer_ic = (
        ee.ImageCollection(cfg.asset_id)
        .filterDate(*time_range)
        .select(cfg.band)
    )

    m = geemap.Map(center=[lat, lon], zoom=8)
    m.add_basemap("SATELLITE")
    m.addLayer(layer_ic.mean(), _VIZ_PARAMS[pollutant], f"{pollutant} mean")
    m.addLayer(site_geom, {"color": "blue"}, "Site buffer")
    m.addLayer(ring_geom, {"color": "red"}, "Background ring")
    m.to_streamlit(height=550)


with right_col:
    run = st.button("Run snapshot", type="primary", use_container_width=True)

    if run:
        aoi = {"centre": centre, "radius_km": radius_km}
        try:
            with st.spinner("Running engine..."):
                result = compute_pollutant_snapshot(
                    aoi=aoi,
                    pollutant=pollutant,
                    time_range=time_range,
                    mode="screening",
                    ee_client=None,
                )
        except IndicatorComputeError as err:
            st.error(f"Compute failed: {err}")
        else:
            site_v       = result[f"air.{pollutant}.site"]
            background_v = result[f"air.{pollutant}.background"]
            anomaly_v    = result[f"air.{pollutant}.anomaly"]
            z_v          = result[f"air.{pollutant}.z"]
            hf_v         = result[f"air.{pollutant}.hf"]
            score_v      = result[f"air.{pollutant}.score"]
            confidence_v = result[f"air.{pollutant}.confidence"]

            # Headline — the score, big and prominent.
            st.markdown("### Result")
            st.metric(
                label="Score",
                value=_fmt(score_v, 2),
                delta="of 1.00",
                delta_color="off",
            )

            # Raw values — measurements on the left, statistical context on the right.
            st.divider()
            st.markdown("**Raw values**")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**Site value**  \n{_fmt(site_v, 2)} {cfg.display_unit}")
                st.markdown(f"**Anomaly**  \n{_fmt(anomaly_v, 2)} {cfg.display_unit}")
            with col_b:
                st.markdown(f"**Background**  \n{_fmt(background_v, 2)} {cfg.display_unit}")
                st.markdown(f"**Z-score**  \n{_fmt(z_v, 2)} σ")

            # Quality — second-order concerns, visually separated.
            st.divider()
            st.markdown("**Quality**")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**Confidence**  \n{_fmt(confidence_v, 2)}")
            with col_b:
                st.markdown(f"**Hotspot frequency**  \n{_fmt(hf_v, 2)}")

            with st.expander("Full payload"):
                st.json(result)

            with st.expander("Provenance"):
                st.json(result[f"_provenance.air.{pollutant}"])

    st.caption(
        f"Queried `{start_date.isoformat()}` → `{end_date.isoformat()}`  ·  "
        f"site buffer **{radius_km} km**  ·  "
        f"background ring **{background_km} km**"
    )
