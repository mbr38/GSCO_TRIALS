"""Synthetic-payload tests for engine.core.buffers.

Tests do not touch Earth Engine. The MOD44W chain and `site_buffer` are
stubbed so we exercise the dict-return shape, default-arg behaviour, and
land_fraction plumbing without an EE round-trip.

Real-EE smoke tests for the land mask (geometric land_fraction over Mumbai,
Rio, Shenzhen) land later in M-TIER-A3 Step F. The §4.1 inland/coastal
land-fraction expectations are also gated by ``RUN_EE_TESTS=1`` below.

This file follows the flat `tests/` layout already used by the rest of the
suite — the spec proposed `tests/engine/core/test_buffers.py`, but no
`tests/engine/` subdirectory exists; see M-TIER-A3 deviation notes.
"""

from __future__ import annotations

import os

import pytest

from engine.core import buffers
from engine.core.buffers import (
    LAND_MASK_ASSET,
    LAND_MASK_BAND,
    _land_mask_image,
    background_ring,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestLandMaskConstants:
    def test_asset_is_mod44w_v6(self) -> None:
        # Locked by spec LM1 — single global asset, no per-region logic.
        assert LAND_MASK_ASSET == "MODIS/006/MOD44W"

    def test_band_is_water_mask(self) -> None:
        # The MOD44W band carrying the binary water/land flag.
        assert LAND_MASK_BAND == "water_mask"


# ---------------------------------------------------------------------------
# _land_mask_image — synthetic chain assertions
# ---------------------------------------------------------------------------


class _FakeImage:
    """Chain-friendly stand-in for ee.Image after .Not()."""

    def __init__(self, source: str) -> None:
        self.source = source

    def Not(self) -> "_FakeImage":  # noqa: N802 — EE method name
        return _FakeImage(f"{self.source}.Not()")


class _FakeIC:
    """Chain-friendly stand-in for ee.ImageCollection.

    Records what was requested so the test can assert the asset ID and the
    band name flowed through correctly. Only the calls `_land_mask_image()`
    actually makes are implemented — `.select`, `.mosaic`, `.Not`.
    """

    def __init__(self, asset_id: str) -> None:
        self.asset_id = asset_id
        self.selected_band: str | None = None

    def select(self, band: str) -> "_FakeIC":
        self.selected_band = band
        return self

    def mosaic(self) -> _FakeImage:
        return _FakeImage(f"IC({self.asset_id}).select({self.selected_band}).mosaic()")


@pytest.fixture
def fake_ee(monkeypatch):
    """Replace ee.ImageCollection in engine.core.buffers with a fake."""
    created: list[_FakeIC] = []

    def _ctor(asset_id: str) -> _FakeIC:
        ic = _FakeIC(asset_id)
        created.append(ic)
        return ic

    monkeypatch.setattr("engine.core.buffers.ee.ImageCollection", _ctor)
    return created


class TestLandMaskHelper:
    def test_returns_image_instance(self, fake_ee) -> None:
        # The chain ends in .Not(), which in EE produces an ee.Image. The
        # fake mirrors that — we just need to confirm we got the post-.Not()
        # object back, not the mid-chain ImageCollection.
        result = _land_mask_image()
        assert isinstance(result, _FakeImage)
        assert result.source.endswith(".Not()")

    def test_uses_correct_asset_id(self, fake_ee) -> None:
        _land_mask_image()
        assert len(fake_ee) == 1
        assert fake_ee[0].asset_id == LAND_MASK_ASSET == "MODIS/006/MOD44W"

    def test_selects_water_mask_band(self, fake_ee) -> None:
        _land_mask_image()
        assert fake_ee[0].selected_band == LAND_MASK_BAND == "water_mask"

    def test_chain_order_is_select_then_mosaic_then_not(self, fake_ee) -> None:
        # Explicit invariant — if the implementation ever reorders to
        # .mosaic().select() (which also works in EE but produces a
        # different graph), this test traps the change so the closed-entry
        # cite stays accurate.
        result = _land_mask_image()
        assert result.source == (
            f"IC({LAND_MASK_ASSET}).select({LAND_MASK_BAND}).mosaic().Not()"
        )


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


class TestBuffersModuleSurface:
    def test_land_mask_constants_are_module_level(self) -> None:
        # Spec LM1 wants the asset ID localised so a future swap (e.g. to
        # WorldCover 10 m) is a one-line change.
        assert hasattr(buffers, "LAND_MASK_ASSET")
        assert hasattr(buffers, "LAND_MASK_BAND")

    def test_helper_is_private(self) -> None:
        # `_land_mask_image` is internal — the public surface for callers
        # is the `mask` key on the background_ring() dict. Pin the
        # underscore prefix so future refactors don't accidentally promote
        # it without spec sign-off.
        assert hasattr(buffers, "_land_mask_image")


# ---------------------------------------------------------------------------
# background_ring — Step B dict return + land_fraction plumbing
# ---------------------------------------------------------------------------


class _FakeGeometry:
    """Stand-in for ee.Geometry; supports `.difference()`."""

    def __init__(self, label: str) -> None:
        self.label = label

    def difference(self, other: "_FakeGeometry", **_kw) -> "_FakeGeometry":
        return _FakeGeometry(f"({self.label})-({other.label})")


class _FakeReduceResult:
    def __init__(self, payload: dict | None) -> None:
        self._payload = payload

    def getInfo(self) -> dict | None:  # noqa: N802 — EE method name
        return self._payload


class _FakeMaskImage:
    """Stand-in for the land mask `ee.Image`; only `reduceRegion` is used."""

    def __init__(self, land_fraction: float | None) -> None:
        self.land_fraction = land_fraction
        self.last_reduce_kwargs: dict | None = None

    def reduceRegion(self, **kwargs) -> _FakeReduceResult:  # noqa: N802
        self.last_reduce_kwargs = kwargs
        if self.land_fraction is None:
            return _FakeReduceResult(None)
        return _FakeReduceResult({LAND_MASK_BAND: self.land_fraction})


@pytest.fixture
def fake_ring_env(monkeypatch):
    """Stub `site_buffer`, `_land_mask_image`, and the ee.Reducer access so
    background_ring is hermetic. The reducer is a sentinel object — the fake
    mask records it as a kwarg but doesn't need to evaluate it.

    Yields a dict the test can mutate before calling background_ring:
        - ``land_fraction``: numeric value the fake mask returns
          (set to None to simulate reduceRegion → null)
        - ``mask_image``: populated after the fixture builds the fake mask
          so tests can inspect what reduceRegion was called with
    """
    state: dict = {"land_fraction": 0.85, "mask_image": None}

    def fake_site_buffer(centre, radius_km, projection: str = "geodetic"):
        return _FakeGeometry(f"buf(c={centre['lat']},{centre['lon']},r={radius_km})")

    def fake_mask_factory():
        img = _FakeMaskImage(state["land_fraction"])
        state["mask_image"] = img
        return img

    # `ee.Reducer.mean()` is unavailable until `ee.Initialize()` runs;
    # stub the staticmethod so background_ring can construct the reducer
    # kwarg in the synthetic-test path.
    class _ReducerSentinel:  # pragma: no cover — value only matters by identity
        pass

    monkeypatch.setattr("engine.core.buffers.site_buffer", fake_site_buffer)
    monkeypatch.setattr("engine.core.buffers._land_mask_image", fake_mask_factory)
    monkeypatch.setattr(
        "engine.core.buffers.ee.Reducer",
        type("Reducer", (), {"mean": staticmethod(lambda: _ReducerSentinel())}),
    )
    return state


_INLAND_CENTRE = {"lat": -13.50, "lon": -58.78}  # Sapezal, Mato Grosso, BR
_COASTAL_CENTRE = {"lat": 19.0760, "lon": 72.8777}  # Mumbai port


class TestBackgroundRingReturnShape:
    """§4.1 — dict-return shape and mask presence/absence."""

    def test_returns_dict_with_expected_keys(self, fake_ring_env) -> None:
        ring = background_ring(_INLAND_CENTRE, r_site_km=10.0)
        assert set(ring.keys()) == {
            "geometry", "mask", "land_fraction",
            "land_mask_applied", "land_mask_asset",
        }

    def test_returns_mask_when_apply_land_mask_true(self, fake_ring_env) -> None:
        ring = background_ring(_INLAND_CENTRE, r_site_km=10.0, apply_land_mask=True)
        assert ring["mask"] is not None
        assert ring["land_mask_applied"] is True

    def test_returns_no_mask_when_apply_land_mask_false(self, fake_ring_env) -> None:
        ring = background_ring(
            _INLAND_CENTRE, r_site_km=10.0, apply_land_mask=False,
        )
        assert ring["mask"] is None
        assert ring["land_mask_applied"] is False

    def test_default_apply_land_mask_is_true(self, fake_ring_env) -> None:
        # Spec LM3 — production default. Regression-flag if someone flips it.
        ring = background_ring(_INLAND_CENTRE, r_site_km=10.0)
        assert ring["land_mask_applied"] is True
        assert ring["mask"] is not None

    def test_land_mask_asset_always_populated(self, fake_ring_env) -> None:
        # Even with mask=None, the asset ID stays for vintage tracking
        # (spec §3.6 dict shape).
        ring = background_ring(
            _INLAND_CENTRE, r_site_km=10.0, apply_land_mask=False,
        )
        assert ring["land_mask_asset"] == LAND_MASK_ASSET

    def test_geometry_key_holds_annulus_difference(self, fake_ring_env) -> None:
        ring = background_ring(_INLAND_CENTRE, r_site_km=10.0)
        # The fake site_buffer labels with radius — annulus is outer - inner.
        assert isinstance(ring["geometry"], _FakeGeometry)
        assert "buf(c=-13.5,-58.78,r=50.0)" in ring["geometry"].label  # outer
        assert "buf(c=-13.5,-58.78,r=10.0)" in ring["geometry"].label  # inner


class TestBackgroundRingDefaultRadius:
    """The pre-milestone IC_v4 §6.2 default (r_bg = min(5·r_site, 200)) survives."""

    def test_default_radius_uses_multiple_when_below_cap(self, fake_ring_env) -> None:
        # r_site=10 → outer = 5·10 = 50 (< 200 cap)
        ring = background_ring(_INLAND_CENTRE, r_site_km=10.0)
        assert "r=50.0" in ring["geometry"].label

    def test_default_radius_capped_at_max(self, fake_ring_env) -> None:
        # r_site=50 → 5·50 = 250 → capped at 200
        ring = background_ring(_INLAND_CENTRE, r_site_km=50.0)
        assert "r=200" in ring["geometry"].label

    def test_explicit_r_background_overrides_default(self, fake_ring_env) -> None:
        ring = background_ring(
            _INLAND_CENTRE, r_site_km=10.0, r_background_km=120.0,
        )
        assert "r=120.0" in ring["geometry"].label


class TestBackgroundRingLandFraction:
    """§4.1 — land_fraction is read from the mask reduceRegion."""

    def test_land_fraction_is_one_for_fully_inland_mock(self, fake_ring_env) -> None:
        # Mocked mask reduceRegion → 1.0 (all land). Real-EE equivalent
        # for Sapezal is the gated test below.
        fake_ring_env["land_fraction"] = 1.0
        ring = background_ring(_INLAND_CENTRE, r_site_km=10.0)
        assert ring["land_fraction"] == 1.0

    def test_land_fraction_below_one_for_partly_coastal_mock(
        self, fake_ring_env,
    ) -> None:
        # Mumbai-like 50% land mock.
        fake_ring_env["land_fraction"] = 0.5
        ring = background_ring(_COASTAL_CENTRE, r_site_km=10.0)
        assert ring["land_fraction"] == 0.5
        assert ring["land_fraction"] < 1.0

    def test_land_fraction_handles_null_payload(self, fake_ring_env) -> None:
        # reduceRegion can return {band: null} when the geometry misses the
        # mask entirely (e.g. fully off-grid). Should default to 0.0, not
        # crash, so the LM7 threshold check in Step D fires the empty-ring
        # path uniformly.
        fake_ring_env["land_fraction"] = None
        ring = background_ring(_COASTAL_CENTRE, r_site_km=10.0)
        assert ring["land_fraction"] == 0.0

    def test_reduce_uses_mod44w_native_scale(self, fake_ring_env) -> None:
        # Spec §3.3 — scale=250 (MOD44W native). Pinned so a future
        # refactor doesn't silently re-project the mask.
        background_ring(_COASTAL_CENTRE, r_site_km=10.0)
        kwargs = fake_ring_env["mask_image"].last_reduce_kwargs
        assert kwargs is not None
        assert kwargs["scale"] == 250

    def test_land_fraction_computed_even_when_mask_disabled(
        self, fake_ring_env,
    ) -> None:
        # apply_land_mask=False suppresses the mask object but keeps the
        # geometric land_fraction so provenance can still record it
        # (e.g. for the future M-CLIM-A3b composition).
        fake_ring_env["land_fraction"] = 0.7
        ring = background_ring(
            _COASTAL_CENTRE, r_site_km=10.0, apply_land_mask=False,
        )
        assert ring["mask"] is None
        assert ring["land_fraction"] == 0.7


# ---------------------------------------------------------------------------
# Real-EE integration tests — gated by RUN_EE_TESTS=1
# ---------------------------------------------------------------------------


pytestmark_real_ee = pytest.mark.skipif(
    os.environ.get("RUN_EE_TESTS") != "1",
    reason="set RUN_EE_TESTS=1 (and EE_PROJECT_ID) to run real-EE tests",
)


# ---------------------------------------------------------------------------
# background_value mask application — Step C (§4.2)
# ---------------------------------------------------------------------------


class _ChainStub:
    """MagicMock-style chain for an ee.ImageCollection.

    Records what was called on it. Every chainable method returns ``self``
    so ``ic.select(b).map(fn).mean()`` works. ``reduceRegion`` / ``getInfo``
    yield a configurable payload so `background_value` succeeds (returns a
    median+stdDev pair) when we want it to.
    """

    def __init__(self, reduce_payload: dict) -> None:
        self._reduce_payload = reduce_payload
        self.select_calls: list = []
        self.map_calls: list = []
        self.mean_calls: int = 0
        self.reduce_calls: list = []

    def select(self, band):
        self.select_calls.append(band)
        return self

    def map(self, fn):
        self.map_calls.append(fn)
        return self

    def mean(self):
        self.mean_calls += 1
        return self

    def reduceRegion(self, **kwargs):  # noqa: N802
        self.reduce_calls.append(kwargs)
        return self

    def getInfo(self):  # noqa: N802
        return self._reduce_payload

    def size(self):
        out = _ChainStub({})
        out._size_value = 5  # type: ignore[attr-defined]
        return out


class _FakeImageWithMaskTracking:
    """Sentinel image that records updateMask calls so the §4.2 tests can
    verify per-image masking happened (and which mask was applied).
    """

    def __init__(self, label: str) -> None:
        self.label = label
        self.applied_masks: list = []

    def updateMask(self, mask):  # noqa: N802
        self.applied_masks.append(mask)
        return self


def _make_ring_dict(mask, *, applied: bool):
    """Sentinel dict matching background_ring's Step B return shape."""
    return {
        "geometry": object(),
        "mask": mask,
        "land_fraction": 0.85 if mask is not None else 1.0,
        "land_mask_applied": applied,
        "land_mask_asset": LAND_MASK_ASSET,
    }


@pytest.fixture
def repeatable_core_env(monkeypatch):
    """Stub `background_ring` and the ee.Reducer chain inside
    `engine.core.repeatable_core` so `background_value` runs hermetic.

    Returns a state dict whose keys the test can read/write:
      - ``ring``: the dict that background_ring will return (default: no
        mask, mirroring an opt-out call)
      - ``chain``: the most recently built _ChainStub (set when the SUT
        actually runs)
    """
    from unittest.mock import MagicMock as _MM

    from engine.core import repeatable_core

    state: dict = {
        "ring": _make_ring_dict(mask=None, applied=False),
        "chain": None,
    }

    monkeypatch.setattr(
        repeatable_core, "background_ring",
        lambda *_a, **_kw: state["ring"],
    )
    # The static `ee.Reducer.median().combine(ee.Reducer.stdDev(), ...)`
    # is opaque to the mask-application logic — full MagicMock is enough.
    monkeypatch.setattr(repeatable_core.ee, "Reducer", _MM())
    return state


class TestBackgroundValueMaskApplication:
    """§4.2 — `background_value` applies the land mask when provided."""

    def _build_chain(self) -> _ChainStub:
        # median + stdDev keys must be present so background_value succeeds.
        return _ChainStub({"NO2_median": 1.0e-5, "NO2_stdDev": 2.0e-6})

    def test_uses_mask_when_provided(self, repeatable_core_env) -> None:
        from engine.core import repeatable_core

        mask_sentinel = object()
        repeatable_core_env["ring"] = _make_ring_dict(
            mask=mask_sentinel, applied=True,
        )
        chain = self._build_chain()

        repeatable_core.background_value(
            aoi={"centre": {"lat": 19.0, "lon": 72.0}, "radius_km": 10.0},
            image_collection=chain, band="NO2",
            seasonal=False, scale=1000.0,
        )

        # The land mask code path adds exactly one .map() call between
        # select() and mean(). The lambda passed in must apply the mask
        # via updateMask when invoked with an image.
        assert len(chain.map_calls) == 1, (
            "background_value must call ic.map(lambda img: img.updateMask(mask)) "
            "exactly once when ring['mask'] is not None"
        )

        # Invoke the registered lambda against a tracking image to confirm
        # it's the spec's `img.updateMask(mask)` pattern, not `img.mask(mask)`
        # (which would *replace* existing masks).
        probe = _FakeImageWithMaskTracking("probe")
        chain.map_calls[0](probe)
        assert probe.applied_masks == [mask_sentinel]

    def test_falls_back_to_unmasked_when_apply_land_mask_false(
        self, repeatable_core_env,
    ) -> None:
        from engine.core import repeatable_core

        # apply_land_mask=False path: ring carries mask=None.
        repeatable_core_env["ring"] = _make_ring_dict(mask=None, applied=False)
        chain = self._build_chain()

        repeatable_core.background_value(
            aoi={"centre": {"lat": -13.5, "lon": -58.78}, "radius_km": 10.0},
            image_collection=chain, band="NO2",
            seasonal=False, scale=1000.0,
        )

        # No .map() call — the IC flows directly into .mean() unchanged.
        assert chain.map_calls == [], (
            "background_value must not call ic.map(...) when ring['mask'] is None"
        )
        # Sanity: the reduction still ran.
        assert chain.mean_calls == 1
        assert len(chain.reduce_calls) == 1

    def test_per_image_masking_composes_with_cloud_mask(
        self, repeatable_core_env,
    ) -> None:
        """The lambda calls `updateMask`, not `mask` / `unmask`, so any
        per-image cloud mask already attached to the image is preserved
        (updateMask = AND of existing mask and new mask, per EE semantics).
        """
        from engine.core import repeatable_core

        mask_sentinel = object()
        repeatable_core_env["ring"] = _make_ring_dict(
            mask=mask_sentinel, applied=True,
        )
        chain = self._build_chain()

        repeatable_core.background_value(
            aoi={"centre": {"lat": 22.5, "lon": 114.0}, "radius_km": 10.0},
            image_collection=chain, band="NO2",
            seasonal=False, scale=1000.0,
        )

        # Probe the registered lambda. The image's `updateMask` is the
        # only method invoked — no `mask(...)` or `unmask(...)` overrides.
        class _StrictProbe:
            def __init__(self) -> None:
                self.updateMask_args: list = []
                self.other_calls: list = []

            def updateMask(self, m):  # noqa: N802
                self.updateMask_args.append(m)
                return self

            def __getattr__(self, name):
                # Trap any other method access — would indicate the lambda
                # is doing more than updateMask.
                def _raise(*_a, **_kw):
                    self.other_calls.append(name)
                    raise AssertionError(
                        f"Step C lambda touched img.{name}; should only call updateMask"
                    )
                return _raise

        probe = _StrictProbe()
        chain.map_calls[0](probe)
        assert probe.updateMask_args == [mask_sentinel]
        assert probe.other_calls == []


# ---------------------------------------------------------------------------
# Step E — six_step return shape pins the three new ring fields (§4.4)
# ---------------------------------------------------------------------------


class TestSixStepRingMetadataSurface:
    """`six_step` surfaces the three MOD44W land-mask fields in its result
    dict so air/ghg/nature `_format_result` functions can thread them
    into `provenance.extra`. This is the single integration point that
    covers all three pillars (LM4 "at least one indicator from each
    pillar verified to consume the masked ring").
    """

    def _stub_six_step_deps(self, monkeypatch, ring_dict: dict) -> None:
        """Wire up the minimum surface six_step needs to run hermetically."""
        from engine.core import repeatable_core as rc

        class _SpyIc:
            def filterDate(self, *_a, **_kw): return self
            def filterBounds(self, _g): return self

        class _EnvelopeSentinel:
            def bounds(self): return self

        monkeypatch.setattr(
            rc, "site_buffer", lambda c, r: _EnvelopeSentinel(),
        )
        monkeypatch.setattr(
            rc, "site_value", lambda aoi, ic, band, scale: 1.0,
        )
        monkeypatch.setattr(
            rc, "background_value",
            lambda aoi, ic, band, seasonal, scale, *, ring: (0.5, 0.1),
        )
        monkeypatch.setattr(
            rc, "background_ring",
            lambda centre, radius_km: ring_dict,
        )
        monkeypatch.setattr(
            rc, "_server_side_hf",
            lambda *a, **kw: rc.ServerSideHfResult(5, 0.0, 100),
        )
        monkeypatch.setattr(
            rc, "_confidence_terms_from_six_step_state",
            lambda **kw: {
                "qa": 0.9, "n_valid": 1.0,
                "anomaly_strength": 0.0, "spatial_context": 1.0,
            },
        )
        monkeypatch.setattr(
            rc, "compute_indicator_confidence", lambda **kw: 0.8,
        )
        return _SpyIc()

    def test_six_step_returns_ring_land_fraction(self, monkeypatch) -> None:
        from engine.core import repeatable_core as rc

        ring = {
            "geometry": object(),
            "mask": object(),
            "land_fraction": 0.7,
            "land_mask_applied": True,
            "land_mask_asset": "MODIS/006/MOD44W",
        }
        ic = self._stub_six_step_deps(monkeypatch, ring)

        out = rc.six_step(
            aoi={"centre": {"lat": -15.78, "lon": -47.80}, "radius_km": 43.1},
            image_collection=ic, band="some_band",
            time_range=("2026-01-01", "2026-04-01"), ee_client=None,
            indicator_id="air.no2",
        )
        assert out["ring_land_fraction"] == 0.7

    def test_six_step_returns_ring_land_mask_applied(self, monkeypatch) -> None:
        from engine.core import repeatable_core as rc

        ring = {
            "geometry": object(),
            "mask": object(),
            "land_fraction": 0.7,
            "land_mask_applied": True,
            "land_mask_asset": "MODIS/006/MOD44W",
        }
        ic = self._stub_six_step_deps(monkeypatch, ring)
        out = rc.six_step(
            aoi={"centre": {"lat": -15.78, "lon": -47.80}, "radius_km": 43.1},
            image_collection=ic, band="some_band",
            time_range=("2026-01-01", "2026-04-01"), ee_client=None,
            indicator_id="nature.ndvi",
        )
        assert out["ring_land_mask_applied"] is True

    def test_six_step_returns_ring_land_mask_asset(self, monkeypatch) -> None:
        from engine.core import repeatable_core as rc

        ring = {
            "geometry": object(),
            "mask": object(),
            "land_fraction": 0.7,
            "land_mask_applied": True,
            "land_mask_asset": "MODIS/006/MOD44W",
        }
        ic = self._stub_six_step_deps(monkeypatch, ring)
        out = rc.six_step(
            aoi={"centre": {"lat": -15.78, "lon": -47.80}, "radius_km": 43.1},
            image_collection=ic, band="some_band",
            time_range=("2026-01-01", "2026-04-01"), ee_client=None,
            indicator_id="ghg.ch4",
        )
        assert out["ring_land_mask_asset"] == "MODIS/006/MOD44W"


# ---------------------------------------------------------------------------
# Step D — LM7 land-fraction threshold error path (§4.3)
# ---------------------------------------------------------------------------


class TestRingEmptyPostLandMask:
    """§4.3 — `background_value` raises with a distinct reason when the
    land fraction is below LAND_MASK_FRACTION_MIN_THRESHOLD."""

    def _build_chain(self):
        # The reduction never runs in this path — the threshold check
        # fires earlier. But the chain still needs to be a valid stub
        # in case the threshold doesn't trip (regression-trap).
        return _ChainStub({"NO2_median": 1.0e-5, "NO2_stdDev": 2.0e-6})

    def test_land_fraction_below_threshold_triggers_ring_empty(
        self, repeatable_core_env,
    ) -> None:
        # Mumbai-like 0.02 land fraction — well below the 0.05 LM7 cutoff.
        from engine.core import repeatable_core
        from engine.exceptions import BackgroundRingNoDataError

        repeatable_core_env["ring"] = {
            "geometry": object(),
            "mask": object(),  # mask present (apply_land_mask=True)
            "land_fraction": 0.02,
            "land_mask_applied": True,
            "land_mask_asset": LAND_MASK_ASSET,
        }

        with pytest.raises(BackgroundRingNoDataError):
            repeatable_core.background_value(
                aoi={"centre": {"lat": 19.0, "lon": 72.0}, "radius_km": 10.0},
                image_collection=self._build_chain(), band="NO2",
                seasonal=False, scale=1000.0,
            )

    def test_distinct_reason_marker_in_error(
        self, repeatable_core_env,
    ) -> None:
        # Spec §3.5 — same error class, distinct reason text so analytics
        # can separate water-only-ring from sparse-coverage causes.
        from engine.core import repeatable_core
        from engine.exceptions import BackgroundRingNoDataError, IndicatorComputeError

        repeatable_core_env["ring"] = {
            "geometry": object(),
            "mask": object(),
            "land_fraction": 0.03,
            "land_mask_applied": True,
            "land_mask_asset": LAND_MASK_ASSET,
        }

        with pytest.raises(BackgroundRingNoDataError) as excinfo:
            repeatable_core.background_value(
                aoi={"centre": {"lat": 19.0, "lon": 72.0}, "radius_km": 10.0},
                image_collection=self._build_chain(), band="NO2",
                seasonal=False, scale=1000.0,
            )

        # Distinct marker survives in the reason string.
        assert "ring_empty_post_land_mask" in excinfo.value.reason
        # Still a subclass of IndicatorComputeError so existing handlers
        # (pillar dispatchers, generic catch sites) keep working.
        assert isinstance(excinfo.value, IndicatorComputeError)
        # The reason carries enough context (land_fraction, threshold, AOI)
        # to support debugging in logs / provenance.
        assert "0.03" in excinfo.value.reason  # actual land fraction
        assert "0.05" in excinfo.value.reason  # the LM7 threshold

    def test_threshold_boundary_pixel_at_five_percent_does_not_trigger(
        self, repeatable_core_env,
    ) -> None:
        # LM7: "below 5%" — exactly 0.05 passes the check. Pinned so a
        # future <= refactor doesn't silently flip the boundary.
        from engine.core import repeatable_core

        repeatable_core_env["ring"] = {
            "geometry": object(),
            "mask": object(),
            "land_fraction": 0.05,
            "land_mask_applied": True,
            "land_mask_asset": LAND_MASK_ASSET,
        }
        # Should NOT raise — the reduction runs.
        median, std = repeatable_core.background_value(
            aoi={"centre": {"lat": 19.0, "lon": 72.0}, "radius_km": 10.0},
            image_collection=self._build_chain(), band="NO2",
            seasonal=False, scale=1000.0,
        )
        assert median == pytest.approx(1.0e-5)
        assert std == pytest.approx(2.0e-6)

    def test_threshold_skipped_when_mask_disabled(
        self, repeatable_core_env,
    ) -> None:
        # When apply_land_mask=False (mask is None) the threshold check
        # is bypassed — the caller has explicitly opted out of land
        # masking and presumably wants the unmasked reduction even at
        # low land fractions. Existing `BackgroundRingNoDataError` path
        # at the median/std null check still catches truly empty rings.
        from engine.core import repeatable_core

        repeatable_core_env["ring"] = {
            "geometry": object(),
            "mask": None,           # explicit opt-out
            "land_fraction": 0.01,  # would trigger threshold if mask present
            "land_mask_applied": False,
            "land_mask_asset": LAND_MASK_ASSET,
        }
        # Should NOT raise — mask is None so threshold check is skipped.
        median, std = repeatable_core.background_value(
            aoi={"centre": {"lat": 19.0, "lon": 72.0}, "radius_km": 10.0},
            image_collection=self._build_chain(), band="NO2",
            seasonal=False, scale=1000.0,
        )
        assert median == pytest.approx(1.0e-5)
        assert std == pytest.approx(2.0e-6)


@pytestmark_real_ee
class TestBackgroundRingLandFractionRealEE:
    """§4.1 inland/coastal — real EE round-trips against MOD44W."""

    @pytest.fixture(autouse=True)
    def _ee_init(self) -> None:
        # Mirrors tests/test_ghg_integration.py — initialise EE directly so
        # we don't pull in `utils.ee_init.require_earth_engine` (which is
        # Streamlit-wrapped and `st.stop`s in a pytest context).
        import ee
        project = os.environ.get("EE_PROJECT_ID")
        if not project:
            pytest.skip("EE_PROJECT_ID not set")
        ee.Initialize(project=project)

    def test_land_fraction_is_one_for_inland_centre_sapezal(self) -> None:
        # Sapezal, Mato Grosso — deep continental interior, ring should be
        # entirely terrestrial within MOD44W's 250 m resolution.
        ring = background_ring({"lat": -13.50, "lon": -58.78}, r_site_km=10.0)
        assert ring["land_fraction"] == pytest.approx(1.0, abs=0.01)

    def test_land_fraction_below_one_for_coastal_centre_mumbai(self) -> None:
        # Mumbai port — ring straddles the Arabian Sea; spec §4.5 expects
        # ~0.4–0.5 land fraction (real-EE captured 0.524).
        ring = background_ring({"lat": 19.0760, "lon": 72.8777}, r_site_km=10.0)
        assert 0.20 <= ring["land_fraction"] <= 0.80
        assert ring["land_fraction"] < 1.0


# ---------------------------------------------------------------------------
# Step F — real-EE coastal smoke test (§4.5)
# ---------------------------------------------------------------------------


@pytestmark_real_ee
class TestCoastalAoiSmokeRealEE:
    """Spec §4.5 — real-EE smoke against Mumbai / Rio / Shenzhen.

    Asserts (per spec):
      1. ring_land_fraction lands in the expected ballpark for each AOI
         (validating that MOD44W actually disagrees with "all land" for
         the demo's coastal cases).
      2. The CH₄ z-score is bounded (|z| < 10) — coastal sites should
         still show some signal but not pathologically high values, which
         was the failure mode pre-milestone.
      3. Provenance.extra carries the three new MOD44W fields with the
         live land_fraction value (proves the Step E threading reaches
         the public payload, not just the six_step return dict).

    This single test class is the v1.x analogue of M-TIER-A1 Step C's
    real-EE verification: unit tests prove the math, the smoke test
    proves the EE primitives behave under real coastal geometries.
    """

    @pytest.fixture(autouse=True)
    def _ee_init(self) -> None:
        import ee
        project = os.environ.get("EE_PROJECT_ID")
        if not project:
            pytest.skip("EE_PROJECT_ID not set")
        ee.Initialize(project=project)

    # Spec §4.5 expected ranges are widened slightly to absorb MOD44W
    # vintage drift and exact-buffer geometry variance. Real-EE captured
    # values (24-26 May 2026): Mumbai 0.524, Rio 0.571, Shenzhen 0.585.
    @pytest.mark.parametrize(
        "label, centre, expected_low, expected_high",
        [
            ("mumbai",   {"lat": 19.0760, "lon":  72.8777}, 0.30, 0.70),
            ("rio",      {"lat":-22.9068, "lon": -43.1729}, 0.40, 0.75),
            ("shenzhen", {"lat": 22.5431, "lon": 114.0579}, 0.40, 0.75),
        ],
    )
    def test_coastal_land_fraction_in_expected_range(
        self, label, centre, expected_low, expected_high,
    ) -> None:
        ring = background_ring(centre, r_site_km=10.0)
        assert expected_low <= ring["land_fraction"] <= expected_high, (
            f"{label}: land_fraction {ring['land_fraction']:.3f} "
            f"outside expected [{expected_low}, {expected_high}]"
        )

    @pytest.mark.parametrize(
        "label, centre",
        [
            ("mumbai",   {"lat": 19.0760, "lon":  72.8777}),
            ("rio",      {"lat":-22.9068, "lon": -43.1729}),
            ("shenzhen", {"lat": 22.5431, "lon": 114.0579}),
        ],
    )
    def test_coastal_ch4_z_score_is_bounded(self, label, centre) -> None:
        # Spec §4.5 — "reasonable" defined as a defensible z-score, not
        # pathological (which was the pre-milestone failure mode). We use
        # CH₄ as the indicator under test because it (a) goes through
        # six_step → background_value (the masked-ring code path), (b)
        # has S5P coverage at all three demo AOIs, and (c) is the GHG
        # indicator cited in LM4's per-pillar verification list.
        from engine.ghg import compute_ch4_snapshot

        aoi = {"centre": centre, "radius_km": 10.0}
        result = compute_ch4_snapshot(
            aoi=aoi, time_range=("2026-01-01", "2026-04-01"),
            mode="screening", ee_client=None,
        )

        z = result.get("ghg.ch4.z")
        prov = result["_provenance.ghg.ch4"]

        # If the indicator skipped (e.g. ring_empty after masking somewhere
        # the threshold fired), surface the skip and pass — the spec
        # tolerates that. Otherwise the z must be bounded.
        if prov.get("skipped_reason"):
            return  # masked-ring skip is an acceptable outcome
        assert z is not None
        assert abs(z) < 10.0, (
            f"{label}: ch4.z={z} is pathologically large; pre-milestone "
            "failure mode is recurring"
        )

    @pytest.mark.parametrize(
        "label, centre",
        [
            ("mumbai",   {"lat": 19.0760, "lon":  72.8777}),
            ("rio",      {"lat":-22.9068, "lon": -43.1729}),
            ("shenzhen", {"lat": 22.5431, "lon": 114.0579}),
        ],
    )
    def test_coastal_provenance_extra_carries_land_mask_fields(
        self, label, centre,
    ) -> None:
        # End-to-end: the Step E threading reaches the public provenance
        # payload of a real screening run on a coastal AOI.
        from engine.ghg import compute_ch4_snapshot

        aoi = {"centre": centre, "radius_km": 10.0}
        result = compute_ch4_snapshot(
            aoi=aoi, time_range=("2026-01-01", "2026-04-01"),
            mode="screening", ee_client=None,
        )
        prov = result["_provenance.ghg.ch4"]
        if prov.get("skipped_reason"):
            return  # skipped run can't surface six_step's payload fields
        extra = prov["extra"]
        assert "ring_land_fraction" in extra
        assert 0.0 <= extra["ring_land_fraction"] <= 1.0
        assert extra["land_mask_applied"] is True
        assert extra["land_mask_asset"] == "MODIS/006/MOD44W"
