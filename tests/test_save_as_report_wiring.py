"""Tests for the M-P11.4 save-as-report routing helper.

Pure-Python — no Streamlit. ``route_to_p11_with_source`` is a state
mutator that takes a dict-like session_state and a source_id; the
side-effect-laden ``st.switch_page`` call is left to the calling site.
That split is what makes these tests possible.
"""

# M-P11.4
from __future__ import annotations

from ui.p11_state import ReportState, ReportStateKind, route_to_p11_with_source


# ---------------------------------------------------------------------------
# 5m. no existing report_state → creates new one with source pre-selected
# ---------------------------------------------------------------------------

def test_route_to_p11_initialises_report_state_when_missing():
    session_state: dict = {}
    route_to_p11_with_source(session_state, "src-1")

    assert "report_state" in session_state
    rs = session_state["report_state"]
    assert isinstance(rs, ReportState)
    assert rs.source_ids == ["src-1"]
    assert rs.kind == ReportStateKind.S1_TEMPLATE_AND_SOURCE


# ---------------------------------------------------------------------------
# 5n. existing report_state → appends source; doesn't duplicate
# ---------------------------------------------------------------------------

def test_route_to_p11_appends_new_source_to_existing_state():
    session_state: dict = {
        "report_state": ReportState(
            template_id="policy_audit",
            source_ids=["src-existing"],
            title="Q2 audit",
        )
    }
    route_to_p11_with_source(session_state, "src-new")

    rs = session_state["report_state"]
    assert rs.source_ids == ["src-existing", "src-new"]
    # Other fields preserved.
    assert rs.template_id == "policy_audit"
    assert rs.title == "Q2 audit"


def test_route_to_p11_does_not_duplicate_existing_source():
    session_state: dict = {
        "report_state": ReportState(source_ids=["src-1", "src-2"]),
    }
    route_to_p11_with_source(session_state, "src-1")

    rs = session_state["report_state"]
    # No duplicate added.
    assert rs.source_ids == ["src-1", "src-2"]


# ---------------------------------------------------------------------------
# 5o. always resets kind to S1 (user lands in template selection)
# ---------------------------------------------------------------------------

def test_route_to_p11_resets_kind_to_s1_from_s2():
    session_state: dict = {
        "report_state": ReportState(
            kind=ReportStateKind.S2_PREVIEW,
            template_id="policy_audit",
            source_ids=["src-old"],
            title="Q1 audit",
        )
    }
    route_to_p11_with_source(session_state, "src-new")

    assert (
        session_state["report_state"].kind
        == ReportStateKind.S1_TEMPLATE_AND_SOURCE
    )


def test_route_to_p11_resets_kind_to_s1_from_s3():
    session_state: dict = {
        "report_state": ReportState(
            kind=ReportStateKind.S3_EXPORT,
            source_ids=["src-old"],
        )
    }
    route_to_p11_with_source(session_state, "src-new")

    assert (
        session_state["report_state"].kind
        == ReportStateKind.S1_TEMPLATE_AND_SOURCE
    )
