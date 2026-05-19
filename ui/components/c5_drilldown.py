"""C5a/b/c — drill-down panels (M-UI-E.4).

Three pillar drill-down panels, each rendered as a Streamlit expander
(collapsed by default). Per ``docs/Wireframes_All_v4.md`` §P-05 C5:

  - Headline = Follow-Up Priority Score + formula breakdown
    (``docs/Indicators_Computation_v4.md`` §1.3 / §2.3 / §3.3).
  - Per-indicator rows. Air and GHG share a uniform 6-column row
    schema (name / site / anomaly / z / confidence / score). Nature
    is sub-sectioned by indicator class because its outputs are too
    heterogeneous for a uniform row schema.
  - "Datasets used" sub-expander listing the pillar's canonical
    M5.6 provenance blocks (``docs/provenance_schema.md``).

The formula weights are pulled from ``engine.constants`` rather than
inlined, so the breakdown stays in lockstep with the live engine if
weights ever change. Display names + payload-key bindings are owned
here.
"""

# M-UI-E.4
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from engine.constants import (
    AIR_FOLLOWUP_WEIGHTS,
    GHG_FOLLOWUP_WEIGHTS,
    NATURE_FOLLOWUP_WEIGHTS,
)
from ui.components.traffic_light import (
    band_colour,
    band_for_score,
    band_label,
    confidence_glyph,
)


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

def _fmt(value: float | None, spec: str) -> str:
    """Format a float per ``spec`` (e.g. ``".2f"``, ``"+.2g"``). ``None``
    renders as the canonical em-dash placeholder."""
    if value is None:
        return "—"
    return f"{value:{spec}}"


@dataclass(frozen=True)
class _FormulaTerm:
    """One term in a pillar's Follow-Up Priority weighted sum."""

    display_name: str
    payload_key:  str
    weight:       float


# Internal-key → (display name, payload key) bindings, paired with the
# weight dicts in engine.constants. The internal keys MUST match the
# engine's dict keys exactly — see _build_formula().
_AIR_TERMS: dict[str, tuple[str, str]] = {
    "proxy":      ("Pollution proxy score",   "air.pollution_proxy_score"),
    "anomaly":    ("Spatiotemporal anomaly",  "air.spatiotemporal_anomaly_score"),
    "trend":      ("Trend (screening = 0)",   "air.trend_score"),
    "confidence": ("Attribution confidence",  "air.attribution_confidence_score"),
}
_GHG_TERMS: dict[str, tuple[str, str]] = {
    "core_support": ("Core audit support",          "ghg.core_audit_support"),
    "anomaly":      ("Spatiotemporal anomaly",      "ghg.spatiotemporal_anomaly"),
    "trend":        ("Trend (screening = 0)",       "ghg.trend"),
    "quality":      ("Data-quality attribution",    "ghg.data_quality_attribution"),
}
_NATURE_TERMS: dict[str, tuple[str, str]] = {
    "biodiversity_exposure": ("Biodiversity exposure",  "nature.biodiversity_exposure"),
    "habitat_conversion":    ("Habitat conversion",     "nature.habitat.conversion_score"),
    "vegetation_condition":  ("Vegetation condition",   "nature.vegetation_condition"),
    "quality_attribution":   ("Quality attribution",    "nature.quality_attribution"),
}


def _build_formula(
    weights: dict[str, float],
    terms: dict[str, tuple[str, str]],
) -> tuple[_FormulaTerm, ...]:
    """Zip an engine weight dict with the UI term bindings.

    Raises ``KeyError`` at import time if the engine adds or renames a
    weight key — that's an intentional fail-loud, since silent drift
    between the breakdown UI and the live formula is the bug this
    construction is designed to prevent.
    """
    return tuple(
        _FormulaTerm(terms[k][0], terms[k][1], weights[k])
        for k in weights
    )


_AIR_FORMULA    = _build_formula(AIR_FOLLOWUP_WEIGHTS,    _AIR_TERMS)
_GHG_FORMULA    = _build_formula(GHG_FOLLOWUP_WEIGHTS,    _GHG_TERMS)
_NATURE_FORMULA = _build_formula(NATURE_FOLLOWUP_WEIGHTS, _NATURE_TERMS)


def _render_headline(
    priority_key:   str,
    confidence_key: str,
    formula:        tuple[_FormulaTerm, ...],
    payload:        dict,
) -> None:
    """Headline: priority score (band-coloured chip + dot) + formula
    breakdown rendered as ``weight × value = contribution`` per term."""
    priority   = payload.get(priority_key)
    confidence = payload.get(confidence_key)
    band       = band_for_score(priority)
    priority_str = f"{priority:.3f}" if priority is not None else "—"
    glyph        = confidence_glyph(confidence)
    colour       = band_colour(band)

    st.markdown(
        f"**Follow-Up Priority Score** &nbsp; "
        f"<span style='background:{colour};color:white;padding:2px 8px;"
        f"border-radius:3px;font-weight:600;'>{priority_str}</span>"
        f"&nbsp; <span style='color:#6b7280;'>{band_label(band)}</span>"
        f"&nbsp;&nbsp; {glyph} confidence",
        unsafe_allow_html=True,
    )

    # M-UI-E.4 polish — render the formula as a 4-column table. The
    # Contribution column is bolded because it's the one the user
    # mentally sums to verify the headline score.
    st.markdown("**Formula**")
    col_n, col_w, col_v, col_c = st.columns([3, 1, 1, 1])
    col_n.caption("Sub-aggregate")
    col_w.caption("Weight")
    col_v.caption("Value")
    col_c.caption("Contribution")
    for term in formula:
        value = payload.get(term.payload_key)
        contribution = term.weight * value if value is not None else None
        col_n, col_w, col_v, col_c = st.columns([3, 1, 1, 1])
        col_n.markdown(term.display_name)
        col_w.markdown(f"{term.weight:.2f}")
        col_v.markdown(_fmt(value, ".3f"))
        col_c.markdown(f"**{_fmt(contribution, '.3f')}**")


# ---------------------------------------------------------------------------
# Uniform per-indicator rows (Air + GHG)
# ---------------------------------------------------------------------------

def _render_row_headers() -> None:
    col_n, col_v, col_a, col_z, col_c, col_s = st.columns([2, 2, 2, 1, 1, 1])
    col_n.caption("Indicator")
    col_v.caption("Site value")
    col_a.caption("Anomaly")
    col_z.caption("Z")
    col_c.caption("Conf")
    col_s.caption("Score")


def _render_uniform_row(
    display_name: str,
    value:        float | None,
    anomaly:      float | None,
    z:            float | None,
    confidence:   float | None,
    score:        float | None,
    value_spec:   str = ".3g",
) -> None:
    """Render one indicator row in the uniform 6-column schema."""
    band   = band_for_score(score)
    colour = band_colour(band)

    col_n, col_v, col_a, col_z, col_c, col_s = st.columns([2, 2, 2, 1, 1, 1])
    col_n.markdown(f"**{display_name}**")
    col_v.markdown(_fmt(value, value_spec))
    col_a.markdown(_fmt(anomaly, "+.3g"))
    col_z.markdown(_fmt(z, ".2f"))
    col_c.markdown(_fmt(confidence, ".2f") + " " + confidence_glyph(confidence))
    col_s.markdown(
        f"<span style='background:{colour};color:white;padding:1px 6px;"
        f"border-radius:3px;font-size:0.85em;'>{_fmt(score, '.2f')}</span>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Air panel (C5a)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _AirRow:
    display_name: str
    indicator:    str           # e.g. "no2"
    value_spec:   str = ".3g"


# Ordered by weight in air.pollution_proxy_score per IC_v4 §1.3.
_AIR_ROWS: tuple[_AirRow, ...] = (
    _AirRow("NO₂",   "no2"),
    _AirRow("SO₂",   "so2"),
    _AirRow("CO",    "co"),
    _AirRow("HCHO",  "hcho"),
    _AirRow("PM₂.₅", "pm25"),
    _AirRow("PM₁₀",  "pm10"),
    _AirRow("O₃",    "o3"),
    _AirRow("AAI",   "aai"),
    _AirRow("AOD",   "aod"),
)


def _render_air_panel(payload: dict) -> None:
    """C5a — Air Pollution drill-down."""
    with st.expander("Air Pollution — drill-down"):
        _render_headline(
            "air.audit_followup_priority",
            "air.attribution_confidence_score",
            _AIR_FORMULA,
            payload,
        )
        # M-UI-E.4 polish — inner dividers separate the formula block,
        # the per-indicator rows, and the datasets-used expander.
        st.divider()
        st.markdown("**Per-indicator values**")
        _render_row_headers()
        for row in _AIR_ROWS:
            _render_uniform_row(
                display_name=row.display_name,
                value=payload.get(f"air.{row.indicator}.site"),
                anomaly=payload.get(f"air.{row.indicator}.anomaly"),
                z=payload.get(f"air.{row.indicator}.z"),
                confidence=payload.get(f"air.{row.indicator}.confidence"),
                score=payload.get(f"air.{row.indicator}.score"),
                value_spec=row.value_spec,
            )
        st.divider()
        _render_datasets_used_subexpander("air", _AIR_DATASET_KEYS, payload)


# ---------------------------------------------------------------------------
# GHG panel (C5b)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _GhgRow:
    display_name: str
    indicator:    str           # "ch4" | "co2" | "viirs"
    value_key:    str           # CO₂ uses .mean; CH₄/VIIRS use .site


_GHG_ROWS: tuple[_GhgRow, ...] = (
    _GhgRow("CH₄",              "ch4",   "ghg.ch4.site"),
    _GhgRow("CO₂ (ODIAC)",      "co2",   "ghg.co2.mean"),
    _GhgRow("Nighttime lights", "viirs", "ghg.viirs.site"),
)


def _render_ghg_panel(payload: dict) -> None:
    """C5b — GHG Emissions drill-down."""
    with st.expander("GHG Emissions — drill-down"):
        _render_headline(
            "ghg.audit_followup_priority",
            "ghg.data_quality_attribution",
            _GHG_FORMULA,
            payload,
        )
        # M-UI-E.4 polish — inner dividers, same pattern as the Air panel.
        st.divider()
        st.markdown("**Per-indicator values**")
        _render_row_headers()
        for row in _GHG_ROWS:
            _render_uniform_row(
                display_name=row.display_name,
                value=payload.get(row.value_key),
                anomaly=payload.get(f"ghg.{row.indicator}.anomaly"),
                z=payload.get(f"ghg.{row.indicator}.z"),
                confidence=payload.get(f"ghg.{row.indicator}.confidence"),
                score=payload.get(f"ghg.{row.indicator}.score"),
            )
        st.divider()
        _render_datasets_used_subexpander("ghg", _GHG_DATASET_KEYS, payload)


# ---------------------------------------------------------------------------
# Nature panel (C5c) — heterogeneous layout
# ---------------------------------------------------------------------------

# Dynamic World class slugs in the canonical schema order — see
# engine.ids.DW_CLASS_TO_ID_SLUG. Listed explicitly here so the C5c table
# layout is stable even if the engine's iteration order changes.
_DW_CLASSES: tuple[tuple[str, str], ...] = (
    ("trees",       "Trees"),
    ("grass",       "Grass"),
    ("crops",       "Crops"),
    ("shrub",       "Shrub/scrub"),
    ("flooded_veg", "Flooded vegetation"),
    ("water",       "Water"),
    ("built",       "Built"),
    ("bare",        "Bare"),
    ("snow",        "Snow/ice"),
)


def _render_nature_panel(payload: dict) -> None:
    """C5c — Nature/Land drill-down. Four sub-sections + DW composition."""
    with st.expander("Nature/Land — drill-down"):
        _render_headline(
            "nature.followup_priority",
            "nature.quality_attribution",
            _NATURE_FORMULA,
            payload,
        )

        # M-UI-E.4 polish — each sub-section leads with an st.metric for
        # the headline value, supporting context renders as a caption
        # alongside. st.divider() separates each sub-section from the
        # previous block (the formula breakdown / preceding sub-section).
        st.divider()
        st.markdown("**Biodiversity exposure**")
        col_metric, col_context = st.columns([1, 2])
        with col_metric:
            st.metric(
                "Proximity score",
                _fmt(payload.get("nature.kba.proximity_score"), ".2f"),
            )
        with col_context:
            dist_km     = payload.get("nature.kba.dist_km")
            overlap_pct = payload.get("nature.kba.overlap_pct")
            overlap_ha  = payload.get("nature.kba.overlap_ha")
            st.caption(
                f"Nearest KBA: **{_fmt(dist_km, '.2f')} km** "
                f"(buffer overlap: {_fmt(overlap_pct, '.2f')}%, "
                f"{_fmt(overlap_ha, '.1f')} ha)"
            )

        # M-UI-E.4 polish — habitat conversion metric + caption.
        st.divider()
        st.markdown("**Habitat conversion**")
        col_metric, col_context = st.columns([1, 2])
        with col_metric:
            st.metric(
                "Conversion score",
                _fmt(payload.get("nature.habitat.conversion_score"), ".2f"),
            )
        with col_context:
            loss_ha        = payload.get("nature.habitat.natural_loss_ha")
            loss_pct       = payload.get("nature.habitat.natural_loss_pct")
            nat_to_built   = payload.get("nature.habitat.nat_to_built_ha")
            annualised     = payload.get("nature.habitat.annualised_rate")
            forest_loss_ha = payload.get("nature.forest_loss.ha")
            lines = [
                f"Natural cover lost: **{_fmt(loss_ha, '.1f')} ha** "
                f"({_fmt(loss_pct, '.2f')}% of buffer)",
                f"Natural → built: **{_fmt(nat_to_built, '.1f')} ha**",
                f"Annualised rate: **{_fmt(annualised, '.1f')} ha/yr**",
            ]
            if forest_loss_ha is not None:
                lines.append(
                    f"Hansen forest loss: **{_fmt(forest_loss_ha, '.1f')} ha**"
                )
            st.caption(" · ".join(lines))

        # M-UI-E.4 polish — NDVI mean leads instead of the score, because
        # the score is often None in v1 (depends on trend.py which isn't
        # in the engine yet). Show the score as a secondary metric so the
        # gap is honest, not hidden.
        st.divider()
        st.markdown("**Vegetation condition**")
        col_metric_a, col_metric_b, col_context = st.columns([1, 1, 2])
        with col_metric_a:
            st.metric(
                "Mean NDVI",
                _fmt(payload.get("nature.ndvi.mean"), ".3f"),
            )
        with col_metric_b:
            st.metric(
                "Score",
                _fmt(payload.get("nature.vegetation_condition"), ".2f"),
            )
        with col_context:
            ndvi_anomaly = payload.get("nature.ndvi.anomaly")
            ndvi_z       = payload.get("nature.ndvi.z")
            low_ndvi_pct = payload.get("nature.low_ndvi.pct")
            st.caption(
                f"NDVI anomaly: **{_fmt(ndvi_anomaly, '+.3f')}** "
                f"(z: {_fmt(ndvi_z, '.2f')}) · "
                f"Buffer below NDVI 0.3: **{_fmt(low_ndvi_pct, '.1f')}%**"
            )

        # M-UI-E.4 polish — dominant land cover as a metric with the
        # class-confidence percentage as the delta caption.
        st.divider()
        st.markdown("**Land cover composition (Dynamic World)**")
        col_metric, col_context = st.columns([1, 2])
        with col_metric:
            dominant_class   = payload.get("nature.dw.dominant_class") or "—"
            class_confidence = payload.get("nature.dw.class_confidence")
            st.metric(
                "Dominant class",
                dominant_class,
                delta=f"{_fmt(class_confidence, '.0%')} confidence",
                delta_color="off",
            )
        with col_context:
            _render_dw_composition_table(payload)

        # M-UI-E.4 polish — divider before the datasets-used expander,
        # matching the Air and GHG panels.
        st.divider()
        _render_datasets_used_subexpander("nature", _NATURE_DATASET_KEYS, payload)


def _render_dw_composition_table(payload: dict) -> None:
    """3-column compact table of the 9-class DW breakdown."""
    col1, col2, col3 = st.columns(3)
    cols = (col1, col2, col3)
    for i, (slug, label) in enumerate(_DW_CLASSES):
        pct = payload.get(f"nature.dw.{slug}_pct")
        ha  = payload.get(f"nature.dw.{slug}_ha")
        cols[i % 3].markdown(
            f"- {label}: **{_fmt(pct, '.1f')}%** ({_fmt(ha, '.0f')} ha)"
        )


# ---------------------------------------------------------------------------
# "Datasets used" sub-expander
# ---------------------------------------------------------------------------

# Per-pillar list of indicator slugs whose canonical M5.6 provenance
# blocks live at ``_provenance.<pillar>.<slug>``. Verified against the
# engine source — every key listed is emitted by run_pillar.
_AIR_DATASET_KEYS:    tuple[str, ...] = (
    "no2", "so2", "co", "hcho", "pm25", "pm10", "o3", "aai", "aod",
)
_GHG_DATASET_KEYS:    tuple[str, ...] = ("ch4", "co2", "viirs")
_NATURE_DATASET_KEYS: tuple[str, ...] = (
    "kba", "dw", "habitat", "forest_loss", "ndvi", "water", "recovery",
)


def _render_datasets_used_subexpander(
    pillar:          str,
    indicator_keys:  tuple[str, ...],
    payload:         dict,
) -> None:
    """One block per indicator showing the canonical 11-field provenance.

    Missing provenance (``None``) renders as 'Not available' rather
    than blowing up — a pillar-wide failure still produces a payload
    with the indicator's score = None and no provenance block.
    """
    with st.expander("Datasets used"):
        for indicator in indicator_keys:
            provenance = payload.get(f"_provenance.{pillar}.{indicator}")
            st.markdown(f"**{pillar}.{indicator}**")
            if provenance is None:
                st.caption("Not available.")
                st.markdown("---")
                continue
            _render_provenance_block(provenance)
            st.markdown("---")


def _render_provenance_block(provenance: dict) -> None:
    """Render one canonical 11-field M5.6 provenance block.

    Skipped-coverage path: when ``skipped_reason`` is set, render the
    skip note prominently and keep the rest as muted detail.
    """
    skipped = provenance.get("skipped_reason")
    if skipped:
        st.warning(f"Skipped: {skipped}")

    data_source = provenance.get("data_source") or "—"
    asset_id    = provenance.get("asset_id")    or "—"
    data_type   = provenance.get("data_type")   or "—"
    st.markdown(
        f"- Source: **{data_source}** ({data_type})\n"
        f"- Asset: `{asset_id}`"
    )

    band         = provenance.get("band") or "—"
    native_scale = provenance.get("native_scale_m")
    time_range   = provenance.get("time_range") or ["—", "—"]
    observations = provenance.get("observations")
    method_note  = provenance.get("method_note")
    coverage     = provenance.get("coverage_window")

    details = [
        f"- Band: `{band}`",
        f"- Native resolution: {native_scale} m" if native_scale else "",
        f"- Time range used: {time_range[0]} → {time_range[1]}",
    ]
    if observations:
        details.append(
            f"- Observations: {observations.get('count', '—')} "
            f"{observations.get('unit', '—')}"
        )
    if coverage:
        details.append(f"- Coverage window: {coverage[0]} → {coverage[1]}")
    if method_note:
        details.append(f"- Method: {method_note}")
    st.markdown("\n".join(d for d in details if d))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_c5_drilldowns(payload: dict) -> None:
    """Render the three C5 pillar drill-down panels."""
    with st.container():
        st.markdown("### Drill-down by pillar")
        _render_air_panel(payload)
        _render_ghg_panel(payload)
        _render_nature_panel(payload)
