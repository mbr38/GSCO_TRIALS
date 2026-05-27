"""Tests for ui.components.multi_map_state (M-UI-A5).

Pure-Python — the active-indicator state machine (§8.2) and the
session-scoped tile cache (§8.4) are exercised through the dependency-injected
helpers (``store`` is a plain dict, ``get_map_id_fn`` is a thunk), so no
Streamlit session or Earth Engine round-trip is needed.
"""

# M-UI-A5
from __future__ import annotations

from ui.components.multi_map_state import (
    ACTIVE_INDICATOR_KEY,
    cache_stats,
    cached_tile_url,
    clear_active,
    get_active,
    set_active,
    sync_cache,
)


# ---------------------------------------------------------------------------
# Active-indicator state machine (§4.2 / §8.2)
# ---------------------------------------------------------------------------

def test_active_defaults_to_none():
    assert get_active({}) is None


def test_set_then_get_active():
    store: dict = {}
    set_active(store, "air.no2.score")
    assert get_active(store) == "air.no2.score"


def test_set_to_a_different_indicator_replaces():
    store: dict = {}
    set_active(store, "air.no2.score")
    set_active(store, "ghg.ch4.score")
    assert get_active(store) == "ghg.ch4.score"


def test_clear_active_returns_to_none():
    store: dict = {}
    set_active(store, "nature.ndvi.score")
    clear_active(store)
    assert get_active(store) is None


def test_clear_active_is_idempotent():
    store: dict = {}
    clear_active(store)  # nothing set — must not raise
    assert ACTIVE_INDICATOR_KEY not in store


# ---------------------------------------------------------------------------
# Cache lifecycle (§6 / §8.4)
# ---------------------------------------------------------------------------

class _Thunk:
    """Counts EE round-trips and returns a distinct URL per call."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return f"https://tiles.example/{self.calls}"


def test_first_render_is_a_miss_and_computes():
    store: dict = {}
    thunk = _Thunk()
    url = cached_tile_url(store, "run-1", "air.no2.score", thunk)
    assert url == "https://tiles.example/1"
    assert thunk.calls == 1
    assert cache_stats(store) == {"hits": 0, "misses": 1, "entries": 1}


def test_second_render_same_indicator_is_a_hit_no_ee_call():
    store: dict = {}
    thunk = _Thunk()
    cached_tile_url(store, "run-1", "air.no2.score", thunk)
    url = cached_tile_url(store, "run-1", "air.no2.score", thunk)
    assert url == "https://tiles.example/1"  # reused, not recomputed
    assert thunk.calls == 1                   # no second round-trip
    assert cache_stats(store)["hits"] == 1


def test_second_indicator_same_run_preserves_first_entry():
    store: dict = {}
    thunk = _Thunk()
    cached_tile_url(store, "run-1", "air.no2.score", thunk)
    cached_tile_url(store, "run-1", "ghg.ch4.score", thunk)
    assert thunk.calls == 2
    assert cache_stats(store)["entries"] == 2
    # First entry still cached — re-fetching it is a hit.
    cached_tile_url(store, "run-1", "air.no2.score", thunk)
    assert thunk.calls == 2


def test_new_run_invalidates_entire_cache():
    store: dict = {}
    thunk = _Thunk()
    cached_tile_url(store, "run-1", "air.no2.score", thunk)
    # New screening → new run_id → cache cleared, indicator recomputed.
    url = cached_tile_url(store, "run-2", "air.no2.score", thunk)
    assert thunk.calls == 2
    assert url == "https://tiles.example/2"
    assert cache_stats(store)["entries"] == 1


def test_new_run_clears_active_indicator():
    """§4.6 — a new screening clears the active map indicator so it can't
    render NO₂ on stale data. (The run is established first — matching the
    real flow where the map host runs once before any tile is clicked.)"""
    store: dict = {}
    sync_cache(store, "run-1")          # establish the run (first render)
    set_active(store, "air.no2.score")  # user clicks a tile
    assert get_active(store) == "air.no2.score"
    sync_cache(store, "run-2")          # new screening
    assert get_active(store) is None


def test_sync_cache_is_idempotent_within_a_run():
    store: dict = {}
    sync_cache(store, "run-1")          # establish the run
    set_active(store, "air.no2.score")  # then a tile click sets active
    sync_cache(store, "run-1")          # same run — must not clear active
    assert get_active(store) == "air.no2.score"


def test_first_sync_clears_any_stale_active():
    """The first sync for a fresh store clears any active indicator left over
    in session state from a prior screening (§4.6 fresh-start guarantee)."""
    store: dict = {}
    set_active(store, "air.no2.score")  # stale value from a prior session
    sync_cache(store, "run-1")          # first sync of this run
    assert get_active(store) is None
