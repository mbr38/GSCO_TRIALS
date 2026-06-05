"""Tests for ui.components.p02_form (M-P02 / Policy-Maker country flow).

Pure-Python — no Streamlit, no Earth Engine. Covers the user-type
hard-branch in ``_available_modes``: MNC (and the defensive fallback)
see Supply Chain + None; Policy Maker sees the Country card + None.
The Country card's Regional / Supply-chain sub-choice is exercised in
the integration / Playwright pass, not here.
"""

# M-P02
from __future__ import annotations

import pytest

from ui.components.p02_form import _available_modes


# ---------------------------------------------------------------------------
# Direct branch checks
# ---------------------------------------------------------------------------

def test_mnc_sees_supply_chain_and_none():
    """MNC's two cards — Supply Chain first, None second."""
    assert _available_modes("mnc") == ("supply_chain", "none")


def test_policy_maker_sees_country_and_none():
    """Policy Maker's two cards — Country first, None second. The
    Country card resolves to a regional or supply-chain pending scope."""
    assert _available_modes("policy_maker") == ("country", "none")


def test_none_user_type_falls_back_to_supply_chain_and_none():
    """Defensive — no user_type set (e.g. session expired) → the MNC
    cards so the page is still usable."""
    assert _available_modes(None) == ("supply_chain", "none")


def test_unknown_user_type_falls_back_to_supply_chain_and_none():
    """Same defensive fallback for unexpected user_type values."""
    assert _available_modes("future_role") == ("supply_chain", "none")


# ---------------------------------------------------------------------------
# Cross-cutting invariants
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("user_type", ["mnc", "policy_maker", None, "x"])
def test_none_mode_is_always_present(user_type):
    """Every user-type branch — including the defensive fallback —
    offers None as an opt-out. Keeps the page usable when the curated
    data doesn't fit the user's actual screening intent."""
    assert "none" in _available_modes(user_type)


def test_mnc_does_not_see_country_card():
    """Hard branch — MNC users get the curated supply-chain card, not
    the Country card."""
    assert "country" not in _available_modes("mnc")


def test_policy_maker_does_not_see_supply_chain_card():
    """Hard branch — Policy Maker users start from the Country card; the
    supply-chain pick lives *inside* it (filtered by country)."""
    assert "supply_chain" not in _available_modes("policy_maker")
