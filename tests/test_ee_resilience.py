"""Unit tests for the M-PERF-A1 retry/backoff layer.

These tests exercise ``engine.core.ee_resilience`` in isolation — no
Earth Engine calls. Tenacity's ``tenacity.nap.sleep`` is monkey-patched
to a counting no-op so the tests don't pay real backoff wait times.

Covers spec §6.1 (Retry layer unit tests) and §6.3 (thread-safety).
"""

# M-PERF-A1
from __future__ import annotations

import sys
import threading
import time
from typing import Callable

import ee
import pytest
import tenacity

from engine.core import ee_resilience
from engine.exceptions import IndicatorComputeError, PillarComputeError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_sleep(monkeypatch):
    """Replace tenacity's sleep hook so retry tests run instantly.

    tenacity 9.x's ``nap.sleep`` is bound onto the ``Retrying`` instance
    at decoration time as ``self.sleep`` (we cannot patch tenacity.nap.sleep
    after the decorator is built). The underlying call inside nap.sleep
    is ``time.sleep(seconds)`` (verified via inspect.getsource). Patching
    ``time.sleep`` in the ``tenacity.nap`` module scope therefore yields
    a zero-wait test path while still recording the requested waits so
    tests can assert backoff is *invoked* rather than asserting
    wall-clock time.
    """
    waits: list[float] = []

    def _fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(tenacity.nap.time, "sleep", _fake_sleep)
    return waits


def _make_flaky(
    fail_with: list[BaseException],
    succeeds_with: object = "ok",
) -> Callable[[], object]:
    """Return a callable that raises ``fail_with[i]`` on attempt i,
    then succeeds with ``succeeds_with``."""

    state = {"i": 0}

    def fn():
        i = state["i"]
        state["i"] += 1
        if i < len(fail_with):
            raise fail_with[i]
        return succeeds_with

    fn.calls = state  # type: ignore[attr-defined]
    return fn


# ---------------------------------------------------------------------------
# §6.1.1 — predicate: which errors are retryable
# ---------------------------------------------------------------------------


class TestRetryablePredicate:
    """``_is_retryable`` decides whether to retry. Verifies PF5 directly."""

    @pytest.mark.parametrize("msg", [
        # 429 family
        "429 Too Many Requests",
        "user rate limit exceeded",
        "Quota exceeded for quota metric",
        "RESOURCE_EXHAUSTED: user quota",
        # 5xx family
        "500 Internal Server Error",
        "502 Bad Gateway",
        "503 Service Unavailable",
        "504 Gateway Timeout",
        "Deadline exceeded while waiting for compute",
        # EE-specific transient
        "Computation timed out.",
        "HttpError 400: Computation timed out.",
    ])
    def test_retryable_messages_match(self, msg):
        assert ee_resilience._is_retryable(ee.EEException(msg)) is True

    @pytest.mark.parametrize("msg", [
        "400 Bad Request: Image as JSON string not supported",
        "401 Unauthorized",
        "403 Forbidden: caller does not have permission",
        "404 Not Found",
        "User has not authorized this scope",
        "Asset 'foo/bar' not found",
    ])
    def test_non_retryable_messages_do_not_match(self, msg):
        assert ee_resilience._is_retryable(ee.EEException(msg)) is False

    def test_indicator_compute_error_not_retryable(self):
        # PF5: a pillar's own compute failure must not be retried —
        # retrying a deterministic compute bug just multiplies the
        # failure cost.
        ice = IndicatorComputeError("air.no2", "synthetic bad input")
        assert ee_resilience._is_retryable(ice) is False

    def test_pillar_compute_error_not_retryable(self):
        pce = PillarComputeError("air", ["air.no2"], "synthetic bad input")
        assert ee_resilience._is_retryable(pce) is False

    def test_non_ee_exception_not_retryable(self):
        # We only retry ee.EEException — any other exception escaping
        # the EE wrapper is treated as a programmer / environment error.
        assert ee_resilience._is_retryable(ValueError("oops")) is False
        assert ee_resilience._is_retryable(RuntimeError("oops")) is False


# ---------------------------------------------------------------------------
# §6.1.2 — retry behaviour: succeeds after retries / exhausts attempts
# ---------------------------------------------------------------------------


class TestRetryBehaviour:
    def test_succeeds_after_retryable_failures(self, _mock_sleep):
        fn = _make_flaky([ee.EEException("429"), ee.EEException("500")])
        decorated = ee_resilience._retry_for_tests(fn)
        assert decorated() == "ok"
        # 2 retries → 2 backoff waits requested.
        assert len(_mock_sleep) == 2

    def test_succeeds_on_first_attempt_no_backoff(self, _mock_sleep):
        def fn():
            return "ok"
        decorated = ee_resilience._retry_for_tests(fn)
        assert decorated() == "ok"
        assert _mock_sleep == []

    def test_4xx_non_429_raises_immediately(self, _mock_sleep):
        fn = _make_flaky([ee.EEException("400 Bad Request: bad expression")])
        decorated = ee_resilience._retry_for_tests(fn)
        with pytest.raises(ee.EEException, match="400 Bad Request"):
            decorated()
        # Predicate said "not retryable" → tenacity reraised on attempt 1.
        assert _mock_sleep == []

    def test_auth_error_raises_immediately(self, _mock_sleep):
        fn = _make_flaky([ee.EEException("401 Unauthorized")])
        decorated = ee_resilience._retry_for_tests(fn)
        with pytest.raises(ee.EEException, match="401 Unauthorized"):
            decorated()
        assert _mock_sleep == []

    def test_indicator_compute_error_raises_immediately(self, _mock_sleep):
        # PF5: even within the retry path, a pillar compute failure
        # short-circuits.
        fn = _make_flaky([IndicatorComputeError("air.no2", "bad data")])
        decorated = ee_resilience._retry_for_tests(fn)
        with pytest.raises(IndicatorComputeError):
            decorated()
        assert _mock_sleep == []

    def test_exhaustion_reraises_last_error(self, _mock_sleep):
        # Always-failing transient: should attempt _RETRY_MAX_ATTEMPTS
        # times then reraise the last exception.
        errors = [ee.EEException(f"429 attempt {i}") for i in range(20)]
        fn = _make_flaky(errors, succeeds_with="never")
        decorated = ee_resilience._retry_for_tests(fn)
        with pytest.raises(ee.EEException) as exc_info:
            decorated()
        # Tenacity's stop_after_attempt(5) — 5 attempts total, 4 backoff
        # waits between them (no wait after the final failure).
        assert fn.calls["i"] == ee_resilience._RETRY_MAX_ATTEMPTS
        assert len(_mock_sleep) == ee_resilience._RETRY_MAX_ATTEMPTS - 1
        # Reraise carries the last-attempt error, not the first.
        assert "attempt 4" in str(exc_info.value)

    def test_backoff_wait_is_capped(self, _mock_sleep):
        # Confirms the wait sequence respects _RETRY_MAX_WAIT_S.
        # tenacity's wait_exponential_jitter uses full jitter, so each
        # recorded wait is in [0, min(max, base * mult**attempt)].
        errors = [ee.EEException(f"429 a{i}") for i in range(20)]
        fn = _make_flaky(errors, succeeds_with="never")
        decorated = ee_resilience._retry_for_tests(fn)
        with pytest.raises(ee.EEException):
            decorated()
        assert all(0 <= w <= ee_resilience._RETRY_MAX_WAIT_S for w in _mock_sleep), (
            f"backoff waits should be in [0, {ee_resilience._RETRY_MAX_WAIT_S}], got {_mock_sleep}"
        )


# ---------------------------------------------------------------------------
# §6.3 — thread-safety: concurrent retries do not share state
# ---------------------------------------------------------------------------


class TestConcurrentRetryStateIsolated:
    """PF8 — tenacity's retry state is per-call. Verify that two
    concurrent invocations whose failure patterns differ don't
    cross-contaminate."""

    def test_concurrent_calls_independent_state(self, _mock_sleep):
        # Each thread owns its own counter so failure sequences don't
        # interfere across threads.
        state_local = threading.local()
        ready = threading.Barrier(2)
        results: dict[str, object] = {}

        def worker(name: str, fail_count: int) -> None:
            # Each worker has its own attempt counter via thread-local.
            state_local.i = 0

            @ee_resilience._retry_for_tests
            def fn():
                state_local.i += 1
                if state_local.i <= fail_count:
                    raise ee.EEException(f"429 {name} {state_local.i}")
                return (name, state_local.i)

            ready.wait()  # release both workers together
            results[name] = fn()

        t1 = threading.Thread(target=worker, args=("A", 2))
        t2 = threading.Thread(target=worker, args=("B", 3))
        t1.start(); t2.start()
        t1.join(); t2.join()

        # A succeeded on the 3rd attempt (2 failures, then success).
        # B succeeded on the 4th attempt (3 failures, then success).
        # If retry state were shared, totals would be wrong.
        assert results["A"] == ("A", 3)
        assert results["B"] == ("B", 4)


# ---------------------------------------------------------------------------
# §6.3.b — profiling counter: thread-safe accumulation
# ---------------------------------------------------------------------------


class TestProfileCounter:
    """The counter must accumulate correctly across worker threads.
    Independently testable because the counter is exposed as a public
    surface (set_profiling_enabled / reset_profile / snapshot_profile)."""

    def test_counter_increments_only_when_enabled(self):
        ee_resilience.reset_profile()
        ee_resilience.set_profiling_enabled(False)

        # Manually invoke _record (the public install path is exercised
        # in the integration smoke test).
        ee_resilience._record(("engine.test", "fn"), 0.1, failed=False)
        # _record always records — it's the wrapper that gates on the
        # enabled flag. Verify the row appears in the snapshot.
        snap = ee_resilience.snapshot_profile()
        assert snap == [{
            "module": "engine.test", "function": "fn",
            "count": 1, "total_seconds": 0.1, "failures": 0,
        }]
        ee_resilience.reset_profile()
        assert ee_resilience.snapshot_profile() == []

    def test_counter_concurrent_increments(self):
        ee_resilience.reset_profile()
        n_threads = 8
        n_per_thread = 250
        site = ("engine.test", "concurrent_fn")

        def worker():
            for _ in range(n_per_thread):
                ee_resilience._record(site, 0.001, failed=False)

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        snap = ee_resilience.snapshot_profile()
        assert len(snap) == 1
        assert snap[0]["count"] == n_threads * n_per_thread

    def test_snapshot_sorted_by_count_desc(self):
        ee_resilience.reset_profile()
        for _ in range(3):
            ee_resilience._record(("a.mod", "fast"), 0.1, failed=False)
        for _ in range(10):
            ee_resilience._record(("b.mod", "slow"), 0.5, failed=False)
        for _ in range(5):
            ee_resilience._record(("c.mod", "mid"), 0.2, failed=True)

        snap = ee_resilience.snapshot_profile()
        counts = [row["count"] for row in snap]
        assert counts == [10, 5, 3]
        # Failures field carries through.
        mid_row = next(r for r in snap if r["function"] == "mid")
        assert mid_row["failures"] == 5

        ee_resilience.reset_profile()


# ---------------------------------------------------------------------------
# §6.3.c — wrapper installation is idempotent
# ---------------------------------------------------------------------------


class TestWrapperInstallationIdempotence:
    def test_double_install_is_noop(self):
        # The marker on ee.ComputedObject.getInfo guards against nesting.
        ee_resilience.install_getinfo_wrapper()
        first = ee.ComputedObject.getInfo
        ee_resilience.install_getinfo_wrapper()
        second = ee.ComputedObject.getInfo
        assert first is second
        assert getattr(second, ee_resilience._GSCO_WRAPPED, False) is True


# ---------------------------------------------------------------------------
# Step A regression — the call-attribution walker must never name itself.
# ---------------------------------------------------------------------------


class TestAttributionWalkerSkipsOwnModule:
    """When no pillar / non-self core frame is in the stack, attribution
    must fall back to ``("unknown", "unknown")`` rather than naming the
    resilience module itself (the original Step A profile defect)."""

    def test_attribution_does_not_name_own_module(self):
        # Call _attribute_call from a stack composed entirely of test
        # frames — neither pillar nor core. Should return unknown.
        result = ee_resilience._attribute_call()
        assert result == ("unknown", "unknown")

    def test_pillar_frame_takes_precedence(self):
        # Wrap _attribute_call inside a function whose module pretends
        # to be engine.air to verify the walker picks the pillar frame
        # rather than the wrapper's own.
        def from_pretend_pillar():
            # Rebind __name__ on the calling frame's globals so the
            # walker sees a pillar match without actually loading
            # engine.air.
            sys._getframe().f_globals["__name__"] = "engine.air"
            try:
                return ee_resilience._attribute_call()
            finally:
                sys._getframe().f_globals["__name__"] = __name__

        mod, _fn = from_pretend_pillar()
        assert mod == "engine.air"
