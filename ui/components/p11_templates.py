"""Report templates registry (M-P11.1 / M-REPORT-A1).

M-REPORT-A1 restructures the surface from the original two flat templates
(``policy_audit`` / ``supplier_audit``) into a bounded **five-registration**
family (spec §3):

  - ``general``      : General report. Offered to BOTH user types. One
                       structure, two framings (RT8) — the MNC variant applies
                       the ESRS framing layer (E1+E2+E4); the policy-maker
                       variant renders the same body with ESRS labels stripped.
                       The dual framing keys off ``user_type`` at render time,
                       NOT off two template IDs (§8.6).
  - ``mnc_ghg``      : MNC GHG-specific report, framed as ESRS E1.
  - ``mnc_air``      : MNC Air-specific report, framed as ESRS E2.
  - ``mnc_nature``   : MNC Nature-specific report, framed as ESRS E4.
  - ``trend``        : Trend report (Option A, RT9). Both user types. Own
                       per-indicator structure, no pillar composite, NOT
                       ESRS-framed. Separate template family.

Each template declares: which user types may pick it (``user_types``), which
pillars it renders (``pillars`` — drives indicator/finding filtering), whether
the ESRS framing layer applies (``esrs`` — only takes effect for MNC renders,
see ``RenderContext`` in ``p11_sections``), and its ordered ``sections`` tuple.
"""

# M-P11.1 / M-REPORT-A1
from __future__ import annotations

from dataclasses import dataclass

# Canonical pillar set, in the locked air → ghg → nature order (CLAUDE.md §7).
ALL_PILLARS: frozenset[str] = frozenset({"air", "ghg", "nature"})


@dataclass(frozen=True)
class ReportTemplate:
    template_id:           str
    display_name:          str
    description:           str
    # M-REPORT-A1: a set, not a single string — the General report and the
    # Trend report are offered to BOTH user types (RT7/RT8/RT11).
    user_types:            frozenset[str]      # {"policy_maker", "mnc"}
    accepted_source_types: frozenset[str]      # e.g. {"screening", "prioritisation"}
    sections:              tuple[str, ...]
    # M-REPORT-A1: which pillars this template renders. The General report
    # covers all three; the MNC pillar reports each cover one. Findings,
    # indicator detail and reference datasets are filtered to this set.
    pillars:               frozenset[str] = ALL_PILLARS
    # M-REPORT-A1: whether the ESRS framing layer (RT4) is available. It only
    # takes effect for MNC renders (a policy maker picking the General report
    # gets the same body with ESRS stripped — RT8). Trend is never ESRS-framed.
    esrs:                  bool           = False


# Shared section bodies (RT8: General is ONE structure, dual-framed at render).
_GENERAL_SECTIONS: tuple[str, ...] = (
    "title_page",
    "executive_summary",
    "methodology",
    "scope_summary",
    "pillar_findings",          # ESRS-framed when ctx.apply_esrs, plain otherwise
    "indicator_detail",
    "reference_datasets",
    "provenance_appendix",
    "composite_formula",        # M-REPORT-A1.1 — how the composite is built
    "glossary",                 # content-aware appendix (RT12)
)

# MNC pillar-specific reports: same section machinery, filtered to one pillar.
_PILLAR_SECTIONS: tuple[str, ...] = (
    "title_page",
    "executive_summary",
    "methodology",
    "scope_summary",
    "pillar_findings",          # always ESRS-framed (MNC-only templates)
    "indicator_detail",
    "reference_datasets",
    "provenance_appendix",
    "composite_formula",        # M-REPORT-A1.1 — composite covers all 3 pillars
    "glossary",
)

# Trend report (Option A, RT9): per-indicator structure, no composite.
_TREND_SECTIONS: tuple[str, ...] = (
    "title_page",
    "scope_summary",
    "trend_indicator_sections",  # per-indicator, grouped under pillar headers
    "provenance_appendix",
    "glossary",
)

# Supplier cooperation report (M-REPORT-COOP): a deliberately concise,
# supplier-facing single-pillar report that frames a screening result as a
# shared starting point for improvement, not a verdict. Its own short section
# family — no executive composite, no indicator-detail table, no provenance
# appendix, no ESRS framing (all intentionally excluded, spec §"Deliberately
# excluded"). The pillar is user-chosen at render time (threaded via the
# RenderContext), so unlike the MNC pillar reports it carries no fixed pillar.
_COOPERATION_SECTIONS: tuple[str, ...] = (
    "cooperation_title",        # title + supplier + screening window
    "cooperation_finding",      # the pillar's finding in plain language (verbal summary)
    "cooperation_improvement",  # where improvement would matter most (dominant driver)
    "cooperation_framing",      # screening-signal, not a determination of cause/compliance
    "glossary",                 # content-aware appendix, scoped to terms used (RT13)
)


_TEMPLATES: tuple[ReportTemplate, ...] = (
    # ── General report (both user types, dual-framed — RT7/RT8) ──────────
    ReportTemplate(
        template_id="general",
        display_name="General report",
        description=(
            "All three pillars — Air, GHG, and Nature. For MNCs the findings "
            "are framed as the metrics & evidence section of ESRS E1/E2/E4; "
            "for policy makers the same body is rendered without ESRS framing."
        ),
        user_types=frozenset({"policy_maker", "mnc"}),
        accepted_source_types=frozenset({"screening", "prioritisation"}),
        sections=_GENERAL_SECTIONS,
        pillars=ALL_PILLARS,
        esrs=True,   # applied for MNC renders only; stripped for policy makers
    ),
    # ── MNC pillar-specific ESRS reports (RT5/RT6) ───────────────────────
    ReportTemplate(
        template_id="mnc_ghg",
        display_name="GHG report (ESRS E1)",
        description=(
            "GHG pillar only, framed as the metrics & evidence section of "
            "ESRS E1 (Climate change). Policy / action / target sub-sections "
            "are shown as labelled out-of-scope stubs."
        ),
        user_types=frozenset({"mnc"}),
        accepted_source_types=frozenset({"screening", "prioritisation"}),
        sections=_PILLAR_SECTIONS,
        pillars=frozenset({"ghg"}),
        esrs=True,
    ),
    ReportTemplate(
        template_id="mnc_air",
        display_name="Air report (ESRS E2)",
        description=(
            "Air pillar only, framed as the metrics & evidence section of "
            "ESRS E2 (Pollution). Policy / action / target sub-sections are "
            "shown as labelled out-of-scope stubs."
        ),
        user_types=frozenset({"mnc"}),
        accepted_source_types=frozenset({"screening", "prioritisation"}),
        sections=_PILLAR_SECTIONS,
        pillars=frozenset({"air"}),
        esrs=True,
    ),
    ReportTemplate(
        template_id="mnc_nature",
        display_name="Nature report (ESRS E4)",
        description=(
            "Nature/Land pillar only, framed as the metrics & evidence "
            "section of ESRS E4 (Biodiversity and ecosystems). Policy / "
            "action / target sub-sections are shown as labelled out-of-scope "
            "stubs."
        ),
        user_types=frozenset({"mnc"}),
        accepted_source_types=frozenset({"screening", "prioritisation"}),
        sections=_PILLAR_SECTIONS,
        pillars=frozenset({"nature"}),
        esrs=True,
    ),
    # ── Supplier cooperation report (both user types — M-REPORT-COOP) ────
    ReportTemplate(
        template_id="supplier_cooperation",
        display_name="Supplier cooperation report",
        description=(
            "A short, supplier-facing report on one pillar (you choose which). "
            "It frames the screening result as a shared starting point for "
            "improvement — where attention would matter most — rather than a "
            "determination of cause or compliance. No cross-supplier ranking, "
            "confidence payload, provenance appendix, or ESRS codes."
        ),
        user_types=frozenset({"policy_maker", "mnc"}),
        accepted_source_types=frozenset({"screening"}),
        sections=_COOPERATION_SECTIONS,
        # Candidate set; the actual pillar is user-chosen and threaded through
        # the RenderContext at render time (M-REPORT-COOP). Never ESRS-framed.
        pillars=ALL_PILLARS,
        esrs=False,
    ),
    # ── Trend report (both user types, not ESRS-framed — RT9/RT11) ───────
    ReportTemplate(
        template_id="trend",
        display_name="Trend report",
        description=(
            "Per-indicator trend drill-downs (Theil–Sen slope + Mann–Kendall "
            "significance) grouped under pillar headers. No pillar composite "
            "and no ESRS framing — trend is a drill-down signal only."
        ),
        user_types=frozenset({"policy_maker", "mnc"}),
        accepted_source_types=frozenset({"trend"}),
        sections=_TREND_SECTIONS,
        pillars=ALL_PILLARS,   # used only as grouping headers (RT10)
        esrs=False,
    ),
)


def templates_for(user_type: str) -> list[ReportTemplate]:
    """Templates available to a user-type, in registry order.

    M-REPORT-A1: membership test against ``user_types`` — the General and
    Trend reports belong to both roles, so they appear for either.
    """
    return [t for t in _TEMPLATES if user_type in t.user_types]


def get_template(template_id: str) -> ReportTemplate | None:
    """Lookup a single template by ID. ``None`` if not found."""
    for t in _TEMPLATES:
        if t.template_id == template_id:
            return t
    return None
