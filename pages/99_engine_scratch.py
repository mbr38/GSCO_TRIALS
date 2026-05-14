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

import pandas as pd
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
from engine.ghg import GHG_INDICATOR_CONFIG
from engine.orchestrator import ScreeningRun
from engine.constants import BACKGROUND_RING_MAX_KM, BACKGROUND_RING_RADIUS_MULTIPLE
from engine.core.buffers import background_ring, site_buffer
from engine.exceptions import IndicatorComputeError, PillarComputeError


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
# Cached result from the last successful Run snapshot. None until the user
# clicks Run for the first time; cleared whenever sidebar inputs drift.
st.session_state.setdefault("scratch_last_run", None)


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
    mode = st.radio(
        "Mode",
        ["Single pollutant", "Full screening (all pillars)"],
        help=(
            "Single pollutant runs compute_pollutant_snapshot for one selected "
            "pollutant. Full screening runs ScreeningRun across Air + GHG — "
            "produces both per-pillar follow-up priorities and the cross-pillar "
            "composite score."
        ),
    )

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

    if mode == "Single pollutant":
        st.subheader("Pollutant + time range")
        pollutant: str | None = st.selectbox(
            "Pollutant", list(AIR_POLLUTANT_CONFIG.keys()),
        )
    else:
        # Full pillar mode uses all nine pollutants — no individual selector.
        st.subheader("Time range")
        pollutant = None
    today = date.today()
    start_date = st.date_input("Start date", value=today - timedelta(days=93))
    end_date = st.date_input("End date", value=today - timedelta(days=3))


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

cfg = AIR_POLLUTANT_CONFIG[pollutant] if pollutant is not None else None
centre = {"lat": lat, "lon": lon}
background_km = min(BACKGROUND_RING_RADIUS_MULTIPLE * radius_km, BACKGROUND_RING_MAX_KM)
time_range = (start_date.isoformat(), end_date.isoformat())

# Drift detection — clear the cached result whenever any sidebar input has
# changed since the last Run, so the displayed map and metrics never outlive
# their inputs. `mode` is part of the tuple so switching mode also clears.
current_inputs = (
    mode, lat, lon, radius_km, pollutant,
    start_date.isoformat(), end_date.isoformat(),
)
last = st.session_state.get("scratch_last_run")
if last is not None and last["inputs"] != current_inputs:
    st.session_state.scratch_last_run = None
    last = None

left_col, right_col = st.columns([3, 2])

with right_col:
    if mode == "Full screening (all pillars)":
        st.info(
            "Full screening runs 9 Air + 2 GHG sequential Earth Engine queries — "
            "first run can take 30–90 seconds."
        )

    run = st.button("Run snapshot", type="primary", use_container_width=True)

    if run:
        aoi = {"centre": centre, "radius_km": radius_km}
        try:
            if mode == "Single pollutant":
                with st.spinner("Running engine..."):
                    result = compute_pollutant_snapshot(
                        aoi=aoi,
                        pollutant=pollutant,
                        time_range=time_range,
                        mode="screening",
                        ee_client=None,
                    )
            elif mode == "Full screening (all pillars)":
                selected = (
                    {f"air.{p}.score" for p in AIR_POLLUTANT_CONFIG.keys()}
                    | {f"ghg.{i}.score" for i in GHG_INDICATOR_CONFIG.keys()}
                )
                with st.spinner("Running full screening (Air + GHG)..."):
                    result = ScreeningRun(
                        aoi=aoi,
                        selected_indicators=selected,
                        time_range=time_range,
                        ee_client=None,
                        centre_metadata={"source": "engine scratch page"},
                    ).run()
        except (IndicatorComputeError, PillarComputeError) as err:
            st.error(f"Compute failed: {err}")
        else:
            st.session_state.scratch_last_run = {
                "inputs":     current_inputs,
                "mode":       mode,
                "result":     result,
                "cfg":        cfg,
                "time_range": time_range,
                "lat":        lat,
                "lon":        lon,
                "radius_km":  radius_km,
                "pollutant":  pollutant,
            }
            last = st.session_state.scratch_last_run

    if last is not None and last["mode"] == "Single pollutant":
        rresult    = last["result"]
        rcfg       = last["cfg"]
        rpollutant = last["pollutant"]

        site_v       = rresult[f"air.{rpollutant}.site"]
        background_v = rresult[f"air.{rpollutant}.background"]
        anomaly_v    = rresult[f"air.{rpollutant}.anomaly"]
        z_v          = rresult[f"air.{rpollutant}.z"]
        hf_v         = rresult[f"air.{rpollutant}.hf"]
        score_v      = rresult[f"air.{rpollutant}.score"]
        confidence_v = rresult[f"air.{rpollutant}.confidence"]

        # Headline — the score, big and prominent.
        st.markdown("### Result")
        st.metric(
            label="Score",
            value=_fmt(score_v, 2),
            delta="of 1.00",
            delta_color="off",
        )
        st.caption(
            "Score is a 0–1 measure of how unusual the site value is compared "
            "to its surrounding background ring, normalised against background "
            "variability. 0 means the site matches its surroundings; 1 means "
            "the site is at or above 3 standard deviations from background. "
            "Thresholds: below 0.33 = low concern (green), 0.33–0.66 = elevated "
            "(amber), above 0.66 = high concern (red)."
        )

        # Raw values — measurements on the left, statistical context on the right.
        st.divider()
        st.markdown("**Raw values**")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"**Site value**  \n{_fmt(site_v, 2)} {rcfg.display_unit}")
            st.markdown(f"**Anomaly**  \n{_fmt(anomaly_v, 2)} {rcfg.display_unit}")
        with col_b:
            st.markdown(f"**Background**  \n{_fmt(background_v, 2)} {rcfg.display_unit}")
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
            st.json(rresult)

        with st.expander("Provenance"):
            st.json(rresult[f"_provenance.air.{rpollutant}"])

    elif last is not None and last["mode"] == "Full screening (all pillars)":
        rresult = last["result"]

        # A. Headline — cross-pillar composite is the top-level audience number.
        st.markdown("### Cross-pillar composite")
        st.metric(
            label="Overall screening score",
            value=_fmt(rresult.get("composite.overall_screening"), 2),
            delta="of 1.00",
            delta_color="off",
        )
        st.caption(
            "Composite is the equal-weighted mean of per-pillar follow-up "
            "priorities (Air + GHG today). Each pillar's priority is itself a "
            "0–1 measure of how unusual the site is vs its surrounding "
            "background ring. Thresholds: below 0.33 = low concern (green), "
            "0.33–0.66 = elevated (amber), above 0.66 = high concern (red). "
            "Composite confidence is the minimum across the per-pillar "
            "confidence aggregates."
        )

        comp_col_a, comp_col_b = st.columns(2)
        with comp_col_a:
            st.markdown(
                "**Composite confidence**  \n"
                f"{_fmt(rresult.get('composite.confidence'), 2)}"
            )
        with comp_col_b:
            st.markdown(
                f"**Pillars run**  \n{', '.join(rresult['_meta']['pillars_run'])}"
            )

        # B. Per-pillar follow-up priorities side by side.
        st.divider()
        st.markdown("**Per-pillar follow-up priority**")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(
                "**Air**  \n"
                f"{_fmt(rresult.get('air.audit_followup_priority'), 2)}"
            )
        with col_b:
            st.markdown(
                "**GHG**  \n"
                f"{_fmt(rresult.get('ghg.audit_followup_priority'), 2)}"
            )

        # C. Air pillar aggregates — the four that feed air.audit_followup_priority.
        st.divider()
        st.markdown("**Air — Pillar aggregates**")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(
                "**Pollution proxy score**  \n"
                f"{_fmt(rresult.get('air.pollution_proxy_score'), 2)}"
            )
            st.markdown(
                "**Trend score**  \n"
                f"{_fmt(rresult.get('air.trend_score'), 2)}"
            )
        with col_b:
            st.markdown(
                "**Spatiotemporal anomaly**  \n"
                f"{_fmt(rresult.get('air.spatiotemporal_anomaly_score'), 2)}"
            )
            st.markdown(
                "**Attribution confidence**  \n"
                f"{_fmt(rresult.get('air.attribution_confidence_score'), 2)}"
            )

        # D. Air sub-aggregates — six derived 0-1 scores per IC_v4 §1.2.
        st.divider()
        st.markdown("**Air — Sub-aggregates**")
        sub_cols_top = st.columns(3)
        sub_cols_top[0].markdown(
            "**PM / Aerosol**  \n"
            f"{_fmt(rresult.get('air.pm_or_aerosol'), 2)}"
        )
        sub_cols_top[1].markdown(
            "**Industrial combustion**  \n"
            f"{_fmt(rresult.get('air.industrial_combustion_proxy'), 2)}"
        )
        sub_cols_top[2].markdown(
            "**Heavy industry**  \n"
            f"{_fmt(rresult.get('air.heavy_industry_score'), 2)}"
        )
        sub_cols_bot = st.columns(3)
        sub_cols_bot[0].markdown(
            "**VOC / photochemical**  \n"
            f"{_fmt(rresult.get('air.voc_photochemical'), 2)}"
        )
        sub_cols_bot[1].markdown(
            "**Smoke / dust transport**  \n"
            f"{_fmt(rresult.get('air.smoke_dust_regional_transport'), 2)}"
        )
        sub_cols_bot[2].markdown(
            "**Industrial burden**  \n"
            f"{_fmt(rresult.get('air.industrial_air_pollution_burden'), 2)}"
        )

        # E. Air per-pollutant breakdown table.
        st.divider()
        st.markdown("**Air — Per-pollutant breakdown**")
        air_rows = []
        for p in AIR_POLLUTANT_CONFIG.keys():
            air_rows.append({
                "Pollutant":  p.upper(),
                "Site":       _fmt(rresult.get(f"air.{p}.site"), 2),
                "Score":      _fmt(rresult.get(f"air.{p}.score"), 2),
                "Z-score":    _fmt(rresult.get(f"air.{p}.z"), 2),
                "Confidence": _fmt(rresult.get(f"air.{p}.confidence"), 2),
            })
        st.dataframe(
            pd.DataFrame(air_rows),
            hide_index=True,
            use_container_width=True,
        )

        # F. GHG pillar aggregates + sub-aggregates side by side.
        st.divider()
        st.markdown("**GHG — Pillar aggregates**")
        gcol_a, gcol_b = st.columns(2)
        with gcol_a:
            st.markdown(
                "**Core audit support**  \n"
                f"{_fmt(rresult.get('ghg.core_audit_support'), 2)}"
            )
            st.markdown(
                "**Trend**  \n"
                f"{_fmt(rresult.get('ghg.trend'), 2)}"
            )
        with gcol_b:
            st.markdown(
                "**Spatiotemporal anomaly**  \n"
                f"{_fmt(rresult.get('ghg.spatiotemporal_anomaly'), 2)}"
            )
            st.markdown(
                "**Data quality attribution**  \n"
                f"{_fmt(rresult.get('ghg.data_quality_attribution'), 2)}"
            )

        # G. GHG per-indicator breakdown table. VIIRS lacks z (reduced
        # measurement set per Schema_v2 §3.1), so its row's Z-score
        # column will render "—".
        st.divider()
        st.markdown("**GHG — Per-indicator breakdown**")
        ghg_rows = []
        for ind in GHG_INDICATOR_CONFIG.keys():
            ghg_rows.append({
                "Indicator":  ind.upper(),
                "Site":       _fmt(rresult.get(f"ghg.{ind}.site"), 2),
                "Score":      _fmt(rresult.get(f"ghg.{ind}.score"), 2),
                "Z-score":    _fmt(rresult.get(f"ghg.{ind}.z"), 2),
                "Confidence": _fmt(rresult.get(f"ghg.{ind}.confidence"), 2),
            })
        st.dataframe(
            pd.DataFrame(ghg_rows),
            hide_index=True,
            use_container_width=True,
        )

        # H. Failures — now namespaced as {pillar: [failures]} after M5c.
        if rresult.get("_failures"):
            failures_dict = rresult["_failures"]
            total = sum(len(v) for v in failures_dict.values())
            with st.expander(f"⚠ {total} failure(s) across pillars"):
                for pillar_name, failure_list in failures_dict.items():
                    st.markdown(f"**{pillar_name.upper()} pillar**")
                    for fail in failure_list:
                        if fail.get("type") == "pillar_wide":
                            st.write(
                                "- _pillar-wide failure_: "
                                f"{fail.get('reason', 'unknown')}"
                            )
                        else:
                            label = (
                                fail.get("pollutant")
                                or fail.get("indicator")
                                or fail.get("indicator_id", "?")
                            )
                            st.write(
                                f"- **{str(label).upper()}**: "
                                f"{fail.get('reason', 'unknown')}"
                            )

        # I. Full payload — debug expander, unchanged from Single mode.
        with st.expander("Full payload"):
            st.json(rresult)

    else:
        st.info("Configure inputs and click **Run snapshot**.")

    st.caption(
        f"Queried `{start_date.isoformat()}` → `{end_date.isoformat()}`  ·  "
        f"site buffer **{radius_km} km**  ·  "
        f"background ring **{background_km} km**"
    )

with left_col:
    # Base map + buffers always render against current sidebar inputs — they
    # are the constant spatial anchor for the audience.
    site_geom = site_buffer(centre, radius_km)
    ring_geom = background_ring(centre, radius_km)

    m = geemap.Map(center=[lat, lon], zoom=8)
    m.add_basemap("SATELLITE")

    # Pollutant layer first (bottom) — only in Single pollutant mode, and only
    # when last_run matches current inputs. Full screening mode skips it because
    # rendering all 9 Air + 2 GHG layers as overlaps would be unreadable.
    if (
        st.session_state.scratch_last_run is not None
        and st.session_state.scratch_last_run["inputs"] == current_inputs
        and st.session_state.scratch_last_run["mode"] == "Single pollutant"
    ):
        layer_ic = (
            ee.ImageCollection(cfg.asset_id)
            .filterDate(*time_range)
            .select(cfg.band)
        )
        m.addLayer(
            layer_ic.mean(),
            _VIZ_PARAMS[pollutant],
            f"{pollutant} mean",
        )

    # Outlines on top so they remain visible. fillColor="00000000" is fully
    # transparent (RGBA with alpha = 0); width=2 keeps the stroke crisp
    # without dominating the basemap.
    def _outline(geom, colour: str, name: str) -> None:
        fc = ee.FeatureCollection([ee.Feature(geom)])
        styled = fc.style(color=colour, fillColor="00000000", width=2)
        m.addLayer(styled, {}, name)

    _outline(ring_geom, "red", "Background ring")
    _outline(site_geom, "blue", "Site buffer")

    m.to_streamlit(height=550)
