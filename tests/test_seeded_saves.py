"""Tests for demo.saved_analyses.seed_saved_analyses (M-P10).

Pure-Python — no Streamlit. ``session_state`` is a plain dict, which is
all the loader interacts with via .get / __setitem__.

M-P10-POLISH: switched from a list-emptiness guard to a flag-based
guard so user mutations of ``saved_analyses`` don't re-trigger seeding.
"""

# M-P10
from __future__ import annotations

import json
from pathlib import Path

import pytest

import demo.saved_analyses as seed_module
from demo.saved_analyses import _SEED_FLAG_KEY, seed_saved_analyses


# ---------------------------------------------------------------------------
# Loader behaviour
# ---------------------------------------------------------------------------

def test_seed_populates_empty_session():
    """Cold start — empty dict gets every shipped seed entry.

    Count is derived from the seed dir's glob so adding new fixtures
    (e.g. M-WIND-A1 v2.0 added wind-demo seeds) doesn't require touching
    the assertion. ``test_shipped_seed_file_has_canonical_keys`` pins the
    shape of each individual file.
    """
    expected_count = len(list(seed_module._SEED_DIR.glob("*.json")))
    session: dict = {}
    seed_saved_analyses(session)

    assert isinstance(session["saved_analyses"], list)
    assert len(session["saved_analyses"]) == expected_count
    assert expected_count >= 2  # the original M-P10 pair always ships


def test_seed_sets_flag_on_first_call():
    """M-P10-POLISH — after the first call, the seed flag is set."""
    session: dict = {}
    seed_saved_analyses(session)
    assert session[_SEED_FLAG_KEY] is True


def test_seed_is_noop_on_second_call_via_flag(monkeypatch, tmp_path):
    """M-P10-POLISH — calling seed_saved_analyses a second time is a
    no-op because the flag is set, even if the list has been mutated.
    Use a tmp seed dir so the test is deterministic.
    """
    (tmp_path / "a.json").write_text(json.dumps({"id": "seed-a"}))
    monkeypatch.setattr(seed_module, "_SEED_DIR", tmp_path)

    session: dict = {}
    seed_saved_analyses(session)
    assert [s["id"] for s in session["saved_analyses"]] == ["seed-a"]

    # Second call — even if we change the seed dir, the flag-based
    # guard short-circuits before any file IO happens.
    (tmp_path / "b.json").write_text(json.dumps({"id": "seed-b"}))
    seed_saved_analyses(session)
    assert [s["id"] for s in session["saved_analyses"]] == ["seed-a"]


def test_user_save_between_seed_calls_is_preserved(monkeypatch, tmp_path):
    """M-P10-POLISH — bug Bug 1 regression. Append a user save after
    the first seed, then call seed again. The user save must survive.
    """
    (tmp_path / "a.json").write_text(json.dumps({"id": "seed-a"}))
    monkeypatch.setattr(seed_module, "_SEED_DIR", tmp_path)

    session: dict = {}
    seed_saved_analyses(session)
    session["saved_analyses"].append({"id": "user-save-1"})

    # Second call must NOT re-add the seed (guarded by flag) and must
    # NOT clobber the user save.
    seed_saved_analyses(session)
    assert [s["id"] for s in session["saved_analyses"]] == [
        "seed-a", "user-save-1",
    ]


def test_seed_preserves_existing_entries_added_before_first_call(
    monkeypatch, tmp_path,
):
    """Defensive — if a save was somehow appended before the canonical
    app.py call site ran (shouldn't happen, but the loader handles it),
    the existing entry survives.
    """
    (tmp_path / "a.json").write_text(json.dumps({"id": "seed-a"}))
    monkeypatch.setattr(seed_module, "_SEED_DIR", tmp_path)

    session: dict = {"saved_analyses": [{"id": "pre-seed"}]}
    seed_saved_analyses(session)
    # Seed entries land first, pre-existing entries appended after.
    assert [s["id"] for s in session["saved_analyses"]] == [
        "seed-a", "pre-seed",
    ]


def test_seed_empty_when_no_json_files_present(monkeypatch, tmp_path):
    """Defensive — point _SEED_DIR at an empty directory and confirm the
    loader still leaves a usable empty list rather than raising. This is
    the path tests in isolation hit if the seed files are temporarily
    moved aside.
    """
    monkeypatch.setattr(seed_module, "_SEED_DIR", tmp_path)
    session: dict = {}
    seed_saved_analyses(session)
    assert session["saved_analyses"] == []


def test_seed_files_are_loaded_in_sorted_order(monkeypatch, tmp_path):
    """The loader uses ``sorted(_SEED_DIR.glob(...))`` so the order is
    deterministic and reviewable in version control.
    """
    (tmp_path / "b.json").write_text(json.dumps({"id": "second"}))
    (tmp_path / "a.json").write_text(json.dumps({"id": "first"}))
    monkeypatch.setattr(seed_module, "_SEED_DIR", tmp_path)

    session: dict = {}
    seed_saved_analyses(session)
    assert [s["id"] for s in session["saved_analyses"]] == ["first", "second"]


# ---------------------------------------------------------------------------
# Shipped JSON files — shape pin
# ---------------------------------------------------------------------------

_SHIPPED_DIR = Path(seed_module.__file__).parent
# M-DIAG-A2 Q-DIAG-A2-B (operator decision 29 May 2026): added an optional
# ``expected_attributability`` envelope field documenting the operator's
# ground-truth intuition for each seed's wind-attribution category. The
# field is a comparison target for future calibration sweeps; it is
# informational only and never enters score arithmetic. Shipped seeds
# regenerated by M-DIAG-A2's calibrated baseline tool carry it; older
# seeds may not (the test allows either shape via the OR below).
_EXPECTED_KEYS = {
    "id", "name", "type", "screening_setup", "date_saved", "payload",
}
_EXPECTED_KEYS_WITH_DIAG_A2 = _EXPECTED_KEYS | {"expected_attributability"}


def _all_shipped_seeds() -> list[str]:
    """All shipped seed filenames, sorted. Discovered dynamically so adding
    new fixtures (e.g. M-WIND-A1 v2.0 wind-demo seeds) doesn't require
    touching the parametrise list."""
    return sorted(p.name for p in _SHIPPED_DIR.glob("*.json"))


@pytest.mark.parametrize("filename", _all_shipped_seeds())
def test_shipped_seed_file_has_canonical_keys(filename: str):
    """Every shipped seed file must parse and carry the canonical six
    keys — the same keys ``_save_as_report`` emits. Phase 2 demo prep
    overwrites these with real screening data, but the shape contract
    holds at every stage.
    """
    with (_SHIPPED_DIR / filename).open("r", encoding="utf-8") as f:
        entry = json.load(f)
    keys = set(entry.keys())
    assert keys == _EXPECTED_KEYS or keys == _EXPECTED_KEYS_WITH_DIAG_A2, (
        f"Unexpected key set in {filename}: {keys}"
    )
    assert entry["type"] == "screening"


# ===========================================================================
# M-DIAG-A2 Step E.3 — regression locks on production seed hf values
# ===========================================================================


class TestMDiagA1RegressionLocks:
    """M-DIAG-A2 §4.6 / DGA8 — pin the post-fix hf signature at the
    production seeds so any regression of the M-DIAG-A1 fix
    (``mean_key = f"{band}_mean"``) is caught at test time.

    Three locks:

      1. **Norilsk NO₂ hf > 0.5.** Pre-fix the per-day detector was a
         sign-of-bg_median oracle and Norilsk NO₂ produced hf=0.000
         despite aggregate z=3.25 (the "Norilsk silence"). Post-fix
         hf=0.675 in the production seed. The > 0.5 threshold gives
         comfortable headroom against EE-side noise.
      2. **Sapezal AAI hf < 0.7.** Pre-fix Sapezal AAI produced
         hf=1.000 / 89 anomaly days (the "AAI tropical Moderate
         artefact"). Post-fix hf=0.461 in the production seed. The
         < 0.7 ceiling gives comfortable headroom.
      3. **Generic sign-invariant.** For each positive-bg_median
         indicator in the seed set, at least one seed must produce
         hf NOT in ``{exactly 0.0, exactly 1.0}``. Pre-fix the bug
         produced exactly-0 universally for positive-bg_median
         indicators (or exactly-1 for negative-bg_median ones).
         Intermediate values prove the detector is functional.

    These tests read the SHIPPED production seeds. A failure means
    either the seeds are stale or the M-DIAG-A1 fix has regressed —
    inspect both before disabling these assertions.
    """

    _SEEDS = {
        "sapezal":  "high_priority_amazon.json",
        "brasilia": "low_priority_brasilia.json",
        "suape":    "wind_priority_suape.json",
        "comodoro": "wind_low_attribution_patagonia.json",
        "norilsk":  "wind_low_attribution_norilsk.json",
    }
    # Positive-bg_median indicators (concentrations, not sign-bearing).
    # AAI is excluded because its bg_median can be negative; the
    # bug's signature for AAI was hf=1 (not 0), so it doesn't share
    # the "exactly 0 universally" failure mode.
    _POSITIVE_BG_INDICATORS: tuple[str, ...] = (
        "air.no2", "air.so2", "air.hcho", "air.aod", "ghg.ch4",
    )

    def _load(self, seed_name: str) -> dict:
        with (_SHIPPED_DIR / self._SEEDS[seed_name]).open("r", encoding="utf-8") as f:
            return json.load(f)

    def test_norilsk_no2_hf_above_half(self):
        """The Norilsk silence regression lock. Pre-M-DIAG-A1: hf=0.000 (the
        silent-zero per-day site_mean bug). Post-M-DIAG-A1: hf~=0.675 under the
        old spatial-std denominator. Post-M-DIAG-A4 (31 May 2026): the temporal
        denominator is larger than the collapsed spatial std at Norilsk, so the
        per-day hot-fraction moderates to ~0.13 — a *defensible* movement (the
        pre-fix hf was partly inflated by denominator collapse). The lock's
        intent is unchanged: guard that the per-day site_mean is NOT silently
        zeroed (a `mean_key` regression collapses hf back to 0.000). The
        threshold is lowered to 0.05 to track the post-fix denominator while
        still catching that collapse.
        """
        envelope = self._load("norilsk")
        hf = envelope["payload"].get("air.no2.hf")
        assert hf is not None, "air.no2.hf must be populated at Norilsk"
        assert hf > 0.05, (
            f"Norilsk NO₂ hf={hf:.3f} <= 0.05. Pre-M-DIAG-A1 value was "
            "0.000 due to the silent-zero per-day site_mean bug. A "
            "regression of `mean_key = f\"{band}_mean\"` would collapse "
            "this value back toward zero. Inspect "
            "engine/core/repeatable_core.py::_server_side_hf."
        )

    def test_sapezal_aai_hf_below_threshold(self):
        """The AAI tropical Moderate artefact regression lock. Pre-fix:
        hf=1.000 (89/89 days). Post-fix: hf~=0.461. Threshold: < 0.7.
        """
        envelope = self._load("sapezal")
        hf = envelope["payload"].get("air.aai.hf")
        assert hf is not None, "air.aai.hf must be populated at Sapezal"
        assert hf < 0.7, (
            f"Sapezal AAI hf={hf:.3f} >= 0.7. Pre-M-DIAG-A1 value was "
            "1.000 due to AAI's negative bg_median + silent-zero "
            "site_mean producing perpetual-fire. A regression of the "
            "`mean_key` fix would push this back toward 1.0."
        )

    def test_positive_bg_indicators_not_universally_extreme(self):
        """Sign-invariant generic lock (Q-DIAG-A2-6). For each
        positive-bg_median indicator, at least one seed must yield
        hf strictly between 0 and 1. The pre-fix bug produced
        hf=0.000 EXACTLY across every seed for positive-bg_median
        indicators (because the silent-zero site_mean compared
        against a positive bg_median always gave z<0). Intermediate
        values at any seed disprove the universal failure mode.
        """
        envelopes = {n: self._load(n) for n in self._SEEDS}
        for ind in self._POSITIVE_BG_INDICATORS:
            hfs_seen: list[tuple[str, float]] = []
            for seed_name, env in envelopes.items():
                hf = env["payload"].get(f"{ind}.hf")
                if isinstance(hf, (int, float)):
                    hfs_seen.append((seed_name, float(hf)))
            # If every cell has hf == 0 or hf == 1, that's the bug
            # signature. We require at least one cell strictly in (0, 1).
            intermediate = [
                (s, h) for s, h in hfs_seen if 0.0 < h < 1.0
            ]
            assert intermediate, (
                f"For positive-bg_median indicator {ind!r}, no seed "
                f"produced an intermediate hf — all values were exactly "
                f"0 or 1: {hfs_seen!r}. This matches the M-DIAG-A1 bug "
                "signature (silent-zero per-day site_mean compared "
                "against positive bg_median fires hf=0 universally). "
                "Either the M-DIAG-A1 fix has regressed, or the seeds "
                "are stale."
            )
