"""
Earth Engine initialisation helper.

Earth Engine changed its auth model: every ee.* call must be tied to a
Google Cloud project that has the Earth Engine API enabled. So this helper
both initialises EE and reads a project ID from an environment variable.

Set EE_PROJECT_ID before running Streamlit:

    export EE_PROJECT_ID=your-project-id

To make it persistent, add the line to your ~/.zprofile.
"""

import os
import streamlit as st


@st.cache_resource(show_spinner="Initialising Earth Engine…")
def init_earth_engine() -> bool:
    """
    Initialise Earth Engine. Returns True on success, False on failure.
    Cached for the lifetime of the Streamlit process.
    """
    try:
        import ee

        project = os.environ.get("EE_PROJECT_ID")
        if not project:
            st.error(
                "Earth Engine project ID not set.\n\n"
                "In your terminal (venv active), run:\n\n"
                "    export EE_PROJECT_ID=your-project-id\n\n"
                "Then restart Streamlit. To make it permanent, add the line "
                "to your `~/.zprofile`."
            )
            st.stop()

        ee.Initialize(project=project)
        return True
    except Exception as exc:
        st.error(
            "Earth Engine failed to initialise. Confirm you've run "
            "`earthengine authenticate` and that your project has the "
            "Earth Engine API enabled."
        )
        st.caption(f"Underlying error: `{exc}`")
        st.stop()
        return False  # unreachable, but keeps type checkers happy


def require_earth_engine() -> None:
    """Guard for pages that need Earth Engine."""
    init_earth_engine()
