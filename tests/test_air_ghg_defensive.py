"""Defensive empty-result tests for engine.air and engine.ghg (M-AIR-GHG-DEFENSIVE).

Mirrors the M-NATURE-DEFENSIVE pattern. When ``site_value`` (in
``engine.core.repeatable_core``) finds zero usable pixels in the site
buffer, it now raises ``SiteBufferNoDataError`` (a subclass of
``IndicatorComputeError``). Each pillar's ``run_pillar`` catches this
subclass before the generic handler and routes the indicator into the
canonical "skipped" shape with an asset-family-specific
``skipped_reason`` (no_s5p_pixels / no_cams_pixels / no_maiac_pixels /
no_viirs_pixels) — surfacing in C4b's failed-tile expander and the C9
banner instead of bubbling up as a hard ``_failures`` entry.

Tests stub ``engine.air.six_step`` / ``engine.ghg.six_step`` to raise
the relevant exception, then assert the run_pillar payload shape.
"""

# M-AIR-GHG-DEFENSIVE
from __future__ import annotations

import pytest

from engine.air import AIR_POLLUTANT_CONFIG
from engine.air import run_pillar as air_run_pillar
from engine.exceptions import (
    BackgroundRingNoDataError,
    IndicatorComputeError,
    SiteBufferNoDataError,
)
from engine.ghg import GHG_INDICATOR_CONFIG
from engine.ghg import run_pillar as ghg_run_pillar
from ui.components.c4b_kpi_grid import _SKIPPED_REASON_TRANSLATIONS
from ui.components.c9_partial_banner import _SKIPPED_REASON_PROSE


# Large enough to clear every pillar's pixel-size guard so the
# parametrized tests can share a single AOI.
_AOI = {"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 50}
_TIME_RANGE = ("2026-02-19", "2026-05-20")


class _FakeIC:
    """Chain-friendly stand-in for ee.ImageCollection — mirrors test_air."""

    def map(self, _fn): return self
    def select(self, _band): return self
    def filterDate(self, *_a, **_kw): return self


@pytest.fixture
def fake_ee_air(monkeypatch):
    """Stub ee.ImageCollection in engine.air so building the IC doesn't
    require a live EE connection."""
    monkeypatch.setattr(
        "engine.air.ee.ImageCollection",
        lambda *_a, **_kw: _FakeIC(),
    )


@pytest.fixture
def fake_ee_ghg(monkeypatch):
    """Stub ee.ImageCollection in engine.ghg for the same reason."""
    monkeypatch.setattr(
        "engine.ghg.ee.ImageCollection",
        lambda *_a, **_kw: _FakeIC(),
    )


# ---------------------------------------------------------------------------
# Per-pollutant config — skipped_reason_no_data field
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pollutant,expected_reason", [
    ("no2",  "no_s5p_pixels"),
    ("so2",  "no_s5p_pixels"),
    ("co",   "no_s5p_pixels"),
    ("hcho", "no_s5p_pixels"),
    ("o3",   "no_s5p_pixels"),
    ("aai",  "no_s5p_pixels"),
    ("pm25", "no_cams_pixels"),
    ("pm10", "no_cams_pixels"),
    ("aod",  "no_maiac_pixels"),
])
def test_air_pollutant_carries_expected_skipped_reason(pollutant, expected_reason):
    """Each pollutant's config carries the right asset-family code."""
    cfg = AIR_POLLUTANT_CONFIG[pollutant]
    assert cfg.skipped_reason_no_data == expected_reason


@pytest.mark.parametrize("indicator,expected_reason", [
    ("ch4",   "no_s5p_pixels"),
    ("viirs", "no_viirs_pixels"),
    ("co2",   "no_odiac_pixels"),
])
def test_ghg_indicator_carries_expected_skipped_reason(indicator, expected_reason):
    cfg = GHG_INDICATOR_CONFIG[indicator]
    assert cfg.skipped_reason_no_data == expected_reason


# ---------------------------------------------------------------------------
# Air run_pillar — SiteBufferNoDataError routes to skipped payload
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pollutant,expected_reason", [
    ("no2",  "no_s5p_pixels"),
    ("pm25", "no_cams_pixels"),
    ("aod",  "no_maiac_pixels"),
])
def test_air_site_empty_emits_skipped_payload(
    monkeypatch, fake_ee_air, pollutant, expected_reason,
):
    """When six_step raises SiteBufferNoDataError for a pollutant,
    run_pillar emits a skipped payload with the asset-family code and
    does NOT register a `_failures` entry.
    """
    def _raise(**_kw):
        raise SiteBufferNoDataError(
            indicator_id=f"air.{pollutant}",
            reason="site buffer has no valid pixels (5 observations…)",
        )
    monkeypatch.setattr("engine.air.six_step", _raise)

    selected = {f"air.{pollutant}.score"}
    payload = air_run_pillar(
        aoi=_AOI,
        time_range=_TIME_RANGE,
        mode="screening",
        selected_indicators=selected,
        ee_client=None,
    )

    # No `_failures` — silent-skip is a coverage statement, not a failure.
    assert "_failures" not in payload
    # Every measurement ID is None.
    assert payload[f"air.{pollutant}.score"]      is None
    assert payload[f"air.{pollutant}.site"]       is None
    assert payload[f"air.{pollutant}.confidence"] is None
    # Provenance carries the expected asset-family code.
    prov = payload[f"_provenance.air.{pollutant}"]
    assert prov["skipped_reason"] == expected_reason


def test_air_buffer_too_small_still_goes_to_failures(monkeypatch, fake_ee_air):
    """Pixel-size pre-check still raises plain IndicatorComputeError →
    routed into ``_failures``, NOT a skipped payload. That's a user-input
    issue (buffer < native pixel), not a coverage statement.

    A 5 km buffer is smaller than CAMS's 44.5 km native pixel, so PM25
    trips the pre-check before six_step is even called. NO₂ is included
    so the pillar doesn't trip the all-failed PillarComputeError.
    """
    small_aoi = {"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 5}
    happy_six_step = {
        "site": 100.0, "background": 50.0, "anomaly": 50.0, "z": 5.0,
        "hf": 0.4, "trend": None, "trend_p": None, "confidence": 0.7,
        "score": 0.6,
    }
    monkeypatch.setattr("engine.air.six_step", lambda **_kw: happy_six_step)

    selected = {"air.no2.score", "air.pm25.score"}
    payload = air_run_pillar(
        aoi=small_aoi,
        time_range=_TIME_RANGE,
        mode="screening",
        selected_indicators=selected,
        ee_client=None,
    )
    # _failures has the PM25 entry — this is a real failure, not a skip.
    assert "_failures" in payload
    assert any(f["indicator_id"] == "air.pm25" for f in payload["_failures"])
    # Provenance is NOT present (only emitted by the skipped path).
    assert "_provenance.air.pm25" not in payload
    # NO₂ still computes normally — proves only PM25 was routed to failures.
    assert payload["air.no2.score"] == 0.6


def test_air_ring_empty_still_routes_to_background_ring_skip(
    monkeypatch, fake_ee_air,
):
    """Regression — M-OCEAN-RING's BackgroundRingNoDataError path is
    distinct from the new site-empty path: ring-empty still emits
    skipped_reason=background_ring_no_data (NOT the asset-family code).
    """
    def _raise(**_kw):
        raise BackgroundRingNoDataError(
            indicator_id="air.no2",
            reason="background ring has no valid pixels…",
        )
    monkeypatch.setattr("engine.air.six_step", _raise)

    selected = {"air.no2.score"}
    payload = air_run_pillar(
        aoi=_AOI,
        time_range=_TIME_RANGE,
        mode="screening",
        selected_indicators=selected,
        ee_client=None,
    )
    assert payload["_provenance.air.no2"]["skipped_reason"] == \
        "background_ring_no_data"
    assert "_failures" not in payload


def test_air_mixed_selection_per_indicator_dispatch(monkeypatch, fake_ee_air):
    """Mixed case — NO₂ produces data; SO₂ trips site-empty; CO trips
    ring-empty. The per-indicator dispatch routes each correctly."""
    default_six_step = {
        "site": 100.0, "background": 50.0, "anomaly": 50.0, "z": 5.0,
        "hf": 0.4, "trend": None, "trend_p": None, "confidence": 0.7,
        "score": 0.6,
    }

    def _dispatch(**kw):
        band = kw["band"]
        if band == "NO2_column_number_density":
            return dict(default_six_step)
        if band == "SO2_column_number_density":
            raise SiteBufferNoDataError(
                indicator_id="air.so2",
                reason="site buffer has no valid pixels",
            )
        if band == "CO_column_number_density":
            raise BackgroundRingNoDataError(
                indicator_id="air.co",
                reason="background ring empty",
            )
        return dict(default_six_step)

    monkeypatch.setattr("engine.air.six_step", _dispatch)

    selected = {"air.no2.score", "air.so2.score", "air.co.score"}
    payload = air_run_pillar(
        aoi=_AOI,
        time_range=_TIME_RANGE,
        mode="screening",
        selected_indicators=selected,
        ee_client=None,
    )
    assert payload["air.no2.score"] == 0.6
    assert payload["air.so2.score"] is None
    assert payload["_provenance.air.so2"]["skipped_reason"] == "no_s5p_pixels"
    assert payload["air.co.score"] is None
    assert payload["_provenance.air.co"]["skipped_reason"] == \
        "background_ring_no_data"
    assert "_failures" not in payload


def test_air_all_pollutants_site_empty_does_not_raise_pillar_error(
    monkeypatch, fake_ee_air,
):
    """Acre scenario — every selected pollutant trips site-empty.
    Skipped indicators are not failures, so PillarComputeError does NOT
    fire. The payload comes back populated with None scores."""
    def _raise(**kw):
        raise SiteBufferNoDataError(
            indicator_id=f"air.{kw.get('band', 'unknown')}",
            reason="site buffer has no valid pixels",
        )
    monkeypatch.setattr("engine.air.six_step", _raise)

    selected = {
        "air.no2.score", "air.so2.score", "air.co.score",
        "air.hcho.score", "air.o3.score", "air.aai.score",
    }
    # No exception — confirms silent-skip semantics.
    payload = air_run_pillar(
        aoi=_AOI,
        time_range=_TIME_RANGE,
        mode="screening",
        selected_indicators=selected,
        ee_client=None,
    )
    assert payload["air.no2.score"]               is None
    assert payload["air.pollution_proxy_score"]   is None
    assert payload["air.audit_followup_priority"] is None
    assert "_failures" not in payload


# ---------------------------------------------------------------------------
# GHG run_pillar — same dispatch for CH₄ / VIIRS
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("indicator,expected_reason", [
    ("ch4",   "no_s5p_pixels"),
    ("viirs", "no_viirs_pixels"),
])
def test_ghg_site_empty_emits_skipped_payload(
    monkeypatch, fake_ee_ghg, indicator, expected_reason,
):
    def _raise(*_a, **_kw):
        raise SiteBufferNoDataError(
            indicator_id=f"ghg.{indicator}",
            reason="site buffer has no valid pixels",
        )
    # M-GHG-REDESIGN-A1 — VIIRS no longer routes through six_step; its empty-
    # data skip is raised from compute_viirs_two_output itself. CH₄
    # still uses the six_step path. Both surface SiteBufferNoDataError, which
    # the dispatcher maps to the indicator's skipped_reason_no_data code.
    if indicator == "viirs":
        monkeypatch.setattr("engine.ghg.compute_viirs_two_output", _raise)
    else:
        monkeypatch.setattr("engine.ghg.six_step", _raise)

    selected = {f"ghg.{indicator}.score"}
    payload = ghg_run_pillar(
        aoi=_AOI,
        time_range=_TIME_RANGE,
        mode="screening",
        selected_indicators=selected,
        ee_client=None,
    )
    assert "_failures" not in payload
    assert payload[f"ghg.{indicator}.score"] is None
    assert payload[f"_provenance.ghg.{indicator}"]["skipped_reason"] == \
        expected_reason


# ---------------------------------------------------------------------------
# Prose translations exist for every new code
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code", [
    "no_s5p_pixels",
    "no_cams_pixels",
    "no_maiac_pixels",
    "no_viirs_pixels",
])
def test_new_skipped_reason_codes_have_c4b_translation(code):
    """Every new code has a user-facing prose translation in C4b."""
    assert code in _SKIPPED_REASON_TRANSLATIONS
    assert len(_SKIPPED_REASON_TRANSLATIONS[code]) > 20  # non-trivial prose


@pytest.mark.parametrize("code", [
    "no_s5p_pixels",
    "no_cams_pixels",
    "no_maiac_pixels",
    "no_viirs_pixels",
])
def test_new_skipped_reason_codes_have_c9_translation(code):
    """C4b ↔ C9 lock-step: every new code is also in the partial banner."""
    assert code in _SKIPPED_REASON_PROSE
    assert len(_SKIPPED_REASON_PROSE[code]) > 20


def test_c4b_and_c9_prose_dicts_carry_identical_air_ghg_codes():
    """Lock-step invariant: every M-AIR-GHG-DEFENSIVE code in C4b is
    also in C9 (and vice versa). Stops the two dicts from drifting."""
    air_ghg_codes = {
        "no_s5p_pixels", "no_cams_pixels", "no_maiac_pixels", "no_viirs_pixels",
    }
    for code in air_ghg_codes:
        assert (code in _SKIPPED_REASON_TRANSLATIONS) == \
               (code in _SKIPPED_REASON_PROSE), \
               f"{code} drift between C4b and C9 dicts"


# ---------------------------------------------------------------------------
# Happy-path regression — site_value still works when the buffer has data
# ---------------------------------------------------------------------------

def test_air_happy_path_unchanged(monkeypatch, fake_ee_air):
    """When six_step returns a normal result, the payload reads as before
    M-AIR-GHG-DEFENSIVE — no skipped-result shape, real score values."""
    happy_six_step = {
        "site": 100.0, "background": 50.0, "anomaly": 50.0, "z": 5.0,
        "hf": 0.4, "trend": None, "trend_p": None, "confidence": 0.7,
        "score": 0.6,
    }
    monkeypatch.setattr("engine.air.six_step", lambda **_kw: happy_six_step)

    selected = {"air.no2.score"}
    payload = air_run_pillar(
        aoi=_AOI,
        time_range=_TIME_RANGE,
        mode="screening",
        selected_indicators=selected,
        ee_client=None,
    )
    assert payload["air.no2.score"] == 0.6
    assert payload["air.no2.site"]  == 100.0
    # Provenance is present but has NO skipped_reason on the happy path.
    prov = payload["_provenance.air.no2"]
    assert prov.get("skipped_reason") is None
