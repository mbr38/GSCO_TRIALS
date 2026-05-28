"""M-PERF-A1 tolerance-based regression harness (Step E).

For each of the 3 regression AOIs (Sapezal, DF, Rio), re-runs
``ScreeningRun`` with the same inputs that produced the baseline
fixture in ``tests/baselines/m_perf_a1/<aoi>.json``, then compares
every leaf in the new payload against the baseline:

  * **Continuous outputs** (numeric leaves): within
    ``rel_tol = 1e-6`` (or ``abs_tol = 1e-9`` near zero) — PF4 / Q-PF-1.
    Float reorder under ``ee.Dictionary`` batching is expected; a real
    formula change is not. The default epsilon catches the latter.

  * **Categorical outputs** (non-numeric leaves — strings, bools, None):
    exact equality — PF3 hard lock. A severity band, attributability
    state, sparse flag, or skipped_reason flip is a HARD FAILURE even
    if the underlying float is within tolerance.

  * **Call-count regression**: the new ``total_getinfo_calls`` must be
    ≤ the baseline's. Batching can only reduce calls — never inflate
    them. PF12 / §6.2.

Each AOI test prints a top-10 diff summary on failure so the culprit is
visible without combing through 200+ leaves.

Gated on ``RUN_EE_TESTS=1`` (same pattern as
``tests/test_ghg_integration.py``) so the synthetic suite stays fast.
"""

# M-PERF-A1
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Iterator

import pytest


# EE-touching tests are gated on RUN_EE_TESTS=1; the comparator-unit
# tests below run unconditionally so the tolerance/categorical logic
# can be exercised in the synthetic suite.
_skip_unless_ee = pytest.mark.skipif(
    os.environ.get("RUN_EE_TESTS") != "1",
    reason="set RUN_EE_TESTS=1 (and EE_PROJECT_ID) to run M-PERF-A1 regression",
)


# ---------------------------------------------------------------------------
# Tolerance (PF4 — locked at Step B)
# ---------------------------------------------------------------------------

_REL_TOL: float = 1e-6
_ABS_TOL: float = 1e-9


# ---------------------------------------------------------------------------
# Baseline directory + AOI catalogue (mirrors tools/m_perf_a1_profile.py)
# ---------------------------------------------------------------------------

_REPO_ROOT     = Path(__file__).resolve().parents[1]
_BASELINE_DIR  = _REPO_ROOT / "tests" / "baselines" / "m_perf_a1"
_AOI_IDS: tuple[str, ...] = (
    "sapezal_5km",
    "distrito_federal_43_1km",
    "rio_coastal_20km",
)


# ---------------------------------------------------------------------------
# Path-skip list — fields that legitimately differ across runs.
# ---------------------------------------------------------------------------

# Computed at the moment of the run; not a science output.
_SKIP_PATHS: frozenset[str] = frozenset({
    "_meta.computed_at",
})


# ---------------------------------------------------------------------------
# Comparator helpers
# ---------------------------------------------------------------------------

def _walk_leaves(obj, prefix: str = "") -> Iterator[tuple[str, object]]:
    """Yield ``(dotted_path, value)`` for every leaf in a nested mapping
    / list / tuple structure.

    Lists *and tuples* are both indexed positionally (``foo.0``,
    ``foo.1``). The dual-walk caller below loads the baseline from JSON
    (which has no tuple type — every array becomes a Python list) and
    compares against the live ``ScreeningRun`` result (which produces
    real Python tuples for fields like ``_meta.time_range`` and
    ``_provenance.<indicator>.time_range``). Treating tuple and list
    identically here is what makes the comparison apples-to-apples; the
    serialization round-trip is not a real categorical change.

    The baseline and current payloads always have the same shape (same
    inputs), so a missing path on either side is itself a categorical
    failure reported by the dual-walk caller below.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            yield from _walk_leaves(v, path)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            path = f"{prefix}.{i}" if prefix else str(i)
            yield from _walk_leaves(v, path)
    else:
        yield (prefix, obj)


def _is_continuous(value) -> bool:
    """Numeric float leaves are continuous; ints, strs, bools, None are not.

    ``bool`` is a subclass of ``int`` in Python — explicit isinstance
    check on ``bool`` first so True/False are categorical (a flag flip
    must be exact-match, never tolerance-soft).
    """
    if isinstance(value, bool):
        return False
    return isinstance(value, float)


def _continuous_within_tolerance(baseline: float, current: float) -> bool:
    """PF4 tolerance: relative 1e-6 OR absolute 1e-9 near zero."""
    return math.isclose(baseline, current, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)


def _diff_payloads(baseline: dict, current: dict) -> list[dict]:
    """Compare every leaf; return a list of diffs.

    Each diff: ``{"kind": "continuous_drift"|"categorical_flip"|"missing",
                  "path": str, "baseline": ..., "current": ...}``.
    """
    baseline_map = {p: v for p, v in _walk_leaves(baseline)}
    current_map  = {p: v for p, v in _walk_leaves(current)}

    diffs: list[dict] = []
    all_paths = set(baseline_map) | set(current_map)
    for path in sorted(all_paths):
        if path in _SKIP_PATHS:
            continue
        if path not in baseline_map:
            diffs.append({
                "kind": "added_path",
                "path": path,
                "baseline": None,
                "current": current_map[path],
            })
            continue
        if path not in current_map:
            diffs.append({
                "kind": "removed_path",
                "path": path,
                "baseline": baseline_map[path],
                "current": None,
            })
            continue

        b_val = baseline_map[path]
        c_val = current_map[path]

        if _is_continuous(b_val) and _is_continuous(c_val):
            if not _continuous_within_tolerance(b_val, c_val):
                diffs.append({
                    "kind": "continuous_drift",
                    "path": path,
                    "baseline": b_val,
                    "current": c_val,
                })
        else:
            # Categorical (str/bool/None/int) — PF3 exact-match hard lock.
            if b_val != c_val:
                diffs.append({
                    "kind": "categorical_flip",
                    "path": path,
                    "baseline": b_val,
                    "current": c_val,
                })
    return diffs


def _format_diffs(diffs: list[dict], limit: int = 10) -> str:
    """Compact summary for pytest failure messages — top-N diffs."""
    lines = [f"diffs vs baseline: {len(diffs)} (showing first {limit})"]
    by_kind: dict[str, int] = {}
    for d in diffs:
        by_kind[d["kind"]] = by_kind.get(d["kind"], 0) + 1
    lines.append("  breakdown: " + ", ".join(
        f"{k}={v}" for k, v in sorted(by_kind.items())
    ))
    for d in diffs[:limit]:
        lines.append(
            f"  [{d['kind']}] {d['path']}: "
            f"baseline={d['baseline']!r}  current={d['current']!r}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _ee_initialised():
    """Initialise EE once for the whole module, mirroring test_ghg_integration."""
    import ee
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        pytest.skip("EE_PROJECT_ID not set")
    ee.Initialize(project=project)
    # Install the resilience wrapper so the new run mirrors the baseline
    # capture: retry ON, profile ON.
    from engine.core.ee_resilience import install_getinfo_wrapper
    install_getinfo_wrapper(enable_retry=True, enable_profile=True)
    yield ee


@pytest.fixture(scope="module")
def _ui_indicators():
    """The 19-item user-selectable set the baseline was captured with."""
    from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS
    return set(ALL_INDICATOR_IDS)


def _load_baseline(aoi_id: str) -> dict:
    path = _BASELINE_DIR / f"{aoi_id}.json"
    if not path.exists():
        pytest.skip(
            f"baseline {path} not found — run "
            f"`python tools/m_perf_a1_profile.py` to capture it"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _run_current(baseline: dict, ee_initialised) -> dict:
    """Re-run ScreeningRun with the baseline's exact inputs."""
    from engine.core.ee_resilience import reset_profile, snapshot_profile
    from engine.orchestrator import ScreeningRun

    aoi_record = baseline["aoi"]
    aoi = {
        "centre":    aoi_record["centre"],
        "radius_km": aoi_record["radius_km"],
    }
    indicators = {p for p, _ in _walk_leaves(baseline["payload"])}
    # Selected-indicators set is preserved verbatim in _meta to keep
    # the rerun's pillar-selection logic identical to the capture.
    selected = set(baseline["payload"]["_meta"]["selected_indicators"])
    time_range = tuple(baseline["time_range"])

    reset_profile()
    payload = ScreeningRun(
        aoi=aoi,
        selected_indicators=selected,
        time_range=time_range,
        ee_client=None,
        centre_metadata=aoi_record["centre_metadata"],
    ).run()
    profile_rows = snapshot_profile()
    total_calls = sum(row["count"] for row in profile_rows)
    return {"payload": payload, "total_getinfo_calls": total_calls,
            "profile": profile_rows}


# ---------------------------------------------------------------------------
# Per-AOI regression tests
# ---------------------------------------------------------------------------


@_skip_unless_ee
@pytest.mark.parametrize("aoi_id", _AOI_IDS)
class TestM_PERF_A1_Regression:
    """Step E — categorical-invariant + tolerance-bounded regression
    against the Step A baseline fixtures."""

    def test_categorical_outputs_exactly_unchanged(
        self, aoi_id, _ee_initialised, _ui_indicators,
    ):
        """PF3 hard lock — no severity / attributability / sparse / skipped_reason
        may flip versus the baseline."""
        baseline = _load_baseline(aoi_id)
        current  = _run_current(baseline, _ee_initialised)
        diffs    = _diff_payloads(baseline["payload"], current["payload"])
        categorical = [d for d in diffs if d["kind"] in
                       ("categorical_flip", "added_path", "removed_path")]
        assert not categorical, _format_diffs(categorical)

    def test_continuous_outputs_within_tolerance(
        self, aoi_id, _ee_initialised, _ui_indicators,
    ):
        """PF4 — relative 1e-6 (or absolute 1e-9 near zero)."""
        baseline = _load_baseline(aoi_id)
        current  = _run_current(baseline, _ee_initialised)
        diffs    = _diff_payloads(baseline["payload"], current["payload"])
        continuous = [d for d in diffs if d["kind"] == "continuous_drift"]
        assert not continuous, _format_diffs(continuous)

    def test_getinfo_call_count_not_inflated(
        self, aoi_id, _ee_initialised, _ui_indicators,
    ):
        """PF12 / §6.2 — batching can only reduce calls.

        On the *post-batching* head this should pass strictly below the
        baseline (≤, not =). Before batching has landed for any
        particular AOI's pillars, the count will equal the baseline.
        """
        baseline = _load_baseline(aoi_id)
        current  = _run_current(baseline, _ee_initialised)
        assert current["total_getinfo_calls"] <= baseline["total_getinfo_calls"], (
            f"getInfo count regressed: baseline="
            f"{baseline['total_getinfo_calls']}, "
            f"current={current['total_getinfo_calls']}"
        )


# ---------------------------------------------------------------------------
# Diff-comparator unit tests (offline — no EE needed).
# Mirror the comparator's edge cases so future changes can't silently
# break the tolerance logic.
# ---------------------------------------------------------------------------


class TestDiffComparator:
    """Run unconditionally — these don't touch EE."""

    def test_identical_payloads_no_diffs(self):
        a = {"x": 1.0, "y": "high", "z": None, "k": [1.0, 2.0]}
        assert _diff_payloads(a, a) == []

    def test_continuous_within_tolerance_no_diff(self):
        a = {"x": 1.0}
        b = {"x": 1.0 + 1e-12}
        assert _diff_payloads(a, b) == []

    def test_continuous_outside_tolerance_flagged(self):
        a = {"x": 1.0}
        b = {"x": 1.01}
        diffs = _diff_payloads(a, b)
        assert len(diffs) == 1
        assert diffs[0]["kind"] == "continuous_drift"

    def test_categorical_flip_flagged(self):
        a = {"sev": "High"}
        b = {"sev": "Concern"}
        diffs = _diff_payloads(a, b)
        assert len(diffs) == 1
        assert diffs[0]["kind"] == "categorical_flip"

    def test_bool_is_categorical_not_continuous(self):
        # PF3: a sparse flag flip must be flagged even at the
        # tolerance-soft boundary (True vs False is not "near zero").
        a = {"is_sparse": True}
        b = {"is_sparse": False}
        diffs = _diff_payloads(a, b)
        assert diffs[0]["kind"] == "categorical_flip"

    def test_none_vs_value_flagged_as_categorical(self):
        # A None→0.0 transition under batching means a real branch
        # changed; tolerance must not absorb it.
        a = {"x": None}
        b = {"x": 0.0}
        diffs = _diff_payloads(a, b)
        assert diffs[0]["kind"] == "categorical_flip"

    def test_skip_paths_excluded(self):
        a = {"_meta": {"computed_at": "2026-01-01T00:00:00Z"}, "x": 1.0}
        b = {"_meta": {"computed_at": "2026-12-31T00:00:00Z"}, "x": 1.0}
        assert _diff_payloads(a, b) == []

    def test_added_path_flagged(self):
        a = {"x": 1.0}
        b = {"x": 1.0, "y": 2.0}
        diffs = _diff_payloads(a, b)
        assert diffs[0]["kind"] == "added_path"
        assert diffs[0]["path"] == "y"

    def test_removed_path_flagged(self):
        a = {"x": 1.0, "y": 2.0}
        b = {"x": 1.0}
        diffs = _diff_payloads(a, b)
        assert diffs[0]["kind"] == "removed_path"
        assert diffs[0]["path"] == "y"

    def test_near_zero_absolute_tolerance(self):
        # Relative tolerance fails for tiny values; absolute kicks in.
        a = {"x": 0.0}
        b = {"x": 1e-12}
        assert _diff_payloads(a, b) == []

    def test_tuple_and_list_treated_identically(self):
        # Baseline is JSON-loaded (tuples become lists); the live engine
        # emits real tuples for fields like _meta.time_range. The walker
        # must compare them as the same path-set so the serialization
        # round-trip doesn't masquerade as a categorical change.
        json_loaded = {"_meta": {"time_range": ["2026-02-22", "2026-05-23"]}}
        engine_live = {"_meta": {"time_range": ("2026-02-22", "2026-05-23")}}
        assert _diff_payloads(json_loaded, engine_live) == []
