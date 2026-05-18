"""Real-Earth-Engine integration tests for the GHG pillar (Milestone 5.5).

These tests issue actual `ee.*` calls and therefore require:
  * EE auth on the machine (e.g. `earthengine authenticate` ran already).
  * `EE_PROJECT_ID` environment variable set to a project with EE API.
  * The ODIAC asset accessible at the configured path.

They're skipped unless `RUN_EE_TESTS=1` is set so the synthetic-payload
test suite stays fast and offline by default.

Pattern mirrors what tests/test_air_integration.py *will* become — Air's
real-EE tests are not yet written; M5.5 ships the first integration test
for the engine, exercising the ODIAC path.
"""

from __future__ import annotations

import os

import pytest

from engine.constants import CO2_TO_C_RATIO


# Module-level skip — all tests in this file are EE-touching.
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_EE_TESTS") != "1",
    reason="set RUN_EE_TESTS=1 (and EE_PROJECT_ID) to run real-EE tests",
)


# Ruhr Valley — a known dense-industrial corridor. Picked because we expect
# both a strong CO₂ total and a relative_intensity meaningfully above 1.
_RUHR_AOI = {"centre": {"lat": 51.4566, "lon": 7.0117}, "radius_km": 50}

# ODIAC coverage is 2020-2023; pick the most recent complete Q1 to give
# the snapshot a chance to find three monthly grids.
_TIME_RANGE = ("2023-01-01", "2023-04-01")


@pytest.fixture(scope="module")
def initialised_ee():
    """Initialise Earth Engine once per module run."""
    import ee
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        pytest.skip("EE_PROJECT_ID not set")
    ee.Initialize(project=project)
    yield ee


class TestCo2SnapshotIntegration:
    def test_compute_co2_snapshot_ruhr_valley(self, initialised_ee) -> None:
        from engine.ghg import compute_co2_snapshot

        result = compute_co2_snapshot(
            aoi=_RUHR_AOI,
            time_range=_TIME_RANGE,
            mode="screening",
            ee_client=None,
        )

        # Industrial corridor — total must be a positive emissions figure.
        assert result["ghg.co2.total"] > 0, (
            f"Ruhr Valley should show positive CO₂ total, "
            f"got {result['ghg.co2.total']!r}"
        )

        # relative_intensity is a positive float, capped at 10 by the
        # CARMA-overlap proxy. Industrial corridor → expect ≥ 1.
        rel = result["ghg.co2.relative_intensity"]
        assert rel is not None
        assert rel > 0
        assert rel <= 10.0   # CO₂ cap

        # Score is a valid 0-1 normalisation.
        score = result["ghg.co2.score"]
        assert score is not None
        assert 0.0 <= score <= 1.0

        # Provenance carries the audit-traceable conversion factor.
        # M5.6 — n_months → observations.count; c_to_co2_factor → extra.
        prov = result["_provenance.ghg.co2"]
        assert prov["asset_id"] == "projects/supply-chain-observatory/assets/odiac"
        assert prov["band"] == "b1"
        assert prov["extra"]["c_to_co2_factor"] == pytest.approx(CO2_TO_C_RATIO)
        # Q1 2023 expects 3 monthly grids.
        assert prov["observations"]["count"] == 3
        assert prov["observations"]["unit"] == "monthly_grids"
