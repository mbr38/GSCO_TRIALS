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


# ---------------------------------------------------------------------------
# Content registry
# ---------------------------------------------------------------------------

def test_registry_has_three_ids_with_nonempty_steps() -> None:
    assert set(TUTORIALS) == set(_EXPECTED_IDS)
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
