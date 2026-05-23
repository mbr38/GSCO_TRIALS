"""Synthetic-payload tests for engine.core.repeatable_core.

Pure-math functions only. The EE-touching functions (`site_value`,
`background_value`, `six_step`) are deferred to milestone 3+ with real
integration tests against known clean/industrial reference points.
"""

from __future__ import annotations

import pytest

from engine.constants import ANOMALY_Z_THRESHOLD
from engine.core.repeatable_core import anomaly_z_hf
from engine.exceptions import IndicatorComputeError, PillarComputeError


class TestAnomalyZHfHappyPath:
    def test_site_equals_background_gives_zero_signal(self) -> None:
        result = anomaly_z_hf(
            site=5.0, bg_median=5.0, bg_std=1.0,
            time_series=[5.0, 5.0, 5.0],
        )
        assert result["anomaly"] == 0.0
        assert result["z"] == 0.0
        assert result["hf"] == 0.0

    def test_z_is_anomaly_divided_by_std(self) -> None:
        result = anomaly_z_hf(
            site=8.0, bg_median=5.0, bg_std=1.5, time_series=[5.0],
        )
        assert result["anomaly"] == pytest.approx(3.0)
        assert result["z"] == pytest.approx(2.0)

    def test_hf_counts_dates_at_or_above_threshold(self) -> None:
        # bg=5, std=1, z_threshold=2 → anomaly observation requires value ≥ 7.
        # 4 of these 10 dates qualify.
        series = [3, 4, 5, 5, 6, 7, 8, 9, 7.5, 5]
        result = anomaly_z_hf(
            site=6.0, bg_median=5.0, bg_std=1.0,
            time_series=series, z_threshold=2.0,
        )
        assert result["hf"] == pytest.approx(4 / 10)

    def test_default_z_threshold_pulled_from_constants(self) -> None:
        # Two values exactly at 2σ → both count.
        series = [7.0, 7.0]
        result = anomaly_z_hf(
            site=7.0, bg_median=5.0, bg_std=1.0, time_series=series,
        )
        assert ANOMALY_Z_THRESHOLD == 2.0
        assert result["hf"] == 1.0

    def test_negative_anomaly_still_returns_signed_z(self) -> None:
        # "Higher is worse" direction is enforced by to_score, not anomaly_z_hf;
        # the raw anomaly/z here keep their signs.
        result = anomaly_z_hf(
            site=2.0, bg_median=5.0, bg_std=1.0, time_series=[2.0],
        )
        assert result["anomaly"] == pytest.approx(-3.0)
        assert result["z"] == pytest.approx(-3.0)
        # No date in the series clears the +2σ threshold:
        assert result["hf"] == 0.0


class TestAnomalyZHfEdgeCases:
    def test_zero_std_returns_anomaly_but_no_z_or_hf(self) -> None:
        result = anomaly_z_hf(
            site=7.0, bg_median=5.0, bg_std=0.0, time_series=[5.0, 6.0],
        )
        assert result["anomaly"] == 2.0
        assert result["z"] is None
        assert result["hf"] is None

    def test_negative_std_treated_as_degenerate(self) -> None:
        # σ is non-negative by construction; defensive against numerical slop.
        result = anomaly_z_hf(
            site=7.0, bg_median=5.0, bg_std=-0.1, time_series=[5.0],
        )
        assert result["z"] is None
        assert result["hf"] is None

    def test_empty_time_series_keeps_anomaly_and_z_but_drops_hf(self) -> None:
        result = anomaly_z_hf(
            site=7.0, bg_median=5.0, bg_std=1.0, time_series=[],
        )
        assert result["anomaly"] == 2.0
        assert result["z"] == 2.0
        assert result["hf"] is None

    def test_all_identical_values_yield_zero_hf(self) -> None:
        result = anomaly_z_hf(
            site=5.0, bg_median=5.0, bg_std=1.0,
            time_series=[5.0] * 5,
        )
        assert result["hf"] == 0.0

    def test_iterable_input_accepted(self) -> None:
        # Generators / iterators must be supported (the orchestrator passes
        # mapped values, not always lists).
        result = anomaly_z_hf(
            site=7.0, bg_median=5.0, bg_std=1.0,
            time_series=(v for v in [7.0, 7.0]),
        )
        assert result["hf"] == 1.0


class TestExceptionTypes:
    def test_indicator_compute_error_carries_id_and_reason(self) -> None:
        err = IndicatorComputeError(indicator_id="air.no2", reason="no pixels")
        assert err.indicator_id == "air.no2"
        assert err.reason == "no pixels"
        assert "air.no2" in str(err)
        assert "no pixels" in str(err)

    def test_pillar_compute_error_carries_affected_ids(self) -> None:
        err = PillarComputeError(
            pillar="air",
            indicator_ids=["air.no2.score", "air.so2.score"],
            reason="EE unavailable",
        )
        assert err.pillar == "air"
        assert err.indicator_ids == ["air.no2.score", "air.so2.score"]
        assert "air" in str(err)


# ---------------------------------------------------------------------------
# Deferred — real EE integration tests live in milestone 3+.
# Stubs are kept so future runs surface them as skipped (not missing).
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="real EE integration test — see milestone 3")
def test_site_value_against_known_clean_rural_point() -> None:
    """E.g. a mid-Atlantic Ocean point should give near-zero NO₂."""


@pytest.mark.skip(reason="real EE integration test — see milestone 3")
def test_background_value_against_known_industrial_point() -> None:
    """E.g. Ruhr valley NO₂ background statistics in a 25 km ring."""


@pytest.mark.skip(reason="real EE integration test — see milestone 3")
def test_six_step_end_to_end_for_no2_at_known_industrial_point() -> None:
    """Full six-step run; assert composite shape and plausible score band."""


# ---------------------------------------------------------------------------
# D3.2 (M-TIER-A1 Step D) — server-side _server_side_hf coverage.
#
# Step C surfaced two EE-server-side bugs that no CI test exercised before:
#
#   Bug 1: ee.Dictionary.get(key, default) fires `default` only when the key
#          is *absent* — when the key is present but maps to null, .get()
#          returns null. Downstream ee.Number(null) then raises
#          "Number.neq: Parameter 'left' is required and may not be null".
#          The fix swapped sentinel-based null detection for a combined
#          Mean+Count reducer; Count is *always* a real Number (0 when no
#          valid pixels, ≥1 otherwise), so is_valid is derived from Count.
#
#   Bug 2: EE's Mean reducer OMITS its output key entirely from the
#          reduceRegion dict when zero valid pixels exist in the buffer.
#          ee.Algorithms.If(cond, then, else) evaluates both branches
#          server-side, so an undefaulted `reduction.get(mean_key)` in
#          the then-branch crashes the map even when is_valid=0 should
#          logically short-circuit it. The fix added a `default=0.0`.
#
# These bugs are EE-server-side semantic quirks; pure-Python mocks must
# faithfully reproduce them or the tests would pass against any
# implementation. The mock-faithfulness story:
#
#   * Python's native dict.get(key, default) ALREADY matches EE's bug-1
#     semantics — `default` fires only on missing-key, not on
#     present-but-None. So `reduction` can be a plain Python dict.
#   * Python's function-call semantics evaluate ALL arguments before
#     entering the called function — so a Python `If(cond, then_expr,
#     else_expr)` automatically evaluates both branches. This is
#     faithful to EE's bug-2 server-side eager evaluation.
#   * ee.Number(None) must RAISE in the mock to reproduce the bug-1
#     crash trigger.
#
# With these three faithfulness properties, a regression that
# reintroduces either bug pattern would crash the relevant test.
# ---------------------------------------------------------------------------


# ----- Minimal EE-faithful mock -------------------------------------------

class _FakeNumber:
    """Mock ee.Number that RAISES on None — faithful to bug-1 EE crash.

    A regression that does `ee.Number(reduction.get(key))` against a
    dict where `key` is present-but-None will hit this raise. That's
    the catch-the-bug behaviour we need.
    """

    def __init__(self, value):
        if value is None:
            raise ValueError(
                "_FakeNumber: parameter required and may not be null "
                "(mock reproducing EE bug-1 'Number.neq: Parameter "
                "left is required and may not be null')."
            )
        if isinstance(value, _FakeNumber):
            value = value.value
        self.value = float(value)

    def _unwrap(self, other):
        return other.value if isinstance(other, _FakeNumber) else other

    def gt(self, other):
        return _FakeNumber(1 if self.value > self._unwrap(other) else 0)

    def gte(self, other):
        return _FakeNumber(1 if self.value >= self._unwrap(other) else 0)

    def subtract(self, other):
        return _FakeNumber(self.value - self._unwrap(other))

    def divide(self, other):
        return _FakeNumber(self.value / self._unwrap(other))

    # `And` (capitalised) mirrors ee.Number.And — server-side logical AND.
    def And(self, other):                                       # noqa: N802
        return _FakeNumber(
            1 if (self.value != 0 and self._unwrap(other) != 0) else 0
        )

    def floor(self):
        import math as _math
        return _FakeNumber(_math.floor(self.value))


def _fake_algorithms_if(cond, then_, else_):
    """Mock ee.Algorithms.If. Python's function-call semantics already
    evaluate both arg expressions before this function runs — faithful
    to EE's bug-2 server-side eager evaluation. We just select the right
    branch here."""
    cond_val = cond.value if isinstance(cond, _FakeNumber) else cond
    return then_ if cond_val else else_


class _FakeAlgorithms:
    If = staticmethod(_fake_algorithms_if)


class _FakeReducer:
    """Opaque reducer placeholder. `_server_side_hf` only passes these
    through to reduceRegion / reduceColumns; the mock collection ignores
    them and computes outputs from its own per-image scripts."""

    def combine(self, **_kw):
        return self

    def repeat(self, _n):
        return self


class _FakeReducerFactory:
    @staticmethod
    def mean():
        return _FakeReducer()

    @staticmethod
    def count():
        return _FakeReducer()

    @staticmethod
    def sum():
        return _FakeReducer()


class _FakeDict:
    """Mock ee.Dictionary that's FAITHFUL to EE's missing-key semantics.

    EE: `Dictionary.get(key)` (no default) RAISES on missing key
        ("Dictionary.get: Dictionary does not contain key: 'NO2'").
    EE: `Dictionary.get(key, default)` fires default ONLY on missing key
        — when key is present-but-null, .get returns null (the bug-1
        behaviour).

    Python's plain `dict.get(key)` returns None on missing — too lenient,
    would silently mask EE bug-2 in our tests. This class makes the
    missing-key case raise like EE does, so a regression that drops the
    `default=0.0` from `reduction.get(mean_key, 0.0)` will trigger the
    raise during Python's eager argument evaluation (which mirrors EE's
    server-side eager evaluation inside If).
    """

    def __init__(self, d: dict):
        self._d = d

    def get(self, key, *default):
        if default:
            # `default` supplied: fire on missing key only (faithful to
            # EE's get(key, default) which does NOT fire on present-null).
            return self._d.get(key, default[0])
        # No default: faithful to EE's `.get(key)` raising on missing.
        if key not in self._d:
            raise KeyError(
                f"_FakeDict.get: Dictionary does not contain key: "
                f"{key!r} (mock reproducing the EE bug-2 crash 'Dictionary.get: "
                f"Dictionary does not contain key')."
            )
        return self._d.get(key)


class _FakeImage:
    """One mock image. `.select(band)` no-ops; `.reduceRegion(...)` returns
    the caller-supplied reduction dict wrapped in a _FakeDict so its
    `.get` semantics match EE's. `.get("system:time_start")` returns the
    image's time_start property — every fake image carries one so the
    per_image map's day_bucket computation has something to operate on.
    """

    # Default time-start; tests that need per-image variation pass their
    # own values via the explicit `time_start` constructor kwarg. The
    # default lands all images on UTC day-bucket 0 (deterministic).
    def __init__(self, reduction: dict, time_start: int = 0):
        self._reduction = _FakeDict(reduction)
        self._props = {"system:time_start": time_start}

    def select(self, _band):
        return self

    def reduceRegion(self, **_kw):                              # noqa: N802
        return self._reduction

    def get(self, key):
        return self._props.get(key, 0)


class _FakeFilterEq:
    """Mock ee.Filter.eq — captures (prop, value) for FeatureCollection.filter()."""

    def __init__(self, prop: str, value):
        self.prop = prop
        # Unwrap _FakeNumber so equality compares to a plain int.
        self.value = value.value if isinstance(value, _FakeNumber) else value


class _FakeFilter:
    @staticmethod
    def eq(prop, value):
        return _FakeFilterEq(prop, value)


class _FakeFeature:
    def __init__(self, _geom, properties):
        self.properties = properties


class _FakeComputed:
    """Wraps a pre-computed dict to support `.getInfo() or {}` chain."""

    def __init__(self, value):
        self._value = value

    def getInfo(self):                                          # noqa: N802
        return self._value


class _FakeList:
    """Mock of EE's server-side list. Supports `.distinct()`."""

    def __init__(self, values):
        self.values = list(values)

    def distinct(self):
        seen: list = []
        for v in self.values:
            if v not in seen:
                seen.append(v)
        return _FakeList(seen)


class _FakeDictionaryConstructor:
    """Mock ee.Dictionary({...}). `.getInfo()` resolves nested _FakeList /
    _FakeNumber values to plain Python equivalents — same shape real EE
    returns from a server-side dict."""

    def __init__(self, mapping: dict):
        self._mapping = mapping

    def getInfo(self):                                          # noqa: N802
        out: dict = {}
        for k, v in self._mapping.items():
            if isinstance(v, _FakeList):
                out[k] = [
                    e.value if isinstance(e, _FakeNumber) else e
                    for e in v.values
                ]
            elif isinstance(v, _FakeNumber):
                out[k] = v.value
            else:
                out[k] = v
        return out


class _FakeImageCollection:
    """Eager Python iteration over fake images.

    `_server_side_hf` calls `.select(band).map(per_image).filter(...).
    aggregate_array(prop).distinct()` plus `ee.Dictionary({...}).getInfo()`.
    We execute that chain in Python, calling per_image on each image
    (which triggers the per_image code path in _server_side_hf, the
    Step C bug-catching surface).
    """

    def __init__(self, images: list[_FakeImage]):
        self.images = images
        self._mapped: list[_FakeFeature] | None = None

    def select(self, _band):
        return self

    def filterDate(self, _start, _end):                         # noqa: N802
        # Mocks ignore date filtering — tests pass time_range=None which
        # already skips chunking, but keep the method for defensive parity.
        return self

    def map(self, fn):
        new = _FakeImageCollection(self.images)
        new._mapped = [fn(img) for img in self.images]
        return new

    def filter(self, filter_obj: _FakeFilterEq):
        # Filter the mapped FeatureCollection by property == value.
        features = self._mapped or []
        new = _FakeImageCollection(self.images)
        new._mapped = [
            feat for feat in features
            if _fake_property_equals(feat.properties.get(filter_obj.prop), filter_obj.value)
        ]
        return new

    def aggregate_array(self, prop: str):                       # noqa: N802
        features = self._mapped or []
        values = []
        for feat in features:
            val = feat.properties.get(prop)
            if isinstance(val, _FakeNumber):
                val = val.value
            values.append(val)
        return _FakeList(values)


def _fake_property_equals(prop_value, expected) -> bool:
    """Compare a Feature property to a Filter.eq expected value, handling
    _FakeNumber wrapping on either side."""
    if isinstance(prop_value, _FakeNumber):
        prop_value = prop_value.value
    if isinstance(expected, _FakeNumber):
        expected = expected.value
    return prop_value == expected


@pytest.fixture
def patched_ee(monkeypatch):
    """Patch the EE module-level references in engine.core.repeatable_core
    so `_server_side_hf` runs against the faithful mock instead of real EE.

    Also patches site_buffer to a no-op (the mock collection ignores
    geometry anyway) — the real site_buffer would try to talk to EE.
    """
    fake_algorithms = _FakeAlgorithms()
    fake_reducer    = _FakeReducerFactory()

    # Reconstruct ee.* surface as a single object with the attributes
    # _server_side_hf reads: Number, Algorithms, Reducer, Feature, Filter,
    # Dictionary. (Filter and Dictionary added by M-TIER-A1 Step 8 Option A
    # — the new aggregation path uses fc.filter(ee.Filter.eq(...)) and
    # ee.Dictionary({...}).getInfo() to count distinct day-buckets.)
    class FakeEE:
        Number     = _FakeNumber
        Algorithms = fake_algorithms
        Reducer    = fake_reducer
        Feature    = _FakeFeature
        Filter     = _FakeFilter
        Dictionary = _FakeDictionaryConstructor

    monkeypatch.setattr("engine.core.repeatable_core.ee", FakeEE)
    monkeypatch.setattr(
        "engine.core.repeatable_core.site_buffer",
        lambda _centre, _radius_km: object(),                   # dummy geom
    )


# ----- Tests --------------------------------------------------------------

class TestServerSideHfEEBugCoverage:
    """D3.2 — coverage for the two Step C bugs."""

    _AOI = {"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 5.0}
    _BAND = "NO2"

    def test_server_side_hf_handles_all_masked_band(self, patched_ee) -> None:
        """Step C bug 1 reproduction: every image's reduceRegion returns
        the masked-band shape — count key present with value 0, mean key
        present with value None. Pre-fix this triggered
        `ee.Number(None).neq(...)` and crashed the map. Post-fix the
        Count-driven is_valid keeps the function safe.

        Faithfulness: the mock dict has `{band: None, band_count: 0}` —
        exactly EE's reduceRegion output when the band is fully masked.
        A regression that switches is_valid back to a sentinel-based
        `reduction.get(band, sentinel)` would call `_FakeNumber(None)`
        and crash, surfacing the regression.
        """
        from engine.core.repeatable_core import _server_side_hf

        # 10 images, all "masked band" shape.
        masked_reduction = {self._BAND: None, f"{self._BAND}_count": 0}
        images = [_FakeImage(masked_reduction) for _ in range(10)]
        ic = _FakeImageCollection(images)

        n_valid, hf = _server_side_hf(
            aoi=self._AOI,
            image_collection=ic,
            band=self._BAND,
            bg_median=5e-5,
            bg_std=1e-5,
            z_threshold=2.0,
            scale=1113.2,
        )
        assert n_valid == 0, (
            "Every image should be invalid (Count=0). A regression to "
            "sentinel-default null-checking would crash on _FakeNumber(None) "
            "instead of returning n_valid=0."
        )
        assert hf is None, "HF must be None when n_valid=0"

    def test_server_side_hf_handles_zero_valid_pixels_with_missing_key(
        self, patched_ee,
    ) -> None:
        """Step C bug 2 reproduction: some images return a reduceRegion
        dict where the mean key is ENTIRELY ABSENT (Count=0 case in EE).
        Pre-fix the eager-evaluated `reduction.get(mean_key)` inside If
        crashed on _FakeNumber(None). Post-fix the `default=0.0` in
        `reduction.get(mean_key, 0.0)` prevents the crash.

        Faithfulness: Python's function-call semantics evaluate ALL
        arguments before entering ee.Algorithms.If — same as EE's
        server-side eager evaluation. A regression that drops the
        `default=0.0` would call `reduction.get(mean_key)` → None →
        `_FakeNumber(None)` → raise, surfacing the regression.

        Mixed payload: 3 images have valid pixels (Count=4, Mean=7.5e-5,
        above threshold), 7 have zero valid pixels (key entirely
        absent — bug 2 trigger). Post-fix:
          - n_valid = 3
          - n_hot   = 3  (all valid images cross z = (7.5e-5 − 5e-5)/1e-5 = 2.5)
        Each image gets a distinct UTC time_start so the new date-counting
        path (Option A) attributes each to its own day-bucket — without
        spread, all images would collapse to one day and n_valid would
        be 1 even on the happy path. The original 100-cap concern is
        unaffected by the spread (we're well under 100 here).
        """
        from engine.core.repeatable_core import _server_side_hf

        # 3 images with valid mean + count; 7 with key entirely absent.
        valid_reduction = {self._BAND: 7.5e-5, f"{self._BAND}_count": 4}
        # KEY OBSERVATION: mean_key is *missing entirely* in this dict
        # (not present-and-None). That's the bug-2 shape EE produces
        # when its Mean reducer omits the band on zero pixels.
        missing_key_reduction = {f"{self._BAND}_count": 0}

        # Distinct UTC days for each image — one image per day-bucket so
        # the day-counting layer doesn't collapse the test.
        ms_day = 86_400_000
        images = (
            [_FakeImage(valid_reduction, time_start=i * ms_day) for i in range(3)]
            + [
                _FakeImage(missing_key_reduction, time_start=(i + 3) * ms_day)
                for i in range(7)
            ]
        )
        ic = _FakeImageCollection(images)

        n_valid, hf = _server_side_hf(
            aoi=self._AOI,
            image_collection=ic,
            band=self._BAND,
            bg_median=5e-5,
            bg_std=1e-5,
            z_threshold=2.0,
            scale=1113.2,
        )
        assert n_valid == 3, (
            "Only the 3 valid images should count. A regression that "
            "drops the `default=0.0` from reduction.get(mean_key, 0.0) "
            "would crash with _FakeNumber(None) on the 7 missing-key "
            "images instead of skipping them."
        )
        # All 3 valid images had mean=7.5e-5 ≥ threshold → all hot.
        assert hf == pytest.approx(1.0)

    def test_server_side_hf_no_artificial_cap(self, patched_ee) -> None:
        """Step C Finding 1 (the under-counting that motivated the
        whole refactor): the legacy _per_date_site_series capped at
        100 images via `.limit(100)`. _server_side_hf maps over the
        WHOLE collection — verify by feeding 500 images spread across
        500 distinct UTC days (post-Option-A date-counting semantics).

        Mixed valid/invalid 50/50, interleaved 1-day apart, so 250
        distinct valid days are seen — well past the legacy 100-cap
        that would have artificially clamped it.
        """
        from engine.core.repeatable_core import _server_side_hf

        valid_reduction   = {self._BAND: 6e-5, f"{self._BAND}_count": 4}
        invalid_reduction = {self._BAND: None, f"{self._BAND}_count": 0}

        # Interleave 250 valid + 250 invalid across 500 distinct UTC days.
        # Day 0 is valid, day 1 is invalid, day 2 is valid, ...
        ms_day = 86_400_000
        images: list[_FakeImage] = []
        for day in range(500):
            reduction = valid_reduction if day % 2 == 0 else invalid_reduction
            images.append(_FakeImage(reduction, time_start=day * ms_day))
        ic = _FakeImageCollection(images)
        assert len(images) == 500

        n_valid, hf = _server_side_hf(
            aoi=self._AOI,
            image_collection=ic,
            band=self._BAND,
            bg_median=5e-5,
            bg_std=1e-5,
            z_threshold=2.0,
            scale=1113.2,
        )
        assert n_valid == 250, (
            f"Expected all 250 valid DAYS to be counted (no cap, no .limit); "
            f"got {n_valid}. If this is ~100, the .limit(100) cap has been "
            f"reintroduced somewhere in _server_side_hf's chain."
        )
        # z = (6e-5 − 5e-5)/1e-5 = 1.0 < 2.0 → none hot.
        assert hf == pytest.approx(0.0)

    def test_server_side_hf_bg_std_zero_returns_n_valid_but_no_hf(
        self, patched_ee,
    ) -> None:
        """Sanity check the degenerate-background branch: n_valid still
        counted, HF returns None (no z computable). Not a bug-fix test
        but the degenerate-branch was added as part of the Step B
        refactor and would otherwise be uncovered. Ten images on ten
        distinct UTC days → n_valid = 10 (date count, not granule count)."""
        from engine.core.repeatable_core import _server_side_hf

        ms_day = 86_400_000
        valid_reduction = {self._BAND: 6e-5, f"{self._BAND}_count": 4}
        ic = _FakeImageCollection([
            _FakeImage(valid_reduction, time_start=i * ms_day) for i in range(10)
        ])

        n_valid, hf = _server_side_hf(
            aoi=self._AOI,
            image_collection=ic,
            band=self._BAND,
            bg_median=5e-5,
            bg_std=0.0,                # degenerate
            z_threshold=2.0,
            scale=1113.2,
        )
        assert n_valid == 10
        assert hf is None
