"""M-VIIRS-REDESIGN-A1 VR8/VR9 — flaring catch-behaviour regression lock (live EE).

Locks the redesigned two-output VIIRS against regression:
  * VR8 — the Comodoro oil/gas region (patagonia_seed) fires `viirs_flaring`
          (intense-source detection the old grammar conflated away).
  * VR9 — the four quiet AOIs do NOT fire `viirs_flaring` (the Appalachia
          false-High of the old grammar must not recur).
Also checks tier separation (heavy > quiet), the discrimination the redesign restored.

EE-gated: skips when Earth Engine can't initialise. Loose floors (sign of behaviour,
not brittle point estimates) — reference run: analysis/m_viirs_redesign_a1_validation.csv.

    EE_PROJECT_ID=supply-chain-observatory python -m pytest \
        tests/test_m_viirs_redesign_regression.py -v
"""
from __future__ import annotations

import os

import pytest

WINDOW = ("2025-09-01", "2025-11-30")
RADIUS_KM = 10
COMODORO = (-45.8645, -67.4969)        # patagonia_seed — oil/gas flaring region
QUIET = {
    "patagonia_diag": (-51.00, -72.90),
    "nz_south": (-45.50, 170.00),
    "appalachia": (35.50, -82.50),
    "amazon_wet": (-4.00, -63.00),
}
NORILSK = (69.35, 88.20)               # heavy industrial reference


@pytest.fixture(scope="module")
def ee_ready():
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


def _flaring(lat, lon):
    import ee
    from engine.ghg import compute_viirs_two_output
    aoi = {"centre": {"lat": lat, "lon": lon}, "radius_km": RADIUS_KM}
    return compute_viirs_two_output(aoi, WINDOW, "screening", ee).get("ghg.viirs.score")


def test_vr8_comodoro_fires_flaring(ee_ready) -> None:
    # Reference run: 0.64. Loose floor — locks that the oil/gas region fires.
    assert _flaring(*COMODORO) >= 0.30


def test_vr9_quiet_sites_do_not_fire(ee_ready) -> None:
    # Reference run: all 0.0 (Sapezal 0.013). Lock the guard at < 0.05.
    for name, (lat, lon) in QUIET.items():
        val = _flaring(lat, lon) or 0.0
        assert val < 0.05, f"{name} flaring {val} ≥ 0.05 — quiet-site guard regressed"


def test_heavy_separates_from_quiet(ee_ready) -> None:
    # The discrimination the redesign restored: heavy ≫ quiet.
    assert (_flaring(*NORILSK) or 0.0) > 0.10
