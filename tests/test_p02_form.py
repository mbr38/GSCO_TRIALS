"""Tests for ui.components.p02_form (M-P02).

Pure-Python — no Streamlit, no Earth Engine. Covers the user-type
hard-branch in ``_available_modes``: MNC sees Supply Chain + None;
Policy Maker sees Region + None; unknown / missing user_type falls
through to all three modes defensively.
"""

# M-P02
from __future__ import annotations

import pytest

from ui.components.p02_form import _available_modes


# ---------------------------------------------------------------------------
# Direct branch checks
# ---------------------------------------------------------------------------

def test_mnc_sees_supply_chain_and_none():
    """MNC's two modes — Supply Chain first, None second."""
    assert _available_modes("mnc") == ("supply_chain", "none")


def test_policy_maker_sees_region_and_none():
    """Policy Maker's two modes — Region first, None second."""
    assert _available_modes("policy_maker") == ("region", "none")


def test_none_user_type_falls_back_to_all_three():
    """Defensive — no user_type set (e.g. session expired) → all three
    modes visible so the page is still usable."""
    assert _available_modes(None) == ("supply_chain", "region", "none")


def test_unknown_user_type_falls_back_to_all_three():
    """Same defensive fallback for unexpected user_type values."""
    assert _available_modes("future_role") == (
        "supply_chain", "region", "none",
    )


# ---------------------------------------------------------------------------
# Cross-cutting invariants
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("user_type", ["mnc", "policy_maker", None, "x"])
def test_none_mode_is_always_present(user_type):
    """Every user-type branch — including the defensive fallback —
    offers None as an opt-out. Keeps the page usable when the curated
    data doesn't fit the user's actual screening intent."""
    assert "none" in _available_modes(user_type)


def test_mnc_cannot_see_region_mode():
    """Hard branch — MNC users never see the Region picker."""
    assert "region" not in _available_modes("mnc")


def test_policy_maker_cannot_see_supply_chain_mode():
    """Hard branch — Policy Maker users never see the Supply Chain picker."""
    assert "supply_chain" not in _available_modes("policy_maker")
