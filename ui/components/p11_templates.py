"""Report templates registry (M-P11.1).

Two templates ship in v1 per locked design:
  - ``policy_audit``   : Policy Maker user type
  - ``supplier_audit`` : MNC user type

Each template declares the section list it renders. M-P11.2 uses
these to drive the preview; M-P11.3 uses the same list for PDF
rendering — the HTML template files (in templates/p11/) match
these section keys.
"""

# M-P11.1
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportTemplate:
    template_id:           str
    display_name:          str
    description:           str
    user_type:             str                # "policy_maker" | "mnc"
    accepted_source_types: frozenset[str]     # e.g. {"screening", "prioritisation"}
    sections:              tuple[str, ...]


_TEMPLATES: tuple[ReportTemplate, ...] = (
    ReportTemplate(
        template_id="policy_audit",
        display_name="Policy audit report",
        description=(
            "Region-level audit framing. Covers methodology, "
            "pillar-by-pillar findings against the screened region, "
            "indicator-level provenance, and regulatory alignment "
            "notes."
        ),
        user_type="policy_maker",
        accepted_source_types=frozenset({"screening", "prioritisation"}),
        sections=(
            "title_page",
            "executive_summary",
            "methodology",
            "pillar_findings",
            "indicator_detail",
            "provenance_appendix",
        ),
    ),
    ReportTemplate(
        template_id="supplier_audit",
        display_name="Supplier audit report",
        description=(
            "Per-supplier deep-dive or portfolio-level prioritisation "
            "framing. Covers methodology, scope, audit-priority "
            "findings, per-supplier or per-pillar drill-down, and "
            "provenance for downstream audit."
        ),
        user_type="mnc",
        accepted_source_types=frozenset({"screening", "prioritisation"}),
        sections=(
            "title_page",
            "executive_summary",
            "methodology",
            "scope_summary",
            "priority_findings",
            "per_supplier_detail",
            "provenance_appendix",
        ),
    ),
)


def templates_for(user_type: str) -> list[ReportTemplate]:
    """Templates available to a user-type, in registry order."""
    return [t for t in _TEMPLATES if t.user_type == user_type]


def get_template(template_id: str) -> ReportTemplate | None:
    """Lookup a single template by ID. ``None`` if not found."""
    for t in _TEMPLATES:
        if t.template_id == template_id:
            return t
    return None
