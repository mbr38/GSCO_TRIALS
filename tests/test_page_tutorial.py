"""Tests for ui.components.page_tutorial (M-TUTORIAL-A1).

Pure-Python — no Streamlit interaction. The registry shape and the
step-index clamp (``_next_index``) carry all the testable logic; the
dialog/stepper rendering is Streamlit-side chrome.
"""

# M-TUTORIAL-A1
from __future__ import annotations

import pytest

from ui.components.page_tutorial import TUTORIALS, _next_index

_EXPECTED_IDS = ("P-02", "P-04", "P-07")

# M-TUTORIAL-RESULTS-A1 — interpretation tutorials for the result pages.
_RESULT_IDS = ("P-05-RESULTS", "P-06-TREND")


# ---------------------------------------------------------------------------
# Content registry
# ---------------------------------------------------------------------------

def test_registry_has_three_ids_with_nonempty_steps() -> None:
    # Setup-page tutorials must all be present (result-page ids are added by
    # M-TUTORIAL-RESULTS-A1 and checked separately).
    assert set(_EXPECTED_IDS) <= set(TUTORIALS)
    for tutorial_id in _EXPECTED_IDS:
        steps = TUTORIALS[tutorial_id]["steps"]
        assert isinstance(steps, list)
        assert len(steps) >= 1
        for step in steps:
            assert step["title"].strip()
            assert step["body"].strip()


def test_every_step_has_title_and_body_keys() -> None:
    for tutorial_id in _EXPECTED_IDS:
        for step in TUTORIALS[tutorial_id]["steps"]:
            assert "title" in step
            assert "body" in step


# ---------------------------------------------------------------------------
# Step-index advance (open then advance updates the index correctly)
# ---------------------------------------------------------------------------

def test_advance_from_zero_moves_forward() -> None:
    n = len(TUTORIALS["P-04"]["steps"])
    assert _next_index(0, 1, n) == 1
    assert _next_index(1, 1, n) == 2


def test_back_is_clamped_at_first_step() -> None:
    assert _next_index(0, -1, 5) == 0


def test_next_is_clamped_at_last_step() -> None:
    n = 5
    assert _next_index(n - 1, 1, n) == n - 1


def test_full_forward_walk_lands_on_last_step() -> None:
    n = len(TUTORIALS["P-07"]["steps"])
    idx = 0
    for _ in range(n + 3):  # extra clicks past the end must not overshoot
        idx = _next_index(idx, 1, n)
    assert idx == n - 1


# ---------------------------------------------------------------------------
# M-TUTORIAL-RESULTS-A1 — result-page tutorials + start_step
# ---------------------------------------------------------------------------

def test_result_tutorials_exist_with_nonempty_steps() -> None:
    for tutorial_id in _RESULT_IDS:
        assert tutorial_id in TUTORIALS
        steps = TUTORIALS[tutorial_id]["steps"]
        assert isinstance(steps, list)
        assert len(steps) >= 1
        for step in steps:
            assert step["title"].strip()
            assert step["body"].strip()


def test_result_tutorials_have_trigger_labels() -> None:
    # Result tutorials carry their own "How to read this" trigger label.
    for tutorial_id in _RESULT_IDS:
        assert TUTORIALS[tutorial_id]["trigger_label"].strip()


def test_steps_use_scannable_structure() -> None:
    # M-TUTORIAL-IMPROVE: bodies are short leads; the detail lives in
    # bullets/legend/schematic. Assert the lead stays a single sentence and
    # that multi-point steps actually carry bullets rather than a paragraph.
    for tutorial_id, spec in TUTORIALS.items():
        for step in spec["steps"]:
            # A lead, not a paragraph: at most one sentence-ending period.
            assert step["body"].count(". ") == 0, (tutorial_id, step["title"])
            for b in step.get("bullets", []):
                assert b.strip()
            for label, tone in step.get("legend", []):
                assert label.strip() and tone.strip()


def test_legend_tones_resolve_to_a_colour() -> None:
    from ui.components.page_tutorial import _tone_colour

    for spec in TUTORIALS.values():
        for step in spec["steps"]:
            for _label, tone in step.get("legend", []):
                assert _tone_colour(tone).startswith("#")


def test_start_step_clamps_into_range() -> None:
    # Opening at start_step initialises the index to that clamped value
    # (mirrors render_tutorial_trigger's reset logic).
    n = len(TUTORIALS["P-05-RESULTS"]["steps"])
    assert _next_index(2, 0, n) == 2          # valid start_step preserved
    assert _next_index(0, 0, n) == 0          # default start
    assert _next_index(n + 5, 0, n) == n - 1  # past-end start clamped
    assert _next_index(-3, 0, n) == 0         # negative start clamped
