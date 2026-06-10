"""
Earth Engine initialisation helper.

Earth Engine changed its auth model: every ee.* call must be tied to a
Google Cloud project that has the Earth Engine API enabled. So this helper
both initialises EE and reads a project ID from an environment variable.

Two auth paths, selected automatically:

* **Local development** — set EE_PROJECT_ID and run `earthengine authenticate`
  once. The cached user OAuth credentials are used. This is the original,
  unchanged path.

      export EE_PROJECT_ID=your-project-id

  To make it persistent, add the line to your ~/.zprofile.

* **Deployed (e.g. Streamlit Community Cloud)** — there is no browser to do the
  interactive OAuth flow, so a service account is used instead. Paste the whole
  downloaded service-account JSON key into `st.secrets` under the key
  `EE_SERVICE_ACCOUNT_JSON` (and set `EE_PROJECT_ID` in secrets too). When that
  secret is present it takes precedence; otherwise we fall back to the local
  interactive path above. See README / `.streamlit/secrets.toml.example`.
"""

import json
import os
import streamlit as st


def _get_secret(key: str):
    """Read a Streamlit secret without raising when no secrets file exists.

    Locally there is usually no `.streamlit/secrets.toml`, in which case
    `st.secrets` access can raise. We treat any failure as "secret absent"
    so the local interactive path is chosen.
    """
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        return None
    return None


@st.cache_resource(show_spinner="Initialising Earth Engine…")
def init_earth_engine() -> bool:
    """
    Initialise Earth Engine. Returns True on success, False on failure.
    Cached for the lifetime of the Streamlit process.
    """
    try:
        import ee

        # Project ID: secrets first (deployed), then env var (local).
        project = _get_secret("EE_PROJECT_ID") or os.environ.get("EE_PROJECT_ID")
        if not project:
            st.error(
                "Earth Engine project ID not set.\n\n"
                "In your terminal (venv active), run:\n\n"
                "    export EE_PROJECT_ID=your-project-id\n\n"
                "Then restart Streamlit. To make it permanent, add the line "
                "to your `~/.zprofile`. (On a deployed app, set EE_PROJECT_ID "
                "in the app secrets instead.)"
            )
            st.stop()

        # Deployed path: service-account JSON pasted into secrets as one block.
        sa_json = _get_secret("EE_SERVICE_ACCOUNT_JSON")
        if sa_json:
            sa = json.loads(sa_json) if isinstance(sa_json, str) else dict(sa_json)
            credentials = ee.ServiceAccountCredentials(
                sa["client_email"], key_data=json.dumps(sa)
            )
            ee.Initialize(credentials, project=project)
        else:
            # Local path: cached user OAuth credentials from
            # `earthengine authenticate`. Unchanged from the original helper.
            ee.Initialize(project=project)
        return True
    except Exception as exc:
        st.error(
            "Earth Engine failed to initialise. Locally: confirm you've run "
            "`earthengine authenticate` and that your project has the Earth "
            "Engine API enabled. Deployed: confirm `EE_SERVICE_ACCOUNT_JSON` is "
            "valid and that the service account is registered for Earth Engine "
            "on the project."
        )
        st.caption(f"Underlying error: `{exc}`")
        st.stop()
        return False  # unreachable, but keeps type checkers happy


def require_earth_engine() -> None:
    """Guard for pages that need Earth Engine."""
    init_earth_engine()
