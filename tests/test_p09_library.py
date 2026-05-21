"""Tests for ui.components.p09_library (M-P09).

Pure-Python. The renderer's surface is Streamlit; the testable logic
is in ``_filter_cards`` and ``_collect_esg_terms``.
"""

# M-P09
from __future__ import annotations

from demo.indicator_library import IndicatorCardContent, load_library
from ui.components.p09_library import _collect_esg_terms, _filter_cards


# ---------------------------------------------------------------------------
# _filter_cards
# ---------------------------------------------------------------------------

def test_filter_cards_empty_filters_returns_all_in_pillar():
    library = load_library()
    cards = _filter_cards(
        library, pillar_id="air", search_query="", esg_filter="(all)",
    )
    # M-P09-COMPOSITES: 9 raw + 4 component scores + 1 aggregate = 14.
    assert len(cards) == 14
    assert all(c.pillar == "air" for c in cards)


def test_filter_cards_search_by_display_name():
    """Searching for 'methane' finds CH₄ — plus any derived entry
    whose narrative discusses methane (M-P09-COMPOSITES: the GHG core
    audit support's definition names the three live signals including
    methane, which is a useful behaviour, not a bug)."""
    library = load_library()
    cards = _filter_cards(
        library, pillar_id="ghg", search_query="methane",
        esg_filter="(all)",
    )
    names = {c.indicator_id for c in cards}
    assert "ghg.ch4.score" in names


def test_filter_cards_search_by_definition_substring():
    """Search hits the definition body, not just the name."""
    library = load_library()
    cards = _filter_cards(
        library, pillar_id="nature", search_query="EUDR",
        esg_filter="(all)",
    )
    # Forest loss + habitat conversion + DW (commodity supply-chain
    # framings); accept the union — pin only that forest_loss is in it.
    names = {c.indicator_id for c in cards}
    assert "nature.forest_loss.ha" in names


def test_filter_cards_search_is_case_insensitive():
    library = load_library()
    upper = _filter_cards(library, "ghg", "METHANE", "(all)")
    lower = _filter_cards(library, "ghg", "methane", "(all)")
    assert {c.indicator_id for c in upper} == {c.indicator_id for c in lower}


def test_filter_cards_esg_filter_narrows_results():
    """EUDR matches only the deforestation-class indicators."""
    library = load_library()
    cards = _filter_cards(
        library, pillar_id="nature", search_query="",
        esg_filter="EU Deforestation Regulation (EUDR, 2025)",
    )
    names = {c.indicator_id for c in cards}
    assert "nature.forest_loss.ha"          in names
    assert "nature.habitat.natural_loss_ha" in names
    # NDVI shouldn't carry EUDR alignment.
    assert "nature.ndvi.score" not in names


def test_filter_cards_search_and_esg_compose_as_and():
    """Both filters apply — AND, not OR.

    Verified by demonstrating that adding the ESG filter strictly
    narrows the search-only result set. NDVI mentions vegetation in
    its definition (so search "vegetation" matches it) but doesn't
    carry EUDR alignment — so the AND should drop it.
    """
    library = load_library()
    search_only = _filter_cards(
        library, pillar_id="nature", search_query="vegetation",
        esg_filter="(all)",
    )
    search_plus_esg = _filter_cards(
        library, pillar_id="nature", search_query="vegetation",
        esg_filter="EU Deforestation Regulation (EUDR, 2025)",
    )
    names_search = {c.indicator_id for c in search_only}
    names_both   = {c.indicator_id for c in search_plus_esg}
    # NDVI matches "vegetation" but isn't EUDR-aligned.
    assert "nature.ndvi.score" in names_search
    assert "nature.ndvi.score" not in names_both
    # AND, not OR: the combined set is a subset of the search-only set.
    assert names_both.issubset(names_search)


def test_filter_cards_no_match_returns_empty_list():
    library = load_library()
    cards = _filter_cards(library, "air", "xyzzy-nothing", "(all)")
    assert cards == []


# ---------------------------------------------------------------------------
# _collect_esg_terms
# ---------------------------------------------------------------------------

def test_collect_esg_terms_returns_sorted_unique_list():
    library = load_library()
    terms = _collect_esg_terms(library)
    assert terms == sorted(terms)
    assert len(terms) == len(set(terms))


def test_collect_esg_terms_includes_known_frameworks():
    """Spot-check that prominent frameworks make it into the dropdown."""
    terms = _collect_esg_terms(load_library())
    joined = " | ".join(terms)
    assert "WHO Air Quality Guidelines (2021)" in joined
    assert "EU Deforestation Regulation (EUDR, 2025)" in joined
    assert "TNFD" in joined


def test_collect_esg_terms_skips_dashes_and_empties():
    """A stub card with esg_alignment='—' shouldn't pollute the list."""
    custom = {
        "x": IndicatorCardContent(
            indicator_id="x", pillar="air", sub_section="single_value",
            display_name="x", definition="x", decision_relevance="x",
            limitations="x", esg_alignment="—",
            asset_id="x", native_scale_m=1.0, data_type="x",
            data_source="x", temporal_frequency="x",
        ),
    }
    assert _collect_esg_terms(custom) == []


# ---------------------------------------------------------------------------
# M-P09-COMPOSITES: composite tab + cross-pillar entries
# ---------------------------------------------------------------------------

class TestCompositeTab:
    def test_composite_tab_returns_at_least_one_entry(self):
        """The fourth tab on P-09 — at minimum, the composite entry."""
        cards = _filter_cards(
            load_library(), pillar_id="composite",
            search_query="", esg_filter="(all)",
        )
        assert len(cards) >= 1
        assert any(
            c.indicator_id == "composite.overall_screening" for c in cards
        )

    def test_composite_tab_excludes_pillar_aggregates(self):
        """Pillar aggregates (air.audit_followup_priority, etc.) live
        in their own pillar tabs, NOT the composite tab."""
        cards = _filter_cards(
            load_library(), pillar_id="composite",
            search_query="", esg_filter="(all)",
        )
        names = {c.indicator_id for c in cards}
        assert "air.audit_followup_priority"    not in names
        assert "ghg.audit_followup_priority"    not in names
        assert "nature.followup_priority"       not in names

    def test_component_scores_appear_in_pillar_tab(self):
        """Air's component scores show up in the Air tab alongside the
        9 raw single values."""
        cards = _filter_cards(
            load_library(), pillar_id="air",
            search_query="", esg_filter="(all)",
        )
        names = {c.indicator_id for c in cards}
        assert "air.pollution_proxy_score"        in names
        assert "air.spatiotemporal_anomaly_score" in names
        assert "air.audit_followup_priority"      in names  # aggregate too

    def test_search_finds_derived_entry_by_display_name(self):
        """'biodiversity exposure' → the derived component score."""
        cards = _filter_cards(
            load_library(), pillar_id="nature",
            search_query="biodiversity exposure", esg_filter="(all)",
        )
        names = {c.indicator_id for c in cards}
        assert "nature.biodiversity_exposure" in names
