"""Tests for ui.components.p04_form scope dispatch (M-P04-ACTIVATE).

Pure-Python — no Streamlit, no EE. Covers ``_source_for_scope``, the
helper that builds the ``centre_metadata.source`` string from the
active scope. P-05's C1 header surfaces this; the test pins the
expected strings so a future refactor can't silently break the
source-attribution UX without tripping the suite.
"""

# M-P04-ACTIVATE
from __future__ import annotations

from demo.regions import Region
from demo.scopes import SupplyChain, SupplyChainNode
from ui.components.p04_form import _source_for_scope


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _chain() -> SupplyChain:
    return SupplyChain(
        id="test_chain",
        name="Test Steel Chain",
        industry="Steel",
        country="Brazil",
        nodes=(
            SupplyChainNode(
                id="n1", name="Node 1", tier="Tier 1",
                lat=-20.0, lon=-44.0,
            ),
        ),
    )


def _region() -> Region:
    return Region(
        name="Pará",
        country="Brazil",
        centroid_lat=-3.99,
        centroid_lon=-53.09,
        radius_km=400.0,
        natural_radius_km=455.0,
    )


# ---------------------------------------------------------------------------
# No-scope / unset
# ---------------------------------------------------------------------------

def test_source_for_none_scope():
    """No scope set at all → free-coordinates label."""
    assert _source_for_scope(None) == "P-04 free coordinates"


def test_source_for_explicit_none_kind():
    """Explicit ``{kind: "none"}`` → same free-coordinates label.

    Distinguished from None in session-state semantics (the user opted
    into no scope vs never visited P-02) but they share the same source
    string — both routes lead to the same UI experience.
    """
    scope = {"kind": "none", "data": None}
    assert _source_for_scope(scope) == "P-04 free coordinates"


# ---------------------------------------------------------------------------
# Supply chain scope
# ---------------------------------------------------------------------------

def test_source_for_supply_chain_scope_includes_chain_name():
    scope = {"kind": "supply_chain", "data": _chain()}
    result = _source_for_scope(scope)
    assert result == "P-04 supply-chain scope · Test Steel Chain"


# ---------------------------------------------------------------------------
# Region scope
# ---------------------------------------------------------------------------

def test_source_for_region_scope_includes_name_and_country():
    scope = {"kind": "region", "data": _region()}
    result = _source_for_scope(scope)
    assert result == "P-04 region scope · Pará, Brazil"


# ---------------------------------------------------------------------------
# Defensive fallbacks
# ---------------------------------------------------------------------------

def test_source_for_unknown_scope_kind_falls_back():
    """Future scope kinds we haven't taught the helper about should
    render a generic label rather than crash."""
    scope = {"kind": "future_kind", "data": None}
    assert _source_for_scope(scope) == "P-04 setup"


def test_source_for_supply_chain_with_missing_data_falls_back():
    """Defensive: ``data`` is ``None`` but ``kind`` says supply_chain
    (malformed state) → fall back to the generic label, don't
    AttributeError on ``data.name``."""
    scope = {"kind": "supply_chain", "data": None}
    assert _source_for_scope(scope) == "P-04 setup"


def test_source_for_region_with_missing_data_falls_back():
    scope = {"kind": "region", "data": None}
    assert _source_for_scope(scope) == "P-04 setup"
