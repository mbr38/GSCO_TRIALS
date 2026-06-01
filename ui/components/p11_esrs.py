"""ESRS framing layer for P-11 reports (M-REPORT-A1 §4).

The ESRS reframe (RT2) is a **layer applied over the shared section body**, not
a parallel set of sections. This module holds the layer's three pieces:

  1. **Topical grouping** — the pillar → ESRS topical-standard map (RT6):
     Air → E2 (Pollution), GHG → E1 (Climate change),
     Nature → E4 (Biodiversity and ecosystems).
  2. **Datapoint labelling** — *deferred* (Step A §8.4). Specific ESRS datapoint
     codes are not in the project docs; this milestone ships topical grouping +
     scope honesty only. The hook is here (``datapoint_label``) returning ``None``
     so the wiring is in place when a datapoint reference is supplied.
  3. **Scope honesty (RT4)** — each ESRS section opens as the *metrics & evidence*
     contribution and renders the policies / actions / targets sub-sections as
     labelled out-of-scope stubs. The report must never imply full compliance.

Deterministic, no LLM (CLAUDE.md §8). Pure string helpers — no Streamlit, no EE.
"""

# M-REPORT-A1
from __future__ import annotations

import html

# RT6 — pillar → (ESRS topical standard code, human topic name).
PILLAR_ESRS: dict[str, tuple[str, str]] = {
    "ghg":    ("E1", "Climate change"),
    "air":    ("E2", "Pollution"),
    "nature": ("E4", "Biodiversity and ecosystems"),
}


def esrs_code(pillar: str) -> str | None:
    """The ESRS topical-standard code for a pillar, e.g. ``"E2"`` for air."""
    pair = PILLAR_ESRS.get(pillar)
    return pair[0] if pair else None


def datapoint_label(indicator_id: str) -> str | None:
    """ESRS datapoint reference for an indicator (RT-§4 item 2).

    DEFERRED (Step A §8.4): per-indicator ESRS datapoint codes are not present
    in the project docs. Until an ESRS datapoint reference is supplied this
    returns ``None`` and no datapoint label is rendered. The topical-grouping
    and scope-honesty parts of §4 do not depend on this and ship now.
    """
    return None


def esrs_topic_heading(pillar: str) -> str:
    """``<h2>`` opening an ESRS topical section — e.g. 'ESRS E2 — Pollution'."""
    code, topic = PILLAR_ESRS[pillar]
    return f"<h2>ESRS {code} — {html.escape(topic)}: metrics &amp; evidence</h2>"


def esrs_metrics_intro(pillar: str) -> str:
    """The 'this is the metrics & evidence section' opener (RT4 scope honesty)."""
    code, topic = PILLAR_ESRS[pillar]
    return (
        "<p class='esrs-intro'><em>This section provides the "
        f"<strong>metrics &amp; evidence</strong> contribution to ESRS {code} "
        f"({html.escape(topic)}). It presents environmental-screening "
        "measurements only — it is not a complete ESRS disclosure.</em></p>"
    )


def esrs_out_of_scope_stub(pillar: str) -> str:
    """Labelled out-of-scope stub for the policy/action/target sub-sections (RT4).

    A short fixed paragraph stating the company supplies that content; the tool
    produces the environmental-screening metrics layer only. Renders the three
    sub-sections ESRS topical standards require so the boundary is visible and
    the report never implies full compliance.
    """
    code, _ = PILLAR_ESRS[pillar]
    return (
        "<div class='esrs-out-of-scope'>"
        f"<h4>ESRS {code} — policies, actions &amp; targets "
        "<span class='oos-tag'>out of scope</span></h4>"
        "<p><em>The disclosing company supplies the policies, actions, and "
        "targets that ESRS "
        f"{code} requires. The GSCO Environmental Monitoring tool produces the "
        "environmental-screening metrics &amp; evidence layer only; these "
        "sub-sections are intentionally out of scope for this report.</em></p>"
        "</div>"
    )
