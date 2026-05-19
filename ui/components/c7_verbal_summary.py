"""C7 — verbal summary paragraphs (M-UI-E.2).

Thin Streamlit wrapper around ``engine.verbal_summary.generate_verbal_summary``.
The generator is the deterministic prose engine from M-UI-E.0; this
component just renders its four-paragraph output as Markdown.

Authority: ``docs/Wireframes_All_v4.md`` §P-05 C7.
"""

# M-UI-E.2
from __future__ import annotations

import streamlit as st

from engine.verbal_summary import generate_verbal_summary


def render_c7_verbal_summary(payload: dict) -> None:
    """Render the C7 verbal summary block — overview + three pillar
    paragraphs, separated by paragraph breaks (``VerbalSummary.joined``).
    """
    summary = generate_verbal_summary(payload)
    with st.container(border=True):
        st.markdown("### Summary")
        st.markdown(summary.joined())
