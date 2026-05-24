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

    def size(self):
        # M-UI-A1-SURFACE engine-gap fix: _server_side_hf now reads
        # chunk_ic.size() into the chunk_result dict to surface
        # granule_count. The mock returns a plain int that the
        # _FakeDictionaryConstructor passes through verbatim.
        return len(self.images)

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

        result = _server_side_hf(
            aoi=self._AOI,
            image_collection=ic,
            band=self._BAND,
            bg_median=5e-5,
            bg_std=1e-5,
            z_threshold=2.0,
            scale=1113.2,
        )
        assert result.n_valid_dates == 0, (
            "Every image should be invalid (Count=0). A regression to "
            "sentinel-default null-checking would crash on _FakeNumber(None) "
            "instead of returning n_valid_dates=0."
        )
        assert result.hf is None, "HF must be None when n_valid_dates=0"
        # M-UI-A1-SURFACE engine-gap: granule_count is the RAW image count
        # regardless of validity. 10 fully-masked images → 10 granules.
        assert result.granule_count == 10

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

        result = _server_side_hf(
            aoi=self._AOI,
            image_collection=ic,
            band=self._BAND,
            bg_median=5e-5,
            bg_std=1e-5,
            z_threshold=2.0,
            scale=1113.2,
        )
        assert result.n_valid_dates == 3, (
            "Only the 3 valid images should count. A regression that "
            "drops the `default=0.0` from reduction.get(mean_key, 0.0) "
            "would crash with _FakeNumber(None) on the 7 missing-key "
            "images instead of skipping them."
        )
        # All 3 valid images had mean=7.5e-5 ≥ threshold → all hot.
        assert result.hf == pytest.approx(1.0)
        assert result.granule_count == 10  # 3 valid + 7 invalid = 10 raw

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

        result = _server_side_hf(
            aoi=self._AOI,
            image_collection=ic,
            band=self._BAND,
            bg_median=5e-5,
            bg_std=1e-5,
            z_threshold=2.0,
            scale=1113.2,
        )
        assert result.n_valid_dates == 250, (
            f"Expected all 250 valid DAYS to be counted (no cap, no .limit); "
            f"got {result.n_valid_dates}. If this is ~100, the .limit(100) "
            f"cap has been reintroduced somewhere in _server_side_hf's chain."
        )
        # z = (6e-5 − 5e-5)/1e-5 = 1.0 < 2.0 → none hot.
        assert result.hf == pytest.approx(0.0)
        # M-UI-A1-SURFACE engine-gap: granule_count counts ALL raw images
        # regardless of validity (500 here = 250 valid + 250 invalid).
        assert result.granule_count == 500

    def test_server_side_hf_returns_n_valid_dates_and_granule_count(
        self, patched_ee,
    ) -> None:
        """M-UI-A1-SURFACE engine-gap fix (24 May 2026).

        Audit-transparency surface: the named-tuple return now carries
        both the distinct-dates count and the raw granule count. 100
        images clustered across 10 distinct UTC days mimics a daily
        product with ~10 swaths/day. Post-fix, the engine reports
        BOTH numbers so reviewers can see the dates-vs-granules ratio.
        """
        from engine.core.repeatable_core import _server_side_hf

        ms_day = 86_400_000
        valid_reduction = {self._BAND: 6e-5, f"{self._BAND}_count": 4}
        # 100 images, 10 per day across 10 distinct UTC days.
        images = [
            _FakeImage(valid_reduction, time_start=(i // 10) * ms_day)
            for i in range(100)
        ]
        ic = _FakeImageCollection(images)

        result = _server_side_hf(
            aoi=self._AOI,
            image_collection=ic,
            band=self._BAND,
            bg_median=5e-5,
            bg_std=1e-5,
            z_threshold=2.0,
            scale=1113.2,
        )
        assert result.n_valid_dates == 10, (
            "10 distinct UTC days; the 10×10 granule fan-out must NOT "
            "inflate the dates count (Option-A semantic lock)."
        )
        assert result.granule_count == 100, (
            "All 100 raw images must be counted regardless of per-date "
            "collapsing. A regression that pre-dedups by day would drop "
            "this to 10 and lose the audit-transparency signal."
        )

    def test_server_side_hf_granule_count_vs_dates_diverges_for_multi_swath(
        self, patched_ee,
    ) -> None:
        """Same engine-gap fix, multi-swath scenario.

        Mimics MAIAC AOD's ~58 granules/day cadence at lower scale: 580
        granules clustered on 10 distinct UTC days. The two numbers must
        diverge in the expected way — n_valid_dates=10, granule_count=580
        — so the close-entry's "granule count is informational; dates is
        the score-bearing number" story is verifiable from the engine
        output, not just from the docstring.
        """
        from engine.core.repeatable_core import _server_side_hf

        ms_day = 86_400_000
        valid_reduction = {self._BAND: 6e-5, f"{self._BAND}_count": 4}
        # 580 images, 58 per day across 10 distinct UTC days.
        images = [
            _FakeImage(valid_reduction, time_start=(i // 58) * ms_day)
            for i in range(580)
        ]
        ic = _FakeImageCollection(images)

        result = _server_side_hf(
            aoi=self._AOI,
            image_collection=ic,
            band=self._BAND,
            bg_median=5e-5,
            bg_std=1e-5,
            z_threshold=2.0,
            scale=1113.2,
        )
        assert result.n_valid_dates == 10
        assert result.granule_count == 580
        # The numbers must diverge — that's the whole point of the fix.
        assert result.granule_count > result.n_valid_dates

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

        result = _server_side_hf(
            aoi=self._AOI,
            image_collection=ic,
            band=self._BAND,
            bg_median=5e-5,
            bg_std=0.0,                # degenerate
            z_threshold=2.0,
            scale=1113.2,
        )
        assert result.n_valid_dates == 10
        assert result.hf is None


# ---------------------------------------------------------------------------
# v1x followup #1 — per-indicator chunk size lookup for _server_side_hf
# ---------------------------------------------------------------------------


class TestServerSideHfChunkSizeLookup:
    """v1x followup #1 (24 May 2026).

    The chunk size for `_server_side_hf` is now per-indicator, sourced
    from `engine.constants.SERVER_SIDE_HF_CHUNK_DAYS_PER_INDICATOR`.
    Low-cadence products (~1 image/day) get `chunk_days = 90` so a 90-day
    window runs as a single chunk — no `_date_chunks_iso`, no per-chunk
    `filterDate`, no 9× round-trip overhead. High-cadence multi-swath
    products (AOD, CH4) stay at `chunk_days = 10` to bound EE compute.

    These tests pin the dispatch by spying on `_date_chunks_iso` and
    counting `filterDate` invocations on the fake collection.
    """

    _AOI = {"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 5.0}
    _BAND = "NO2"
    _TIME_RANGE = ("2026-02-22", "2026-05-23")    # 90 days inclusive
    _MS_DAY = 86_400_000

    def _make_collection(
        self, n_images: int, monkeypatch,
    ) -> _FakeImageCollection:
        """Build a mock collection of n_images valid images, each on a
        distinct UTC day, with `.filterDate` instrumented to count calls."""
        valid_reduction = {self._BAND: 6e-5, f"{self._BAND}_count": 4}
        images = [
            _FakeImage(valid_reduction, time_start=i * self._MS_DAY)
            for i in range(n_images)
        ]
        ic = _FakeImageCollection(images)
        # Monkey-patch filterDate to count calls (default mock just returns
        # self; that's fine, we only need the call count for the dispatch
        # assertion).
        ic._filter_calls = 0
        original_filterDate = ic.filterDate                     # noqa: N806
        def counting_filterDate(start, end):                    # noqa: N802
            ic._filter_calls += 1
            return original_filterDate(start, end)
        monkeypatch.setattr(ic, "filterDate", counting_filterDate)
        return ic

    def test_server_side_hf_single_chunk_path_for_low_cadence_indicator(
        self, patched_ee, monkeypatch,
    ) -> None:
        """`air.no2` has chunk_days = 90 in the lookup. With a 90-day
        window, `_date_chunks_iso` must NOT be called and `filterDate`
        must NOT fire on the collection — the upstream-filtered
        `ic_window` is reused as-is."""
        from engine.core.repeatable_core import _server_side_hf
        import engine.core.repeatable_core as _rc

        spy_calls: list = []
        original = _rc._date_chunks_iso
        def spy(*args, **kw):
            spy_calls.append((args, kw))
            return original(*args, **kw)
        monkeypatch.setattr(_rc, "_date_chunks_iso", spy)

        ic = self._make_collection(100, monkeypatch)
        result = _server_side_hf(
            aoi=self._AOI, image_collection=ic, band=self._BAND,
            bg_median=5e-5, bg_std=1e-5,
            z_threshold=2.0, scale=1113.2,
            time_range=self._TIME_RANGE,
            indicator_id="air.no2",
        )

        assert spy_calls == [], (
            "_date_chunks_iso must NOT be called when chunk_days >= window_days"
        )
        assert ic._filter_calls == 0, (
            "filterDate must NOT fire on the single-chunk fast path"
        )
        # All 100 distinct UTC days counted (the per_image map ran once
        # over the full collection).
        assert result.n_valid_dates == 100
        # z = (6e-5 − 5e-5) / 1e-5 = 1.0 < 2.0 → no hot days.
        assert result.hf == pytest.approx(0.0)

    def test_server_side_hf_chunked_path_for_high_cadence_indicator(
        self, patched_ee, monkeypatch,
    ) -> None:
        """`air.aod` has chunk_days = 10 in the lookup. A 90-day window
        → 9 chunks → `_date_chunks_iso` IS called, `filterDate` fires 9
        times, and the set-union-across-chunks logic dedupes day buckets
        correctly even when the mock filterDate is a no-op."""
        from engine.core.repeatable_core import _server_side_hf
        import engine.core.repeatable_core as _rc

        spy_calls: list = []
        original = _rc._date_chunks_iso
        def spy(time_range, chunk_days):
            spy_calls.append({"time_range": time_range, "chunk_days": chunk_days})
            return original(time_range, chunk_days=chunk_days)
        monkeypatch.setattr(_rc, "_date_chunks_iso", spy)

        ic = self._make_collection(50, monkeypatch)
        result = _server_side_hf(
            aoi=self._AOI, image_collection=ic, band=self._BAND,
            bg_median=5e-5, bg_std=1e-5,
            z_threshold=2.0, scale=1113.2,
            time_range=self._TIME_RANGE,
            indicator_id="air.aod",
        )

        assert len(spy_calls) == 1, (
            "_date_chunks_iso must be called exactly once on the chunked path"
        )
        assert spy_calls[0]["chunk_days"] == 10, (
            "chunk_days for air.aod must be 10 per the per-indicator lookup"
        )
        assert ic._filter_calls == 9, (
            f"Expected 9 filterDate calls for 90-day window / 10-day chunks; "
            f"got {ic._filter_calls}"
        )
        # The mock filterDate is a no-op (returns full collection), so each
        # of the 9 chunks sees all 50 images. Union-across-chunks dedupes
        # to 50 distinct day buckets. This is also the property that
        # guarantees real-EE chunking produces the same total as a single
        # full-window call — proven here by construction.
        assert result.n_valid_dates == 50

    def test_server_side_hf_unknown_indicator_falls_through_to_default(
        self, patched_ee, monkeypatch,
    ) -> None:
        """An indicator_id absent from the lookup dict (e.g. a future
        indicator added to NATURE_INDICATOR_CONFIG before someone
        remembers to update the chunk-size lookup) must fall through to
        `SERVER_SIDE_HF_CHUNK_DAYS_DEFAULT = 10`, NOT raise KeyError,
        NOT crash, NOT silently skip chunking."""
        from engine.constants import SERVER_SIDE_HF_CHUNK_DAYS_DEFAULT
        from engine.core.repeatable_core import _server_side_hf
        import engine.core.repeatable_core as _rc

        spy_calls: list = []
        original = _rc._date_chunks_iso
        def spy(time_range, chunk_days):
            spy_calls.append({"chunk_days": chunk_days})
            return original(time_range, chunk_days=chunk_days)
        monkeypatch.setattr(_rc, "_date_chunks_iso", spy)

        ic = self._make_collection(20, monkeypatch)
        result = _server_side_hf(
            aoi=self._AOI, image_collection=ic, band=self._BAND,
            bg_median=5e-5, bg_std=1e-5,
            z_threshold=2.0, scale=1113.2,
            time_range=self._TIME_RANGE,
            indicator_id="air.fictional_future_indicator",
        )

        assert len(spy_calls) == 1
        assert spy_calls[0]["chunk_days"] == SERVER_SIDE_HF_CHUNK_DAYS_DEFAULT
        # 90-day window / 10-day default chunks = 9 chunks.
        assert ic._filter_calls == 9
        del result  # unused; suppress the assignment-not-used hint.


# ---------------------------------------------------------------------------
# v1x followup #2 — concurrent chunks within an indicator
# ---------------------------------------------------------------------------


class TestServerSideHfChunkConcurrency:
    """v1x followup #2 (24 May 2026).

    When `_server_side_hf` takes the chunked path (chunk_days < window_days,
    so `len(chunks) > 1`), each chunk's getInfo() runs concurrently via a
    ThreadPoolExecutor. The single-chunk fast paths (low-cadence indicators
    + the no-time_range path) keep their inline execution.

    These tests pin three properties:
      - chunked path actually instantiates the executor and submits each
        chunk to it (3.3a),
      - fast path skips the executor entirely (3.3b),
      - set-union semantics for day_buckets across chunks dedupe correctly
        even when two chunks return overlapping day_buckets (3.3c).
    """

    _AOI = {"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 5.0}
    _BAND = "NO2"
    _TIME_RANGE = ("2026-02-22", "2026-05-23")    # 90 days inclusive
    _MS_DAY = 86_400_000

    def _make_collection(self, n_images: int) -> _FakeImageCollection:
        valid_reduction = {self._BAND: 6e-5, f"{self._BAND}_count": 4}
        images = [
            _FakeImage(valid_reduction, time_start=i * self._MS_DAY)
            for i in range(n_images)
        ]
        return _FakeImageCollection(images)

    def test_server_side_hf_chunked_path_runs_concurrently_for_aod(
        self, patched_ee, monkeypatch,
    ) -> None:
        """`air.aod` triggers 9 chunks (90-day window / 10-day chunks).
        Each chunk MUST be submitted to a ThreadPoolExecutor and the
        per-chunk helper MUST be invoked exactly 9 times."""
        import concurrent.futures as _cf
        import engine.core.repeatable_core as _rc
        from engine.core.repeatable_core import _server_side_hf

        executor_instantiations = []
        real_pool = _cf.ThreadPoolExecutor

        class _SpyPool(real_pool):
            def __init__(self, *a, **kw):
                executor_instantiations.append(kw)
                super().__init__(*a, **kw)

        monkeypatch.setattr(
            _rc.concurrent.futures, "ThreadPoolExecutor", _SpyPool,
        )

        chunk_calls = []
        real_chunker = _rc._process_chunk_for_server_side_hf

        def spy_chunker(selected, chunk, per_image):
            chunk_calls.append(chunk)
            return real_chunker(selected, chunk, per_image)

        monkeypatch.setattr(
            _rc, "_process_chunk_for_server_side_hf", spy_chunker,
        )

        ic = self._make_collection(50)
        result = _server_side_hf(
            aoi=self._AOI, image_collection=ic, band=self._BAND,
            bg_median=5e-5, bg_std=1e-5,
            z_threshold=2.0, scale=1113.2,
            time_range=self._TIME_RANGE,
            indicator_id="air.aod",
        )

        # ThreadPoolExecutor instantiated exactly once (one with-block),
        # max_workers capped at the 9-chunk count (not the constant ceiling).
        assert len(executor_instantiations) == 1
        assert executor_instantiations[0].get("max_workers") == 9
        # Per-chunk helper called once per chunk (9 chunks for AOD's
        # 90-day window / 10-day chunk_days).
        assert len(chunk_calls) == 9
        # Sanity: each chunk_calls entry is a real (iso_start, iso_end)
        # tuple, not None — the chunked path never feeds None to the
        # helper (that's reserved for the fast path).
        assert all(
            isinstance(c, tuple) and len(c) == 2 for c in chunk_calls
        )
        # Regression: result must match the synchronous baseline. The
        # mock filterDate is a no-op so every chunk sees all 50 images;
        # set-union dedupes to 50 distinct days.
        assert result.n_valid_dates == 50

    def test_server_side_hf_fast_path_does_not_use_executor(
        self, patched_ee, monkeypatch,
    ) -> None:
        """`air.no2` has chunk_days = 90 → single chunk = fast path.
        The ThreadPoolExecutor MUST NOT be instantiated (no thread-pool
        creation overhead for indicators that fit in one call)."""
        import concurrent.futures as _cf
        import engine.core.repeatable_core as _rc
        from engine.core.repeatable_core import _server_side_hf

        executor_instantiations = []
        real_pool = _cf.ThreadPoolExecutor

        class _SpyPool(real_pool):
            def __init__(self, *a, **kw):
                executor_instantiations.append(kw)
                super().__init__(*a, **kw)

        monkeypatch.setattr(
            _rc.concurrent.futures, "ThreadPoolExecutor", _SpyPool,
        )

        chunk_calls = []
        real_chunker = _rc._process_chunk_for_server_side_hf

        def spy_chunker(selected, chunk, per_image):
            chunk_calls.append(chunk)
            return real_chunker(selected, chunk, per_image)

        monkeypatch.setattr(
            _rc, "_process_chunk_for_server_side_hf", spy_chunker,
        )

        ic = self._make_collection(50)
        result = _server_side_hf(
            aoi=self._AOI, image_collection=ic, band=self._BAND,
            bg_median=5e-5, bg_std=1e-5,
            z_threshold=2.0, scale=1113.2,
            time_range=self._TIME_RANGE,
            indicator_id="air.no2",
        )

        assert executor_instantiations == [], (
            "Fast path must not instantiate ThreadPoolExecutor"
        )
        # Single inline call with `chunk=None` (the fast-path sentinel
        # the chunked-vs-fast dispatch uses).
        assert chunk_calls == [None]
        assert result.n_valid_dates == 50

    def test_server_side_hf_chunk_results_union_correctly_under_concurrency(
        self, patched_ee, monkeypatch,
    ) -> None:
        """When two chunks happen to compute the same day_bucket (e.g. a
        cross-chunk-boundary granule), the set-union accumulator MUST
        deduplicate. A regression that switched the union to e.g. list
        extension would double-count those days and inflate
        n_valid_dates."""
        import engine.core.repeatable_core as _rc
        from engine.core.repeatable_core import _server_side_hf

        # Per-chunk synthetic return values with overlapping day_buckets.
        # 9 chunks (AOD path); the 1st and 2nd chunks share day 100; the
        # 2nd and 3rd chunks share day 200. Set union must collapse both
        # overlaps. Naive list-concat would yield 7 days instead of 5
        # across the first 3 chunks (the rest are empty).
        per_chunk_returns = [
            ({100, 50}, {100}, 10),       # chunk 0
            ({100, 200, 75}, {100}, 8),    # chunk 1 — shares 100 with chunk 0
            ({200, 99}, set(), 5),         # chunk 2 — shares 200 with chunk 1
            (set(), set(), 0),              # remaining 6 chunks empty
            (set(), set(), 0),
            (set(), set(), 0),
            (set(), set(), 0),
            (set(), set(), 0),
            (set(), set(), 0),
        ]
        call_idx = {"i": 0}

        def fake_chunker(selected, chunk, per_image):
            i = call_idx["i"]
            call_idx["i"] += 1
            return per_chunk_returns[i]

        monkeypatch.setattr(
            _rc, "_process_chunk_for_server_side_hf", fake_chunker,
        )

        ic = self._make_collection(10)  # contents irrelevant — chunker mocked
        result = _server_side_hf(
            aoi=self._AOI, image_collection=ic, band=self._BAND,
            bg_median=5e-5, bg_std=1e-5,
            z_threshold=2.0, scale=1113.2,
            time_range=self._TIME_RANGE,
            indicator_id="air.aod",
        )

        # Union: {100, 50} ∪ {100, 200, 75} ∪ {200, 99} = {50, 75, 99, 100, 200}
        # = 5 distinct days. (List-concat regression would give 7.)
        assert result.n_valid_dates == 5
        # Hot days: {100} ∪ {100} ∪ {} = {100} = 1 distinct hot day.
        # hf = 1 / 5 = 0.2.
        assert result.hf == pytest.approx(0.2)
        # Granule count is a plain sum (no dedup) — 10 + 8 + 5 = 23.
        assert result.granule_count == 23


# ---------------------------------------------------------------------------
# v1x followup #13 — filterBounds at the analysis envelope in six_step
# ---------------------------------------------------------------------------


class TestSixStepFilterBoundsScope:
    """v1x followup #13 (24 May 2026). six_step now applies
    filterBounds(analysis_envelope) immediately after filterDate, where
    analysis_envelope = site_buffer(centre, r_background_km). Two
    invariants the test pins:

      - filterBounds IS called (regression guard against the pre-#13
        state where the orchestrator iterated the full global granule
        pool, e.g. ~120K MAIAC granules for a 90-day window).
      - The geometry is the analysis envelope (r_background_km), NOT
        the site buffer (r_site_km). Filtering on site_buffer alone
        would drop granules that intersect only the background ring,
        silently changing background_value's reduction.
    """

    def test_six_step_filterBounds_uses_analysis_envelope_not_site_buffer(
        self, monkeypatch,
    ) -> None:
        import engine.core.repeatable_core as rc

        # Capture filterBounds calls on the IC.
        filter_bounds_calls = []
        date_calls = []

        class _SpyIc:
            def filterDate(self, start, end):
                date_calls.append((start, end))
                return self
            def filterBounds(self, geom):
                filter_bounds_calls.append(geom)
                return self

        # Capture every site_buffer() invocation. The only one inside
        # six_step's own body is the envelope construction; site_value
        # and background_value's internal site_buffer / background_ring
        # calls are stubbed away below. The envelope sentinel implements
        # .bounds() (returns itself) because six_step now calls
        # filterBounds(envelope.bounds()) per the MODIS-projection fix.
        class _EnvelopeSentinel:
            def bounds(self):
                return self

        sentinel_envelope = _EnvelopeSentinel()
        captured_radius_km = []

        def fake_site_buffer(centre, radius_km):
            captured_radius_km.append(radius_km)
            return sentinel_envelope

        monkeypatch.setattr(rc, "site_buffer", fake_site_buffer)

        # Stub the rest of six_step's downstream surface — they have
        # their own coverage and would otherwise need full EE mocks.
        monkeypatch.setattr(
            rc, "site_value",
            lambda aoi, ic, band, scale: 1.0,
        )
        monkeypatch.setattr(
            rc, "background_value",
            lambda aoi, ic, band, seasonal, scale: (0.5, 0.1),
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
            rc, "compute_indicator_confidence",
            lambda **kw: 0.8,
        )

        aoi = {"centre": {"lat": -15.78, "lon": -47.80}, "radius_km": 43.1}
        rc.six_step(
            aoi=aoi, image_collection=_SpyIc(), band="some_band",
            time_range=("2026-01-01", "2026-04-01"), ee_client=None,
            indicator_id="air.no2",
        )

        # filterDate fired once (regression guard for the date filter
        # itself — the new filterBounds line sits immediately after it).
        assert date_calls == [("2026-01-01", "2026-04-01")]

        # filterBounds fired exactly once with the envelope sentinel,
        # NOT a separate object derived from the site buffer.
        assert filter_bounds_calls == [sentinel_envelope]

        # Envelope radius = min(BACKGROUND_RING_RADIUS_MULTIPLE * 43.1,
        # BACKGROUND_RING_MAX_KM) = min(215.5, 200.0) = 200.0. Pins that
        # six_step picks the larger envelope, not the smaller site_buffer
        # radius (43.1) — the key safety property of the fix.
        assert captured_radius_km == [200.0]

    def test_six_step_filterBounds_envelope_for_small_buffer_below_max(
        self, monkeypatch,
    ) -> None:
        """At small site radii (e.g. Sapezal r=5 km) the envelope falls
        below the 200 km cap and equals 5 × radius_km = 25 km. Pins the
        formula on the non-clamped branch."""
        import engine.core.repeatable_core as rc

        class _SpyIc:
            def filterDate(self, *_a, **_kw): return self
            def filterBounds(self, _g): return self

        class _EnvelopeSentinel:
            def bounds(self): return self

        captured_radius_km = []
        monkeypatch.setattr(
            rc, "site_buffer",
            lambda centre, radius_km: (
                captured_radius_km.append(radius_km) or _EnvelopeSentinel()
            ),
        )
        monkeypatch.setattr(
            rc, "site_value",
            lambda aoi, ic, band, scale: 1.0,
        )
        monkeypatch.setattr(
            rc, "background_value",
            lambda aoi, ic, band, seasonal, scale: (0.5, 0.1),
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
            rc, "compute_indicator_confidence",
            lambda **kw: 0.8,
        )

        aoi = {"centre": {"lat": -13.5, "lon": -58.8}, "radius_km": 5.0}
        rc.six_step(
            aoi=aoi, image_collection=_SpyIc(), band="some_band",
            time_range=("2026-01-01", "2026-04-01"), ee_client=None,
            indicator_id="air.no2",
        )

        # min(5 * 5.0, 200.0) = 25.0 — the unclamped 5× branch.
        assert captured_radius_km == [25.0]
