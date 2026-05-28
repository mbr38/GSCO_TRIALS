"""Unit tests for engine.nature.compute_regional_loss_evidence.

Added by M-V1x-RECONCILE; reframed by M-ATTRIB-A1 (AT5). The indicator is
now **reference data**, not attribution. It emits a continuous ring-vs-buffer
loss-rate ratio (and a window label) instead of the old binary
``External_Driver_Screening`` sub-score. Pins:

1. `nature.regional_loss_evidence.ratio` = ring_loss_rate /
   max(buffer_loss_rate, 1e-9). >1 ⇒ the surrounding ring lost forest faster
   than the supplier buffer (broader regional pattern); <1 ⇒ the buffer was
   a relatively active deforestation pocket.
2. The raw boolean `regional_loss_evidence_raw` flag (1.0 when ring rate
   > HANSEN_LOSS_RATIO_THRESHOLD × buffer rate) is preserved in
   provenance.extra for the audit trail.
3. `nature.external_driver_screening` is no longer emitted, and
   provenance.extra no longer carries `confidence_terms` (not a confidence).
4. Hansen window is fixed at the most recent HANSEN_LOOKBACK_YEARS years
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
    # M-TIER-A3 Step B — background_ring returns a dict; nature.py extracts
    # `["geometry"]`. Wrap the sentinel ring geom in the dict shape so the
    # SUT's `ring = background_ring(...)["geometry"]` continues to receive
    # the area-bearing _RingGeom.
    monkeypatch.setattr(
        "engine.nature.background_ring",
        lambda *_a, **_kw: {
            "geometry": ring_geom,
            "mask": None,
            "land_fraction": 1.0,
            "land_mask_applied": True,
            "land_mask_asset": "MODIS/006/MOD44W",
        },
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
    def test_ratio_high_when_ring_outpaces_buffer(
        self, monkeypatch,
    ) -> None:
        # Site: 5 km buffer ≈ 7854 ha → ~78.54 million m². Loss: 1 ha = 10_000 m².
        # Ring: 500 million m² (~5x site area in m² makes for clean numbers).
        # Loss: 200 ha = 2_000_000 m².
        # buffer_rate = 10_000 / 78_540_000  ≈ 1.27e-4
        # ring_rate   = 2_000_000 / 500_000_000 = 4.0e-3
        # ratio       = ring_rate / buffer_rate ≈ 31.4 → >> 2.0 →
        #   regional_loss_evidence_raw = 1.0 (broader regional pattern).
        _install_fakes(
            monkeypatch,
            site_area_ha=7854.0,
            ring_area_m2=500_000_000.0,
            site_loss_m2=10_000.0,
            ring_loss_m2=2_000_000.0,
        )
        from engine.nature import compute_regional_loss_evidence
        out = compute_regional_loss_evidence(_AOI, _TIME_RANGE, ee_client=None)
        prov = out["_provenance.nature.regional_loss_evidence"]
        expected_ratio = (
            prov["extra"]["ring_loss_rate_m2_per_m2"]
            / prov["extra"]["buffer_loss_rate_m2_per_m2"]
        )
        # M-ATTRIB-A1 (AT5): continuous ratio output, no external_driver score.
        assert "nature.external_driver_screening" not in out
        assert out["nature.regional_loss_evidence.ratio"] == pytest.approx(expected_ratio)
        assert out["nature.regional_loss_evidence.ratio"] > 1.0
        assert prov["extra"]["ratio"] == pytest.approx(expected_ratio)
        # Raw evidence flag preserved in extra for the audit trail.
        assert prov["extra"]["regional_loss_evidence_raw"] == 1.0
        assert prov["indicator_id"] == "nature.regional_loss_evidence"
        assert prov["temporal_mode"] == "standing_exposure"
        assert prov["data_type"] == "reference_dataset"
        # M-ATTRIB-A1 (§7.3): confidence_terms removed — no longer a confidence.
        assert "confidence_terms" not in prov["extra"]
        assert prov["extra"]["ring_loss_rate_m2_per_m2"] > (
            HANSEN_LOSS_RATIO_THRESHOLD * prov["extra"]["buffer_loss_rate_m2_per_m2"]
        )

    def test_ratio_below_one_when_buffer_loss_rate_dominates(self, monkeypatch) -> None:
        # Buffer is losing aggressively; ring is comparatively quiet. Ring rate
        # is < buffer rate → ratio < 1 and raw flag 0.0 (buffer was an active
        # deforestation pocket).
        _install_fakes(
            monkeypatch,
            site_area_ha=7854.0,
            ring_area_m2=500_000_000.0,
            site_loss_m2=5_000_000.0,                       # 500 ha
            ring_loss_m2=5_000_000.0,                       # also 500 ha
        )
        from engine.nature import compute_regional_loss_evidence
        out = compute_regional_loss_evidence(_AOI, _TIME_RANGE, ee_client=None)
        assert out["nature.regional_loss_evidence.ratio"] < 1.0
        prov = out["_provenance.nature.regional_loss_evidence"]
        assert prov["extra"]["regional_loss_evidence_raw"] == 0.0

    def test_ratio_zero_when_both_rates_zero(self, monkeypatch) -> None:
        # No Hansen loss in either region — ratio = 0 / max(0, 1e-9) = 0.0,
        # raw evidence 0.0. No divide-by-zero.
        _install_fakes(
            monkeypatch,
            site_area_ha=7854.0,
            ring_area_m2=500_000_000.0,
            site_loss_m2=0.0,
            ring_loss_m2=0.0,
        )
        from engine.nature import compute_regional_loss_evidence
        out = compute_regional_loss_evidence(_AOI, _TIME_RANGE, ee_client=None)
        assert out["nature.regional_loss_evidence.ratio"] == 0.0
        prov = out["_provenance.nature.regional_loss_evidence"]
        assert prov["extra"]["regional_loss_evidence_raw"] == 0.0

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
            # M-ATTRIB-A1 (AT5/AT6): window label is a "YYYY–YYYY" string for
            # the Hansen-card context line, spanning HANSEN_LOOKBACK_YEARS.
            window = out["nature.regional_loss_evidence.window"]
            assert isinstance(window, str)
            start_yr, end_yr = (int(y) for y in window.split("–"))
            assert end_yr - start_yr + 1 == HANSEN_LOOKBACK_YEARS
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
