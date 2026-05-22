"""Streamlit entry point with programmatic page registration.

M-DEMO-POLISH — replaces the implicit filename-based navigation with
``st.Page`` / ``st.navigation``. The user-facing sidebar labels are
explicit; the landing page reads as "Landing" instead of the
filename-derived "app".

Run with: ``streamlit run gsco_app.py``.
"""

# M-DEMO-POLISH
import streamlit as st


landing = st.Page(
    "app.py",
    title="Landing",
    icon="🏠",
    default=True,
)
scope = st.Page(
    "pages/02_Scope_Setup.py",
    title="Scope Setup",
    icon="🌍",
)
hub = st.Page(
    "pages/03_Workflow_Hub.py",
    title="Workflow Hub",
    icon="🔀",
)
inspect = st.Page(
    "pages/04_Inspect_Setup.py",
    title="Inspect — Setup",
    icon="🔍",
)
results = st.Page(
    "pages/05_Screening_Results.py",
    title="Inspect — Results",
    icon="📊",
)
prio = st.Page(
    "pages/07_Prioritisation_Setup.py",
    title="Prioritisation — Setup",
    icon="📋",
)
prio_results = st.Page(
    "pages/08_Prioritisation_Results.py",
    title="Prioritisation — Results",
    icon="📈",
)
library = st.Page(
    "pages/09_Indicator_Library.py",
    title="Indicator Library",
    icon="📚",
)
saved = st.Page(
    "pages/10_Saved_Analyses.py",
    title="Saved Analyses",
    icon="💾",
)
reports = st.Page(
    "pages/11_Reports.py",
    title="Reports",
    icon="📄",
)
# Developer-only — kept in the navigation registry so existing
# ``st.switch_page("pages/99_engine_scratch.py")`` calls from P-05
# continue to resolve under ``st.navigation``.
scratch = st.Page(
    "pages/99_engine_scratch.py",
    title="Engine Scratch (dev)",
    icon="🧪",
)


pg = st.navigation({
    "Main": [
        landing,
        scope,
        hub,
        inspect,
        results,
        prio,
        prio_results,
        library,
        saved,
        reports,
    ],
    "Developer": [scratch],
})
pg.run()
