"""M-DIAG-A4 DGC12 — catch-behaviour regression lock (live Earth Engine).

Locks the post-fix detector's behaviour against future regression: at the
strongest validation event (Quebec 2023 wildfire smoke) the AAI per-day
detector must still surface a clear set of hot days, AND it must separate the
event from a re-selected clean control (Patagonia) — the discrimination the
denominator fix restored.

EE-gated: skips cleanly when Earth Engine can't initialise (no creds / offline),
so the default suite stays hermetic. Run with credentials to exercise the lock:

    EE_PROJECT_ID=supply-chain-observatory python -m pytest \
        tests/test_m_diag_a4_regression_event.py -v

Numbers are loose floors, not the probe's exact values — the lock guards the
*sign* of the behaviour (event catches; event ≫ control), not a brittle point
estimate. See analysis/m_diag_a4_validation_probe.json for the reference run.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="module")
def ee_ready():
    """Initialise EE or skip the whole module."""
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        pytest.skip("EE_PROJECT_ID not set — live regression lock skipped")
    try:
        import ee
        ee.Initialize(project=project)
        ee.Number(1).getInfo()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Earth Engine unavailable — {type(exc).__name__}: {exc}")
    return True


def _aai(aoi, window):
    from engine.air import compute_pollutant_snapshot
    snap = compute_pollutant_snapshot(aoi, "aai", window, "screening", None)
    hf = snap.get("air.aai.hf")
    prov = snap.get("_provenance.air.aai", {}) or {}
    extra = prov.get("extra", {}) or {}
    n_valid = extra.get("n_valid_dates") or 0
    n_hot = round((hf or 0.0) * n_valid)
    return {
        "hf": hf,
        "n_valid": n_valid,
        "n_hot": n_hot,
        "clim_applied": extra.get("clim_baseline_applied"),
        "bg_std_spatial": extra.get("bg_std_spatial"),
        "bg_std_temporal": extra.get("bg_std_temporal"),
    }


# Reference AOIs/windows — mirror analysis/m_diag_a4_validation_probe.py.
_QUEBEC_EVENT = (
    {"centre": {"lat": 52.0, "lon": -72.0}, "radius_km": 25},
    ("2023-06-01", "2023-07-15"),
)
_PATAGONIA_CONTROL = (
    {"centre": {"lat": -45.864, "lon": -67.496}, "radius_km": 10},
    ("2023-06-01", "2023-09-01"),
)


def test_quebec_event_catches_hot_days(ee_ready):
    """DGC12 — AAI surfaces ≥ 4 hot days at the Quebec 2023 wildfire event."""
    event = _aai(*_QUEBEC_EVENT)
    assert event["clim_applied"] is True, "temporal denominator must be applied"
    assert event["n_hot"] >= 4, f"event under-caught: {event}"


def test_event_separates_from_clean_control(ee_ready):
    """The denominator fix restored event/control hf separation."""
    event = _aai(*_QUEBEC_EVENT)
    control = _aai(*_PATAGONIA_CONTROL)
    # Clean control fires rarely now (pre-fix median control hf was 0.33).
    assert (control["hf"] or 0.0) < 0.15, f"control over-fires: {control}"
    # Event hot-fraction clearly exceeds the control's.
    assert (event["hf"] or 0.0) > (control["hf"] or 0.0), (
        f"no separation: event={event} control={control}"
    )


def test_temporal_denominator_corrects_spatial_collapse(ee_ready):
    """The new denominator is materially larger than the collapsed spatial std
    at the clean control (the M-DIAG-A3 §4 ratio is > 1, not ~1)."""
    control = _aai(*_PATAGONIA_CONTROL)
    spatial = control["bg_std_spatial"]
    temporal = control["bg_std_temporal"]
    assert spatial and temporal
    assert temporal / spatial > 2.0, (
        f"spatial collapse not corrected: spatial={spatial} temporal={temporal}"
    )
