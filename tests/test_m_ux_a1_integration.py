"""Integration tests for M-UX-A1 — the three UX surfaces together.

Confirms the loader copy (2.6), saved-analyses search (2.7) over the *real*
production seed files, and the parameter-transparency registry (2.8) all load
and behave together, with no shared-state interaction.
"""

# M-UX-A1
from __future__ import annotations

import json
from pathlib import Path

from demo.indicator_library import load_library
from engine import parameter_registry as pr
from ui.components.p10_list import _filter_saves
from ui.page_state import SCREENING_LOADER_COPY


_SEED_DIR = Path(__file__).resolve().parent.parent / "demo" / "saved_analyses"


def _load_real_seeds() -> list[dict]:
    """Load the committed production saved-analyses seed files."""
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(_SEED_DIR.glob("*.json"))]


class TestSurfacesCoexist:
    def test_all_three_surfaces_import_cleanly(self) -> None:
        # 2.6 constant, 2.7 filter, 2.8 registry — all importable together.
        assert isinstance(SCREENING_LOADER_COPY, str)
        assert callable(_filter_saves)
        assert pr.load_registry()  # non-empty

    def test_no_lint_problems_on_cold_load(self) -> None:
        assert pr.lint_inventory() == []


class TestSearchOnProductionSeeds:
    def test_seeds_load(self) -> None:
        seeds = _load_real_seeds()
        assert len(seeds) >= 2

    def test_empty_query_returns_all_production_seeds(self) -> None:
        seeds = _load_real_seeds()
        assert _filter_saves(seeds, "") == seeds

    def test_search_finds_a_real_seed_by_supplier_or_name(self) -> None:
        # The seed set includes Suape and Norilsk wind demos; both should be
        # findable by a substring of their name/supplier.
        seeds = _load_real_seeds()
        suape = _filter_saves(seeds, "suape")
        assert len(suape) == 1
        norilsk = _filter_saves(seeds, "norilsk")
        assert len(norilsk) == 1

    def test_search_is_case_insensitive_on_real_data(self) -> None:
        seeds = _load_real_seeds()
        assert _filter_saves(seeds, "SUAPE") == _filter_saves(seeds, "suape")

    def test_no_match_returns_empty_on_real_data(self) -> None:
        seeds = _load_real_seeds()
        assert _filter_saves(seeds, "zzz-no-such-supplier") == []


class TestParameterCoverageAcrossLibrary:
    def test_every_card_lookup_returns_a_list(self) -> None:
        # P-09 calls get_parameters_for_indicator for every card id; none
        # should raise, and each returns a (possibly empty) list.
        library = load_library()
        for card in library.values():
            params = pr.get_parameters_for_indicator(card.indicator_id)
            assert isinstance(params, list)

    def test_some_cards_have_parameters(self) -> None:
        # The surface must actually render somewhere — at least the air
        # gases and habitat conversion carry parameters.
        library = load_library()
        with_params = [
            c.indicator_id for c in library.values()
            if pr.get_parameters_for_indicator(c.indicator_id)
        ]
        assert len(with_params) >= 5

    def test_negative_case_indicator_without_parameters(self) -> None:
        # UX17 negative path — ODIAC CO2 has no annotated thresholds, so the
        # section is omitted (empty list → renderer no-ops).
        assert pr.get_parameters_for_indicator("ghg.co2.score") == []

    def test_shared_constant_appears_under_multiple_cards(self) -> None:
        # UX19 — a shared constant renders under more than one card.
        library = load_library()
        cards_with_norm_k = [
            c.indicator_id for c in library.values()
            if any(r.name == "NORMALISATION_K"
                   for r in pr.get_parameters_for_indicator(c.indicator_id))
        ]
        assert len(cards_with_norm_k) > 1
