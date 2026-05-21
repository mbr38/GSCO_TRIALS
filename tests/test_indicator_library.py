"""Tests for demo.indicator_library (M-P09).

Pure-Python — no Streamlit, no Earth Engine. Loads the JSON manifest
and exercises the cross-reference against the engine configs.
"""

# M-P09
from __future__ import annotations

import pytest

from demo.indicator_library import (
    IndicatorCardContent,
    _describe_frequency,
    _load_manifest,
    _pillar_for,
    _stub_entry,
    get_esg_caveat,
    load_library,
)
from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS


# ---------------------------------------------------------------------------
# load_library — completeness + content integrity
# ---------------------------------------------------------------------------

def test_load_library_returns_19_raw_plus_16_derived():
    """v1 catalogue: 19 raw indicators + 16 derived (12 component
    scores + 3 pillar aggregates + 1 composite) = 35 entries total
    after M-P09-COMPOSITES."""
    lib = load_library()
    assert len(lib) == 35
    raw     = [c for c in lib.values() if c.kind == "raw"]
    derived = [c for c in lib.values() if c.kind == "derived"]
    assert len(raw)     == 19
    assert len(derived) == 16


def test_load_library_covers_every_raw_canonical_id():
    """ALL_INDICATOR_IDS must be a subset of the library's raw entries.

    M-P09-COMPOSITES: equality no longer holds (the library is larger
    than the raw registry), so we assert subset instead.
    """
    library_keys = set(load_library().keys())
    assert set(ALL_INDICATOR_IDS).issubset(library_keys)


def test_every_entry_has_nonempty_narrative_content():
    """No card should ship as a stub — that's a content gap to fix.
    Applies to both raw and derived entries.

    ``esg_alignment == "—"`` is a legitimate "no framework mapping"
    signal (e.g. confidence / trend sub-aggregates have no ESG
    alignment), so we accept it for that field only. The other
    narrative fields must carry real content.
    """
    for indicator_id, card in load_library().items():
        for field in (
            "display_name", "definition", "decision_relevance",
            "limitations", "esg_alignment",
        ):
            value = getattr(card, field)
            assert value, (
                f"{indicator_id}: {field} is empty"
            )
            if field != "esg_alignment":
                assert value != "—", (
                    f"{indicator_id}: {field} is dash-placeholder"
                )
            assert "Documentation pending" not in value, (
                f"{indicator_id}: {field} fell through to stub"
            )


def test_every_raw_entry_has_technical_metadata():
    """Raw entries: asset_id / data_type / data_source must be non-empty.
    native_scale_m may be None for vector assets (KBA).

    M-P09-COMPOSITES: scoped to ``kind == "raw"``. Derived entries
    have empty technical fields by design — formula + weights instead.
    """
    for indicator_id, card in load_library().items():
        if card.kind != "raw":
            continue
        assert card.asset_id,    f"{indicator_id}: asset_id missing"
        assert card.data_type,   f"{indicator_id}: data_type missing"
        assert card.data_source, f"{indicator_id}: data_source missing"
        if indicator_id == "nature.kba.proximity_score":
            assert card.native_scale_m is None
        else:
            assert isinstance(card.native_scale_m, (int, float))
            assert card.native_scale_m > 0


def test_load_library_is_cached():
    """Two calls return the same object — @cache works."""
    assert load_library() is load_library()


# ---------------------------------------------------------------------------
# Per-card field correctness — spot checks
# ---------------------------------------------------------------------------

def test_kba_card_marked_as_reference_dataset():
    card = load_library()["nature.kba.proximity_score"]
    assert card.data_type == "reference_dataset"
    assert "KBA" in card.display_name or "Biodiversity" in card.display_name


def test_co2_card_marked_as_inventory_allocation():
    """ODIAC is allocation, not measurement — must be flagged honestly."""
    card = load_library()["ghg.co2.score"]
    assert card.data_type == "emissions_inventory_allocation"
    # ODIAC asset path is lowercase (`assets/odiac`) — case-insensitive check.
    assert "odiac" in card.asset_id.lower()


def test_pm25_card_marked_as_gridded_model_output():
    """CAMS PM is model output, not measurement."""
    card = load_library()["air.pm25.score"]
    assert card.data_type == "gridded_model_output"
    assert "CAMS" in card.asset_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("indicator_id, expected_pillar", [
    ("air.no2.score",                 "air"),
    ("ghg.ch4.score",                 "ghg"),
    ("nature.kba.proximity_score",    "nature"),
    ("nature.dw.trees_pct",           "nature"),
])
def test_pillar_for_maps_canonical_ids(indicator_id, expected_pillar):
    assert _pillar_for(indicator_id) == expected_pillar


@pytest.mark.parametrize("asset_id, expected_substring", [
    ("COPERNICUS/S5P/OFFL/L3_NO2",                          "Sentinel-5P"),
    ("ECMWF/CAMS/NRT",                                      "CAMS"),
    ("projects/supply-chain-observatory/assets/odiac",      "ODIAC"),
    ("GOOGLE/DYNAMICWORLD/V1",                              "Dynamic World"),
    ("UMD/hansen/global_forest_change_2023_v1_11",          "Hansen"),
    ("MODIS/061/MOD13Q1",                                   "NDVI"),
    ("MODIS/061/MCD19A2_GRANULES",                          "MAIAC"),
    ("NASA/VIIRS/002/VNP46A2",                              "VIIRS"),
    ("ImaginaryAsset/ThatNobodyShips",                      "Varies"),
])
def test_describe_frequency_known_assets(asset_id, expected_substring):
    assert expected_substring in _describe_frequency(asset_id)


def test_load_manifest_returns_dict_with_meta_and_indicators():
    manifest = _load_manifest()
    assert "_meta" in manifest
    assert "air.no2.score" in manifest


def test_get_esg_caveat_returns_manifest_string():
    caveat = get_esg_caveat()
    assert "indicative" in caveat.lower()


# ---------------------------------------------------------------------------
# Stub fallback (defensive)
# ---------------------------------------------------------------------------

def test_stub_entry_has_every_narrative_field():
    """Defensive: a stub still has all the keys the loader expects, so
    a missing manifest entry produces a degraded card rather than
    a KeyError when the loader builds an IndicatorCardContent."""
    stub = _stub_entry("ghost.indicator.id")
    for field in (
        "sub_section", "display_name", "definition",
        "decision_relevance", "limitations", "esg_alignment",
    ):
        assert field in stub
    assert "ghost.indicator.id" in stub["display_name"]


# ---------------------------------------------------------------------------
# Dataclass shape
# ---------------------------------------------------------------------------

def test_indicator_card_content_is_frozen():
    import dataclasses
    card = next(iter(load_library().values()))
    with pytest.raises(dataclasses.FrozenInstanceError):
        card.display_name = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# M-P09-COMPOSITES: derived-entry / live-source canary tests
# ---------------------------------------------------------------------------

class TestDerivedEntries:
    """The derived entries (component scores + pillar aggregates +
    composite) are the M-P09-COMPOSITES scope. Their formulas and
    weights are pulled live from c5_drilldown; these tests verify the
    lockstep and catch drift in either direction."""

    def test_all_three_pillar_aggregates_present(self) -> None:
        lib = load_library()
        for pid in (
            "air.audit_followup_priority",
            "ghg.audit_followup_priority",
            "nature.followup_priority",
        ):
            assert pid in lib
            assert lib[pid].kind        == "derived"
            assert lib[pid].sub_section == "aggregate"

    def test_pillar_aggregate_weights_match_c5_drilldown(self) -> None:
        """Live-source lockstep: library weights == c5_drilldown
        weights, term-for-term. Drift in either surface fails here."""
        from ui.components.c5_drilldown import (
            _AIR_FORMULA, _GHG_FORMULA, _NATURE_FORMULA,
        )
        lib = load_library()
        for indicator_id, formula in [
            ("air.audit_followup_priority",    _AIR_FORMULA),
            ("ghg.audit_followup_priority",    _GHG_FORMULA),
            ("nature.followup_priority",       _NATURE_FORMULA),
        ]:
            expected = {t.payload_key: t.weight for t in formula}
            assert lib[indicator_id].weights == expected, (
                f"{indicator_id}: weights drifted from c5_drilldown"
            )

    def test_pillar_aggregate_weights_sum_to_one(self) -> None:
        """Standing invariant — every aggregate is a probability-like
        weighted sum, by design. Inherited from M-UI-E.4."""
        lib = load_library()
        for indicator_id in (
            "air.audit_followup_priority",
            "ghg.audit_followup_priority",
            "nature.followup_priority",
        ):
            assert sum(lib[indicator_id].weights.values()) == pytest.approx(1.0)

    def test_composite_is_equal_weighted_mean(self) -> None:
        lib = load_library()
        card = lib["composite.overall_screening"]
        assert card.kind   == "derived"
        assert card.pillar == "composite"
        assert card.weights == {
            "air.audit_followup_priority": pytest.approx(1 / 3),
            "ghg.audit_followup_priority": pytest.approx(1 / 3),
            "nature.followup_priority":    pytest.approx(1 / 3),
        }
        assert sum(card.weights.values()) == pytest.approx(1.0)

    def test_component_scores_have_inputs_but_no_formula(self) -> None:
        """v1 component scores: no exact formula / weights (M-COMPONENT-
        WEIGHTS deferred to v1.x), but DO carry a hand-authored
        ``inputs`` list of upstream IDs. Sanity check across all 12."""
        lib = load_library()
        component_ids = [
            "air.pollution_proxy_score",
            "air.spatiotemporal_anomaly_score",
            "air.trend_score",
            "air.attribution_confidence_score",
            "ghg.core_audit_support",
            "ghg.spatiotemporal_anomaly",
            "ghg.trend",
            "ghg.data_quality_attribution",
            "nature.biodiversity_exposure",
            "nature.habitat.conversion_score",
            "nature.vegetation_condition",
            "nature.quality_attribution",
        ]
        for indicator_id in component_ids:
            card = lib[indicator_id]
            assert card.kind        == "derived"
            assert card.sub_section == "component_score"
            assert card.formula     is None, (
                f"{indicator_id}: unexpected formula on component score"
            )
            assert card.weights     is None
            assert card.inputs, (
                f"{indicator_id}: missing inputs list (M-P09-COMPOSITES v2)"
            )
            assert all(isinstance(x, str) for x in card.inputs)


    def test_component_score_inputs_resolve_to_known_engine_keys(self) -> None:
        """Canary: every ID in any component score's ``inputs`` list
        resolves to a key the engine actually knows about. Catches
        typos in the manifest without coupling to the (huge) full
        engine emitted-keys enumeration.

        "Known" is the union of:

        - ``engine.ids.ALL_INDICATOR_IDS`` — the canonical schema.
        - Keys appearing in any of the weight dicts the compute_*
          aggregates consume. These include engine-internal
          intermediates like ``nature.habitat.*_pct_norm`` that
          aren't in the canonical schema but are real engine outputs
          produced inside ``_augment_habitat_pct_norms`` etc.
        """
        from engine.constants import (
            AIR_POLLUTION_PROXY_WEIGHTS,
            BIODIVERSITY_EXPOSURE_WEIGHTS,
            CORE_GHG_AUDIT_SUPPORT_WEIGHTS,
            GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS,
            HABITAT_CONVERSION_WEIGHTS,
            NATURE_QUALITY_ATTRIBUTION_WEIGHTS,
            VEGETATION_CONDITION_WEIGHTS,
        )
        from engine.ids import ALL_INDICATOR_IDS as CANONICAL_IDS

        known: set[str] = set(CANONICAL_IDS)
        for weight_dict in (
            AIR_POLLUTION_PROXY_WEIGHTS,
            CORE_GHG_AUDIT_SUPPORT_WEIGHTS,
            GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS,
            BIODIVERSITY_EXPOSURE_WEIGHTS,
            HABITAT_CONVERSION_WEIGHTS,
            VEGETATION_CONDITION_WEIGHTS,
            NATURE_QUALITY_ATTRIBUTION_WEIGHTS,
        ):
            known.update(weight_dict.keys())

        lib = load_library()
        violations: list[str] = []
        for indicator_id, card in lib.items():
            if not card.inputs:
                continue
            for input_id in card.inputs:
                if input_id not in known:
                    violations.append(
                        f"{indicator_id}: input {input_id!r} doesn't "
                        f"resolve to a known engine key"
                    )
        assert not violations, "\n".join(violations)

    def test_aggregate_payload_keys_match_engine_keys(self) -> None:
        """Canary: every payload_key in a derived aggregate's weights
        dict can be resolved as a key the engine actually emits.

        Builds on M-NATURE-KEYS's drift-prevention pattern. Component
        scores referenced in aggregate weights must exist in the
        library as derived entries (since component scores ARE the
        c5_drilldown payload keys). Drift would mean the library
        references a key no engine code emits.
        """
        lib = load_library()
        # Every component score referenced by an aggregate exists as a
        # derived entry in the library.
        for aggregate_id in (
            "air.audit_followup_priority",
            "ghg.audit_followup_priority",
            "nature.followup_priority",
        ):
            for term_key in lib[aggregate_id].weights:
                assert term_key in lib, (
                    f"{aggregate_id} references unknown term {term_key!r}"
                )
                assert lib[term_key].kind == "derived"

    def test_derived_indicator_ids_module_constant(self) -> None:
        """Pin the constant for direct importers (renderer, tests)."""
        from demo.indicator_library import DERIVED_INDICATOR_IDS
        assert len(DERIVED_INDICATOR_IDS) == 16
        assert "composite.overall_screening"   in DERIVED_INDICATOR_IDS
        assert "nature.biodiversity_exposure"  in DERIVED_INDICATOR_IDS
        assert "air.audit_followup_priority"   in DERIVED_INDICATOR_IDS

    def test_composite_lives_in_composite_pillar(self) -> None:
        """The composite card's pillar field is 'composite' — drives
        the 4th tab on P-09."""
        assert load_library()["composite.overall_screening"].pillar == "composite"
