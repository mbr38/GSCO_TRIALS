"""Tests for ui.components.c8_action_bar._build_save_name (M-P10-POLISH).

Pure-Python — the builder is decoupled from Streamlit. Each test pins
one branch of the precedence rules in the function's docstring:
supply-chain → region → coordinate fallback.
"""

# M-P10-POLISH
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from ui.components.c8_action_bar import _build_save_name


# ---------------------------------------------------------------------------
# Test fixtures — minimal stand-ins for SupplyChain and Region
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _FakeChain:
    name: str


@dataclass(frozen=True)
class _FakeRegion:
    name:    str
    country: str


_FIXED_NOW = datetime(2026, 5, 20, 14, 23, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Supply-chain branch
# ---------------------------------------------------------------------------

class TestSupplyChainName:
    def test_supply_chain_scope_with_node_name(self) -> None:
        setup = {
            "centre":          {"lat": -11.86, "lon": -55.51},
            "centre_metadata": {
                "source":    "P-04 supply-chain scope · Soy & Cattle",
                "node_id":   "node_05",
                "node_name": "Sinop Soy Hub",
            },
        }
        scope = {
            "kind": "supply_chain",
            "data": _FakeChain(name="Soy & Cattle — Pará / Mato Grosso"),
        }
        name = _build_save_name(setup, scope, _FIXED_NOW)
        assert name == "Sinop Soy Hub — Soy & Cattle — Pará / Mato Grosso"

    def test_supply_chain_falls_back_when_node_name_missing(self) -> None:
        """Scope is supply_chain but centre_metadata didn't carry a
        node_name (e.g. a save from a pre-M-P10-POLISH session). Builder
        falls through to the coordinate format."""
        setup = {
            "centre":          {"lat": -11.86, "lon": -55.51},
            "centre_metadata": {"source": "P-04 supply-chain scope"},
        }
        scope = {
            "kind": "supply_chain",
            "data": _FakeChain(name="Soy & Cattle"),
        }
        name = _build_save_name(setup, scope, _FIXED_NOW)
        assert name.startswith("Screening @ (-11.8600, -55.5100)")


# ---------------------------------------------------------------------------
# Region branch
# ---------------------------------------------------------------------------

class TestRegionName:
    def test_region_scope_with_region_name_and_country(self) -> None:
        setup = {
            "centre":          {"lat": -15.78, "lon": -47.93},
            "centre_metadata": {
                "source":      "P-04 region scope · Distrito Federal, Brazil",
                "region_name": "Distrito Federal",
                "country":     "Brazil",
            },
        }
        scope = {
            "kind": "region",
            "data": _FakeRegion(name="Distrito Federal", country="Brazil"),
        }
        name = _build_save_name(setup, scope, _FIXED_NOW)
        assert name == "Distrito Federal, Brazil — Region screening"

    def test_region_falls_back_when_metadata_incomplete(self) -> None:
        """Region scope without region_name on centre_metadata falls to
        the coordinate format — same defensive behaviour as supply-chain.
        """
        setup = {
            "centre":          {"lat": -15.78, "lon": -47.93},
            "centre_metadata": {"source": "P-04 region scope"},  # No region_name/country.
        }
        scope = {
            "kind": "region",
            "data": _FakeRegion(name="Distrito Federal", country="Brazil"),
        }
        name = _build_save_name(setup, scope, _FIXED_NOW)
        assert name.startswith("Screening @ (-15.7800, -47.9300)")


# ---------------------------------------------------------------------------
# Fallback branch — none scope / missing scope / unexpected shape
# ---------------------------------------------------------------------------

class TestCoordinateFallback:
    def test_none_scope_uses_coordinate_format(self) -> None:
        """``scope == None`` is the no-scope (free coords) state."""
        setup = {"centre": {"lat": -23.5505, "lon": -46.6333}}
        name = _build_save_name(setup, None, _FIXED_NOW)
        assert name == (
            "Screening @ (-23.5505, -46.6333) — 2026-05-20 14:23 UTC"
        )

    def test_scope_kind_none_uses_coordinate_format(self) -> None:
        """The explicit ad-hoc fallback ``{"kind": "none"}`` hits the
        same branch as a missing scope key."""
        setup = {"centre": {"lat": -23.5505, "lon": -46.6333}}
        scope = {"kind": "none", "data": None}
        name = _build_save_name(setup, scope, _FIXED_NOW)
        assert name.startswith("Screening @ (-23.5505, -46.6333)")

    def test_empty_setup_uses_zero_coordinates(self) -> None:
        """Defensive — no centre / no setup keys at all renders
        (0.0000, 0.0000), matching the pre-M-P10-POLISH behaviour."""
        name = _build_save_name({}, None, _FIXED_NOW)
        assert name == (
            "Screening @ (0.0000, 0.0000) — 2026-05-20 14:23 UTC"
        )

    def test_unexpected_scope_kind_uses_coordinate_format(self) -> None:
        """A scope dict whose ``kind`` is neither ``"supply_chain"`` nor
        ``"region"`` (e.g. a future kind we haven't taught the builder
        about) safely falls back instead of raising."""
        setup = {"centre": {"lat": 1.0, "lon": 2.0}}
        scope = {"kind": "future_kind_we_dont_know", "data": object()}
        name = _build_save_name(setup, scope, _FIXED_NOW)
        assert name.startswith("Screening @ (1.0000, 2.0000)")
