"""Section functions for P-11 reports (M-P11.2).

Each section is one function returning an HTML fragment. The
renderer composes a template's report by calling sections in the
order declared by the template's ``sections`` tuple, joining the
fragments inside the Jinja shell.

Reuses ``engine.verbal_summary.generate_verbal_summary`` so report
prose stays in lockstep with P-05's C7 surface.
"""

# M-P11.2 / M-REPORT-A1
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from engine.constants import (
    AIR_FOLLOWUP_WEIGHTS,
    GHG_FOLLOWUP_WEIGHTS,
    NATURE_FOLLOWUP_WEIGHTS,
    TRAFFIC_LIGHT_THRESHOLDS,
)
from engine.verbal_summary import generate_verbal_summary
from ui.components.p04_indicator_registry import (
    ALL_INDICATOR_IDS,
    INDICATORS_BY_PILLAR,
    display_name,
)
from ui.components.p11_esrs import (
    PILLAR_ESRS,
    esrs_metrics_intro,
    esrs_out_of_scope_stub,
    esrs_topic_heading,
)
from ui.components.p11_templates import ALL_PILLARS
from ui.components.trend_record import (
    significance_text,
    slope_display,
    verdict_badge,
)
from ui.components.trend_svg import build_trend_svg


# ──────────────────────────────────────────────────────────────────
# Render context (M-REPORT-A1, Step A §8.1 — flat model + threading)
# ──────────────────────────────────────────────────────────────────

# Locked pillar render order (CLAUDE.md §7: air → ghg → nature).
_PILLAR_ORDER: tuple[str, ...] = ("air", "ghg", "nature")

# Per-pillar follow-up-priority key + display label (the pillar's headline
# severity metric). Composite is deliberately absent — pillar-specific and
# trend reports carry no composite (RT9), and the per-pillar metric is what
# the ESRS topical sections need.
_PILLAR_SCORE: dict[str, tuple[str, str]] = {
    "air":    ("Air Pollution", "air.audit_followup_priority"),
    "ghg":    ("GHG Emissions", "ghg.audit_followup_priority"),
    "nature": ("Nature/Land",   "nature.followup_priority"),
}


@dataclass(frozen=True)
class RenderContext:
    """Render-time context threaded into section functions (Step A §8.1).

    Built by the assembler from the template + the active ``user_type``. Carries
    the framing decisions the flat section model can't infer on its own:
    which pillars to render, and whether the ESRS layer is active. The General
    report's dual framing (RT8) is exactly ``apply_esrs`` differing by user type.
    """
    user_type:   str            = ""
    pillars:     frozenset[str] = ALL_PILLARS
    apply_esrs:  bool           = False
    template_id: str            = ""

    @classmethod
    def from_template(cls, template, user_type: str) -> "RenderContext":
        # ESRS framing (RT4) only takes effect for MNC renders. A policy maker
        # picking the General report gets the same body with ESRS stripped (RT8).
        return cls(
            user_type=user_type or "",
            pillars=template.pillars,
            apply_esrs=bool(template.esrs) and (user_type == "mnc"),
            template_id=template.template_id,
        )


def _ctx(ctx: "RenderContext | None") -> "RenderContext":
    """Resolve a default context for direct (test) calls with no ctx."""
    return ctx if ctx is not None else RenderContext()


def _ordered_pillars(pillars: frozenset[str]) -> list[str]:
    """The active pillars in the locked air → ghg → nature order."""
    return [p for p in _PILLAR_ORDER if p in pillars]


# M-REPORT-A1.1 (RF1) — the report-template identity shown on the cover.
def _report_type_name(ctx: "RenderContext") -> str:
    """Human name for the report template, for the cover/title block (RF1).

    ESRS pillar reports → "ESRS E1 — Climate change report" (and E2/E4); the
    General report → "Environmental screening report" (both user-type variants);
    the trend report → "Environmental trend report". A bare/no-ctx render falls
    back to the screening name.
    """
    if ctx.template_id == "trend":
        return "Environmental trend report"
    if ctx.template_id == "general":
        return "Environmental screening report"
    if len(ctx.pillars) == 1:
        pillar = _ordered_pillars(ctx.pillars)[0]
        code, topic = PILLAR_ESRS.get(pillar, ("", pillar))
        return f"ESRS {code} — {topic} report"
    return "Environmental screening report"


def _source_divider(name: str, *, multi: bool) -> str:
    """A per-source section sub-header (RF2).

    Multi-source reports keep the source label as a chapter divider (Wireframes
    P-11 multi-source case). Single-source reports name the source once (in the
    scope / exec summary) and suppress the per-section repetition → returns "".
    """
    return f"<h3>{html.escape(name)}</h3>" if multi else ""


def _indicator_base(registry_id: str) -> str:
    """Value-key base for a registry indicator id (``air.no2.score`` → ``air.no2``)."""
    return registry_id.rsplit(".", 1)[0]


def _attributability_state(payload: dict, base: str) -> str | None:
    """Best-effort attributability state for an indicator (RF3).

    Checks, in order: a direct ``<base>.attributability_state`` payload key
    (VIIRS, habitat conversion), then the indicator's provenance ``extra``
    (M-WIND-A1 ``wind_attributability_state`` for Air; M-ATTRIB-A1
    ``spatial_link_terms.attributability_state`` for the habitat spatial link).
    Returns the capitalised state, or ``None`` when the indicator carries none.
    """
    direct = payload.get(f"{base}.attributability_state")
    if direct:
        return str(direct).capitalize()
    prov = payload.get(f"_provenance.{base}") or {}
    extra = prov.get("extra") if isinstance(prov, dict) else None
    if not isinstance(extra, dict):
        return None
    state = extra.get("wind_attributability_state")
    if not state:
        terms = extra.get("spatial_link_terms")
        if isinstance(terms, dict):
            state = terms.get("attributability_state")
    return str(state).capitalize() if state else None


# ──────────────────────────────────────────────────────────────────
# Section dispatch
# ──────────────────────────────────────────────────────────────────

def get_section(section_key: str) -> Callable | None:
    """Map a template's section key to its render function."""
    return _SECTION_REGISTRY.get(section_key)


# ──────────────────────────────────────────────────────────────────
# Title page
# ──────────────────────────────────────────────────────────────────

def _render_title_page(state, sources, ctx=None) -> str:
    """First page — report-type identity, title, date, source count.

    M-REPORT-A1.1 (RF1): the cover names the report template (ESRS E1/E2/E4
    report, Environmental screening report, or Environmental trend report) so
    the template identity is visible on page one — not only in the findings.
    """
    ctx = _ctx(ctx)
    today = datetime.now(timezone.utc)
    title_text = state.title.strip() if state.title else ""
    title = html.escape(title_text or "Untitled report")
    report_type = html.escape(_report_type_name(ctx))
    date_str = today.strftime("%d %B %Y")
    n_sources = len(sources)
    source_word = "source" if n_sources == 1 else "sources"
    return f"""
    <section>
      <p class="report-type">{report_type}</p>
      <h1>{title}</h1>
      <div class="meta-grid">
        <span class="meta-label">Report type</span><span>{report_type}</span>
        <span class="meta-label">Report date</span><span>{date_str}</span>
        <span class="meta-label">Sources</span><span>{n_sources} {source_word}</span>
        <span class="meta-label">Generated by</span><span>GSCO Environmental Monitoring tool</span>
      </div>
    </section>
    """


# ──────────────────────────────────────────────────────────────────
# Executive summary
# ──────────────────────────────────────────────────────────────────

def _render_executive_summary(state, sources, ctx=None) -> str:
    """Short composite findings summary across all sources.

    M-REPORT-A2 (RA2/RA3): the composite column shows the whole-screening
    ``overall_screening`` (all three pillars). In a single-pillar ESRS report
    (mnc_ghg / air / nature) that is ambiguous — it can read as the pillar's
    own score. There we relabel the column to name it explicitly and add a
    one-line scope-of-composite note. The General report (all three pillars)
    and any direct/no-ctx call are unchanged.
    """
    ctx = _ctx(ctx)
    single_pillar = len(ctx.pillars) == 1
    composite_header = (
        "Overall screening composite (all 3 pillars)"
        if single_pillar else "Composite"
    )

    blocks = ["<section>", "<h2>Executive Summary</h2>"]
    notes_text = (state.notes or "").strip()
    if notes_text:
        blocks.append(f"<p>{html.escape(notes_text)}</p>")
    blocks.append(
        f"<p>This report covers {len(sources)} saved "
        f"{'analysis' if len(sources) == 1 else 'analyses'} "
        f"selected from the GSCO Environmental Monitoring tool.</p>"
    )

    # Per-source one-liner.
    blocks.append("<table>")
    blocks.append(
        f"<tr><th>Source</th><th>Type</th><th>{composite_header}</th>"
        "<th>Band</th></tr>"
    )
    for src in sources:
        name = html.escape(src.get("name", "Untitled"))
        type_ = html.escape(src.get("type", "—"))
        composite = _composite_score(src)
        band, band_label = _band_for_score(composite)
        composite_str = f"{composite:.2f}" if composite is not None else "—"
        blocks.append(
            f"<tr><td>{name}</td><td>{type_}</td><td>{composite_str}</td>"
            f"<td><span class='pillar-chip {band}'>{band_label}</span></td></tr>"
        )
    blocks.append("</table>")

    # RA2 — scope-of-composite note (single-pillar ESRS reports only).
    if single_pillar:
        pillar = _ordered_pillars(ctx.pillars)[0]
        _, topic = PILLAR_ESRS.get(pillar, ("", pillar))
        blocks.append(
            "<p class='composite-scope-note'><em>This report details the "
            f"{html.escape(topic)} pillar only. The overall screening "
            "composite above reflects all three pillars (Air, GHG, Nature) "
            "and is shown for context.</em></p>"
        )

    blocks.append("</section>")
    return "\n".join(blocks)


# ──────────────────────────────────────────────────────────────────
# Methodology
# ──────────────────────────────────────────────────────────────────

def _render_methodology(state, sources, ctx=None) -> str:
    """Standard methodology block, source-agnostic."""
    n_indicators_each = [_count_indicators_run(s) for s in sources]
    partial = [n for n in n_indicators_each if n is not None and n < 19]
    caveat = ""
    if partial:
        caveat = (
            "<div class='caveat'>"
            f"<strong>Partial coverage.</strong> {len(partial)} of "
            f"{len(sources)} sources in this report ran with fewer than "
            "the full 19 indicators. See per-source methodology notes "
            "below for details on what was screened."
            "</div>"
        )
    return f"""
    <section>
      <h2>Methodology</h2>
      <p>The GSCO Environmental Monitoring tool computes environmental
         screening across three pillars — Air Pollution, Greenhouse Gas
         Emissions, and Nature/Land — drawing on satellite earth-observation
         data via Google Earth Engine, scientific reference datasets, and
         emissions inventory products.</p>
      <p>Each pillar produces a 0–1 follow-up priority score. Bands:
         0.66+ = red (audit-first), 0.33–0.66 = amber (investigate),
         &lt; 0.33 = green (routine). Confidence is reported alongside
         each score and reflects coverage, retrieval quality, and
         spatial-temporal applicability.</p>
      <p><strong>How to read severity (attributability framing).</strong>
         Severity scores measure whether a site shows unusual pollution
         <em>relative to its surrounding region</em> — not absolute pollution
         levels. A low (green) rating means the site is not standing out from
         its surroundings, even where the wider region is itself polluted; an
         amber or red rating means the site stands out as anomalous against
         its regional context, suggesting a site-specific contribution worth
         investigating. This applies to the Air pillar's satellite indicators
         and the equivalent anomaly grammars elsewhere. Reference datasets
         (CH₄, Hansen, ODIAC) are shown for context and do not feed the
         scores.</p>
      {caveat}
    </section>
    """


# ──────────────────────────────────────────────────────────────────
# Scope summary (MNC supplier audit only)
# ──────────────────────────────────────────────────────────────────

def _render_scope_summary(state, sources, ctx=None) -> str:
    """Supplier-focused scope: lists supplier names, AOIs, time windows."""
    blocks = ["<section>", "<h2>Scope Summary</h2>", "<table>"]
    blocks.append(
        "<tr><th>Source</th><th>Centre</th><th>Buffer (km)</th>"
        "<th>Time range</th></tr>"
    )
    for src in sources:
        setup = src.get("screening_setup") or src.get("prioritisation_setup") or {}
        centre = setup.get("centre") or {}
        lat = centre.get("lat")
        lon = centre.get("lon")
        centre_str = (
            f"({lat:.4f}, {lon:.4f})"
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float))
            else "—"
        )
        radius = setup.get("radius_km", "—")
        time_range = setup.get("time_range") or []
        time_str = " → ".join(time_range) if time_range else "—"
        name = html.escape(src.get("name", "Untitled"))
        blocks.append(
            f"<tr><td>{name}</td><td>{centre_str}</td><td>{radius}</td>"
            f"<td>{html.escape(time_str)}</td></tr>"
        )
    blocks.append("</table>")
    blocks.append("</section>")
    return "\n".join(blocks)


# ──────────────────────────────────────────────────────────────────
# Pillar findings (Policy audit)
# ──────────────────────────────────────────────────────────────────

def _render_pillar_findings(state, sources, ctx=None) -> str:
    """Pillar-by-pillar findings per source.

    M-REPORT-A1 (RT8): dual-framed. When ``ctx.apply_esrs`` (MNC renders of the
    General or any pillar-specific template) the findings are grouped under ESRS
    topical headers with metrics-&-evidence framing + out-of-scope stubs (RT4).
    Otherwise — the policy-maker General report, or a direct call with no ctx —
    the same body renders plainly, with ESRS labels stripped.
    """
    ctx = _ctx(ctx)
    if ctx.apply_esrs:
        return _render_esrs_pillar_findings(sources, ctx)

    multi = len(sources) > 1  # RF2 — source label is a divider only when 2+.
    blocks = ["<section class='chapter-break'>",
              "<h2>Pillar Findings</h2>"]
    for i, src in enumerate(sources):
        if i > 0 and multi:
            blocks.append("<div class='chapter-break'></div>")
        blocks.append(_render_source_pillar_block(src, ctx, multi=multi))
    blocks.append("</section>")
    return "\n".join(blocks)


def _verbal_paragraph_map(src) -> dict | None:
    """Per-pillar verbal-summary paragraphs for a full-coverage screening source.

    Returns ``{"overview", "air", "ghg", "nature"}`` when the source ran all 19
    indicators (the verbal summary's breadth precondition — mirrors P-05's
    M-HIDE-SUMMARY); ``None`` otherwise so callers can fall back to score tables.
    """
    setup = src.get("screening_setup") or {}
    selected = set(setup.get("indicators") or [])
    if selected != set(ALL_INDICATOR_IDS):
        return None
    payload = src.get("payload") or {}
    try:
        v = generate_verbal_summary(payload)
        return {"overview": v.overview, "air": v.air,
                "ghg": v.ghg, "nature": v.nature}
    except Exception:  # noqa: BLE001
        return None


def _render_single_pillar_score(payload, pillar: str) -> str:
    """A one-row score table for a single pillar's headline severity metric."""
    label, key = _PILLAR_SCORE[pillar]
    score = payload.get(key)
    band, band_label = _band_for_score(score)
    score_str = f"{score:.2f}" if isinstance(score, (int, float)) else "—"
    return (
        "<table>"
        "<tr><th>Pillar</th><th>Follow-up priority</th><th>Band</th></tr>"
        f"<tr><td>{label}</td><td>{score_str}</td>"
        f"<td><span class='pillar-chip {band}'>{band_label}</span></td></tr>"
        "</table>"
    )


# M-REPORT-A1 §4 — ESRS framing layer over the shared pillar-findings body.
def _render_esrs_pillar_findings(sources, ctx) -> str:
    """ESRS-framed findings: topical grouping + metrics&evidence + stubs (RT4).

    Indicator findings are grouped under their ESRS topical standard (RT6),
    filtered to ``ctx.pillars`` (the pillar-specific MNC reports render one
    pillar). Each topical section opens as metrics & evidence and closes with a
    labelled out-of-scope stub for the policies/actions/targets the company
    supplies — so the report never implies full ESRS compliance.
    """
    blocks = ["<section class='chapter-break'>",
              "<h2>Findings by ESRS topic</h2>"]
    pillars = _ordered_pillars(ctx.pillars)
    multi = len(sources) > 1  # RF2 — source label is a divider only when 2+.
    for src in sources:
        divider = _source_divider(src.get("name", "Untitled source"), multi=multi)
        if divider:
            blocks.append(divider)

        if src.get("type") == "prioritisation":
            blocks.append(
                "<div class='caveat'>"
                "This is a prioritisation source — see the Priority Findings "
                "section for the per-supplier breakdown."
                "</div>"
            )
            continue

        payload = src.get("payload") or {}
        verbal = _verbal_paragraph_map(src)
        for pillar in pillars:
            blocks.append("<div class='esrs-topic'>")
            blocks.append(esrs_topic_heading(pillar))
            blocks.append(esrs_metrics_intro(pillar))
            para = (verbal or {}).get(pillar)
            if para:
                blocks.append(f"<p>{html.escape(para)}</p>")
            elif verbal is None:
                blocks.append(
                    "<div class='caveat'>A narrative summary is shown only "
                    "for full (19-indicator) screenings — the score below "
                    "reflects what was measured for this pillar.</div>"
                )
            blocks.append(_render_single_pillar_score(payload, pillar))
            blocks.append(esrs_out_of_scope_stub(pillar))
            blocks.append("</div>")
    blocks.append("</section>")
    return "\n".join(blocks)


# M-P11.2-FIX
def _render_source_pillar_block(src, ctx=None, *, multi=True) -> str:
    name = src.get("name", "Untitled source")
    payload = src.get("payload") or {}
    blocks = [_source_divider(name, multi=multi)]  # RF2 — "" when single-source

    # M-P11.2-FIX: prioritisation sources don't carry a single
    # screening payload — point readers to the priority section.
    if src.get("type") == "prioritisation":
        blocks.append(
            "<div class='caveat'>"
            "This is a prioritisation source — see the Priority Findings "
            "section for the per-supplier breakdown."
            "</div>"
        )
        return "\n".join(blocks)

    # M-P11.2-FIX: verbal summary requires breadth-of-coverage. If the
    # source didn't run all 19 indicators, skip the prose and show a
    # caveat + pillar-score table instead. Mirrors M-HIDE-SUMMARY on P-05.
    setup = src.get("screening_setup") or {}
    selected = set(setup.get("indicators") or [])
    if selected == set(ALL_INDICATOR_IDS):
        try:
            verbal = generate_verbal_summary(payload)
            paragraphs = [verbal.overview, verbal.air, verbal.ghg, verbal.nature]
        except Exception:  # noqa: BLE001
            paragraphs = ["Verbal summary unavailable for this source."]
        for para in paragraphs:
            if para:
                blocks.append(f"<p>{html.escape(para)}</p>")
    else:
        n_selected = len(selected)
        blocks.append(
            "<div class='caveat'>"
            f"<strong>Partial coverage.</strong> This source ran "
            f"{n_selected} of 19 indicators. A narrative summary is "
            f"shown only for full screenings — the per-pillar score "
            f"table below reflects what was measured."
            "</div>"
        )
        blocks.append(_render_pillar_score_block(payload))

    return "\n".join(blocks)


# ──────────────────────────────────────────────────────────────────
# Priority findings (MNC supplier audit)
# ──────────────────────────────────────────────────────────────────

def _render_priority_findings(state, sources, ctx=None) -> str:
    """For prioritisation sources: ranked table. For screening sources:
    per-source composite + bands."""
    blocks = ["<section class='chapter-break'>",
              "<h2>Priority Findings</h2>"]
    for src in sources:
        if src.get("type") == "prioritisation":
            blocks.append(_render_prioritisation_table(src))
        else:
            blocks.append(_render_screening_priority_block(src))
    blocks.append("</section>")
    return "\n".join(blocks)


def _render_prioritisation_table(src) -> str:
    name = html.escape(src.get("name", "Untitled prioritisation"))
    supplier_results = src.get("supplier_results", [])
    blocks = [f"<h3>{name}</h3>", "<table>"]
    blocks.append(
        "<tr><th>Supplier</th><th>Status</th>"
        "<th>Air</th><th>GHG</th><th>Nature</th><th>Composite</th></tr>"
    )
    for sup in supplier_results:
        supplier_name = html.escape(sup.get("name", "—"))
        status = html.escape(sup.get("status", "—"))
        result = sup.get("result") or {}
        blocks.append(
            f"<tr><td>{supplier_name}</td><td>{status}</td>"
            f"<td>{_fmt(result.get('air.audit_followup_priority'))}</td>"
            f"<td>{_fmt(result.get('ghg.audit_followup_priority'))}</td>"
            f"<td>{_fmt(result.get('nature.followup_priority'))}</td>"
            f"<td>{_fmt(result.get('composite.overall_screening'))}</td></tr>"
        )
    blocks.append("</table>")
    return "\n".join(blocks)


def _render_screening_priority_block(src) -> str:
    name = html.escape(src.get("name", "Untitled screening"))
    payload = src.get("payload") or {}
    return f"<h3>{name}</h3>" + _render_pillar_score_block(payload)


def _render_pillar_score_block(payload) -> str:
    blocks = ["<table>", "<tr><th>Pillar</th><th>Score</th><th>Band</th></tr>"]
    for label, key in (
        ("Air Pollution",       "air.audit_followup_priority"),
        ("GHG Emissions",       "ghg.audit_followup_priority"),
        ("Nature/Land",         "nature.followup_priority"),
        ("Composite (overall)", "composite.overall_screening"),
    ):
        score = payload.get(key)
        band, band_label = _band_for_score(score)
        score_str = f"{score:.2f}" if isinstance(score, (int, float)) else "—"
        blocks.append(
            f"<tr><td>{label}</td><td>{score_str}</td>"
            f"<td><span class='pillar-chip {band}'>{band_label}</span></td></tr>"
        )
    blocks.append("</table>")
    return "\n".join(blocks)


# ──────────────────────────────────────────────────────────────────
# Indicator detail (Policy audit) — per-source KPI table
# ──────────────────────────────────────────────────────────────────

# Reference datasets are NOT scored anomaly indicators and do not use the
# z-score grammar — they are shown in the Reference datasets section instead.
# Excluded from Indicator Detail to avoid near-empty rows (CH₄ + ODIAC +
# Hansen, per the M-CH4-A1 operator decision that CH₄ is reference data, not a
# scored finding).
_REFERENCE_ONLY_INDICATOR_IDS: frozenset[str] = frozenset({
    "ghg.ch4.score",          # CH₄ — raw column reading (reference)
    "ghg.co2.score",          # ODIAC — inventory-allocated (reference)
    "nature.forest_loss.ha",  # Hansen — regional_loss_evidence flag (reference)
})

_PILLAR_DETAIL_LABELS: dict[str, str] = {
    "air": "Air Pollution", "ghg": "GHG Emissions", "nature": "Nature / Land",
}


def _fmt_num(value, fmt: str = "{:.3g}") -> str:
    """Format a numeric payload value, or ``—`` when absent/non-numeric."""
    return fmt.format(value) if isinstance(value, (int, float)) else "—"


def _fmt_pct_fraction(value) -> str:
    """A 0–1 fraction as a percent (``0.42`` → ``42%``), else ``—``."""
    return f"{value:.0%}" if isinstance(value, (int, float)) else "—"


def _table(headers: tuple[str, ...], rows: list[str]) -> str:
    """A simple HTML table from a header tuple + pre-rendered ``<tr>`` rows."""
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    return f"<table><tr>{head}</tr>{''.join(rows)}</table>"


# ── Per-pillar Indicator Detail tables (M-REPORT-A1.1 — grammars differ) ─────
# Each pillar reports the parameters that fit its scoring grammar (CLAUDE.md §7:
# do NOT harmonise grammars). All values are projected from the existing
# screening payload — no new compute.

_AIR_DETAIL_HEADERS = (
    "Indicator", "Site value", "Background", "z-score",
    "Anomaly frequency", "Confidence", "Attributability",
)


def _render_air_detail_table(payload, indicator_ids) -> str:
    """Air pillar — repeatable-core z-score grammar (site/background/z/HF)."""
    rows = []
    for rid in indicator_ids:
        base = _indicator_base(rid)
        rows.append(
            f"<tr><td>{html.escape(display_name(rid))}</td>"
            f"<td>{_fmt_num(payload.get(f'{base}.site'))}</td>"
            f"<td>{_fmt_num(payload.get(f'{base}.background'))}</td>"
            f"<td>{_fmt_num(payload.get(f'{base}.z'), '{:+.2f}')}</td>"
            f"<td>{_fmt_pct_fraction(payload.get(f'{base}.hf'))}</td>"
            f"<td>{_fmt_num(payload.get(f'{base}.confidence'), '{:.2f}')}</td>"
            f"<td>{html.escape(_attributability_state(payload, base) or '—')}"
            "</td></tr>"
        )
    return _table(_AIR_DETAIL_HEADERS, rows)


_GHG_DETAIL_HEADERS = (
    "Indicator", "Site brightness", "Lit-contrast percentile",
    "Flaring fraction", "Lit ring pixels", "Confidence", "Attributability",
)


def _render_ghg_detail_table(payload, indicator_ids) -> str:
    """GHG pillar — VIIRS sustained-contrast grammar (M-GHG-REDESIGN-A1).

    The only scored GHG indicator after reference datasets (CH₄/ODIAC) are
    excluded. Reports brightness / lit-contrast percentile / flaring fraction —
    the presence-and-flaring parameters its grammar produces, not z-scores.
    """
    rows = []
    for rid in indicator_ids:
        base = _indicator_base(rid)
        lcp = payload.get(f"{base}.lit_contrast_percentile")
        rows.append(
            f"<tr><td>{html.escape(display_name(rid))}</td>"
            f"<td>{_fmt_num(payload.get(f'{base}.site_brightness'))}</td>"
            f"<td>{_fmt_pct_fraction(lcp / 100 if isinstance(lcp, (int, float)) else None)}</td>"
            f"<td>{_fmt_pct_fraction(payload.get(f'{base}.flaring_frac'))}</td>"
            f"<td>{_fmt_num(payload.get(f'{base}.ring_lit_pixel_count'), '{:,.0f}')}</td>"
            f"<td>{_fmt_num(payload.get(f'{base}.confidence'), '{:.2f}')}</td>"
            f"<td>{html.escape(_attributability_state(payload, base) or '—')}"
            "</td></tr>"
        )
    return _table(_GHG_DETAIL_HEADERS, rows)


_NATURE_DETAIL_HEADERS = (
    "Indicator", "Key metric", "Confidence", "Attributability",
)


def _nature_key_metric(payload, registry_id: str) -> str:
    """Headline metric for a Nature indicator — each uses its own grammar.

    Returns a short human string projecting the indicator's most relevant
    field(s); ``—`` when nothing is available. No new compute.
    """
    base = _indicator_base(registry_id)
    g = payload.get

    def num(key, fmt="{:.3g}"):
        v = g(f"{base}.{key}")
        return fmt.format(v) if isinstance(v, (int, float)) else None

    parts: list[str] = []
    if base == "nature.kba":
        if (d := num("dist_km", "{:.1f}")) is not None:
            parts.append(f"{d} km to nearest KBA")
        if (o := num("overlap_pct", "{:.0f}")) is not None:
            parts.append(f"{o}% buffer overlap")
    elif base == "nature.dw":
        dom = g(f"{base}.dominant_class")
        if dom:
            parts.append(f"dominant: {html.escape(str(dom))}")
        if (t := num("trees_pct", "{:.0f}")) is not None:
            parts.append(f"trees {t}%")
        if (b := num("built_pct", "{:.0f}")) is not None:
            parts.append(f"built {b}%")
    elif base == "nature.habitat":
        if (loss := num("natural_loss_ha", "{:,.0f}")) is not None:
            pct = num("natural_loss_pct", "{:.1f}")
            parts.append(f"{loss} ha natural loss"
                         + (f" ({pct}% of buffer)" if pct is not None else ""))
        if (rate := num("annualised_rate", "{:,.0f}")) is not None:
            parts.append(f"{rate} ha/yr")
    elif base == "nature.ndvi":
        if (m := num("mean", "{:.2f}")) is not None:
            parts.append(f"NDVI mean {m}")
        if (z := num("z", "{:+.2f}")) is not None:
            parts.append(f"z {z}")
    elif base == "nature.water":
        if (a := num("area_now_ha", "{:,.0f}")) is not None:
            parts.append(f"{a} ha water / flooded veg")
    elif base == "nature.recovery":
        if (gain := num("natural_cover_gain_ha", "{:,.0f}")) is not None:
            parts.append(f"{gain} ha cover gain")
        if (imp := num("ndvi_improvement_pct", "{:.0f}")) is not None:
            parts.append(f"NDVI +{imp}%")
    return "; ".join(parts) if parts else "—"


def _render_nature_detail_table(payload, indicator_ids) -> str:
    """Nature pillar — heterogeneous grammars, one headline metric per row."""
    rows = []
    for rid in indicator_ids:
        base = _indicator_base(rid)
        rows.append(
            f"<tr><td>{html.escape(display_name(rid))}</td>"
            f"<td>{html.escape(_nature_key_metric(payload, rid))}</td>"
            f"<td>{_fmt_num(payload.get(f'{base}.confidence'), '{:.2f}')}</td>"
            f"<td>{html.escape(_attributability_state(payload, base) or '—')}"
            "</td></tr>"
        )
    return _table(_NATURE_DETAIL_HEADERS, rows)


_PILLAR_DETAIL_RENDERERS = {
    "air":    _render_air_detail_table,
    "ghg":    _render_ghg_detail_table,
    "nature": _render_nature_detail_table,
}


# M-P11-FIX / M-REPORT-A1.1
def _render_indicator_detail(state, sources, ctx=None) -> str:
    """Per-indicator audit evidence, **grouped into one table per pillar**.

    The pillars use deliberately different scoring grammars (CLAUDE.md §7), so a
    single fixed-column table can't represent them honestly. Each pillar gets a
    table with the parameters that fit its grammar:

      - **Air** — repeatable-core z-score: site / background / z / anomaly
        (hotspot) frequency / confidence / attributability.
      - **GHG** — VIIRS sustained-contrast: site brightness / lit-contrast
        percentile / flaring fraction / lit ring pixels / confidence /
        attributability (CH₄ + ODIAC are reference, excluded).
      - **Nature** — heterogeneous: one headline metric per indicator +
        confidence + attributability.

    All values are projected from the existing payload (no new compute).
    Findings carries the pillar-level prose story; this is the indicator-level
    audit evidence — the two no longer overlap. Full-coverage screening sources
    only; filtered to ``ctx.pillars`` (RF5).
    """
    full_screening_sources = [
        s for s in sources
        if s.get("type") == "screening"
        and set((s.get("screening_setup") or {}).get("indicators") or [])
            == set(ALL_INDICATOR_IDS)
    ]
    if not full_screening_sources:
        return ""

    ctx = _ctx(ctx)
    active_pillars = _ordered_pillars(ctx.pillars)
    # Reference datasets (CH₄ / ODIAC / Hansen) are excluded everywhere.
    pillar_indicators = {
        p: [i for i in INDICATORS_BY_PILLAR.get(p, [])
            if i not in _REFERENCE_ONLY_INDICATOR_IDS]
        for p in active_pillars
    }
    if not any(pillar_indicators.values()):
        return ""

    multi = len(full_screening_sources) > 1  # RF2 divider only when 2+.
    blocks = ["<section class='chapter-break'>",
              "<h2>Indicator Detail</h2>",
              "<p><em>Per-indicator audit evidence, grouped by pillar. Each "
              "pillar reports the parameters that fit its measurement grammar — "
              "Air uses site-vs-background z-score anomalies, GHG (VIIRS) uses "
              "sustained lit-contrast, Nature uses cover / area / vegetation "
              "metrics. Values are projected from the screening payload.</em></p>"]
    for src in full_screening_sources:
        divider = _source_divider(src.get("name", "Untitled"), multi=multi)
        if divider:
            blocks.append(divider)
        payload = src.get("payload") or {}
        for pillar in active_pillars:
            ids = pillar_indicators[pillar]
            if not ids:
                continue
            blocks.append(
                f"<h3 class='pillar-group'>{_PILLAR_DETAIL_LABELS[pillar]}</h3>"
            )
            blocks.append(_PILLAR_DETAIL_RENDERERS[pillar](payload, ids))
    blocks.append("</section>")
    return "\n".join(blocks)


# ──────────────────────────────────────────────────────────────────
# Per-supplier detail (MNC supplier audit)
# ──────────────────────────────────────────────────────────────────

# M-P11.2-FIX
def _render_per_supplier_detail(state, sources, ctx=None) -> str:
    # M-P11.2-FIX: only prioritisation sources contribute to this
    # section. Screening sources are fully covered by priority_findings
    # above — rendering them again here was duplicating the same
    # pillar-score table.
    prioritisation_sources = [
        s for s in sources if s.get("type") == "prioritisation"
    ]
    if not prioritisation_sources:
        return ""

    blocks = ["<section class='chapter-break'>",
              "<h2>Per-Supplier Detail</h2>"]
    for src in prioritisation_sources:
        blocks.append(_render_prioritisation_supplier_breakdown(src))
    blocks.append("</section>")
    return "\n".join(blocks)


def _render_prioritisation_supplier_breakdown(src) -> str:
    """For prioritisation source: one h3 per supplier with their scores."""
    name = html.escape(src.get("name", "Prioritisation"))
    supplier_results = src.get("supplier_results", [])
    blocks = [f"<h3>{name}</h3>"]
    for sup in supplier_results:
        if sup.get("status") in ("failed", "cancelled"):
            continue
        supplier_name = html.escape(sup.get("name", "—"))
        result = sup.get("result") or {}
        blocks.append(f"<h4>{supplier_name}</h4>")
        blocks.append(_render_pillar_score_block(result))
    return "\n".join(blocks)


# ──────────────────────────────────────────────────────────────────
# Reference datasets (M-UI-A6 RD10)
# ──────────────────────────────────────────────────────────────────

# RD10 — disclaimer mirrors the in-app C5 sub-section framing (§4.3) so the
# print report carries the same "context, not scoring" signpost.
# M-REPORT-A1.1 (RF4): prose tightened so each dataset's role is unambiguous —
# what it is, why it appears, and why it is excluded from the composite. No
# structural change (same disclaimer + per-dataset table + footnote shape).
_REFERENCE_DATASETS_DISCLAIMER: str = (
    "Reference data context — not part of the composite score. Each dataset "
    "below is shown to inform interpretation; none feeds the scored "
    "site-vs-region anomaly. Their individual roles are noted underneath."
)

# Audit footnotes — same intent as the C5 cards (RD8 + §4.2), simplified for
# print (the C5 strings live in ui.components.c5_drilldown; kept aligned by
# intent, not import, to avoid an engine/UI cross-dependency in the report
# layer). RF4: one clause per dataset spelling out its role + exclusion. Each
# clause is tagged with its owning pillar so the footnote stays pillar-pure
# (RF5) — a GHG report's footnote does not describe Hansen, etc.
_REFERENCE_DATASETS_FOOTNOTE_CLAUSES: tuple[tuple[str, str], ...] = (
    ("nature",
     "Hansen forest loss feeds only the regional_loss_evidence binary flag in "
     "External Driver Screening — it appears here as regional context and is "
     "not scored in the composite."),
    ("ghg",
     "ODIAC is an inventory-allocated emissions product, not an atmospheric "
     "measurement; it appears as an emissions-intensity reference and is "
     "excluded from the composite."),
    ("ghg",
     "CH₄ is a raw column reading for the screening window, shown as reference "
     "context rather than a scored anomaly."),
)


def _render_reference_dataset_block(payload, pillars=ALL_PILLARS) -> str:
    """One reference-dataset table for a single screening payload.

    Mirrors the C5 cards' headline metrics (Hansen cumulative loss %, ODIAC
    annual emissions intensity, CH₄ column average), with the same RD12 "Data
    not available" fallback when a value is missing.

    M-CH4-A1 (30 May 2026): CH₄ added as a third reference row — it is now
    reference data alongside Hansen + ODIAC and appears in the PDF's reference
    section (operator decision, overriding spec CH7/Q-4). It is shown as a raw
    column reading, not a scored finding.

    M-REPORT-A1: rows are filtered to ``pillars`` so a pillar-specific MNC
    report shows only its relevant reference data (Hansen → Nature/E4; ODIAC +
    CH₄ → GHG/E1; the Air report has no reference datasets). The default
    (all pillars) preserves the original three-row table.
    """
    loss_pct = payload.get("nature.forest_loss.pct")
    co2_mean = payload.get("ghg.co2.mean")
    ch4_site = payload.get("ghg.ch4.site")
    hansen_val = (
        f"{loss_pct:.2f}% of buffer area lost (5-year cumulative)"
        if loss_pct is not None else "Data not available for this AOI"
    )
    odiac_val = (
        f"{co2_mean:,.0f} t CO₂ yr⁻¹ per pixel "
        "(annual emissions intensity)"
        if co2_mean is not None else "Data not available for this AOI"
    )
    ch4_val = (
        f"{ch4_site:,.0f} ppb column average (screening window)"
        if ch4_site is not None else "Data not available for this AOI"
    )
    # (row_html, owning_pillar) — row renders only when its pillar is active.
    rows = [
        (f"<tr><td>Hansen forest loss</td><td>{html.escape(hansen_val)}</td>"
         "<td>Hansen Global Forest Change (University of Maryland)</td></tr>",
         "nature"),
        (f"<tr><td>ODIAC CO₂</td><td>{html.escape(odiac_val)}</td>"
         "<td>ODIAC fossil-fuel CO₂ (NIES, Japan)</td></tr>",
         "ghg"),
        (f"<tr><td>CH₄ (methane)</td><td>{html.escape(ch4_val)}</td>"
         "<td>Sentinel-5P TROPOMI (Copernicus / ESA)</td></tr>",
         "ghg"),
    ]
    active_rows = [r for r, pillar in rows if pillar in pillars]
    if not active_rows:
        return ""
    # RF4/RF5 — footnote clauses filtered to the datasets actually shown.
    footnote = " ".join(
        clause for pillar, clause in _REFERENCE_DATASETS_FOOTNOTE_CLAUSES
        if pillar in pillars
    )
    return "\n".join([
        "<table>",
        "<tr><th>Reference dataset</th><th>Value</th><th>Source</th></tr>",
        *active_rows,
        "</table>",
        f"<p><em>{html.escape(footnote)}</em></p>",
    ])


def _render_reference_datasets(state, sources, ctx=None) -> str:
    """RD10 — reference-dataset context section for the PDF report.

    Appears after the scored-indicators section. Renders the Hansen + ODIAC
    reference values per screening source, marked clearly as context rather
    than scoring. Returns "" (section omitted) when no screening source is
    present — e.g. a pure-prioritisation report carries no per-AOI payload.
    """
    screening_sources = [s for s in sources if s.get("type") == "screening"]
    if not screening_sources:
        return ""
    ctx = _ctx(ctx)
    multi = len(screening_sources) > 1  # RF2 — divider only when 2+ sources.
    # M-REPORT-A1: filter rows to the active pillars. The Air report (E2) has no
    # reference datasets, so all per-source blocks come back empty and the whole
    # section is omitted.
    body = []
    for src in screening_sources:
        block = _render_reference_dataset_block(src.get("payload") or {},
                                                ctx.pillars)
        if not block:
            continue
        divider = _source_divider(src.get("name", "Untitled"), multi=multi)
        if divider:
            body.append(divider)
        body.append(block)
    if not body:
        return ""
    blocks = [
        "<section class='chapter-break'>",
        "<h2>Reference datasets</h2>",
        f"<p><em>{html.escape(_REFERENCE_DATASETS_DISCLAIMER)}</em></p>",
        *body,
        "</section>",
    ]
    return "\n".join(blocks)


# ──────────────────────────────────────────────────────────────────
# Trend graph (M-TREND-A2 / UT10)
#
# M-REPORT-A2 (RA5) — LEGACY / UNWIRED. This section is no longer wired into
# any template: trend moved to its own family (`trend_indicator_sections`) in
# M-REPORT-A1. It stays registered only so the trend-view fallback tests keep
# exercising the SVG-failure → series-table degrade path. Do NOT add it to a
# template's section list — use `trend_indicator_sections` for the trend report.
# ──────────────────────────────────────────────────────────────────

def _render_trend_graph(state, sources, ctx=None) -> str:
    """Per-indicator trend graphs for any saved trend records in the report.

    LEGACY (M-REPORT-A2 RA5): unwired from all templates; retained for
    fallback-test use only — see the section banner above.

    Emits one block per ``type=="trend"`` source: an inline SVG of the trend
    graph (scatter + Theil–Sen line; season bands when flagged) generated from
    the saved per-day series, plus a short prose verdict + the metrics.
    Returns "" (section omitted) when no trend sources are present.

    Graceful fallback (UT10 / §8): if SVG generation fails for a record, that
    record's block degrades to a statistics summary + a series table rather
    than breaking the section — consistent with the assembler's per-section
    try/except.
    """
    trend_sources = [s for s in sources if s.get("type") == "trend"]
    if not trend_sources:
        return ""
    blocks = [
        "<section class='chapter-break'>",
        "<h2>Trend analysis</h2>",
        "<p><em>Per-indicator trend drill-downs (Theil–Sen slope + "
        "Mann–Kendall significance over the screening window). Trend is a "
        "drill-down signal — it does not enter the composite screening "
        "score.</em></p>",
    ]
    for src in trend_sources:
        name = html.escape(src.get("display_name") or src.get("indicator_id") or "Trend")
        result = src.get("trend_result") or {}
        setup = src.get("screening_setup") or {}
        lat = (setup.get("centre") or {}).get("lat")
        blocks.append(f"<h3>{name}</h3>")
        blocks.append(_render_one_trend_block(result, lat, name))
    blocks.append("</section>")
    return "\n".join(blocks)


# M-REPORT-A1 §5 — Trend report (Option A, RT9/RT10).
def _render_trend_indicator_sections(state, sources, ctx=None) -> str:
    """The Trend report's body: per-indicator sections grouped by pillar.

    Option A (RT9): own per-indicator structure, **no pillar composite**. Pillar
    names (Air / GHG / Nature) are used only as **grouping headers** (RT10) —
    they carry no aggregate score. Each indicator section reuses the same
    verdict + metrics + inline SVG block as the live trend view, generated from
    the saved per-day series (no recompute). Not ESRS-framed (RT11).
    """
    trend_sources = [s for s in sources if s.get("type") == "trend"]
    if not trend_sources:
        return ""

    # Group by owning pillar (indicator-id prefix), preserving pillar order.
    by_pillar: dict[str, list[dict]] = {}
    for src in trend_sources:
        pillar = (src.get("indicator_id") or "").split(".")[0]
        by_pillar.setdefault(pillar, []).append(src)

    blocks = [
        "<section class='chapter-break'>",
        "<h2>Trend analysis</h2>",
        "<p><em>Per-indicator trend drill-downs (Theil–Sen slope + "
        "Mann–Kendall significance over the screening window). Pillar headings "
        "group the indicators for organisation only — trend is a drill-down "
        "signal and carries no pillar or composite score.</em></p>",
    ]
    pillar_labels = {"air": "Air Pollution", "ghg": "GHG Emissions",
                     "nature": "Nature/Land"}
    # Active pillars first in the locked order, then any unrecognised group.
    ordered = _ordered_pillars(frozenset(by_pillar))
    ordered += [p for p in by_pillar if p not in ordered]
    for pillar in ordered:
        label = pillar_labels.get(pillar, pillar.title() or "Other")
        blocks.append(f"<h3 class='pillar-group'>{html.escape(label)}</h3>")
        for src in by_pillar[pillar]:
            name = html.escape(
                src.get("display_name") or src.get("indicator_id") or "Trend"
            )
            result = src.get("trend_result") or {}
            setup = src.get("screening_setup") or {}
            lat = (setup.get("centre") or {}).get("lat")
            blocks.append(f"<h4>{name}</h4>")
            blocks.append(_render_one_trend_block(result, lat, name))
    blocks.append("</section>")
    return "\n".join(blocks)


def _render_one_trend_block(result: dict, lat, name: str = "") -> str:
    """One trend record → verdict + metrics + inline SVG, with a table
    fallback if the SVG build raises."""
    badge = verdict_badge(result)
    conf = result.get("trend_confidence")
    conf_str = "—" if conf is None else f"{conf:.2f}"
    metrics = (
        f"<p><strong>{html.escape(badge['text'])}</strong></p>"
        f"<ul>"
        f"<li>Significance: {html.escape(significance_text(result))}</li>"
        f"<li>Trend confidence: {conf_str}</li>"
        f"<li>Raw slope: {html.escape(slope_display(result))}</li>"
        f"</ul>"
    )
    try:
        seasonal = bool(result.get("seasonal_flag"))
        svg = build_trend_svg(
            result, lat=lat, show_season_bands=seasonal, width=680,
            y_label=name or "Site value",
            title=f"{name} — daily site value" if name else None,
        )
        return metrics + f"<div class='trend-graph'>{svg}</div>"
    except Exception as exc:  # noqa: BLE001 — never emit a broken section
        return metrics + _render_trend_series_table(result, str(exc))


def _render_trend_series_table(result: dict, error: str) -> str:
    """Fallback when SVG generation fails: the per-day series as a table."""
    rows = [
        f"<tr><td>{html.escape(str(iso))}</td><td>{html.escape(f'{v:.4g}')}</td></tr>"
        for iso, v in (result.get("series") or [])
    ]
    return (
        f"<p><em>Graph unavailable ({html.escape(error)}); showing the "
        f"per-day series.</em></p>"
        "<table class='series-table'><thead><tr><th>Date</th>"
        "<th>Value</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


# ──────────────────────────────────────────────────────────────────
# Provenance appendix
# ──────────────────────────────────────────────────────────────────

def _render_provenance_appendix(state, sources, ctx=None) -> str:
    ctx = _ctx(ctx)
    multi = len(sources) > 1  # RF2 — source label is a divider only when 2+.
    blocks = ["<section class='chapter-break'>",
              "<h2>Provenance Appendix</h2>",
              "<p>Reference assets, computation scales, and time "
              "windows for every indicator that returned data in "
              "this report's sources.</p>"]
    for src in sources:
        divider = _source_divider(src.get("name", "Source"), multi=multi)
        if divider:
            blocks.append(divider)
        payload = src.get("payload") or {}
        # RF5 — pillar reports filter provenance (and every sub-appendice fed
        # from it) to the report's pillars; the General report shows all.
        blocks.append(_render_provenance_for_payload(payload, ctx.pillars))
    blocks.append("</section>")
    return "\n".join(blocks)


def _render_provenance_for_payload(payload, pillars=ALL_PILLARS) -> str:
    prov_blocks = [
        (key.removeprefix("_provenance."), val)
        for key, val in payload.items()
        if isinstance(key, str) and key.startswith("_provenance.")
        and isinstance(val, dict)
        # RF5 — keep only indicators whose pillar prefix is in scope.
        and key.removeprefix("_provenance.").split(".")[0] in pillars
    ]
    if not prov_blocks:
        return "<p>No provenance entries.</p>"
    blocks = ["<table>",
              "<tr><th>Indicator</th><th>Asset</th><th>Scale (m)</th>"
              "<th>Time range</th><th>Status</th></tr>"]
    for ind_id, prov in sorted(prov_blocks):
        asset = html.escape(str(prov.get("asset_id", "—")))
        scale = prov.get("native_scale_m", "—")
        time_range = prov.get("time_range") or []
        time_str = " → ".join(time_range) if time_range else "—"
        status = "Skipped" if prov.get("skipped_reason") else "OK"
        blocks.append(
            f"<tr><td>{html.escape(ind_id)}</td><td>{asset}</td>"
            f"<td>{scale}</td><td>{html.escape(time_str)}</td>"
            f"<td>{status}</td></tr>"
        )
    blocks.append("</table>")

    # M-UI-A1-SURFACE Sub-milestone 3 (24 May 2026): per-indicator
    # audit-transparency extras (n_valid_dates, granule_count, …).
    # confidence_terms is deliberately excluded — it has its own
    # dedicated surface in the P-05 C5 "What's behind this confidence?"
    # expander, not in the report appendix. Do NOT "fix" this exclusion
    # without re-reading the M-UI-A1-SURFACE spec §3 sub-milestone 3.
    extras_html = _render_provenance_extras(prov_blocks)
    if extras_html:
        blocks.append(extras_html)
    # M-TIER-A3 Step H2 — coastal handling sub-block. Renders only when
    # at least one indicator's ring touched water; reuses Surface 1's
    # copy template for consistency with the P-05 C5 expander.
    coastal_html = _render_coastal_handling_appendix(prov_blocks)
    if coastal_html:
        blocks.append(coastal_html)
    # M-FALLBACK-A1 §5.5 — "Fallback applied" sub-block. Renders only when
    # at least one indicator used the SPPY or climatology fallback; omitted
    # entirely otherwise (§7.11).
    fallback_html = _render_fallback_appendix(prov_blocks)
    if fallback_html:
        blocks.append(fallback_html)
    # M-ATTRIB-A1 §5.6 — habitat attribution context. Low-only; omitted
    # entirely otherwise (parallels coastal / fallback sub-blocks).
    habitat_attrib_html = _render_habitat_attribution_appendix(prov_blocks)
    if habitat_attrib_html:
        blocks.append(habitat_attrib_html)
    # M-WIND-A1 v2.0 §6.4 — wind attribution context. Low-only (WA20);
    # supplier with no Low-wind indicators gets no section. Lists each
    # affected indicator with its mean wind speed and asymmetry ratio.
    wind_attrib_html = _render_wind_attribution_appendix(prov_blocks)
    if wind_attrib_html:
        blocks.append(wind_attrib_html)
    return "\n".join(blocks)


# M-TIER-A3 Step H2 — copy mirrors the C5 expander Surface 1 template
# (kept in sync by string match in `tests/test_coastal_handling_surfaces.py`).
_COASTAL_HANDLING_APPENDIX_HEADER: str = "Coastal AOI handling"
_COASTAL_HANDLING_APPENDIX_INTRO: str = (
    "One or more indicators in this report ran against a background ring "
    "that partly overlapped the coastline. The tool applied a global land "
    "mask (MODIS MOD44W v6, 250 m) to exclude ocean pixels from the "
    "baseline reduction — the median + σ comparison was computed against "
    "the terrestrial portion of the ring only. Without this adjustment, "
    "ocean pixels (which have near-zero pollution and would otherwise "
    "average in as \"clean background\") would artificially depress the "
    "baseline and inflate the supplier's anomaly score. The land-only "
    "baseline gives a more honest comparison against the surrounding "
    "terrestrial area."
)


def _render_coastal_handling_appendix(
    prov_blocks: list[tuple[str, dict]],
) -> str:
    """Render a coastal-AOI-handling sub-block when any indicator's
    background ring was partly over water (spec H2 PDF surface).

    Iterates the report's provenance blocks once. For each indicator
    whose `extra.ring_land_fraction < 1.0` and `extra.land_mask_applied`
    is truthy, surface a row showing the geometric land fraction. If
    *no* indicator hit the coastline, omit the section entirely so the
    PDF doesn't carry a misleading "this is a coastal site" heading
    for a fully inland AOI.
    """
    rows: list[str] = []
    any_below_warning_threshold = False
    for ind_id, prov in sorted(prov_blocks):
        extra = prov.get("extra")
        if not isinstance(extra, dict):
            continue
        land_fraction = extra.get("ring_land_fraction")
        if not isinstance(land_fraction, (int, float)):
            continue
        if land_fraction >= 1.0:
            continue
        # RF6 — gate on the mask being *effectively applied*: require
        # land_mask_applied truthy (not merely "not False"), matching the live
        # P-05 C5 expander's `land_mask_applied AND ring_land_fraction < 1.0`.
        if not extra.get("land_mask_applied"):
            continue
        water_pct = max(0, min(100, round((1.0 - float(land_fraction)) * 100)))
        land_pct  = 100 - water_pct
        # RF6 — skip indicators that round to 100% land / 0% water: the mask did
        # not effectively fire, so the row would misleadingly imply a coastal
        # AOI (the first-artifact bug).
        if water_pct < 1:
            continue
        rows.append(
            f"<li><strong>{html.escape(ind_id)}</strong> — "
            f"{land_pct}% land / {water_pct}% water</li>"
        )
        # Warning band threshold matches the C5 expander Surface 1.
        if land_fraction < 0.20:
            any_below_warning_threshold = True
    if not rows:
        return ""
    parts = [
        f"<h4>{_COASTAL_HANDLING_APPENDIX_HEADER}</h4>",
        f"<p>{_COASTAL_HANDLING_APPENDIX_INTRO}</p>",
        "<ul class='provenance-extras'>",
        "\n".join(rows),
        "</ul>",
    ]
    if any_below_warning_threshold:
        parts.append(
            "<p><em>At least one indicator's comparison area is mostly "
            "water; the baseline is computed from a small land area and "
            "should be interpreted with care.</em></p>"
        )
    return "\n".join(parts)


# M-FALLBACK-A1 §5.5 — PDF audit-transparency "Fallback applied" sub-block.
# Surfaces the same fallback facts the in-app C5 expander shows, persisted in
# the auditor's exportable artefact.
_FALLBACK_APPENDIX_HEADER: str = "Fallback methodology applied"
_FALLBACK_APPENDIX_INTRO: str = (
    "One or more indicators in this report could not be computed from "
    "current-window satellite data and used a documented fallback. Each "
    "substitution carries a reduced confidence score (year-old data ×0.60; "
    "regional baseline ×0.75). The substitutions are listed below for audit "
    "transparency."
)


def _render_fallback_appendix(prov_blocks: list[tuple[str, dict]]) -> str:
    """Render the §5.5 fallback sub-block, or "" when no fallback fired.

    Lists per-indicator temporal (SPPY / sliding-lookback) and climatology
    substitutions, plus the AOI scale class when it's larger than site-scale.
    """
    temporal_rows: list[str] = []
    climatology_rows: list[str] = []
    scale_class: str | None = None

    for ind_id, prov in sorted(prov_blocks):
        extra = prov.get("extra")
        if not isinstance(extra, dict):
            continue
        if scale_class is None:
            sc = extra.get("aoi_scale_class")
            if sc in ("regional", "biome"):
                scale_class = sc
        if extra.get("temporal_fallback_used"):
            strategy = extra.get("temporal_fallback_strategy")
            window = extra.get("temporal_fallback_source_window") or "an earlier period"
            window = window.replace("/", " to ")
            label = (
                "earlier-window data"
                if strategy == "sliding_lookback"
                else "same-period-previous-year data"
            )
            temporal_rows.append(
                f"<li><strong>{html.escape(ind_id)}</strong> — {label} "
                f"({html.escape(window)}) due to sparse current-window coverage</li>"
            )
        if extra.get("climatology_fallback_used"):
            vintage = html.escape(str(extra.get("climatology_fallback_vintage") or "latest"))
            climatology_rows.append(
                f"<li><strong>{html.escape(ind_id)}</strong> — regional baseline "
                f"(country median, {vintage} vintage) due to sparse ring coverage</li>"
            )

    if not temporal_rows and not climatology_rows:
        return ""

    parts = [
        f"<h4>{_FALLBACK_APPENDIX_HEADER}</h4>",
        f"<p>{_FALLBACK_APPENDIX_INTRO}</p>",
        "<ul class='provenance-extras'>",
        *temporal_rows,
        *climatology_rows,
        "</ul>",
    ]
    if scale_class is not None:
        parts.append(
            f"<p>AOI scale class: <strong>{html.escape(scale_class)}</strong> "
            f"— background comparisons reflect regional-scale context.</p>"
        )
    return "\n".join(parts)


# M-ATTRIB-A1 §5.6 — PDF "Habitat attribution context" sub-block. Low-only,
# parallel to the coastal / fallback sub-blocks. Surfaces the supplier→change
# centroid offset for auditors when habitat conversion attributability is Low.
_HABITAT_ATTRIB_APPENDIX_HEADER: str = "Habitat attribution context"


def _render_habitat_attribution_appendix(
    prov_blocks: list[tuple[str, dict]],
) -> str:
    """Render the §5.6 habitat-attribution sub-block, or "" unless Low.

    Reads `extra.spatial_link_terms` from the
    `nature.supplier_spatial_link` provenance block. Fires only when the
    attributability state is "low" (High / Moderate / Sparse surface on the
    map, not in the report); omitted entirely otherwise.
    """
    for ind_id, prov in prov_blocks:
        if ind_id != "nature.supplier_spatial_link":
            continue
        extra = prov.get("extra")
        if not isinstance(extra, dict):
            continue
        terms = extra.get("spatial_link_terms")
        if not isinstance(terms, dict):
            continue
        if terms.get("attributability_state") != "low":
            return ""
        offset = terms.get("centroid_offset_km")
        dist = f"{offset:.1f} km" if isinstance(offset, (int, float)) else "—"
        direction = terms.get("direction") or "—"
        n_change = terms.get("n_change_pixels") or 0
        return "\n".join([
            f"<h4>{_HABITAT_ATTRIB_APPENDIX_HEADER}</h4>",
            "<p>This supplier shows <strong>Low</strong> attribution "
            "confidence on habitat conversion:</p>",
            "<ul class='provenance-extras'>",
            f"<li>Centroid of habitat changes: <strong>{dist}</strong> from "
            f"supplier ({html.escape(str(direction))} direction)</li>",
            f"<li>N = <strong>{int(n_change)}</strong> change pixels</li>",
            "<li>Interpretation: detected changes are spatially concentrated "
            "away from the supplier coordinate.</li>",
            "</ul>",
        ])
    return ""


# M-WIND-A1 v2.0 §6.4 — PDF "Wind attribution context" sub-block. Low-only,
# parallel to coastal / fallback / habitat-attribution sub-blocks. Lists each
# in-scope Air indicator whose wind attributability fired Low so auditors see
# exactly which signals carry an upwind-transport caveat.
_WIND_ATTRIB_APPENDIX_HEADER: str = "Wind attribution context"

_WIND_ATTRIB_APPENDIX_INTRO: str = (
    "This supplier shows <strong>Low</strong> attribution confidence on the "
    "following indicators due to wind conditions during anomaly days. Strong "
    "winds and asymmetric upwind/downwind background values suggest the "
    "observed anomalies may reflect transported pollution from external "
    "sources rather than (or in addition to) the supplier itself."
)


def _render_wind_attribution_appendix(
    prov_blocks: list[tuple[str, dict]],
) -> str:
    """Render the §6.4 wind-attribution sub-block, or "" when no Low fired.

    Iterates the report's provenance blocks once. For each in-scope Air
    indicator (NO₂, SO₂, HCHO, AAI, AOD) whose
    ``extra.wind_attributability_state == "low"``, surface a row with the
    mean wind speed, asymmetry ratio, and the wind data window. Moderate
    and High indicators surface visually on the map (not in the PDF, per
    WA20); supplier with no Low-wind indicators gets no section at all.
    """
    rows: list[str] = []
    for ind_id, prov in sorted(prov_blocks):
        extra = prov.get("extra")
        if not isinstance(extra, dict):
            continue
        if extra.get("wind_attributability_state") != "low":
            continue
        speed = extra.get("wind_mean_speed_ms")
        ratio = extra.get("wind_mean_asymmetry_ratio")
        window = extra.get("wind_data_window") or ""
        window_str = (
            window.replace("/", " to ") if isinstance(window, str) and "/" in window
            else "—"
        )
        if isinstance(ratio, (int, float)):
            metrics_str = (
                f"Mean wind <strong>{speed:.1f} m/s</strong>, asymmetry ratio "
                f"<strong>{ratio:.2f}</strong>"
            ) if isinstance(speed, (int, float)) else (
                f"Asymmetry ratio <strong>{ratio:.2f}</strong>"
            )
        else:
            metrics_str = (
                f"Mean wind <strong>{speed:.1f} m/s</strong> (all anomaly days calm)"
                if isinstance(speed, (int, float)) else "wind metrics unavailable"
            )
        rows.append(
            f"<li><strong>{html.escape(ind_id)}</strong> — {metrics_str} "
            f"({html.escape(window_str)})<br/>"
            f"<em>Low attribution confidence — wind conditions suggest "
            f"external sources may have contributed.</em></li>"
        )
    if not rows:
        return ""
    return "\n".join([
        f"<h4>{_WIND_ATTRIB_APPENDIX_HEADER}</h4>",
        f"<p>{_WIND_ATTRIB_APPENDIX_INTRO}</p>",
        "<ul class='provenance-extras'>",
        "\n".join(rows),
        "</ul>",
    ])


# M-UI-A1-SURFACE Sub-milestone 3 polish (24 May 2026): the PDF
# audience is business / audit-reviewer-facing and benefits from a
# narrow, narrative surface. Engineering calibration parameters
# (aod_qa_bit_mask, distance_decay_km, conversion_saturation_pct,
# ndvi_negative_trend_threshold, baseline_*, ring/buffer_loss_rate_*,
# hansen_max_loss_year, lookback_years, ratio_threshold, etc.) belong
# in the CSV export (which already carries them as dedicated columns);
# the PDF appendix surfaces only the multi-swath dates-vs-granules
# story the M-TIER-A1 close-entry promised. confidence_terms is
# still excluded — that surface lives in the P-05 C5 "What's behind
# this confidence?" expander.
_PDF_AUDIT_TRANSPARENCY_KEYS: frozenset[str] = frozenset({
    "n_valid_dates",
    "granule_count",
})


def _render_provenance_extras(prov_blocks: list[tuple[str, dict]]) -> str:
    """Build the per-indicator audit-transparency sub-block.

    Renders as English prose, one bullet per indicator where
    ``granule_count > n_valid_dates`` (multi-swath products like
    MAIAC AOD at ~58 granules/day, S5P L3 CH4 at ~14×). Single-image-
    per-day products (NO2, SO2, CO, HCHO, O3, AAI, PM2.5, PM10, NDVI,
    VIIRS) have ``granule_count == n_valid_dates`` and would tell no
    story — they're omitted.

    The entire section is omitted when no indicator has multi-swath
    divergence (e.g. pre-engine-fix payloads with no extras, or
    payloads with only single-image-per-day products) so the PDF
    doesn't carry a dangling empty heading.

    Allowlist enforcement: only ``_PDF_AUDIT_TRANSPARENCY_KEYS`` are
    read from ``provenance.extra``. See that constant's comment for
    the boundary rationale.
    """
    rows: list[str] = []
    for ind_id, prov in sorted(prov_blocks):
        extra = prov.get("extra")
        if not isinstance(extra, dict):
            continue
        # Read only the allowlisted keys; everything else is engineering
        # calibration that belongs in the CSV, not the PDF appendix.
        n_valid_dates = extra.get("n_valid_dates")
        granule_count = extra.get("granule_count")
        if not isinstance(n_valid_dates, int) or not isinstance(granule_count, int):
            continue
        if granule_count <= n_valid_dates:
            continue  # single-image-per-day — no audit story to tell.
        rows.append(
            f"<li><strong>{html.escape(ind_id)}</strong> — "
            f"{n_valid_dates:,} distinct dates observed across "
            f"{granule_count:,} raw images</li>"
        )
    if not rows:
        return ""
    return (
        "<h4>Audit-transparency extras</h4>\n"
        "<p><em>Multi-swath satellite indicators, showing distinct "
        "observation dates vs raw image counts processed.</em></p>\n"
        "<ul class='provenance-extras'>\n"
        + "\n".join(rows)
        + "\n</ul>\n"
        "<p><em>Per-indicator engineering parameters are available "
        "in the CSV export.</em></p>"
    )


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

def _composite_score(src) -> float | None:
    """Pull composite from screening payload or prioritisation summary."""
    if src.get("type") == "screening":
        value = (src.get("payload") or {}).get("composite.overall_screening")
        return value if isinstance(value, (int, float)) else None
    if src.get("type") == "prioritisation":
        # Use mean across plottable suppliers as a quick summary.
        results = src.get("supplier_results", [])
        scores = []
        for r in results:
            if r.get("status") not in ("success", "partial"):
                continue
            value = (r.get("result") or {}).get("composite.overall_screening")
            if isinstance(value, (int, float)):
                scores.append(value)
        return sum(scores) / len(scores) if scores else None
    return None


def _band_for_score(score: float | None) -> tuple[str, str]:
    """Return (css_class, human_label)."""
    if not isinstance(score, (int, float)):
        return "grey", "No data"
    low, high = TRAFFIC_LIGHT_THRESHOLDS
    if score >= high:
        return "red", "High priority"
    if score >= low:
        return "amber", "Moderate"
    return "green", "Low priority"


def _count_indicators_run(src) -> int | None:
    setup = src.get("screening_setup") or src.get("prioritisation_setup") or {}
    indicators = setup.get("indicators") or []
    return len(indicators) if indicators else None


def _fmt(value) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


# ──────────────────────────────────────────────────────────────────
# Composite formula appendix (M-REPORT-A1.1)
# ──────────────────────────────────────────────────────────────────

# Human labels for the per-pillar follow-up-priority term keys (the dict keys
# live in engine.constants; labels describe what each term is).
_AIR_FOLLOWUP_LABELS = {
    "proxy":      "Air Pollution Proxy score",
    "anomaly":    "Spatiotemporal anomaly",
    "confidence": "Confidence",
}
_GHG_FOLLOWUP_LABELS = {
    "core_support": "Core GHG audit support (VIIRS flaring + combustion proxy)",
    "quality":      "Data-quality attribution",
}
_NATURE_FOLLOWUP_LABELS = {
    "biodiversity_exposure": "Biodiversity exposure",
    "habitat_conversion":    "Habitat conversion",
    "vegetation_condition":  "Vegetation condition",
    "quality_attribution":   "Measurement quality",
}


def _render_weight_table(weights: dict, labels: dict) -> str:
    """A Term · Weight table for one pillar's follow-up-priority blend."""
    rows = [
        f"<tr><td>{html.escape(labels.get(k, k))}</td>"
        f"<td>{w:.2f}</td></tr>"
        for k, w in weights.items()
    ]
    return _table(("Term", "Weight"), rows)


def _render_composite_formula(state, sources, ctx=None) -> str:
    """Composite-score methodology appendix (M-REPORT-A1.1).

    Explains how the overall screening composite is built from the indicators:
    the composite is the equal-weighted mean of the three pillar follow-up
    priorities (Indicators_Computation_v4 §4), and each pillar priority is a
    weighted blend of its terms (IC_v4 §1.3 / §2.3 / §3.3). Weights are read
    from ``engine.constants`` so this appendix never drifts from the engine.
    Always covers all three pillars — the composite is a whole-screening figure
    even in a single-pillar report (consistent with the exec-summary note).
    """
    blocks = [
        "<section class='chapter-break'>",
        "<h2>Composite score methodology</h2>",
        "<p>The <strong>overall screening composite</strong> is the "
        "equal-weighted mean of the three pillar follow-up-priority scores "
        "(Indicators_Computation_v4 §4):</p>",
        "<p class='formula'><em>composite = ( Air priority + GHG priority + "
        "Nature priority ) ÷ 3</em></p>",
        "<p>Scores run 0–1; bands are 0.66+ red (audit-first), 0.33–0.66 amber "
        "(investigate), &lt;0.33 green (routine). If any pillar could not be "
        "computed the composite is left undefined rather than averaged over the "
        "survivors. Composite <em>confidence</em> is the minimum of the pillar "
        "confidences (IC_v4 §4).</p>",
        "<p>Each pillar's follow-up priority is itself a weighted blend of its "
        "terms:</p>",
        "<h3 class='pillar-group'>Air Pollution priority (IC_v4 §1.3)</h3>",
        _render_weight_table(AIR_FOLLOWUP_WEIGHTS, _AIR_FOLLOWUP_LABELS),
        "<h3 class='pillar-group'>GHG Emissions priority (IC_v4 §2.3)</h3>",
        _render_weight_table(GHG_FOLLOWUP_WEIGHTS, _GHG_FOLLOWUP_LABELS),
        "<h3 class='pillar-group'>Nature / Land priority (IC_v4 §3.3)</h3>",
        _render_weight_table(NATURE_FOLLOWUP_WEIGHTS, _NATURE_FOLLOWUP_LABELS),
        "<p><em>Reference datasets (Hansen forest loss, ODIAC CO₂, CH₄) are "
        "context only and do not enter the composite — see Reference "
        "datasets.</em></p>",
        "</section>",
    ]
    return "\n".join(blocks)


# ──────────────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────────────

_SECTION_REGISTRY: dict[str, Callable] = {
    "title_page":            _render_title_page,
    "executive_summary":     _render_executive_summary,
    "methodology":           _render_methodology,
    "scope_summary":         _render_scope_summary,
    "pillar_findings":       _render_pillar_findings,
    "priority_findings":     _render_priority_findings,
    "indicator_detail":      _render_indicator_detail,
    "per_supplier_detail":   _render_per_supplier_detail,
    "trend_graph":           _render_trend_graph,
    # M-REPORT-A1 §5 — Trend report's own per-indicator structure (RT9).
    "trend_indicator_sections": _render_trend_indicator_sections,
    "reference_datasets":    _render_reference_datasets,
    "provenance_appendix":   _render_provenance_appendix,
    # M-REPORT-A1.1 — composite-formula appendix.
    "composite_formula":     _render_composite_formula,
}
