"""Per-country climatology fixture: loading, country lookup, baseline access.

The 1.2 regional-climatology fallback (M-FALLBACK-A1 §4.2) substitutes a
per-country median ± σ for the background-ring baseline when the ring is
unavailable. This module is the read side:

- ``load_climatology`` reads and caches ``demo/climatology.json`` (the
  fixture committed to the repo; regenerated annually by
  ``tools/regen_climatology_fixtures.py``).
- ``country_for_centroid`` resolves an AOI centroid to a country name via
  the GAUL level0 boundary asset (A.4 recon: same family
  ``demo/regions.py`` already uses, resolving Q-FB-1 toward consistency).
- ``climatology_baseline`` looks up ``(median, std, vintage)`` for one
  ``country × indicator``.

All lookups degrade gracefully to ``None`` (missing country, missing
indicator, EE error). A ``None`` means "no climatology available" — the
caller (``six_step``) then re-raises the original ring-empty error so the
indicator skips exactly as in pre-milestone code. No silent defaults
(CLAUDE.md §7).

Spec authority: docs/M-FALLBACK-A1_spec (1).md §4.2, FB9–FB13.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from engine.constants import CLIMATOLOGY_COUNTRY_ASSET


# The fixture ships alongside the other demo fixtures (A.5 recon: JSON under
# demo/, the same convention as demo/indicator_library.json).
_FIXTURE_PATH: Final[Path] = (
    Path(__file__).resolve().parent.parent.parent / "demo" / "climatology.json"
)


@dataclass(frozen=True)
class ClimatologyBaseline:
    """Background substitute for one country × indicator (§4.2).

    ``median`` replaces ``mean(background_ring)`` and ``std`` replaces
    ``stdDev(background_ring)`` in the z-score. ``vintage`` is the fixture
    publication year (e.g. ``"2026"`` for the 2023–2025 window) and is
    surfaced in provenance.
    """

    median: float
    std: float
    vintage: str


# ---------------------------------------------------------------------------
# Fixture loading (cached at module scope)
# ---------------------------------------------------------------------------

_fixture_cache: dict | None = None


def load_climatology(path: Path | None = None) -> dict:
    """Load and cache the climatology fixture.

    ``path`` overrides the default location (used by tests). The cache keys
    on the default path only; passing an explicit ``path`` always re-reads
    so tests stay isolated.

    Returns the parsed dict: ``{"_meta": {...}, "countries": {country:
    {indicator: {"median": float, "std": float}}}}``.
    """
    global _fixture_cache
    if path is not None:
        return json.loads(Path(path).read_text())
    if _fixture_cache is None:
        _fixture_cache = json.loads(_FIXTURE_PATH.read_text())
    return _fixture_cache


def clear_cache() -> None:
    """Reset the fixture cache. Exposed for tests."""
    global _fixture_cache
    _fixture_cache = None


def fixture_vintage(fixture: dict | None = None) -> str:
    """Return the fixture's published vintage year (e.g. ``"2026"``)."""
    fx = fixture if fixture is not None else load_climatology()
    return fx["_meta"]["vintage"]


# ---------------------------------------------------------------------------
# Centroid → country lookup (EE point-in-polygon against GAUL level0)
# ---------------------------------------------------------------------------

_country_lookup_cache: dict[tuple[float, float], str | None] = {}


def country_for_centroid(
    lat: float,
    lon: float,
    ee_client=None,  # noqa: ARG001 — accepted for signature parity; uses ee directly
) -> str | None:
    """Resolve an AOI centroid to a GAUL level0 country name.

    Point-in-polygon against ``CLIMATOLOGY_COUNTRY_ASSET``. Returns the
    ``ADM0_NAME`` of the country containing the point, or ``None`` if the
    point falls outside all polygons (open ocean, Antarctica gaps) or the
    EE query fails for any reason — callers treat ``None`` as "no
    climatology available" and skip rather than substitute a wrong country.

    AOIs spanning multiple countries resolve to the centroid's country
    (documented limitation, §4.2 edge case / Q-FB-2).

    Cached on rounded (lat, lon) to avoid repeat round-trips within a batch.
    """
    key = (round(lat, 3), round(lon, 3))
    if key in _country_lookup_cache:
        return _country_lookup_cache[key]

    name: str | None = None
    try:
        import ee

        point = ee.Geometry.Point([lon, lat])
        fc = ee.FeatureCollection(CLIMATOLOGY_COUNTRY_ASSET).filterBounds(point)
        names = fc.aggregate_array("ADM0_NAME").getInfo()
        if names:
            name = str(names[0])
    except Exception:
        # Any EE failure (no init, network, asset gap) → no climatology.
        # Degrade to skip rather than guess a country.
        name = None

    _country_lookup_cache[key] = name
    return name


def clear_country_cache() -> None:
    """Reset the centroid→country cache. Exposed for tests."""
    _country_lookup_cache.clear()


# ---------------------------------------------------------------------------
# Baseline accessor
# ---------------------------------------------------------------------------

def climatology_baseline(
    country: str | None,
    indicator_key: str,
    *,
    fixture: dict | None = None,
) -> ClimatologyBaseline | None:
    """Look up ``(median, std, vintage)`` for one country × indicator.

    Returns ``None`` when the country is unknown, the indicator is absent
    for that country, or either statistic is missing/non-finite. A ``None``
    means the climatology fallback cannot fire for this indicator here.

    ``indicator_key`` is the base id (e.g. ``"air.no2"``, ``"ghg.ch4"``) —
    the same form used in ``CLIMATOLOGY_INDICATORS``.
    """
    if not country:
        return None
    fx = fixture if fixture is not None else load_climatology()
    country_entry = fx.get("countries", {}).get(country)
    if not country_entry:
        return None
    stats = country_entry.get(indicator_key)
    if not stats:
        return None
    median = stats.get("median")
    std = stats.get("std")
    if median is None or std is None:
        return None
    try:
        median_f = float(median)
        std_f = float(std)
    except (TypeError, ValueError):
        return None
    return ClimatologyBaseline(
        median=median_f, std=std_f, vintage=str(fx["_meta"]["vintage"]),
    )
