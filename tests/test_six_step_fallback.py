"""Integration tests for the fallback machinery inside `six_step`
(M-FALLBACK-A1 §7.1–§7.3).

These exercise the §4.5 composition decision table end-to-end through
`engine.core.repeatable_core.six_step`, with Earth Engine stubbed at the
module level. A `_SpyIc` records the date window each reduction runs over,
so the stub `site_value` / `background_value` can fail the current window
and succeed (or fail) the SPPY / sliding window — precisely modelling
cloudy-period recovery.

No live EE. The confidence-multiplier arithmetic itself is pinned in
test_fallback.py; here we verify the provenance flags, which window the
value came from, and that recovery keeps confidence non-None.
"""

from __future__ import annotations

import pytest

from engine.core import repeatable_core as rc
from engine.core.fallback import FallbackContext, sppy_window
from engine.exceptions import BackgroundRingNoDataError, SiteBufferNoDataError


_AOI = {"centre": {"lat": -13.5, "lon": -58.8}, "radius_km": 50}
_TR = ("2026-03-01", "2026-05-30")
_SPPY = sppy_window(_TR)  # ("2025-03-01", "2025-05-30")

_BRAZIL_FIXTURE = {
    "_meta": {"vintage": "2026"},
    "countries": {"Brazil": {
        "air.no2": {"median": 38.0, "std": 26.0},
        "nature.ndvi": {"median": 0.6, "std": 0.1},  # present but ndvi is out-of-scope
    }},
}


class _EnvelopeSentinel:
    def bounds(self):
        return self


class _SpyIc:
    """ImageCollection stand-in that remembers the filterDate window."""

    def __init__(self, window=None):
        self.window = window

    def filterDate(self, start, end):
        return _SpyIc((start, end))

    def filterBounds(self, _geom):
        return self


def _wire(
    monkeypatch,
    *,
    site_fail_windows=frozenset(),
    ring_fail_windows=frozenset(),
    ring_land_fraction=0.7,
    country="Brazil",
):
    """Stub the EE surface six_step touches. `*_fail_windows` are the date
    windows for which the site / ring reduction raises (zero pixels)."""
    monkeypatch.setattr(rc, "site_buffer", lambda c, r: _EnvelopeSentinel())

    ring = {
        "geometry": object(),
        "mask": object(),
        "land_fraction": ring_land_fraction,
        "land_mask_applied": True,
        "land_mask_asset": "MODIS/006/MOD44W",
    }
    monkeypatch.setattr(rc, "background_ring", lambda centre, radius_km: ring)

    def _site_value(aoi, ic, band, scale=None):
        if ic.window in site_fail_windows:
            raise SiteBufferNoDataError(indicator_id=band, reason="no pixels")
        return 100.0
    monkeypatch.setattr(rc, "site_value", _site_value)

    def _background_value(aoi, ic, band, seasonal, scale, *, ring):
        if ic.window in ring_fail_windows:
            raise BackgroundRingNoDataError(indicator_id=band, reason="no pixels")
        return (50.0, 10.0)
    monkeypatch.setattr(rc, "background_value", _background_value)

    monkeypatch.setattr(
        rc, "_server_side_hf",
        lambda *a, **kw: rc.ServerSideHfResult(5, 0.4, 100),
    )
    monkeypatch.setattr(rc, "country_for_centroid", lambda lat, lon: country)


def _six_step(indicator_id="air.no2", **ctx_kwargs):
    fixture = ctx_kwargs.pop("fixture", _BRAZIL_FIXTURE)
    strict = ctx_kwargs.pop("strict", False)
    strategy = ctx_kwargs.pop("strategy", "sppy")
    ctx = FallbackContext(
        strict_audit_mode=strict,
        temporal_fallback_strategy=strategy,
        climatology_fixture=fixture,
    )
    return rc.six_step(
        aoi=_AOI,
        image_collection=_SpyIc(),
        band="some_band",
        time_range=_TR,
        ee_client=None,
        indicator_id=indicator_id,
        fallback=ctx,
    )


# ---------------------------------------------------------------------------
# No-op / aoi_scale_class always emitted
# ---------------------------------------------------------------------------

def test_no_fallback_context_emits_scale_class_only(monkeypatch) -> None:
    _wire(monkeypatch)
    out = rc.six_step(
        aoi=_AOI, image_collection=_SpyIc(), band="b", time_range=_TR,
        ee_client=None, indicator_id="air.no2", fallback=None,
    )
    extra = out["fallback_extra"]
    assert extra["aoi_scale_class"] == "regional"  # 50 km
    assert extra["temporal_fallback_used"] is False
    assert extra["climatology_fallback_used"] is False
    assert out["site"] == 100.0 and out["background"] == 50.0


# ---------------------------------------------------------------------------
# Mode A — site fails, SPPY recovers it
# ---------------------------------------------------------------------------

def test_mode_a_sppy_recovers_site(monkeypatch) -> None:
    _wire(monkeypatch, site_fail_windows={_TR})  # current site empty, SPPY ok
    out = _six_step()
    assert out["site"] == 100.0          # recovered from SPPY window
    assert out["background"] == 50.0     # current ring still used
    extra = out["fallback_extra"]
    assert extra["temporal_fallback_used"] is True
    assert extra["temporal_fallback_strategy"] == "sppy"
    assert extra["temporal_fallback_source_window"] == f"{_SPPY[0]}/{_SPPY[1]}"
    assert extra["climatology_fallback_used"] is False
    # Confidence stays non-None — N_valid was drawn from the SPPY window
    # (where data exists), not the empty current window.
    assert out["confidence"] is not None


def test_mode_a_sppy_also_empty_raises(monkeypatch) -> None:
    # Both current and SPPY site empty → indicator genuinely fails.
    _wire(monkeypatch, site_fail_windows={_TR, _SPPY})
    with pytest.raises(SiteBufferNoDataError):
        _six_step()


# ---------------------------------------------------------------------------
# Mode B — background fails, climatology auto-applies
# ---------------------------------------------------------------------------

def test_mode_b_climatology_substitutes_background(monkeypatch) -> None:
    _wire(monkeypatch, ring_fail_windows={_TR})  # current ring empty; site fine
    out = _six_step()
    assert out["site"] == 100.0
    assert out["background"] == 38.0     # climatology median for Brazil/no2
    extra = out["fallback_extra"]
    assert extra["climatology_fallback_used"] is True
    assert extra["climatology_fallback_vintage"] == "2026"
    assert extra["temporal_fallback_used"] is False
    # z uses the climatology median + std: (100 - 38) / 26.
    assert out["z"] == pytest.approx((100.0 - 38.0) / 26.0)


def test_mode_b_no_country_raises(monkeypatch) -> None:
    # Ring fails and the centroid can't be resolved → no climatology → fail.
    _wire(monkeypatch, ring_fail_windows={_TR}, country=None)
    with pytest.raises(BackgroundRingNoDataError):
        _six_step()


def test_out_of_scope_indicator_gets_no_climatology(monkeypatch) -> None:
    # nature.ndvi is SPPY-eligible but OUT of climatology scope (FB10):
    # a ring failure must NOT be papered over with a climatology baseline.
    _wire(monkeypatch, ring_fail_windows={_TR})
    with pytest.raises(BackgroundRingNoDataError):
        _six_step(indicator_id="nature.ndvi")


# ---------------------------------------------------------------------------
# Mode 1 — water ring fires climatology directly (no SPPY for the ring)
# ---------------------------------------------------------------------------

def test_mode_1_water_ring_uses_climatology(monkeypatch) -> None:
    # land_fraction below the mask threshold → structurally water.
    _wire(monkeypatch, ring_land_fraction=0.0)
    out = _six_step()
    assert out["site"] == 100.0
    assert out["background"] == 38.0
    extra = out["fallback_extra"]
    assert extra["climatology_fallback_used"] is True
    assert extra["temporal_fallback_used"] is False


# ---------------------------------------------------------------------------
# Mode C — both fail
# ---------------------------------------------------------------------------

def test_mode_c_sppy_recovers_both(monkeypatch) -> None:
    # Current site + ring empty; SPPY recovers both → temporal only.
    _wire(monkeypatch, site_fail_windows={_TR}, ring_fail_windows={_TR})
    out = _six_step()
    assert out["site"] == 100.0
    assert out["background"] == 50.0     # SPPY ring, not climatology
    extra = out["fallback_extra"]
    assert extra["temporal_fallback_used"] is True
    assert extra["climatology_fallback_used"] is False


def test_mode_c_sppy_site_then_climatology_ring(monkeypatch) -> None:
    # Site recovers via SPPY; ring empty in BOTH current and SPPY → climatology.
    _wire(
        monkeypatch,
        site_fail_windows={_TR},
        ring_fail_windows={_TR, _SPPY},
    )
    out = _six_step()
    assert out["site"] == 100.0
    assert out["background"] == 38.0     # climatology
    extra = out["fallback_extra"]
    assert extra["temporal_fallback_used"] is True
    assert extra["climatology_fallback_used"] is True  # compound 0.45


# ---------------------------------------------------------------------------
# Strict audit mode disables both fallbacks (FB16)
# ---------------------------------------------------------------------------

def test_strict_audit_mode_disables_fallbacks(monkeypatch) -> None:
    _wire(monkeypatch, site_fail_windows={_TR})  # SPPY would recover, but…
    with pytest.raises(SiteBufferNoDataError):
        _six_step(strict=True)


# ---------------------------------------------------------------------------
# Sliding-lookback strategy (single-supplier retry, FB5)
# ---------------------------------------------------------------------------

def test_sliding_lookback_recovers_on_second_window(monkeypatch) -> None:
    from engine.core.fallback import sliding_lookback_windows

    windows = sliding_lookback_windows(_TR)
    # Current + first lookback empty; second lookback has coverage.
    fail = {_TR, windows[0]}
    _wire(monkeypatch, site_fail_windows=fail)
    out = _six_step(strategy="sliding_lookback")
    extra = out["fallback_extra"]
    assert extra["temporal_fallback_used"] is True
    assert extra["temporal_fallback_strategy"] == "sliding_lookback"
    assert extra["temporal_fallback_source_window"] == f"{windows[1][0]}/{windows[1][1]}"
