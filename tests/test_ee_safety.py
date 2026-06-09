"""Tests for engine.core.ee_safety.with_guaranteed_band.

The offline wiring tests assert the server-side graph shape (zero getInfo
round-trips, the band-count predicate, the masked-constant substitution). The
real-EE behavioural test (RUN_EE_TESTS=1) proves the actual band-less crash is
prevented end-to-end.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from engine.core import with_guaranteed_band


class TestWithGuaranteedBandWiring:
    """Offline graph-shape assertions — `ee` is fully mocked so no network."""

    @staticmethod
    def _mock_ee(monkeypatch):
        fake_ee = MagicMock(name="ee")
        # ee.Algorithms.If(predicate, a, b) -> a sentinel we can identify.
        fake_ee.Algorithms.If.return_value = "IF_RESULT"
        fake_ee.Image.side_effect = lambda x: ("IMAGE", x)
        # ee.Image.constant(0).rename(band).updateMask(...) chain.
        const_chain = MagicMock(name="const_chain")
        const_chain.rename.return_value = const_chain
        const_chain.updateMask.return_value = const_chain
        fake_ee.Image.constant.return_value = const_chain
        monkeypatch.setattr("engine.core.ee_safety.ee", fake_ee)
        return fake_ee, const_chain

    def test_zero_getinfo_round_trips(self, monkeypatch) -> None:
        fake_ee, _ = self._mock_ee(monkeypatch)
        image = MagicMock(name="image")
        with_guaranteed_band(image, "NDVI")
        # The whole guard is server-side: it must never materialise anything.
        image.getInfo.assert_not_called()
        assert not any(
            "getInfo" in str(c) for c in fake_ee.mock_calls
        )

    def test_substitutes_masked_constant_named_band(self, monkeypatch) -> None:
        fake_ee, const_chain = self._mock_ee(monkeypatch)
        image = MagicMock(name="image")
        with_guaranteed_band(image, "label")
        # masked constant: ee.Image.constant(0).rename("label").updateMask(...)
        fake_ee.Image.constant.assert_any_call(0)
        const_chain.rename.assert_called_once_with("label")
        const_chain.updateMask.assert_called_once()

    def test_if_predicate_is_band_count_gt_zero(self, monkeypatch) -> None:
        fake_ee, const_chain = self._mock_ee(monkeypatch)
        image = MagicMock(name="image")
        result = with_guaranteed_band(image, "NDVI")
        # Predicate: image.bandNames().size().gt(0)
        image.bandNames.assert_called_once()
        image.bandNames.return_value.size.assert_called_once()
        image.bandNames.return_value.size.return_value.gt.assert_called_once_with(0)
        # If(predicate, original_image, masked_constant)
        if_args = fake_ee.Algorithms.If.call_args.args
        assert if_args[1] is image            # non-empty branch: untouched
        assert if_args[2] is const_chain      # empty branch: masked constant
        # Wrapped back into ee.Image(...).
        assert result == ("IMAGE", "IF_RESULT")


# Module-level skip for the real-EE behavioural test.
_ee_required = pytest.mark.skipif(
    os.environ.get("RUN_EE_TESTS") != "1",
    reason="set RUN_EE_TESTS=1 (and EE_PROJECT_ID) to run real-EE tests",
)


@_ee_required
class TestWithGuaranteedBandRealEe:
    @pytest.fixture(scope="class")
    def initialised_ee(self):
        import ee
        project = os.environ.get("EE_PROJECT_ID")
        if not project:
            pytest.skip("EE_PROJECT_ID not set")
        ee.Initialize(project=project)
        return ee

    def test_empty_collection_band_op_does_not_throw(self, initialised_ee) -> None:
        ee = initialised_ee
        # A filter guaranteed to yield ZERO images → .mean() is band-less.
        empty = (
            ee.ImageCollection("MODIS/061/MOD13Q1")
            .select("NDVI")
            .filterDate("1990-01-01", "1990-01-02")  # predates the mission
        )
        guarded = with_guaranteed_band(empty.mean(), "NDVI")
        # The unguarded version raises "Image.lt: ... Got 0 and 1"; the guarded
        # one must evaluate cleanly and carry exactly the NDVI band.
        assert guarded.bandNames().getInfo() == ["NDVI"]
        # And a per-pixel band op (the thing that used to crash) now works.
        mask = guarded.lt(0.3)
        assert mask.bandNames().getInfo() == ["NDVI"]

    def test_non_empty_collection_is_unchanged(self, initialised_ee) -> None:
        ee = initialised_ee
        nonempty = (
            ee.ImageCollection("MODIS/061/MOD13Q1")
            .select("NDVI")
            .filterDate("2023-01-01", "2023-02-01")
        )
        mean = nonempty.mean()
        guarded = with_guaranteed_band(mean, "NDVI")
        assert guarded.bandNames().getInfo() == ["NDVI"]
