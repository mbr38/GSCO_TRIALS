"""Streamlit entry point with programmatic page registration.

M-DEMO-POLISH — replaces the implicit filename-based navigation with
``st.Page`` / ``st.navigation``. The user-facing sidebar labels are
explicit; the landing page reads as "Landing" instead of the
filename-derived "app".

Run with: ``streamlit run gsco_app.py``.
"""

# M-DEMO-POLISH
import streamlit as st

from ui.theme.theme import apply_gsco_theme

# Inject the GSCO global CSS at the top of the navigation script.
# Streamlit's standard rerun model re-executes this entire script
# top-to-bottom on every user interaction (st.navigation is a router,
# not an alternative execution model), so this call themes every page
# render — no per-page wrapper needed.
apply_gsco_theme()


landing = st.Page(
    "app.py",
    title="Landing",
    default=True,
)
scope = st.Page(
    "pages/02_Scope_Setup.py",
    title="Scope Setup",
)
hub = st.Page(
    "pages/03_Workflow_Hub.py",
    title="Workflow Hub",
)
inspect = st.Page(
    "pages/04_Inspect_Setup.py",
    title="Inspect — Setup",
)
results = st.Page(
    "pages/05_Screening_Results.py",
    title="Inspect — Results",
)
# M-TREND-A2 — per-indicator trend drill-down (P-06). Registered so the
# ``st.switch_page("pages/06_Trend_View.py")`` calls from the C4b "view trend"
# tile link, the single-indicator map button, and the P-10 saved-trend Open
# action all resolve under ``st.navigation``. Reached by drilling into one
# indicator from a screening; shows an empty-state if opened with no context.
trend = st.Page(
    "pages/06_Trend_View.py",
    title="Trend View",
)
prio = st.Page(
    "pages/07_Prioritisation_Setup.py",
    title="Prioritisation — Setup",
)
prio_results = st.Page(
    "pages/08_Prioritisation_Results.py",
    title="Prioritisation — Results",
)
library = st.Page(
    "pages/09_Indicator_Library.py",
    title="Indicator Library",
)
saved = st.Page(
    "pages/10_Saved_Analyses.py",
    title="Saved Analyses",
)
reports = st.Page(
    "pages/11_Reports.py",
    title="Reports",
)
# Developer-only — kept in the navigation registry so existing
# ``st.switch_page("pages/99_engine_scratch.py")`` calls from P-05
# continue to resolve under ``st.navigation``.
scratch = st.Page(
    "pages/99_engine_scratch.py",
    title="Engine Scratch (dev)",
)


pg = st.navigation({
    "Main": [
        landing,
        scope,
        hub,
        inspect,
        results,
        trend,
        prio,
        prio_results,
        library,
        saved,
        reports,
    ],
    "Developer": [scratch],
})
pg.run()
