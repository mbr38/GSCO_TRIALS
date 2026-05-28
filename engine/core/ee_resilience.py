"""EE request resilience layer (M-PERF-A1).

A single chokepoint that wraps ``ee.ComputedObject.getInfo`` with:

  1. Exponential-backoff retry on transient errors (HTTP 429 / 5xx /
     EE "Computation timed out") — PF5/PF6.
  2. Wall-time timing log that mirrors the pre-milestone behaviour from
     ``app.py`` (so existing log scraping keeps working). The retry sits
     *inside* the timing path so the log captures total time including
     retries (per the spec's "retry-outside-timing" guidance).
  3. An optional thread-safe call counter used by Step A profiling
     (`tools/m_perf_a1_profile.py`). Disabled by default; the Streamlit
     app does not pay any counter cost.

The wrapper is installed via ``install_getinfo_wrapper()`` (idempotent
via the ``_GSCO_WRAPPED`` marker — Streamlit reruns the script on every
interaction, so we must not nest wrappers per the comment in app.py).

Pillar-agnostic by design (PF17): wind's ERA5 ``getInfo`` calls under
M-WIND-A1 v2.0 inherit retry + counting for free, without any
pillar-specific change.

Background: ``ee.data.computeValue`` (which ``getInfo`` calls) already
passes ``num_retries=MAX_RETRIES=5`` to googleapiclient, which retries
HTTP 5xx with exponential backoff but **not** 429. Adding our wrapper
therefore:
  - Covers 429 (the primary missing case);
  - Covers "Computation timed out" (HTTP 400 + specific message, not
    retried by googleapiclient);
  - Compounds with EE's built-in retry on 5xx (worst case ~25 attempts
    over ~150s). PF5 still mandates 5xx coverage; the compounding is
    bounded and rare enough to be acceptable.
"""

# M-PERF-A1
from __future__ import annotations

import logging
import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Iterable

import ee
import tenacity


# ---------------------------------------------------------------------------
# Retry configuration (PF6 — tunable, module-private)
# ---------------------------------------------------------------------------

# Base wait before the first retry, in seconds.
_RETRY_BASE_S: float = 1.0

# Exponential multiplier between attempts.
_RETRY_MULTIPLIER: float = 2.0

# Maximum number of attempts (initial + retries). 5 attempts at base=1s,
# mult=2 gives cumulative max waits of 1+2+4+8 = 15s before the 5th attempt
# plus jitter; total wait capped by _RETRY_MAX_WAIT_S below.
_RETRY_MAX_ATTEMPTS: int = 5

# Hard cap on a single backoff wait, in seconds. Combined with the
# attempts cap this bounds the worst-case end-to-end retry tail to
# ~30s under PF6.
_RETRY_MAX_WAIT_S: float = 30.0


# ---------------------------------------------------------------------------
# Logger (mirrors the historical "ee_timing" channel from app.py).
# ---------------------------------------------------------------------------

_logger = logging.getLogger("ee_timing")
if not _logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[ee_timing] %(message)s"))
    _logger.addHandler(_h)
    _logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Idempotence marker (preserved from app.py's pre-milestone wrapper)
# ---------------------------------------------------------------------------

# Streamlit re-executes app.py on every user interaction. Without the
# marker each rerun would re-wrap the (already-wrapped) getInfo and
# nest N deep — producing N duplicate log lines per real EE call.
_GSCO_WRAPPED = "_gsco_ee_timing_wrapped"


# ---------------------------------------------------------------------------
# Retryable-error predicate (PF5)
# ---------------------------------------------------------------------------

# Substrings we look for in the EEException message to identify a
# transient/retryable failure. ``ee.data._translate_cloud_exception``
# rewrites googleapiclient.errors.HttpError into ee.EEException carrying
# ``HttpError._get_reason()`` as the message — so the underlying status
# code is lost, but the reason phrase usually survives.
_RETRYABLE_MESSAGE_FRAGMENTS: tuple[str, ...] = (
    # 429 — quota / rate limit
    "429",
    "too many requests",
    "rate limit",
    "quota exceeded",
    "user rate limit",
    "resource_exhausted",
    # 5xx — transient server. EE/googleapiclient already retries 5xx
    # internally; our wrapper compounds (capped). Listed per spec PF5.
    "500",
    "502",
    "503",
    "504",
    "internal server error",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
    "deadline exceeded",
    # EE-specific transient: HTTP 400 + this message phrase is the
    # canonical "computation graph took too long" failure described in
    # engine/core/repeatable_core.py:416.
    "computation timed out",
)


def _is_retryable(exc: BaseException) -> bool:
    """Decide whether ``exc`` is a transient error worth retrying.

    Returns True on 429 / 5xx / EE-specific "computation timed out".
    Returns False on:
      - Any non-EEException (callers shouldn't see those here, but be
        conservative — only retry what we know is transient);
      - Non-retryable 4xx (bad request, auth);
      - ``IndicatorComputeError`` (a genuine compute failure, not a
        network/throttle case — PF5 explicitly excludes it).

    The predicate is intentionally string-based: ee.EEException carries
    a flat message, so we cannot dispatch on an exception subclass.
    """
    # Hard exclusion: pillar compute failures must not be retried. The
    # pillar already decided the indicator is unrecoverable — retrying
    # turns one bad indicator into max_attempts × bad indicators.
    # Imported lazily so this module doesn't depend on the rest of the
    # engine at import time.
    try:
        from engine.exceptions import IndicatorComputeError, PillarComputeError
        if isinstance(exc, (IndicatorComputeError, PillarComputeError)):
            return False
    except ImportError:  # pragma: no cover — engine.exceptions always present
        pass

    if not isinstance(exc, ee.EEException):
        return False

    msg = str(exc).lower()
    return any(fragment in msg for fragment in _RETRYABLE_MESSAGE_FRAGMENTS)


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

# Built with tenacity (already a streamlit transitive dep — see
# requirements.txt). ``wait_exponential_jitter`` uses full jitter:
# wait = uniform(0, min(max, base * mult ** attempt)).
_retry_on_transient = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable),
    wait=tenacity.wait_exponential_jitter(
        initial=_RETRY_BASE_S,
        max=_RETRY_MAX_WAIT_S,
        exp_base=_RETRY_MULTIPLIER,
    ),
    stop=tenacity.stop_after_attempt(_RETRY_MAX_ATTEMPTS),
    reraise=True,
)


# ---------------------------------------------------------------------------
# Profiling counter (Step A — instrument the wrapper to count calls)
# ---------------------------------------------------------------------------

# Counter state lives at module scope and is guarded by a single lock so
# concurrent worker threads (Air/Nature ThreadPoolExecutor under
# orchestrator stage 1, plus the per-pillar pools) all increment the same
# counter without corruption.

@dataclass
class _CallSiteStats:
    """One row in the profiling report."""
    count: int = 0
    total_seconds: float = 0.0
    failures: int = 0


@dataclass
class _ProfileState:
    enabled: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)
    by_site: dict[tuple[str, str], _CallSiteStats] = field(
        default_factory=lambda: defaultdict(_CallSiteStats),
    )


_profile = _ProfileState()


# Module prefixes we attribute calls to. The deepest frame whose module
# matches one of these is the "owning" call site (pillar + function).
# Order matters only when frames overlap — pillar modules are checked
# before core helpers so a getInfo from ``engine.core.repeatable_core``
# invoked by ``engine.air.compute_pollutant_snapshot`` is attributed to
# Air (the calling pillar) rather than the helper.
_PILLAR_MODULE_PREFIXES: tuple[str, ...] = (
    "engine.air",
    "engine.ghg",
    "engine.nature",
    "engine.orchestrator",
)
_CORE_MODULE_PREFIXES: tuple[str, ...] = (
    "engine.core",
    "demo.regions",
)


# Frames inside this module must never count as the call site —
# otherwise the wrapper attributes calls to itself whenever no pillar
# frame appears upstream (e.g. fixture loads, module-level helpers).
_OWN_MODULE = "engine.core.ee_resilience"


def _attribute_call() -> tuple[str, str]:
    """Walk up the stack to find the call's (pillar/module, function).

    Returns ``("<module>", "<function>")``. Prefers the deepest pillar
    frame (engine.air / engine.ghg / engine.nature / engine.orchestrator);
    falls back to the deepest core frame (engine.core / demo.regions),
    skipping this module so the wrapper never attributes to itself.
    Returns ``("unknown", "unknown")`` if nothing matches.

    Uses ``sys._getframe`` rather than ``inspect.stack`` — the latter
    materialises file source lines on every frame, which is expensive
    enough to skew our own timings.
    """
    pillar_hit: tuple[str, str] | None = None
    core_hit: tuple[str, str] | None = None

    # Start at the caller's caller so we skip the wrapper itself.
    frame = sys._getframe(1)
    while frame is not None:
        mod = frame.f_globals.get("__name__", "")
        fn = frame.f_code.co_name
        if mod == _OWN_MODULE:
            # The wrapper's own frame must never become an attribution
            # target — that would just be self-counting.
            pass
        elif mod.startswith(_PILLAR_MODULE_PREFIXES) and pillar_hit is None:
            pillar_hit = (mod, fn)
        elif mod.startswith(_CORE_MODULE_PREFIXES) and core_hit is None:
            core_hit = (mod, fn)
        frame = frame.f_back

    if pillar_hit is not None:
        return pillar_hit
    if core_hit is not None:
        return core_hit
    return ("unknown", "unknown")


def set_profiling_enabled(enabled: bool) -> None:
    """Turn the profiling counter on/off.

    Disabled by default so the Streamlit app pays no counter cost. The
    M-PERF-A1 profiling CLI flips it on around its ScreeningRun call.
    """
    _profile.enabled = bool(enabled)


def reset_profile() -> None:
    """Clear all recorded counts. Used between AOIs in the profiler."""
    with _profile.lock:
        _profile.by_site.clear()


def snapshot_profile() -> list[dict]:
    """Return the current counter state as a sorted list of rows.

    Each row: ``{"module": ..., "function": ..., "count": int,
    "total_seconds": float, "failures": int}``. Sorted by count
    descending (the natural "top offenders" view the profiler emits).
    """
    with _profile.lock:
        rows = [
            {
                "module": mod,
                "function": fn,
                "count": stats.count,
                "total_seconds": stats.total_seconds,
                "failures": stats.failures,
            }
            for (mod, fn), stats in _profile.by_site.items()
        ]
    rows.sort(key=lambda r: (-r["count"], r["module"], r["function"]))
    return rows


def _record(call_site: tuple[str, str], elapsed: float, *, failed: bool) -> None:
    """Increment the per-call-site counter under the lock."""
    with _profile.lock:
        stats = _profile.by_site[call_site]
        stats.count += 1
        stats.total_seconds += elapsed
        if failed:
            stats.failures += 1


# ---------------------------------------------------------------------------
# Wrapper installer (the chokepoint — composes timing + retry + counter)
# ---------------------------------------------------------------------------

def install_getinfo_wrapper(
    *,
    enable_retry: bool = True,
    enable_profile: bool = False,
) -> None:
    """Idempotently monkey-patch ``ee.ComputedObject.getInfo``.

    Composition (outer → inner):
        timing-log → retry (optional) → original getInfo

    The retry sits *inside* the timing path so the log + profile counter
    capture total wall-time including retries (correct observability).

    Args:
        enable_retry: Whether the retry/backoff layer should be active.
            Set False in the baseline-capture run of the profiler so the
            pre-batching baseline reflects the unwrapped behaviour
            exactly.
        enable_profile: Whether to record per-call-site stats into the
            module-level counter. ``set_profiling_enabled`` lets callers
            flip this on/off without reinstalling the wrapper.

    Idempotent via the ``_GSCO_WRAPPED`` marker — calling twice is a
    no-op (the existing wrapper is left in place).
    """
    if getattr(ee.ComputedObject.getInfo, _GSCO_WRAPPED, False):
        # Already wrapped (Streamlit rerun, repeated import). Just toggle
        # the profile flag in case the caller changed their mind.
        if enable_profile:
            set_profiling_enabled(True)
        return

    original = ee.ComputedObject.getInfo

    # Inner retry layer. tenacity's retry state is per-call (closure over
    # the decorated function), so concurrent invocations from different
    # worker threads do not share state — see PF8 / the
    # test_concurrent_retry_state_isolated unit test.
    if enable_retry:
        @_retry_on_transient
        def _with_retry(self, *args, **kwargs):
            return original(self, *args, **kwargs)
    else:
        def _with_retry(self, *args, **kwargs):
            return original(self, *args, **kwargs)

    def _wrapped_getInfo(self, *args, **kwargs):
        label = type(self).__name__
        t0 = time.perf_counter()
        try:
            result = _with_retry(self, *args, **kwargs)
            elapsed = time.perf_counter() - t0
            _logger.info(f"{label}.getInfo()  {elapsed:6.2f}s  OK")
            if _profile.enabled:
                _record(_attribute_call(), elapsed, failed=False)
            return result
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            _logger.info(f"{label}.getInfo()  {elapsed:6.2f}s  FAILED: {exc}")
            if _profile.enabled:
                _record(_attribute_call(), elapsed, failed=True)
            raise

    setattr(_wrapped_getInfo, _GSCO_WRAPPED, True)
    ee.ComputedObject.getInfo = _wrapped_getInfo

    if enable_profile:
        set_profiling_enabled(True)


# ---------------------------------------------------------------------------
# Test seam: tenacity decorator usable on arbitrary callables.
# ---------------------------------------------------------------------------

def _retry_for_tests(func: Callable) -> Callable:
    """Apply the same retry policy to an arbitrary callable.

    Exposed for unit tests that need to exercise the predicate +
    backoff schedule without monkey-patching ee.ComputedObject. Not
    part of the public engine surface.
    """
    return _retry_on_transient(func)


__all__: Iterable[str] = (
    "install_getinfo_wrapper",
    "set_profiling_enabled",
    "reset_profile",
    "snapshot_profile",
)
