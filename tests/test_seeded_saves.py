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
_EXPECTED_KEYS = {
    "id", "name", "type", "screening_setup", "date_saved", "payload",
}


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
    assert set(entry.keys()) == _EXPECTED_KEYS
    assert entry["type"] == "screening"
