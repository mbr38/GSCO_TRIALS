"""Tests for the M-UI-A2 indicator-name info popover (fixture + loader).

Pure-Python — no Streamlit. Covers:

  - Fixture integrity: every in-scope indicator has the ``tooltip_summary``
    field present (text or null per HS12).
  - Exemplar copy integrity: 5 exemplars per spec §5 are present and
    follow the spec's two-sentence + word-budget + acronym constraints.
  - Loader: ``tooltip_summary_for`` returns the right value for
    populated / null / unknown ids.
  - Schema: ``IndicatorCardContent`` exposes the new field.

Render-time behaviour (popover trigger, dialog open, session-state
routing) is not asserted here — those touch Streamlit's render layer,
which the existing M-UI-E.* tests intentionally skip in favour of
in-browser verification.
"""

# M-UI-A2
from __future__ import annotations

import re

import pytest

from demo.indicator_library import (
    IndicatorCardContent,
    load_library,
    tooltip_summary_for,
)


# ---------------------------------------------------------------------------
# Spec scope — the 23 in-scope indicator ids per M-UI-A2_spec.md §2.1
# ---------------------------------------------------------------------------

# Family-level ids in the spec are stored at the library's canonical-id
# representative entry: each family has exactly one card in the library
# (e.g. nature.kba → nature.kba.proximity_score). Keys here are what the
# fixture actually uses; the family-level intent is preserved (one entry
# per family) per the M-V1x-RECONCILE pragmatic interpretation.

_IN_SCOPE_IDS: tuple[str, ...] = (
    # Composite + 3 pillar follow-up priorities
    "composite.overall_screening",
    "air.audit_followup_priority",
    "ghg.audit_followup_priority",
    "nature.followup_priority",
    # Air raw (9)
    "air.no2.score",
    "air.so2.score",
    "air.co.score",
    "air.hcho.score",
    "air.pm25.score",
    "air.pm10.score",
    "air.o3.score",
    "air.aai.score",
    "air.aod.score",
    # GHG raw (3)
    "ghg.ch4.score",
    "ghg.co2.score",
    "ghg.viirs.score",
    # Nature raw families (7) — one card per family
    "nature.kba.proximity_score",
    "nature.dw.trees_pct",
    "nature.habitat.natural_loss_ha",
    "nature.forest_loss.ha",
    "nature.ndvi.score",
    "nature.water.area_now_ha",
    "nature.recovery.score",
)

# Step G expansion — once the remaining 18 summaries land, the
# integrity tests below run against all 23 in-scope ids, not just the
# original five spec §5 exemplars.
_EXEMPLAR_IDS: tuple[str, ...] = _IN_SCOPE_IDS

# Plain Latin-uppercase acronyms (length ≥ 2) that may appear
# unexpanded in summaries. Spec §7.3 lists NDVI and KBA explicitly;
# the others all appear in canonical display names (the indicator name
# itself spells them out parenthetically, e.g. "Carbon Monoxide (CO)"),
# so they're "spelled out on first use" by construction. Sub-script
# acronyms (NO₂, SO₂, CH₄, CO₂, O₃, PM₂.₅, PM₁₀) don't trip the
# Latin-only regex so they don't need to be listed.
_PLAIN_LATIN_ACRONYM_WHITELIST: frozenset[str] = frozenset({
    "NDVI",  # spec §7.3
    "KBA",   # spec §7.3
    "CO",    # spec §7.3 (carbon monoxide)
    "HCHO",  # formaldehyde — display name is "Formaldehyde (HCHO)"
    "AAI",   # aerosol absorbing index — display name expands it
    "AOD",   # aerosol optical depth — display name expands it
    "VIIRS", # nightlights sensor — display name is "Nighttime Lights (VIIRS)"
})


# ---------------------------------------------------------------------------
# Spec §2.1 — 23 in-scope ids all present
# ---------------------------------------------------------------------------

def test_in_scope_ids_total_23_per_spec():
    """Sanity check on the test fixture itself: spec §2.1 says 23."""
    assert len(_IN_SCOPE_IDS) == 23


def test_every_in_scope_id_has_tooltip_summary_field():
    """Per HS12 the field must be present even when no copy is written —
    None is a valid value, missing is a content-coverage gap."""
    lib = load_library()
    for indicator_id in _IN_SCOPE_IDS:
        card = lib.get(indicator_id)
        assert card is not None, (
            f"{indicator_id!r} missing from library — expected as "
            f"an in-scope tooltip_summary host"
        )
        # tooltip_summary defaults to None on the dataclass — what we
        # really check is that load_library populates the attribute for
        # this id without raising on the manifest read.
        assert hasattr(card, "tooltip_summary")


# ---------------------------------------------------------------------------
# Spec §5 — exemplar copy is present, two sentences, within word budget
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("indicator_id", _EXEMPLAR_IDS)
def test_exemplar_has_non_null_summary(indicator_id: str):
    summary = tooltip_summary_for(indicator_id)
    assert summary is not None, (
        f"{indicator_id!r} listed in spec §5 exemplars but its "
        f"tooltip_summary is null — fixture drift"
    )
    assert summary.strip() != ""


@pytest.mark.parametrize("indicator_id", _EXEMPLAR_IDS)
def test_exemplar_body_is_two_sentences(indicator_id: str):
    """Two body sentences per HS4 and per the spec §5 exemplar form
    (``**Bolded Name.** Body sentence 1. Body sentence 2.``).

    The bolded lead-in is the indicator's plain-English name and its
    terminating full stop isn't counted as a sentence — the body that
    follows must contain exactly two sentence terminators.
    """
    summary = tooltip_summary_for(indicator_id)
    assert summary is not None
    # Drop the bolded lead-in title (``**...**``) so its terminator
    # doesn't inflate the body-sentence count.
    body = re.sub(r"^\*\*[^*]+\*\*\s*", "", summary)
    terminators = re.findall(r"[.!?](?:\s|$)", body)
    assert len(terminators) == 2, (
        f"{indicator_id!r} body has {len(terminators)} sentence "
        f"terminators; expected 2 per HS4. Body after stripping the "
        f"bolded lead-in: {body!r}"
    )


@pytest.mark.parametrize("indicator_id", _EXEMPLAR_IDS)
def test_exemplar_within_word_budget(indicator_id: str):
    """Spec §5 style targets ~25-50 words. We allow some headroom (20-60)
    so a single edit doesn't trip the test, but the order of magnitude is
    the contract."""
    summary = tooltip_summary_for(indicator_id)
    assert summary is not None
    stripped = summary.replace("**", "")
    word_count = len(stripped.split())
    assert 20 <= word_count <= 60, (
        f"{indicator_id!r} summary has {word_count} words; "
        f"spec §5 targets 25-50 (this test allows 20-60). "
        f"Summary: {summary!r}"
    )


@pytest.mark.parametrize("indicator_id", _EXEMPLAR_IDS)
def test_exemplar_acronyms_only_from_whitelist(indicator_id: str):
    """Per spec §7.3 the only acronyms that may appear unexpanded are
    the whitelist. Anything else needs to be spelled out on first use."""
    summary = tooltip_summary_for(indicator_id)
    assert summary is not None
    # Strip markdown bold + subscript-containing tokens like NO₂ so the
    # ALL-CAPS scan focuses on Latin-alphabet acronyms.
    stripped = summary.replace("**", "")
    # Capture standalone runs of 2+ Latin uppercase letters that are
    # word-boundary-isolated (not inside CamelCase). Includes a few
    # legitimate ones — the assertion is that any hit is whitelisted.
    candidates = re.findall(r"\b[A-Z]{2,}\b", stripped)
    for hit in candidates:
        assert hit in _PLAIN_LATIN_ACRONYM_WHITELIST, (
            f"{indicator_id!r} contains unwhitelisted acronym {hit!r}. "
            f"Spell it out on first use, or extend "
            f"_PLAIN_LATIN_ACRONYM_WHITELIST if it's well-known. "
            f"Summary: {summary!r}"
        )


# ---------------------------------------------------------------------------
# Loader — tooltip_summary_for() lookup behaviour
# ---------------------------------------------------------------------------

def test_tooltip_summary_for_returns_text_for_populated_exemplar():
    summary = tooltip_summary_for("air.no2.score")
    assert summary is not None
    assert "Nitrogen Dioxide" in summary


def test_tooltip_summary_for_returns_none_for_unknown_id():
    """Unknown indicator id returns None (same silent fallback). This
    is what the popover helper relies on to know not to render."""
    assert tooltip_summary_for("totally.fake.id") is None


def test_tooltip_summary_for_is_none_for_sub_aggregate():
    """Sub-aggregates like air.pollution_proxy_score are out of scope
    per spec §2.2 — the field isn't written at all on these entries,
    which surfaces through the loader as None (defaults from the
    dataclass init)."""
    assert tooltip_summary_for("air.pollution_proxy_score") is None


# ---------------------------------------------------------------------------
# Schema — IndicatorCardContent exposes the new field
# ---------------------------------------------------------------------------

def test_indicator_card_content_exposes_tooltip_summary():
    """Future-proofing: anyone who relies on the dataclass shape should
    see the field surface as an attribute. Defaults to None so existing
    construction sites don't need to pass it."""
    card = load_library()["air.no2.score"]
    assert isinstance(card, IndicatorCardContent)
    assert hasattr(card, "tooltip_summary")


def test_indicator_card_content_tooltip_summary_defaults_to_none():
    """Construct a card without passing tooltip_summary; field should
    default to None — important so the loader's _build_*_card sites can
    omit the kwarg without breaking dataclass construction."""
    card = IndicatorCardContent(
        indicator_id="test.x",
        pillar="test",
        sub_section="single_value",
        display_name="X",
        definition="x",
        decision_relevance="x",
        limitations="x",
        esg_alignment="x",
        asset_id="",
        native_scale_m=None,
        data_type="",
        data_source="",
        temporal_frequency="",
    )
    assert card.tooltip_summary is None
