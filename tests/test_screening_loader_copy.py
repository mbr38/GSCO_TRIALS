"""Tests for the screening loader copy (M-UX-A1 item 2.6).

The loader spinner text on P-05 (S1_Computing) is a static string locked by
spec UX2/UX3. It lives as a single constant in ``ui.page_state`` so the copy
is one-touch to update and assertable without booting Streamlit.
"""

# M-UX-A1
from __future__ import annotations

from pathlib import Path

from ui.page_state import SCREENING_LOADER_COPY


# UX3 — exact locked wording.
_EXPECTED = (
    "Running screening — typically 1-3 minutes. Larger AOIs and coastal "
    "locations may take longer."
)


class TestScreeningLoaderCopy:
    def test_exact_wording_locked(self) -> None:
        # UX3: the loader uses the spec-mandated wording verbatim.
        assert SCREENING_LOADER_COPY == _EXPECTED

    def test_no_stale_runtime_estimate(self) -> None:
        # The old "~30–60 seconds" / "60-120s" estimates are gone; the new
        # copy talks in minutes (UX2 — honest current-regime wording).
        assert "second" not in SCREENING_LOADER_COPY.lower()
        assert "minute" in SCREENING_LOADER_COPY.lower()

    def test_page_uses_the_constant_single_source(self) -> None:
        # UX2 / test-plan 6.1: the copy is in a single location. The page
        # must reference the constant, not inline a literal spinner string.
        page = (
            Path(__file__).resolve().parent.parent
            / "pages" / "05_Screening_Results.py"
        ).read_text(encoding="utf-8")
        assert "st.spinner(SCREENING_LOADER_COPY)" in page
        # No leftover hardcoded runtime estimate in the page.
        assert "30–60 seconds" not in page
