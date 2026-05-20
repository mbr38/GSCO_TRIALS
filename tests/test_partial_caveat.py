"""Tests for ui.components.c_partial_caveat (M-PARTIAL-CAVEAT).

Pure-Python — no Streamlit runtime. We monkeypatch the module's
``st.info`` to capture whether the banner was rendered and what
text it was passed.
"""

# M-PARTIAL-CAVEAT
from __future__ import annotations

import pytest

from ui.components import c_partial_caveat
from ui.components.c_partial_caveat import render_partial_caveat
from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS


class _InfoSpy:
    """Capture calls to st.info — body text + kwargs."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, body: str, **kwargs) -> None:
        self.calls.append((body, kwargs))


@pytest.fixture
def info_spy(monkeypatch):
    spy = _InfoSpy()
    # The module imports streamlit as ``st``; patch its ``info`` attr.
    monkeypatch.setattr(c_partial_caveat.st, "info", spy)
    return spy


# ---------------------------------------------------------------------------
# No-op vs render decision
# ---------------------------------------------------------------------------

def test_full_selection_is_a_noop(info_spy):
    """All 19 canonical indicators selected → banner does not render."""
    render_partial_caveat(set(ALL_INDICATOR_IDS))
    assert info_spy.calls == []


def test_subset_renders_banner_with_count(info_spy):
    """A 3-indicator subset renders the banner with '3 of 19'."""
    selected = {"air.no2.score", "ghg.ch4.score", "nature.kba.proximity_score"}
    render_partial_caveat(selected)
    assert len(info_spy.calls) == 1
    body, _ = info_spy.calls[0]
    assert "Partial screening" in body
    assert f"3 of {len(ALL_INDICATOR_IDS)} indicators" in body


def test_empty_selection_renders_zero_of_total(info_spy):
    """Defensive: an empty selection still fires with '0 of N'."""
    render_partial_caveat(set())
    assert len(info_spy.calls) == 1
    body, _ = info_spy.calls[0]
    assert f"0 of {len(ALL_INDICATOR_IDS)} indicators" in body


def test_unknown_ids_dont_count_toward_total(info_spy):
    """Extra/unknown IDs are ignored — count uses canonical-set membership."""
    selected = {"air.no2.score", "bogus.not_a_real_id", "another.fake"}
    render_partial_caveat(selected)
    assert len(info_spy.calls) == 1
    body, _ = info_spy.calls[0]
    # Only the one canonical ID counts.
    assert f"1 of {len(ALL_INDICATOR_IDS)} indicators" in body


def test_unknown_ids_alongside_full_canonical_still_noop(info_spy):
    """If the full canonical set is present plus extras, no banner."""
    selected = set(ALL_INDICATOR_IDS) | {"bogus.id_v2"}
    render_partial_caveat(selected)
    assert info_spy.calls == []
