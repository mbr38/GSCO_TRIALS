"""Tests for ui.components.persistent_nav (M-P0103).

Pure-Python — no Streamlit. Pins ``_scope_chip_label``, the pure
wording helper feeding the nav strip's scope chip. The render path
itself writes to Streamlit and can't be asserted on directly.
"""

# M-P0103
from __future__ import annotations

from demo.regions import Region
from demo.scopes import SupplyChain, SupplyChainNode
from ui.components.persistent_nav import _scope_chip_label


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _chain() -> SupplyChain:
    return SupplyChain(
        id="t",
        name="Test Steel Chain",
        industry="Steel",
        country="Brazil",
        nodes=(
            SupplyChainNode(
                id="n1", name="N1", tier="Tier 1",
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
# _scope_chip_label
# ---------------------------------------------------------------------------

def test_no_scope_renders_pick_scope_prompt():
    """``None`` → invites the user to pick a scope."""
    label, button = _scope_chip_label(None)
    assert label  == "Scope: not set"
    assert button == "Pick scope"


def test_explicit_none_kind_renders_same_prompt():
    """``{"kind": "none"}`` shares the no-scope label exactly — the two
    states diverge in semantics but converge in UI."""
    label, button = _scope_chip_label({"kind": "none", "data": None})
    assert label  == "Scope: not set"
    assert button == "Pick scope"


def test_supply_chain_scope_label_includes_chain_name():
    scope = {"kind": "supply_chain", "data": _chain()}
    label, button = _scope_chip_label(scope)
    assert label  == "Scope: Test Steel Chain"
    assert button == "Change"


def test_region_scope_label_includes_name_and_country():
    scope = {"kind": "region", "data": _region()}
    label, button = _scope_chip_label(scope)
    assert label  == "Scope: Pará, Brazil"
    assert button == "Change"


def test_country_regional_scope_label_includes_country():
    """Regional-analysis scope stores only the country; the chip marks it
    as a regional analysis."""
    scope = {"kind": "country_regional", "data": {"country": "India"}}
    label, button = _scope_chip_label(scope)
    assert label  == "Scope: India (regional)"
    assert button == "Change"


def test_unknown_scope_kind_falls_back():
    """Future scope kinds we haven't taught the chip about render a
    neutral fallback rather than crashing the nav strip."""
    scope = {"kind": "future_kind", "data": None}
    label, button = _scope_chip_label(scope)
    assert label  == "Scope: —"
    assert button == "Pick scope"
