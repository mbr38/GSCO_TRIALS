"""Session-state + cache contract for the multi-indicator P-05 map (M-UI-A5).

Small, dependency-injected module that owns the three pieces of state the
multi-indicator map needs so they can't drift between the C4b tile
affordance (which *sets* the active indicator) and the C4a map host (which
*reads* it). Keeping the contract here also breaks the import cycle that
would otherwise form (c4b would import the host for the setter; the host
imports ``MAP_ANCHOR_ID`` from c4b).

Two layers:

  - **Pure helpers** (``set_active``, ``sync_cache``, ``cached_tile_url`` …)
    take an explicit ``store`` dict so the state machine (§8.2) and cache
    (§8.4) can be unit-tested without booting Streamlit or Earth Engine.
  - **Streamlit-bound wrappers** (``set_active_indicator`` …) pass
    ``st.session_state`` to the pure helpers. The page / components call
    these.

Authority: docs/M-UI-A5_spec §4 (state machine), §6 (cache).
"""

# M-UI-A5
from __future__ import annotations

from typing import Callable

import streamlit as st


# HTML id of the scroll target the multi-indicator map renders. Every C4b
# tile's "View on map →" affordance requests a scroll here after setting the
# active indicator (MV16). Lives here (not in c4b) so the host and the tile
# affordance share one source of truth.
MAP_ANCHOR_ID: str = "multi-indicator-map-anchor"

# Session-state keys (flat top-level, per the codebase convention — recon A.7).
ACTIVE_INDICATOR_KEY: str = "active_map_indicator"   # str | None
CACHE_KEY: str = "map_render_cache"                  # dict[indicator_id, {"tile_url": str}]
CACHE_META_KEY: str = "map_render_cache_meta"        # {"run_id", "hits", "misses"}
SCROLL_FLAG_KEY: str = "_scroll_to_map"              # bool — one-shot scroll request


# ---------------------------------------------------------------------------
# Active indicator — pure helpers (store-injected)
# ---------------------------------------------------------------------------

def set_active(store: dict, indicator_id: str) -> None:
    store[ACTIVE_INDICATOR_KEY] = indicator_id


def get_active(store: dict) -> str | None:
    return store.get(ACTIVE_INDICATOR_KEY)


def clear_active(store: dict) -> None:
    store.pop(ACTIVE_INDICATOR_KEY, None)


# ---------------------------------------------------------------------------
# Cache — pure helpers (store-injected)
# ---------------------------------------------------------------------------

def sync_cache(store: dict, run_id: str) -> dict:
    """Ensure the cache is valid for ``run_id``; return the cache dict.

    Invalidation (§6.4): when ``run_id`` changes — i.e. a new screening ran
    (new AOI, window, or indicator selection all mint a fresh ``run_id``,
    recon A.8) — the entire raster cache is dropped *and* the active map
    indicator is cleared (§4.6, the stale-NO₂-on-new-data bug). Idempotent
    within a run: calling it repeatedly with the same ``run_id`` is a no-op.
    """
    meta = store.get(CACHE_META_KEY)
    if meta is None or meta.get("run_id") != run_id:
        store[CACHE_KEY] = {}
        store[CACHE_META_KEY] = {"run_id": run_id, "hits": 0, "misses": 0}
        clear_active(store)
    return store[CACHE_KEY]


def invalidate_indicator(store: dict, indicator_id: str) -> int:
    """Drop cached map tiles for a single indicator (M-FALLBACK-A1 / FB18).

    The patch-on-existing retry recomputes one indicator while preserving the
    rest of the screening, so only that indicator's map tile is stale — not
    the whole cache (Q-FB-3). Prefix-matches on the base id so both the base
    (``air.no2``) and any measurement variant (``air.no2.score``) clear.
    Returns the number of cache entries removed. No-op when the cache is
    empty / not yet built.
    """
    cache = store.get(CACHE_KEY)
    if not isinstance(cache, dict):
        return 0
    base = indicator_id
    doomed = [
        k for k in cache
        if k == base or str(k).startswith(base + ".")
    ]
    for key in doomed:
        cache.pop(key, None)
    return len(doomed)


def cached_tile_url(
    store: dict,
    run_id: str,
    indicator_id: str,
    get_map_id_fn: Callable[[], str],
) -> str:
    """Return the cached EE tile-URL for ``indicator_id``, computing on miss.

    ``get_map_id_fn`` is a zero-arg thunk that performs the actual Earth
    Engine ``getMapId`` round-trip and returns the XYZ tile-URL template. It
    is only invoked on a cache miss, which is the whole point of MV11: the
    second click on the same indicator within a session reuses the result
    with no EE call. Injecting the thunk keeps this function EE-free and so
    unit-testable (§8.4).
    """
    cache = sync_cache(store, run_id)
    meta = store[CACHE_META_KEY]
    entry = cache.get(indicator_id)
    if entry is not None:
        meta["hits"] += 1
        return entry["tile_url"]
    url = get_map_id_fn()
    cache[indicator_id] = {"tile_url": url}
    meta["misses"] += 1
    return url


def cache_stats(store: dict) -> dict:
    """Hit / miss / entry counts for the observability caption (§6.5)."""
    meta = store.get(CACHE_META_KEY, {})
    cache = store.get(CACHE_KEY, {})
    return {
        "hits": meta.get("hits", 0),
        "misses": meta.get("misses", 0),
        "entries": len(cache),
    }


# ---------------------------------------------------------------------------
# Streamlit-bound wrappers
# ---------------------------------------------------------------------------

def set_active_indicator(indicator_id: str) -> None:
    set_active(st.session_state, indicator_id)


def get_active_indicator() -> str | None:
    return get_active(st.session_state)


def clear_active_indicator() -> None:
    clear_active(st.session_state)


def request_scroll() -> None:
    """Flag that the next render should scroll to the map anchor (MV16)."""
    st.session_state[SCROLL_FLAG_KEY] = True


def consume_scroll() -> bool:
    """Read-and-clear the one-shot scroll request."""
    return bool(st.session_state.pop(SCROLL_FLAG_KEY, False))
