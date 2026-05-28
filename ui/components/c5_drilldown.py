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

import re
from dataclasses import dataclass

import streamlit as st

from engine.constants import (
    AIR_FOLLOWUP_WEIGHTS,
    COLUMN_TO_SURFACE_MULTIPLIER,
    CONFIDENCE_FORMULA_WEIGHTS,
    GHG_FOLLOWUP_WEIGHTS,
    HABITAT_SPATIAL_LINK_MOD_KM,
    NATURE_FOLLOWUP_WEIGHTS,
)
from ui.components.indicator_info import render_indicator_name_with_info
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
    # M-ATTRIB-A1 (AT16): renamed — measurement quality, not attribution.
    "confidence": ("Measurement quality",     "air.measurement_quality_score"),
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
    # M-ATTRIB-A1 (AT13): renamed — measurement quality, not attribution.
    "quality_attribution":   ("Measurement quality",    "nature.measurement_quality"),
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
    breakdown rendered as ``weight × value = contribution`` per term.

    M-FOLLOWUP-FALLBACK: when the priority is None, render a grey
    "Not available" chip rather than the band-coloured score. Same
    rationale as the C3 chip's no-data variant — strict-None signals a
    real upstream gap and the UI should reflect that, not show a
    misleading "—" in a band-coloured pill.
    """
    priority   = payload.get(priority_key)
    confidence = payload.get(confidence_key)
    glyph      = confidence_glyph(confidence)

    if priority is None:
        st.markdown(
            "**Follow-Up Priority Score** &nbsp; "
            "<span style='background:#9ca3af;color:white;padding:2px 8px;"
            "border-radius:3px;font-weight:600;'>—</span>"
            "&nbsp; <span style='color:#6b7280;'>Not available</span>"
            f"&nbsp;&nbsp; {glyph} confidence",
            unsafe_allow_html=True,
        )
    else:
        band         = band_for_score(priority)
        priority_str = f"{priority:.3f}"
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
    any_missing = False
    for term in formula:
        value = payload.get(term.payload_key)
        if value is None:
            any_missing = True
        contribution = term.weight * value if value is not None else None
        col_n, col_w, col_v, col_c = st.columns([3, 1, 1, 1])
        col_n.markdown(term.display_name)
        col_w.markdown(f"{term.weight:.2f}")
        col_v.markdown(_fmt(value, ".3f"))
        col_c.markdown(f"**{_fmt(contribution, '.3f')}**")

    # M-NATURE-KEYS — surface the v1 gap explicitly. Sub-aggregates can
    # show "—" for two reasons:
    #   1. a genuine v1 engine gap (e.g. nature.vegetation_condition is
    #      always None until engine/core/trend.py / M-TREND-ENGINE lands);
    #   2. dependencies that failed/skipped for this AOI (e.g. DW skipped
    #      because of cloud cover → biodiversity_exposure goes None via
    #      strict-null propagation).
    # The caption fires for either; the C9 partial banner + C4b "Failed"
    # tiles already disambiguate (1) from (2) for the user.
    if any_missing:
        st.caption(
            "Sub-aggregates showing — are not available for this run. "
            "Either the v1 engine doesn't yet compute the aggregate (e.g. "
            "Vegetation condition; lands with the Trend View milestone) "
            "or an upstream indicator was skipped — see the partial-coverage "
            "banner and failed tiles for details."
        )


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
    *,
    indicator_id: str | None = None,
    key_prefix:   str        = "c5_row",
) -> None:
    """Render one indicator row in the uniform 6-column schema.

    M-UI-A2: when ``indicator_id`` is provided, the name column hosts the
    indicator-info popover. Default ``None`` keeps the function callable
    from any future site that doesn't need the popover (degrades to plain
    bold name).
    """
    band   = band_for_score(score)
    colour = band_colour(band)

    col_n, col_v, col_a, col_z, col_c, col_s = st.columns([2, 2, 2, 1, 1, 1])
    with col_n:
        if indicator_id:
            # M-UI-A2 (name-as-trigger): the bold name itself opens the
            # popover. No separate ⓘ element to drift to the bottom of
            # the row, which was the failure mode of the earlier stacked
            # layout.
            render_indicator_name_with_info(
                display_name=display_name,
                indicator_id=indicator_id,
                key_prefix=key_prefix,
            )
        else:
            st.markdown(f"**{display_name}**")
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
            "air.measurement_quality_score",  # M-ATTRIB-A1 (AT16)
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
                indicator_id=f"air.{row.indicator}.score",
                key_prefix="c5_air",
            )
            _render_confidence_terms_expander(
                payload, "air", row.indicator, row.display_name,
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
                indicator_id=f"ghg.{row.indicator}.score",
                key_prefix="c5_ghg",
            )
            _render_confidence_terms_expander(
                payload, "ghg", row.indicator, row.display_name,
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
    """C5c — Nature/Land details (deep-dive). Four sub-sections + DW composition.

    M-UI-A4 (SR13, spec v1.1): the scored Nature *headline* metrics — KBA
    proximity, Dynamic World dominant class, NDVI deviation — now lead the
    C4b indicator snapshot as severity tiles. This panel was restructured
    into the "Nature details" deep-dive: it keeps the pillar Follow-Up
    Priority + formula and the non-tileable supporting detail (KBA
    overlap/ha, habitat sub-breakdowns, the 9-class DW composition table,
    recovery, water area, regional-loss evidence, and the per-indicator
    confidence-term breakdowns).

    Hansen forest loss and ODIAC CO₂ stay in C5 as reference datasets (they
    are NOT snapshot tiles per spec v1.1); their reference-dataset visual
    treatment is M-UI-A6's job, not this milestone's.
    """
    with st.expander("Nature/Land — details (deep-dive)"):
        st.caption(
            "Scored headline Nature indicators (biodiversity proximity, land "
            "cover, vegetation) now lead the Indicator snapshot above. This "
            "section provides the full supporting detail; reference datasets "
            "(e.g. Hansen forest loss) remain here."
        )
        _render_headline(
            "nature.followup_priority",
            "nature.measurement_quality",  # M-ATTRIB-A1 (AT13)
            _NATURE_FORMULA,
            payload,
        )

        # M-UI-E.4 polish — each sub-section leads with an st.metric for
        # the headline value, supporting context renders as a caption
        # alongside. st.divider() separates each sub-section from the
        # previous block (the formula breakdown / preceding sub-section).
        st.divider()
        # M-UI-A2: family-level info popover routes to the KBA card.
        render_indicator_name_with_info(
            display_name="Biodiversity exposure",
            indicator_id="nature.kba.proximity_score",
            key_prefix="c5_nature_biodiversity",
        )
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
        _render_nature_confidence_row(payload, "nature.kba.confidence")
        _render_confidence_terms_expander(payload, "nature", "kba", "KBA proximity")

        # M-UI-E.4 polish — habitat conversion metric + caption.
        st.divider()
        # M-UI-A2: family-level info popover routes to the habitat card.
        render_indicator_name_with_info(
            display_name="Habitat conversion",
            indicator_id="nature.habitat.natural_loss_ha",
            key_prefix="c5_nature_habitat",
        )
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
            # M-UI-A6: the Hansen forest-loss line was removed from this
            # caption — Hansen now lives in the dedicated "Reference
            # datasets" sub-section below so the same dataset doesn't read
            # twice in C5. The habitat sub-breakdowns remain (DW-based,
            # scored).
            lines = [
                f"Natural cover lost: **{_fmt(loss_ha, '.1f')} ha** "
                f"({_fmt(loss_pct, '.2f')}% of buffer)",
                f"Natural → built: **{_fmt(nat_to_built, '.1f')} ha**",
                f"Annualised rate: **{_fmt(annualised, '.1f')} ha/yr**",
            ]
            st.caption(" · ".join(lines))
        # M-ATTRIB-A1 (§5.4): measurement quality + categorical attributability,
        # replacing the old per-indicator confidence rows. The forest_loss and
        # regional_loss_evidence confidence rows are gone — both are reference
        # data, surfaced in the "Reference datasets" sub-section, not here.
        _render_habitat_attributability(payload)

        # M-UI-E.4 polish — NDVI mean leads instead of the score, because
        # the score is often None in v1 (depends on trend.py which isn't
        # in the engine yet). Show the score as a secondary metric so the
        # gap is honest, not hidden.
        st.divider()
        # M-UI-A2: family-level info popover routes to the NDVI card.
        render_indicator_name_with_info(
            display_name="Vegetation condition",
            indicator_id="nature.ndvi.score",
            key_prefix="c5_nature_vegetation",
        )
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
        _render_nature_confidence_row(payload, "nature.ndvi.confidence",     label="NDVI")
        _render_nature_confidence_row(payload, "nature.recovery.confidence", label="recovery")
        _render_confidence_terms_expander(payload, "nature", "ndvi",     "NDVI")
        _render_confidence_terms_expander(payload, "nature", "recovery", "recovery")

        # M-UI-E.4 polish — dominant land cover as a metric with the
        # class-confidence percentage as the delta caption.
        st.divider()
        # M-UI-A2: family-level info popover routes to the DW card.
        render_indicator_name_with_info(
            display_name="Land cover composition (Dynamic World)",
            indicator_id="nature.dw.trees_pct",
            key_prefix="c5_nature_dw",
        )
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
        # M-UI-A1-SURFACE Sub-milestone 1: nature.water has no card of its
        # own; the JRC GSW area is land-cover-adjacent, so its confidence
        # rides with the DW card. nature.dw's own A1 confidence is
        # deliberately not duplicated here — class_confidence already
        # serves as the DW card's confidence affordance.
        _render_nature_confidence_row(payload, "nature.water.confidence", label="water area")
        _render_confidence_terms_expander(payload, "nature", "water", "water area")

        # M-UI-E.4 polish — divider before the datasets-used expander,
        # matching the Air and GHG panels.
        st.divider()
        _render_datasets_used_subexpander("nature", _NATURE_DATASET_KEYS, payload)


def _format_nature_confidence_line(
    confidence: float | None,
    label:      str | None = None,
) -> str:
    """Pure formatter for the Nature per-indicator confidence caption.

    M-UI-A1-SURFACE Sub-milestone 1. Closes the Nature drilldown
    asymmetry where only ``nature.dw.class_confidence`` was rendered
    inline. Each Nature indicator that contributes to a card now
    surfaces its M-TIER-A1 ``<indicator>.confidence`` via this
    caption. Numeric uses 3 decimals per spec (Air/GHG uniform rows
    use ``.2f``; Nature drilldown spec calls for 3 to align with
    the confidence_terms expander coming in Sub-milestone 2).
    """
    glyph  = confidence_glyph(confidence)
    prefix = f"Confidence ({label})" if label else "Confidence"
    return f"{prefix}: {glyph} {_fmt(confidence, '.3f')}"


def _render_nature_confidence_row(
    payload:        dict,
    confidence_key: str,
    label:          str | None = None,
) -> None:
    """Render the per-indicator confidence caption inside a Nature card."""
    confidence = payload.get(confidence_key)
    st.caption(_format_nature_confidence_line(confidence, label=label))


# ---------------------------------------------------------------------------
# M-ATTRIB-A1 — habitat-conversion attributability (C5 §5.3 / §5.4)
# ---------------------------------------------------------------------------

# Badge colours shared with the M-UI-A5 map overlay (AT9) and the bucket
# grammar shared with M-WIND-A1 v2.0 (AT19).
_ATTRIBUTABILITY_COLOURS: dict[str, str] = {
    "high":     "#16a34a",
    "moderate": "#f59e0b",
    "low":      "#dc2626",
}
_ATTRIBUTABILITY_LABELS: dict[str, str] = {
    "high": "High", "moderate": "Moderate", "low": "Low", "sparse": "Sparse",
}


def _spatial_link_terms(payload: dict) -> dict:
    """Pull the M-ATTRIB-A1 spatial-link terms out of provenance.extra."""
    prov = payload.get("_provenance.nature.supplier_spatial_link") or {}
    return (prov.get("extra") or {}).get("spatial_link_terms") or {}


def _render_habitat_attributability(payload: dict) -> None:
    """M-ATTRIB-A1 (§5.4 / §5.3) — the measurement-quality + attributability
    rows for the habitat-conversion panel, plus the Low-only C5 expander.

    Measurement quality and attributability are separate (AT1): the former
    is the habitat indicator's M-TIER-A1 confidence; the latter is the
    categorical supplier→change-centroid offset (does not enter any score).
    """
    # Measurement quality — the habitat indicator's M-TIER-A1 confidence.
    mq = payload.get("nature.habitat.confidence")
    st.caption(f"Measurement quality: {confidence_glyph(mq)} {_fmt(mq, '.3f')}")

    state = payload.get("nature.habitat.attributability_state")
    offset = payload.get("nature.supplier_spatial_link.centroid_offset_km")
    n_change = payload.get("nature.supplier_spatial_link.n_change_pixels")

    if state in _ATTRIBUTABILITY_COLOURS:  # high / moderate / low
        colour = _ATTRIBUTABILITY_COLOURS[state]
        label = _ATTRIBUTABILITY_LABELS[state]
        centred = (
            f" &nbsp;(centred {offset:.1f} km from supplier)"
            if offset is not None else ""
        )
        st.markdown(
            f"Attributability: <span style='color:{colour}'>⬤</span> "
            f"**{label}**{centred}",
            unsafe_allow_html=True,
        )
    elif state == "sparse":
        st.caption(
            "Attributability: Sparse — too few habitat-change pixels "
            f"(N = {n_change or 0}) to locate a change centroid."
        )
    # state absent (habitat not run) → render nothing.

    # C5 expander — Low-only sub-section (§5.3 / AT11), parallel to the
    # coastal-handling and fallback sub-sections.
    if state == "low":
        terms = _spatial_link_terms(payload)
        direction = terms.get("direction") or "—"
        dist = offset if offset is not None else 0.0
        with st.expander("What's behind this attributability?", expanded=False):
            st.markdown("**Habitat attributability context**")
            st.markdown(
                f"Low attribution confidence — habitat changes occurred away "
                f"from the supplier coordinate (**{dist:.1f} km** from supplier)."
            )
            st.markdown(
                f"- Centroid of habitat changes: **{dist:.1f} km** from supplier\n"
                f"- Direction: **{direction}**\n"
                f"- Change pixels: **{n_change or 0}**"
            )
            st.caption(
                "The detected habitat changes are spatially concentrated more "
                f"than {HABITAT_SPATIAL_LINK_MOD_KM:.0f} km from the supplier "
                "coordinate, suggesting they may reflect activities at distant "
                "operations or different actors within the AOI rather than the "
                "supplier itself."
            )

    # Habitat measurement-quality breakdown ("What's behind this measurement?").
    _render_confidence_terms_expander(payload, "nature", "habitat", "habitat")


# ---------------------------------------------------------------------------
# M-UI-A1-SURFACE Sub-milestone 2 — "What's behind this confidence?" panel
# ---------------------------------------------------------------------------

# Per-term display labels + plain-language captions. Copy is the authoritative
# user-facing wording for the four A1 confidence-formula terms and the
# column-to-surface multiplier; ties to docs/M-TIER-A1_plain_language_explainer.md.
# Keys MUST match engine.constants.CONFIDENCE_FORMULA_WEIGHTS.
_CONFIDENCE_TERM_LABELS: dict[str, tuple[str, str]] = {
    "qa": (
        "Data quality",
        "How clean the raw sensor data was",
    ),
    "n_valid": (
        "Observation coverage",
        "How many observation days vs expected for this sensor's revisit cadence",
    ),
    "anomaly_strength": (
        "Anomaly persistence",
        "Fraction of observation days that crossed the anomaly threshold",
    ),
    "spatial_context": (
        "Pixel/buffer match",
        "How well the satellite's pixel size matches the analysis buffer",
    ),
}

_COLUMN_TO_SURFACE_CAPTION: str = (
    "Reduction for satellite measurements that look at the whole air "
    "column rather than ground-level"
)

_STRICT_NONE_TERM_CAPTION: str = (
    "this term couldn't be computed; the indicator's confidence is None "
    "and dropped from the pillar rollup."
)


@dataclass(frozen=True)
class _ConfidenceTermRow:
    """One row inside the confidence_terms breakdown table.

    `value` and `contribution` are None for strict-None propagation —
    matches engine.core.confidence.compute_indicator_confidence.
    """

    key:          str
    display_name: str
    caption:      str
    value:        float | None
    weight:       float
    contribution: float | None


def _build_confidence_terms_rows(
    terms: dict | None,
) -> list[_ConfidenceTermRow] | None:
    """Pure helper — return per-term rows for rendering, or None if
    terms is missing/empty.

    Iterates over CONFIDENCE_FORMULA_WEIGHTS so the row order tracks the
    engine's canonical term order. Each row carries the value (or None),
    the engine's weight for that term, and the precomputed contribution
    (value × weight, or None on strict-None).
    """
    if not terms:
        return None
    rows: list[_ConfidenceTermRow] = []
    for key, weight in CONFIDENCE_FORMULA_WEIGHTS.items():
        display_name, caption = _CONFIDENCE_TERM_LABELS[key]
        value = terms.get(key)
        contribution = value * weight if value is not None else None
        rows.append(_ConfidenceTermRow(
            key=key,
            display_name=display_name,
            caption=caption,
            value=value,
            weight=weight,
            contribution=contribution,
        ))
    return rows


def _compute_final_confidence(
    terms: dict | None,
) -> tuple[float | None, float | None, str | None]:
    """Pure helper — return (c_raw, c_final, uncertainty_tag).

    Mirrors engine.core.confidence.compute_indicator_confidence's
    strict-None semantics and column-to-surface multiplier. Used to
    render the highlighted final confidence at the bottom of the
    breakdown. Returning the math here (rather than reading the
    payload's `.confidence` field) lets the caller verify the
    breakdown adds up to the final number on screen.
    """
    if not terms:
        return None, None, None
    tag = terms.get("column_to_surface_uncertainty")
    values = [terms.get(k) for k in CONFIDENCE_FORMULA_WEIGHTS]
    if any(v is None for v in values):
        return None, None, tag
    c_raw = sum(
        v * w for v, w in zip(values, CONFIDENCE_FORMULA_WEIGHTS.values())
    )
    if tag in COLUMN_TO_SURFACE_MULTIPLIER:
        multiplier = COLUMN_TO_SURFACE_MULTIPLIER[tag]
        c_final = max(0.0, min(1.0, c_raw * multiplier))
    else:
        c_final = c_raw
    return c_raw, c_final, tag


def _should_render_column_to_surface_row(tag: str | None) -> bool:
    """True iff the column-to-surface multiplier is < 1.0.

    M-UI-A1-SURFACE Sub-milestone 2 fix (24 May 2026). When the
    multiplier is 1.00 (tags ``n_a`` and ``strong``), the row adds no
    information — the formula's contribution is the same as if the
    multiplier weren't applied — so the expander suppresses it. The
    row only renders for tags that actually penalise: ``moderate``
    (0.95), ``moderate_weak`` (0.88), ``weak`` (0.80).
    """
    if not tag or tag not in COLUMN_TO_SURFACE_MULTIPLIER:
        return False
    return COLUMN_TO_SURFACE_MULTIPLIER[tag] < 1.0


def _render_confidence_terms(terms: dict | None) -> None:
    """Render the 4-term confidence breakdown inside an expandable section.

    `terms` is the dict from ``_provenance.<indicator>.extra.confidence_terms``:
    ``{qa, n_valid, anomaly_strength, spatial_context, column_to_surface_uncertainty}``.

    Layout per term: name + caption + value (3 dp) + 0-1 progress bar +
    ``× weight = contribution``. After the four rows: column-to-surface
    adjustment (enum tag + multiplier) and the final confidence value
    band-coloured per the same thresholds the C3 chip uses.

    Strict-None: a per-term None renders "—" + the strict-None caption;
    a None/empty dict short-circuits to "No confidence breakdown
    available for this indicator."
    """
    rows = _build_confidence_terms_rows(terms)
    if rows is None:
        st.caption("No confidence breakdown available for this indicator.")
        return

    for row in rows:
        col_name, col_value, col_bar, col_contrib = st.columns([3, 1, 2, 2])
        with col_name:
            st.markdown(f"**{row.display_name}**")
            st.caption(row.caption)
        with col_value:
            st.markdown(f"`{_fmt(row.value, '.3f')}`")
        with col_bar:
            if row.value is not None:
                st.progress(max(0.0, min(1.0, row.value)))
            else:
                st.caption("—")
        with col_contrib:
            if row.contribution is not None:
                st.markdown(
                    f"× {row.weight:.2f} = **{row.contribution:.3f}**"
                )
            else:
                st.caption(_STRICT_NONE_TERM_CAPTION)

    c_raw, c_final, tag = _compute_final_confidence(terms)
    st.divider()
    # M-UI-A1-SURFACE Sub-milestone 2 fix (24 May 2026): suppress the
    # column-to-surface adjustment row entirely when the multiplier is
    # 1.00 (i.e. tag in {`n_a`, `strong`}). The row only adds visual
    # noise when the multiplier doesn't actually penalise the score.
    if _should_render_column_to_surface_row(tag):
        multiplier = COLUMN_TO_SURFACE_MULTIPLIER[tag]
        col_tag, col_mult = st.columns([3, 3])
        with col_tag:
            st.markdown("**Column-to-surface adjustment**")
            st.caption(_COLUMN_TO_SURFACE_CAPTION)
        with col_mult:
            st.markdown(
                f"Tag: `{tag}` &nbsp; × **{multiplier:.2f}**"
            )

    if c_final is not None:
        colour = band_colour(band_for_score(c_final))
        st.markdown(
            "**Final confidence:** "
            f"<span style='background:{colour};color:white;padding:2px 8px;"
            f"border-radius:3px;font-weight:600;'>{c_final:.3f}</span>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "**Final confidence:** "
            "<span style='color:#6b7280;'>Not available "
            "(strict-None propagation)</span>",
            unsafe_allow_html=True,
        )


def _render_confidence_terms_expander(
    payload: dict,
    pillar:  str,
    slug:    str,
    label:   str,
) -> None:
    """Wire the breakdown helper to the payload's provenance.extra.

    Pull ``_provenance.<pillar>.<slug>.extra.confidence_terms`` from
    the payload and render it inside an ``st.expander``. Nesting depth
    is panel-expander → this expander, same depth as the existing
    "Datasets used" sub-expander (verified working in Streamlit 1.57).

    M-TIER-A3 Step H2 — when the background ring is partly over water
    (``ring_land_fraction < 1.0``), append a "Coastal handling"
    sub-section explaining how the land mask shaped the baseline.
    Fully inland AOIs see no change to the expander (sub-section omitted).
    """
    provenance = payload.get(f"_provenance.{pillar}.{slug}") or {}
    extra      = provenance.get("extra") or {}
    terms      = extra.get("confidence_terms")
    with st.expander(
        f"What's behind this confidence? ({label})",
        expanded=False,
    ):
        _render_confidence_terms(terms)
        _render_coastal_handling_section(extra)
        _render_fallback_section(extra)


# ---------------------------------------------------------------------------
# M-TIER-A3 Step H2 — "Coastal handling" sub-section inside the C5 expander
# ---------------------------------------------------------------------------

# Visibility threshold per spec §3.8 — render the sub-section only when the
# ring is at least partly over water. Fully inland AOIs (land_fraction ≈ 1.0)
# see no change to the expander.
_COASTAL_HANDLING_VISIBILITY_THRESHOLD: float = 1.0

# Warning band threshold per spec §3.8 — append a methodology caveat when
# the residual land area is small but above LM7's hard skip floor (0.05).
_COASTAL_HANDLING_WARNING_THRESHOLD: float = 0.20

_COASTAL_HANDLING_HEADER: str = "**Coastal handling**"

_COASTAL_HANDLING_BODY_TEMPLATE: str = (
    "This site is near water. The surrounding comparison area "
    "(the *background ring*) overlaps the coastline, so **{water_pct}%** of "
    "it is ocean. The tool excludes those ocean pixels from the comparison, "
    "leaving the remaining **{land_pct}%** of land to serve as the baseline."
    "\n\n"
    "Without this adjustment, ocean pixels — which have near-zero pollution "
    "and would otherwise be averaged in as \"clean background\" — would "
    "artificially depress the baseline and inflate the supplier's anomaly "
    "score. The land-only baseline gives a more honest comparison against "
    "the surrounding terrestrial area."
)

_COASTAL_HANDLING_WARNING: str = (
    "This site's comparison area is mostly water; the baseline is computed "
    "from a small land area and should be interpreted with care."
)


def _format_coastal_handling_pcts(
    land_fraction: float,
) -> tuple[int, int]:
    """Return (water_pct, land_pct) for the spec §3.8 template, rounded to ints.

    Pure helper so the rounding rule has a single source of truth and the
    rendering function stays declarative.
    """
    land_pct = round(max(0.0, min(1.0, land_fraction)) * 100)
    water_pct = 100 - land_pct
    return water_pct, land_pct


def _render_coastal_handling_section(extra: dict | None) -> None:
    """Render the spec §3.8 Surface 1 sub-section, or no-op.

    Visibility:
      - Sub-section is omitted entirely when `extra` is absent / lacks
        `ring_land_fraction` / `ring_land_fraction >= 1.0` (fully inland)
        / `land_mask_applied` is False.
      - When 0.20 ≤ land_fraction < 1.0: header + body template.
      - When 0.05 < land_fraction < 0.20: header + body + warning caveat.
        (Below 0.05 the LM7 floor fires the skip path before we ever
        reach the C5 expander; the warning is the surfacing for the
        narrow "mostly-water but not empty" band.)
    """
    if not isinstance(extra, dict):
        return
    land_fraction = extra.get("ring_land_fraction")
    if land_fraction is None or land_fraction >= _COASTAL_HANDLING_VISIBILITY_THRESHOLD:
        return
    if extra.get("land_mask_applied") is False:
        # Mask not applied; the section's claims would be misleading.
        return

    water_pct, land_pct = _format_coastal_handling_pcts(land_fraction)
    st.divider()
    st.markdown(_COASTAL_HANDLING_HEADER)
    st.markdown(_COASTAL_HANDLING_BODY_TEMPLATE.format(
        water_pct=water_pct, land_pct=land_pct,
    ))
    if land_fraction < _COASTAL_HANDLING_WARNING_THRESHOLD:
        st.warning(_COASTAL_HANDLING_WARNING)


# ---------------------------------------------------------------------------
# M-FALLBACK-A1 §5.2 — "Fallback applied" sub-sections inside the C5 expander
# ---------------------------------------------------------------------------
# Extends the M-TIER-A3 coastal-handling pattern: each sub-section is
# conditionally rendered from the corresponding provenance.extra flag
# (temporal_fallback_used / climatology_fallback_used).

_TEMPORAL_FALLBACK_HEADER: str = "**Fallback applied**"

_TEMPORAL_FALLBACK_SPPY_BODY: str = (
    "This indicator used **same-period-previous-year** data ({window}) "
    "because current-window observations were too sparse to compute a "
    "reliable value. Confidence is reduced to reflect that year-old data is "
    "degraded evidence."
)

_TEMPORAL_FALLBACK_SLIDING_BODY: str = (
    "This indicator used data from an **earlier window with adequate "
    "coverage** ({window}) because the current window's observations were "
    "too sparse. Confidence is reduced to reflect that the data is not from "
    "the requested period."
)

_CLIMATOLOGY_FALLBACK_HEADER: str = "**Regional baseline**"

_CLIMATOLOGY_FALLBACK_BODY: str = (
    "The background comparison uses the **country-level regional baseline** "
    "({vintage} vintage) because the area around the site had insufficient "
    "satellite coverage to build a local comparison ring. Confidence is "
    "reduced to reflect the coarser, regional-scale baseline."
)


def _format_fallback_window(source_window: str | None) -> str:
    """Turn the stored ``"<start>/<end>"`` provenance string into prose.

    Returns ``"<start> to <end>"`` or a neutral fallback phrase if the
    field is missing / malformed.
    """
    if not source_window or "/" not in source_window:
        return "an earlier period"
    start, _, end = source_window.partition("/")
    return f"{start} to {end}"


def _render_fallback_section(extra: dict | None) -> None:
    """Render the §5.2 fallback sub-sections, or no-op when none fired.

    Two independent, conditionally-rendered blocks:
      - temporal (1.1 SPPY / sliding-lookback) when ``temporal_fallback_used``
      - climatology (1.2 regional baseline) when ``climatology_fallback_used``
    Both can render together (the compound-fallback case).
    """
    if not isinstance(extra, dict):
        return

    if extra.get("temporal_fallback_used"):
        strategy = extra.get("temporal_fallback_strategy")
        window = _format_fallback_window(extra.get("temporal_fallback_source_window"))
        body = (
            _TEMPORAL_FALLBACK_SLIDING_BODY
            if strategy == "sliding_lookback"
            else _TEMPORAL_FALLBACK_SPPY_BODY
        )
        st.divider()
        st.markdown(_TEMPORAL_FALLBACK_HEADER)
        st.markdown(body.format(window=window))

    if extra.get("climatology_fallback_used"):
        vintage = extra.get("climatology_fallback_vintage") or "latest"
        st.divider()
        st.markdown(_CLIMATOLOGY_FALLBACK_HEADER)
        st.markdown(_CLIMATOLOGY_FALLBACK_BODY.format(vintage=vintage))


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
    """One block per indicator showing the canonical 15-field provenance.

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
    """Render one canonical 15-field provenance block.

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

    # M-UI-A1-SURFACE Sub-milestone 3 (24 May 2026): iterate over the
    # provenance.extra dict and surface audit-transparency fields.
    # confidence_terms is deliberately excluded — it has its own
    # dedicated surface in the "What's behind this confidence?"
    # expander (Sub-milestone 2). Do NOT "fix" this exclusion without
    # re-reading the M-UI-A1-SURFACE spec §3 sub-milestone 3 design
    # decision: surfacing confidence_terms here would duplicate content.
    extra_lines = _format_provenance_extra_lines(provenance.get("extra"))
    if extra_lines:
        st.markdown("**Extra (audit transparency)**")
        st.markdown("\n".join(f"- {line}" for line in extra_lines))


# Pretty-name lookup for the known A1 audit-transparency keys in
# `provenance.extra`. Unknown keys fall through to a defensive raw-key
# render so the iteration doesn't silently drop fields the engine adds
# later without a UI update.
_EXTRA_FIELD_LABELS: dict[str, str] = {
    "n_valid_dates":               "Valid dates observed",
    "granule_count":                "Raw image (granule) count",
    "column_to_surface_multiplier": "Column-to-surface multiplier",
    # M-TIER-A3 Step H2 — MOD44W land-mask audit-transparency fields.
    "ring_land_fraction":           "Background ring land fraction",
    "land_mask_applied":            "Land mask applied to ring",
    "land_mask_asset":              "Land mask asset",
}


def _format_extra_value(value) -> str:
    """Format an `extra` field value for a single-line label:value cell.

    Ints render as ints; floats with 3 decimals; nested dicts/lists are
    pretty-printed inline (compact JSON). Anything else falls through to
    ``str(value)`` — defensive, never crashes.
    """
    if value is None:
        return "—"
    if isinstance(value, bool):
        # bool is a subclass of int — handle before the int branch.
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, (list, tuple, dict)):
        try:
            import json
            return f"`{json.dumps(value, default=str)}`"
        except (TypeError, ValueError):
            return f"`{value!r}`"
    return str(value)


def _format_provenance_extra_lines(extra) -> list[str]:
    """Pure helper — return a list of markdown lines for the extras section.

    Returns an empty list when extra is None / empty / not a dict, or
    when it contains only the ``confidence_terms`` key (which is rendered
    separately in the C5 confidence-terms expander).
    """
    if not isinstance(extra, dict) or not extra:
        return []
    lines: list[str] = []
    for key, value in extra.items():
        if key == "confidence_terms":
            # See _render_provenance_block — deliberate exclusion.
            continue
        label = _EXTRA_FIELD_LABELS.get(key, key)
        lines.append(f"{label}: {_format_extra_value(value)}")
    return lines


# ---------------------------------------------------------------------------
# M-UI-A6 — Reference datasets (Hansen forest loss + ODIAC CO₂) in C5
# ---------------------------------------------------------------------------
#
# Hansen and ODIAC were demoted out of the live composite (audit §9.3 v1.4 /
# M5.5b) and removed from the C4b headline grid (M-UI-A4 v1.1). They survive
# in C5 as *reference* context: cumulative / inventory-allocated values that
# complement the live screening window without being scored. This sub-section
# renders them with deliberately muted chrome (no severity badge, no
# confidence dot — RD3/RD4) so they read as context, not as a finding.
#
# Vintage is derived in the UI (no engine change, per Step B decision):
# ODIAC from its provenance coverage_window; Hansen from the year embedded in
# its provenance asset_id, falling back to a constant kept in lockstep with
# engine.nature._HANSEN_MAX_LOSS_YEAR.

# RD5 — canonical badge text. Single phrasing, no per-indicator variation.
_REFERENCE_BADGE_TEXT: str = "Reference dataset — not used in composite score"

# §4.1 Hansen interpretation bands. UI-presentation thresholds (the engine
# computes the value; the UI buckets it into prose), so they live here next
# to the rendering — same pattern as the coastal-handling thresholds above,
# not engine.constants. The 1% "moderate" boundary is intentionally aligned
# with engine.constants.HANSEN_VERBAL_MENTION_THRESHOLD (the C7 mention gate).
_HANSEN_SUBSTANTIAL_LOSS_PCT: float = 5.0
_HANSEN_MODERATE_LOSS_PCT:    float = 1.0

# Fallback Hansen vintage when the provenance asset_id can't be parsed.
# Mirrors engine.nature._HANSEN_MAX_LOSS_YEAR (23 → 2023); bump in lockstep
# when the Hansen asset vintage advances.
_HANSEN_VINTAGE_FALLBACK_YEAR: int = 2023

# §4 source lines.
_HANSEN_SOURCE_LINE: str = "Hansen Global Forest Change (University of Maryland)"
_ODIAC_SOURCE_LINE:  str = "ODIAC fossil-fuel CO₂ (NIES, Japan)"

# §4.1 / RD8 — Hansen audit footnote (what Hansen *does* feed).
_HANSEN_AUDIT_FOOTNOTE: str = (
    "Hansen contributes to the regional_loss_evidence binary flag in "
    "External Driver Screening when ring-vs-buffer loss differs "
    "significantly, but is not part of the composite score."
)
# §4.2 — ODIAC audit footnote.
_ODIAC_AUDIT_FOOTNOTE: str = (
    "ODIAC is an inventory-allocated dataset, not an atmospheric "
    "measurement, and is not used in the composite score."
)

# §4.2 — ODIAC interpretation. No high/low conditional copy in v1.x (the
# metric needs regional contextualisation this milestone doesn't supply).
_ODIAC_INTERPRETATION: str = (
    "Inventory-allocated estimate of fossil-fuel CO₂ emissions density in "
    "the AOI."
)
_ODIAC_UNAVAILABLE_INTERPRETATION: str = (
    "ODIAC data is not available for the requested year range."
)

# RD12 — common missing-data headline replacement.
_DATA_UNAVAILABLE_TEXT: str = "Data not available for this AOI"

# §4.3 — sub-section header disclaimer (the most important defensive copy).
# The second sentence (M-UI-A6 follow-up) makes the fixed-window /
# cross-reference-only framing explicit: these values sit on a fixed,
# latest-available window that need not align with the analysis period.
_REFERENCE_SECTION_HEADER_COPY: str = (
    "The following data are shown for context and are not part of the "
    "composite score. They reflect cumulative or inventory-allocated values "
    "over a fixed, latest-available window — not your analysis window — so "
    "use them to cross-reference the live signals rather than as "
    "measurements of the screening period."
)

# §5.3 / RD11 — "Why reference data?" explainer (sub-section-level per the
# Step B decision on Q-A6-1).
_WHY_REFERENCE_DATA_COPY: str = (
    "Hansen forest loss and ODIAC CO₂ aren't included in the composite "
    "score because they measure different things from the live indicators. "
    "Hansen is a cumulative tally of forest cover loss over a multi-year "
    "window; ODIAC is an annual inventory of estimated fossil-fuel "
    "emissions allocated to grid cells. Both are shown here as **context** — "
    "useful background that complements the live screening signals without "
    "competing with them on the same scale."
)


def _parse_year_from_asset_id(asset_id: str | None) -> int | None:
    """Extract a 4-digit vintage year from a provenance ``asset_id``.

    Hansen embeds its release year in the asset path
    (``UMD/hansen/global_forest_change_2023_v1_11`` → 2023). Returns the
    last 19xx/20xx run in the string, or None if none is present.
    """
    if not asset_id:
        return None
    matches = re.findall(r"(?:19|20)\d{2}", asset_id)
    return int(matches[-1]) if matches else None


def _hansen_vintage_year(payload: dict) -> int:
    """Hansen vintage — parsed from the forest_loss provenance asset_id,
    falling back to the module constant when provenance is absent."""
    provenance = payload.get("_provenance.nature.forest_loss") or {}
    year = _parse_year_from_asset_id(provenance.get("asset_id"))
    return year if year is not None else _HANSEN_VINTAGE_FALLBACK_YEAR


def _odiac_vintage_year(payload: dict) -> int | None:
    """ODIAC vintage — the latest year of the CO₂ provenance coverage_window
    (e.g. ``["2020-01-01", "2023-12-31"]`` → 2023). None when absent."""
    provenance = payload.get("_provenance.ghg.co2") or {}
    window = provenance.get("coverage_window")
    if not window or len(window) < 2 or not window[1]:
        return None
    try:
        return int(str(window[1])[:4])
    except (ValueError, TypeError):
        return None


def _hansen_interpretation(loss_pct: float | None) -> str:
    """§4.1 — one-sentence interpretation keyed to the cumulative loss band."""
    if loss_pct is None:
        return "Hansen data is not available for this AOI."
    if loss_pct >= _HANSEN_SUBSTANTIAL_LOSS_PCT:
        return (
            "Substantial cumulative loss in the buffer area; consider how "
            "recent deforestation may relate to this supplier."
        )
    if loss_pct >= _HANSEN_MODERATE_LOSS_PCT:
        return "Moderate cumulative loss in the buffer area."
    return "Minimal cumulative loss in the buffer area."


@dataclass(frozen=True)
class _ReferenceCardFields:
    """Resolved, render-ready content for one reference card (RD7 order).

    Pure data — built by the per-indicator field helpers and consumed by
    ``_render_reference_card``. ``value_str is None`` is the RD12
    missing-data signal (card still renders; headline shows the
    data-unavailable message).
    """

    display_name:   str
    indicator_id:   str        # P-09 library key for the M-UI-A2 affordance
    key_prefix:     str
    value_str:      str | None
    unit_line:      str
    vintage_line:   str
    source_line:    str
    interpretation: str
    audit_footnote: str
    # M-ATTRIB-A1 (AT6/AT22): optional regional-context line (Hansen only).
    regional_context: str | None = None


def _regional_context_line(payload: dict) -> str | None:
    """M-ATTRIB-A1 (§5.5 / AT6) — the Hansen-card regional-context line.

    Reads the reference-data ring-vs-buffer ratio + window from the
    regional_loss_evidence reframe (Step F) and pairs the headline ratio
    line with a one-sentence interpretation keyed to the ratio band.
    Returns None when the ratio is unavailable (line is then omitted).
    """
    ratio = payload.get("nature.regional_loss_evidence.ratio")
    window = payload.get("nature.regional_loss_evidence.window")
    if ratio is None or window is None:
        return None
    if ratio < 0.5:
        interp = (
            "Forest loss in the surrounding ring is lower than within the "
            "buffer — the supplier's buffer area was a relatively active "
            "deforestation pocket."
        )
    elif ratio <= 2.0:
        interp = (
            "Forest loss in the ring and buffer are similar — no strong "
            "regional vs local pattern."
        )
    else:
        interp = (
            "Forest loss in the surrounding ring is higher than within the "
            "buffer — the supplier's buffer was relatively quiet within a "
            "broader regional deforestation pattern."
        )
    return (
        f"Regional context: ring loss is {ratio:.1f}× buffer loss over "
        f"{window}. {interp}"
    )


def _hansen_card_fields(payload: dict) -> _ReferenceCardFields:
    """§4.1 — resolve the Hansen reference card content from the payload."""
    loss_pct = payload.get("nature.forest_loss.pct")
    value_str = None if loss_pct is None else f"{loss_pct:.2f}%"
    vintage = _hansen_vintage_year(payload)
    return _ReferenceCardFields(
        display_name="Hansen forest loss",
        indicator_id="nature.forest_loss.ha",   # P-09 card key (A.4)
        key_prefix="c5_ref_hansen",
        value_str=value_str,
        unit_line="of buffer area lost (5-year cumulative)",
        vintage_line=f"Latest Hansen data: {vintage}",
        source_line=_HANSEN_SOURCE_LINE,
        interpretation=_hansen_interpretation(loss_pct),
        audit_footnote=_HANSEN_AUDIT_FOOTNOTE,
        regional_context=_regional_context_line(payload),  # M-ATTRIB-A1 (AT22)
    )


def _odiac_card_fields(payload: dict) -> _ReferenceCardFields:
    """§4.2 — resolve the ODIAC reference card content from the payload."""
    co2_mean = payload.get("ghg.co2.mean")
    value_str = (
        None if co2_mean is None else f"{co2_mean:,.0f} t CO₂ yr⁻¹ per pixel"
    )
    vintage = _odiac_vintage_year(payload)
    vintage_line = (
        f"Latest ODIAC year: {vintage}" if vintage is not None
        else "Latest ODIAC year: —"
    )
    interpretation = (
        _ODIAC_INTERPRETATION if co2_mean is not None
        else _ODIAC_UNAVAILABLE_INTERPRETATION
    )
    return _ReferenceCardFields(
        display_name="CO₂ (ODIAC)",
        indicator_id="ghg.co2.score",            # P-09 card key (A.4)
        key_prefix="c5_ref_odiac",
        value_str=value_str,
        unit_line="annual emissions intensity",
        vintage_line=vintage_line,
        source_line=_ODIAC_SOURCE_LINE,
        interpretation=interpretation,
        audit_footnote=_ODIAC_AUDIT_FOOTNOTE,
    )


def _render_reference_card(fields: _ReferenceCardFields) -> None:
    """Render one reference card per the RD7 standardised structure.

    Visual chrome is deliberately muted (RD6): the name uses the M-UI-A2
    popover affordance (which carries the "Learn more →" P-09 link — Step B
    decision: no separate bottom link), a subtle small-caps badge, a
    smaller-than-verdict headline (1.6em), muted greys, and an italic audit
    footnote. No severity badge and no confidence dot (RD3/RD4).
    """
    with st.container(border=True):
        # RD7 #1 — name + M-UI-A2 affordance (popover → "Learn more →" P-09).
        render_indicator_name_with_info(
            display_name=fields.display_name,
            indicator_id=fields.indicator_id,
            key_prefix=fields.key_prefix,
        )
        # RD7 #2 / RD5 — badge. Small-caps, muted background, no severity hue.
        st.markdown(
            "<span style='display:inline-block;font-size:0.72em;"
            "font-variant:small-caps;letter-spacing:0.03em;"
            "background:rgba(255,255,255,0.06);color:#9ca3af;"
            "border:1px solid rgba(255,255,255,0.14);padding:1px 8px;"
            f"border-radius:3px;'>{_REFERENCE_BADGE_TEXT}</span>",
            unsafe_allow_html=True,
        )
        # RD7 #3 — headline value + unit, or the RD12 unavailable message.
        if fields.value_str is None:
            st.markdown(
                "<div style='font-size:1.1em;color:#9ca3af;margin-top:8px;'>"
                f"{_DATA_UNAVAILABLE_TEXT}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='font-size:1.6em;font-weight:600;margin-top:8px;"
                f"color:#e5e7eb;'>{fields.value_str}</div>"
                "<div style='font-size:0.85em;color:#9ca3af;'>"
                f"{fields.unit_line}</div>",
                unsafe_allow_html=True,
            )
        # RD7 #4/#5 — vintage + source.
        st.markdown(
            "<div style='font-size:0.9em;color:#9ca3af;margin-top:10px;'>"
            f"{fields.vintage_line}<br>Source: {fields.source_line}</div>",
            unsafe_allow_html=True,
        )
        # M-ATTRIB-A1 (§5.5 / AT6/AT22) — regional-context line (Hansen only),
        # between source and interpretation.
        if fields.regional_context is not None:
            st.markdown(
                "<div style='font-size:0.9em;color:#9ca3af;margin-top:8px;'>"
                f"{fields.regional_context}</div>",
                unsafe_allow_html=True,
            )
        # RD7 #6 — one-sentence interpretation.
        st.markdown(
            f"<div style='margin-top:10px;'>{fields.interpretation}</div>",
            unsafe_allow_html=True,
        )
        # §5.4 — italic audit footnote.
        st.markdown(
            "<div style='font-size:0.85em;color:#9ca3af;font-style:italic;"
            f"margin-top:4px;'>{fields.audit_footnote}</div>",
            unsafe_allow_html=True,
        )


def _render_reference_datasets_section(payload: dict) -> None:
    """RD2 — the "Reference datasets" sub-section in C5.

    Hansen + ODIAC cards (RD1), rendered after the scored Nature deep-dive
    and before C6. Presented as a **collapsed expander**, consistent with the
    three pillar drill-down panels above, so it reads as a peer item rather
    than an always-open block; the §4.3 disclaimer caption is the first thing
    shown on expand. Both cards always render (RD12) — the missing-data state
    lives inside each card so the examiner knows the dataset was queried.
    Two-column on desktop, stacks on narrow viewports (RD §5.2). The
    structure is reusable for future reference datasets (RD14): add a field
    helper + a card column.
    """
    st.divider()
    with st.expander("Reference datasets", expanded=False):
        st.caption(_REFERENCE_SECTION_HEADER_COPY)
        col_hansen, col_odiac = st.columns(2)
        with col_hansen:
            _render_reference_card(_hansen_card_fields(payload))
        with col_odiac:
            _render_reference_card(_odiac_card_fields(payload))
        # RD11 / Q-A6-1 — single sub-section-level explainer.
        with st.expander("Why reference data?", expanded=False):
            st.markdown(_WHY_REFERENCE_DATA_COPY)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_c5_drilldowns(payload: dict) -> None:
    """Render the three C5 pillar drill-down panels + the reference-dataset
    sub-section (M-UI-A6)."""
    with st.container():
        st.markdown("### Drill-down by pillar")
        _render_air_panel(payload)
        _render_ghg_panel(payload)
        _render_nature_panel(payload)
        # M-UI-A6 (RD2) — reference datasets after the scored Nature
        # deep-dive, before C6.
        _render_reference_datasets_section(payload)
