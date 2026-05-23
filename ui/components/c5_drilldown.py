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
    COLUMN_TO_SURFACE_MULTIPLIER,
    CONFIDENCE_FORMULA_WEIGHTS,
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
        _render_nature_confidence_row(payload, "nature.kba.confidence")
        _render_confidence_terms_expander(payload, "nature", "kba", "KBA proximity")

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
        _render_nature_confidence_row(payload, "nature.habitat.confidence",        label="habitat")
        _render_nature_confidence_row(payload, "nature.forest_loss.confidence",    label="forest loss")
        _render_nature_confidence_row(payload, "nature.regional_loss_evidence.confidence", label="regional loss evidence")
        _render_confidence_terms_expander(payload, "nature", "habitat",                 "habitat")
        _render_confidence_terms_expander(payload, "nature", "forest_loss",             "forest loss")
        _render_confidence_terms_expander(payload, "nature", "regional_loss_evidence",  "regional loss evidence")

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
        _render_nature_confidence_row(payload, "nature.ndvi.confidence",     label="NDVI")
        _render_nature_confidence_row(payload, "nature.recovery.confidence", label="recovery")
        _render_confidence_terms_expander(payload, "nature", "ndvi",     "NDVI")
        _render_confidence_terms_expander(payload, "nature", "recovery", "recovery")

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
    """
    provenance = payload.get(f"_provenance.{pillar}.{slug}") or {}
    extra      = provenance.get("extra") or {}
    terms      = extra.get("confidence_terms")
    with st.expander(
        f"What's behind this confidence? ({label})",
        expanded=False,
    ):
        _render_confidence_terms(terms)


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
# Public entry point
# ---------------------------------------------------------------------------

def render_c5_drilldowns(payload: dict) -> None:
    """Render the three C5 pillar drill-down panels."""
    with st.container():
        st.markdown("### Drill-down by pillar")
        _render_air_panel(payload)
        _render_ghg_panel(payload)
        _render_nature_panel(payload)
