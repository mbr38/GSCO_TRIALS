"""Unit tests for engine.nature.compute_regional_loss_evidence.

Added by M-V1x-RECONCILE per the spec's §5 step 15. Pins the three
behaviours from audit §9.3:

1. Flag = 1.0 when ring_loss_rate > 2× buffer_loss_rate.
2. Flag = 0.0 otherwise (buffer dominates, or rates are comparable).
3. Hansen window is fixed at the most recent HANSEN_LOOKBACK_YEARS years
   independent of the user's `time_range`.

These tests avoid EE entirely — the function's EE surface is faked at the
import-name level via monkeypatch, so the test exercises the logic that
divides loss-by-area and applies the ratio threshold.
"""

from __future__ import annotations

import pytest

from engine.constants import (
    HANSEN_LOOKBACK_YEARS,
    HANSEN_LOSS_RATIO_THRESHOLD,
)


_AOI = {"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 5.0}
_TIME_RANGE = ("2023-01-01", "2023-04-01")


# Synthetic geometry sentinels — site_buffer and background_ring return
# these instead of real ee.Geometry objects so the fake reduceRegion can
# tell them apart via id().
class _SiteGeom:
    def __init__(self, area_m2: float):
        self._area_m2 = area_m2
    def area(self, **_kw):
        return _GetInfo(self._area_m2)


class _RingGeom:
    def __init__(self, area_m2: float):
        self._area_m2 = area_m2
    def area(self, **_kw):
        return _GetInfo(self._area_m2)


class _GetInfo:
    """Implements ee.ComputedObject.getInfo() returning a pre-set value."""
    def __init__(self, value):
        self._value = value
    def getInfo(self):
        return self._value


class _FakeAreaImage:
    """Stands in for `area_image = loss_mask.multiply(ee.Image.pixelArea())`.

    Returns site-vs-ring loss m² based on which geometry is reduced over.
    Tracks all (geometry, scale) pairs the SUT calls reduceRegion with so
    tests can assert on the parameters used.
    """
    def __init__(self, site_id: int, ring_id: int,
                 site_loss_m2: float, ring_loss_m2: float):
        self._site_id = site_id
        self._ring_id = ring_id
        self._site_loss = site_loss_m2
        self._ring_loss = ring_loss_m2
        self.calls: list[dict] = []

    def reduceRegion(self, *, geometry, scale, reducer=None,
                     bestEffort=None, maxPixels=None):       # noqa: N803
        self.calls.append({
            "geometry_id": id(geometry),
            "scale": scale,
        })
        if id(geometry) == self._site_id:
            value = self._site_loss
        elif id(geometry) == self._ring_id:
            value = self._ring_loss
        else:
            value = 0.0
        return _GetInfo({"lossyear": value})


class _FakeImageBuilder:
    """Fake `ee.Image(asset_id).select("lossyear").gte(...).And(...).multiply(...)` chain."""
    def __init__(self, area_image: _FakeAreaImage):
        self._area_image = area_image
    def select(self, *_):
        return self
    def gte(self, *_):
        return self
    def And(self, *_):
        return self
    def lte(self, *_):
        return self
    def multiply(self, *_):
        return self._area_image


def _install_fakes(
    monkeypatch,
    *,
    site_area_ha: float,
    ring_area_m2: float,
    site_loss_m2: float,
    ring_loss_m2: float,
):
    """Monkeypatch every EE entry point the SUT uses, plus the buffer helpers."""
    site_geom = _SiteGeom(site_area_ha * 10_000.0)
    ring_geom = _RingGeom(ring_area_m2)

    monkeypatch.setattr(
        "engine.nature.site_buffer",
        lambda *_a, **_kw: site_geom,
    )
    monkeypatch.setattr(
        "engine.nature.background_ring",
        lambda *_a, **_kw: ring_geom,
    )
    # `_buffer_area_ha` reads from a pure-Python calculation, not EE; the
    # SUT uses its return value to compute site_area_m2. We override it
    # to match `site_area_ha` exactly so the rate math is predictable.
    monkeypatch.setattr(
        "engine.nature._buffer_area_ha",
        lambda _radius_km: site_area_ha,
    )

    area_image = _FakeAreaImage(
        site_id=id(site_geom),
        ring_id=id(ring_geom),
        site_loss_m2=site_loss_m2,
        ring_loss_m2=ring_loss_m2,
    )

    class _FakeImage:
        """Callable like `ee.Image(asset_id)` AND has staticmethod `pixelArea`."""
        def __new__(cls, *_a, **_kw):
            return _FakeImageBuilder(area_image)

        @staticmethod
        def pixelArea():    # noqa: N802
            return object()

    monkeypatch.setattr("engine.nature.ee.Image", _FakeImage)

    class _FakeReducer:
        @staticmethod
        def sum():
            return object()

    monkeypatch.setattr("engine.nature.ee.Reducer", _FakeReducer)
    # adaptive_scale_m takes a geometry; just return Hansen's native scale.
    monkeypatch.setattr(
        "engine.nature.adaptive_scale_m",
        lambda _geom, native_scale_m: native_scale_m,
    )

    return area_image


class TestRegionalLossEvidence:
    def test_returns_one_when_ring_loss_rate_exceeds_2x_buffer_rate(
        self, monkeypatch,
    ) -> None:
        # Site: 5 km buffer ≈ 7854 ha → ~78.54 million m². Loss: 1 ha = 10_000 m².
        # Ring: 500 million m² (~5x site area in m² makes for clean numbers).
        # Loss: 200 ha = 2_000_000 m².
        # buffer_rate = 10_000 / 78_540_000  ≈ 1.27e-4
        # ring_rate   = 2_000_000 / 500_000_000 = 4.0e-3
        # ratio       = ring_rate / buffer_rate ≈ 31.4 → >> 2.0 → flag = 1.0
        _install_fakes(
            monkeypatch,
            site_area_ha=7854.0,
            ring_area_m2=500_000_000.0,
            site_loss_m2=10_000.0,
            ring_loss_m2=2_000_000.0,
        )
        from engine.nature import compute_regional_loss_evidence
        out = compute_regional_loss_evidence(_AOI, _TIME_RANGE, ee_client=None)
        assert out["nature.external_driver_screening"] == 1.0
        prov = out["_provenance.nature.regional_loss_evidence"]
        assert prov["indicator_id"] == "nature.regional_loss_evidence"
        assert prov["temporal_mode"] == "standing_exposure"
        assert prov["data_type"] == "reference_dataset"
        # And the extras carry the per-rate diagnostics.
        assert prov["extra"]["ring_loss_rate_m2_per_m2"] > (
            HANSEN_LOSS_RATIO_THRESHOLD * prov["extra"]["buffer_loss_rate_m2_per_m2"]
        )

    def test_returns_zero_when_buffer_loss_rate_dominates(self, monkeypatch) -> None:
        # Buffer is losing aggressively; ring is quiet. Ring rate is < 2x buffer
        # rate, so no "external driver" — supplier owns the change.
        _install_fakes(
            monkeypatch,
            site_area_ha=7854.0,
            ring_area_m2=500_000_000.0,
            site_loss_m2=5_000_000.0,                       # 500 ha
            ring_loss_m2=5_000_000.0,                       # also 500 ha — ring rate is 1/buffer-rate × area ratio
        )
        from engine.nature import compute_regional_loss_evidence
        out = compute_regional_loss_evidence(_AOI, _TIME_RANGE, ee_client=None)
        assert out["nature.external_driver_screening"] == 0.0

    def test_returns_zero_when_both_rates_zero(self, monkeypatch) -> None:
        # No Hansen loss in either region — flag must be 0.0 (not NaN, not None).
        _install_fakes(
            monkeypatch,
            site_area_ha=7854.0,
            ring_area_m2=500_000_000.0,
            site_loss_m2=0.0,
            ring_loss_m2=0.0,
        )
        from engine.nature import compute_regional_loss_evidence
        out = compute_regional_loss_evidence(_AOI, _TIME_RANGE, ee_client=None)
        assert out["nature.external_driver_screening"] == 0.0

    def test_uses_fixed_five_year_lookback_independent_of_time_range(
        self, monkeypatch,
    ) -> None:
        # The Hansen window in provenance must be the fixed 5-year lookback,
        # NOT the user's time_range. Audit §9.3: Hansen's annual cadence
        # makes time_range slicing unreliable, so we use a standing window.
        area_image = _install_fakes(
            monkeypatch,
            site_area_ha=7854.0,
            ring_area_m2=500_000_000.0,
            site_loss_m2=10_000.0,
            ring_loss_m2=10_000.0,
        )

        from engine.nature import compute_regional_loss_evidence

        for tr in [
            ("2020-01-01", "2020-06-30"),
            ("2023-01-01", "2023-12-31"),
            ("2025-01-01", "2025-04-01"),
        ]:
            area_image.calls.clear()
            out = compute_regional_loss_evidence(_AOI, tr, ee_client=None)
            prov = out["_provenance.nature.regional_loss_evidence"]
            # time_range is the fixed Hansen window, not `tr`.
            assert prov["time_range"] != tr, (
                f"time_range should reflect fixed Hansen lookback, not the "
                f"user-supplied window {tr}"
            )
            # And the observations.count records HANSEN_LOOKBACK_YEARS.
            assert prov["observations"]["count"] == HANSEN_LOOKBACK_YEARS
            assert prov["observations"]["unit"] == "annual_rasters"
            # And both buffer + ring reductions happened.
            assert len(area_image.calls) == 2

    def test_provenance_carries_full_15_field_shape(self, monkeypatch) -> None:
        _install_fakes(
            monkeypatch,
            site_area_ha=7854.0,
            ring_area_m2=500_000_000.0,
            site_loss_m2=10_000.0,
            ring_loss_m2=10_000.0,
        )
        from engine.nature import compute_regional_loss_evidence
        out = compute_regional_loss_evidence(_AOI, _TIME_RANGE, ee_client=None)
        prov = out["_provenance.nature.regional_loss_evidence"]
        assert list(prov.keys()) == [
            "indicator_id",
            "asset_id", "band", "data_type", "data_source",
            "native_scale_m", "method_note", "time_range",
            "coverage_window", "skipped_reason", "observations",
            "column_to_surface_uncertainty", "temporal_mode",
            "sector_signal_anomaly", "extra",
        ]
