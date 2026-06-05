"""Tests for demo.scopes (M-DEMO-DATA).

Pure-Python — no Streamlit, no EE. Asserts the three hand-curated
demo supply chains load, parse to the expected dataclass shape, and
have well-formed coordinates + unique IDs.
"""

# M-DEMO-DATA
from __future__ import annotations

import pytest

from demo.scopes import (
    SupplyChain,
    SupplyChainNode,
    all_scopes,
    country_scopes,
    get_scope,
    mnc_scopes,
)


# Module-level constants. The three Brazil MNC chains plus the India EV
# country chain. Adding a scope means adding the ID here too.
_BRAZIL_SCOPE_IDS: tuple[str, ...] = (
    "garments_sao_paulo_rio",
    "steel_minas_gerais",
    "soy_para_mato_grosso",
)
_EXPECTED_SCOPE_IDS: tuple[str, ...] = _BRAZIL_SCOPE_IDS + ("india_ev",)


# ---------------------------------------------------------------------------
# Load + count
# ---------------------------------------------------------------------------

def test_all_scopes_returns_four_entries():
    assert len(all_scopes()) == 4


def test_all_scopes_returns_sorted_by_name():
    scopes = all_scopes()
    names = [s.name for s in scopes]
    assert names == sorted(names)


def test_all_scope_ids_match_expected_set():
    ids = {s.id for s in all_scopes()}
    assert ids == set(_EXPECTED_SCOPE_IDS)


def test_scope_ids_are_unique():
    ids = [s.id for s in all_scopes()]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Per-scope shape + nodes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scope_id", _EXPECTED_SCOPE_IDS)
def test_scope_has_at_least_one_node(scope_id):
    scope = get_scope(scope_id)
    assert scope is not None
    assert len(scope.nodes) >= 1


@pytest.mark.parametrize("scope_id", _BRAZIL_SCOPE_IDS)
def test_mnc_scope_country_is_brazil(scope_id):
    """The three MNC demo chains all live in Brazil."""
    assert get_scope(scope_id).country == "Brazil"


@pytest.mark.parametrize("scope_id", _EXPECTED_SCOPE_IDS)
def test_every_node_has_valid_coordinates(scope_id):
    """Lat ∈ [-90, 90], lon ∈ [-180, 180] for every node."""
    scope = get_scope(scope_id)
    for node in scope.nodes:
        assert -90.0  <= node.lat <= 90.0, node.id
        assert -180.0 <= node.lon <= 180.0, node.id


@pytest.mark.parametrize("scope_id", _EXPECTED_SCOPE_IDS)
def test_node_ids_within_a_scope_are_unique(scope_id):
    scope = get_scope(scope_id)
    ids = [n.id for n in scope.nodes]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("scope_id", _EXPECTED_SCOPE_IDS)
def test_every_node_parsed_as_typed_dataclass(scope_id):
    """Each node is a frozen ``SupplyChainNode`` — confirms ``from_dict``
    wired everything through the dataclass constructor."""
    scope = get_scope(scope_id)
    for node in scope.nodes:
        assert isinstance(node, SupplyChainNode)


# ---------------------------------------------------------------------------
# get_scope
# ---------------------------------------------------------------------------

def test_get_scope_returns_the_named_scope():
    scope = get_scope("steel_minas_gerais")
    assert isinstance(scope, SupplyChain)
    # Branded with a real Brazilian steelmaker; geography retained in the name.
    assert scope.name == "Usiminas — Iron & Steel (Minas Gerais)"


def test_get_scope_returns_none_for_unknown_id():
    assert get_scope("nope") is None


# ---------------------------------------------------------------------------
# Audience split — MNC corporate chains vs country chains
# ---------------------------------------------------------------------------

def test_brazil_chains_default_to_mnc_audience():
    """The three Brazil JSONs carry no ``audience`` field → default 'mnc'."""
    for scope_id in _BRAZIL_SCOPE_IDS:
        assert get_scope(scope_id).audience == "mnc"


def test_india_ev_is_a_policy_maker_chain():
    chain = get_scope("india_ev")
    assert chain is not None
    assert chain.audience == "policy_maker"
    assert chain.country == "India"


def test_india_ev_has_24_clean_nodes():
    """The 5 country-centroid placeholders are dropped — 24 real nodes."""
    chain = get_scope("india_ev")
    assert len(chain.nodes) == 24
    # No node sits on India's geographic centroid placeholder coordinate.
    for node in chain.nodes:
        assert not (node.lat == pytest.approx(20.593684)
                    and node.lon == pytest.approx(78.96288)), node.id


def test_mnc_scopes_excludes_india_ev():
    """``mnc_scopes`` is the MNC picker source — must not leak the
    India EV country chain."""
    ids = {s.id for s in mnc_scopes()}
    assert ids == set(_BRAZIL_SCOPE_IDS)
    assert "india_ev" not in ids


def test_country_scopes_india_returns_india_ev():
    scopes = country_scopes("India")
    assert {s.id for s in scopes} == {"india_ev"}


def test_country_scopes_brazil_is_empty():
    """The Brazil chains are MNC-audience, so the Policy-Maker country
    picker finds nothing for Brazil (yet)."""
    assert country_scopes("Brazil") == ()


def test_steel_scope_first_node_matches_source_json():
    """Spot-check one scope's parsed shape against the source JSON —
    catches accidental field renames / coordinate flips."""
    scope = get_scope("steel_minas_gerais")
    first = scope.nodes[0]
    assert first.id   == "steel_mg_01"
    assert first.name == "Ipatinga Integrated Steelworks (demo)"
    assert first.tier == "Tier 1"
    assert first.lat  == pytest.approx(-19.4675)
    assert first.lon  == pytest.approx(-42.5364)
    assert "high NO₂/SO₂" in (first.notes or "")
