"""Nominatim geocoder wrapper (M-P04-Geocode).

Wraps OpenStreetMap's free Nominatim API for geocoding place-name
queries to lat/lon. Used by P-04's Free Coordinates tab.

No API key. Usage policy: 1 request/second and a meaningful User-Agent
header (https://operations.osmfoundation.org/policies/nominatim/).
The 1-req/sec ceiling is enforced module-locally; that's fine for the
single-user demo but a multi-user deployment would need either a real
rate limiter or a paid geocoder.

Pure-Python, no Streamlit imports — testable via stubbed
``requests.get``.
"""

# M-P04-Geocode
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Final

import requests


_NOMINATIM_URL:        Final[str]   = "https://nominatim.openstreetmap.org/search"
_USER_AGENT:           Final[str]   = "GSCO-Environmental-Tool/v1 (demo)"
_TIMEOUT_S:            Final[float] = 10.0
_MAX_RESULTS:          Final[int]   = 5
_MIN_REQUEST_INTERVAL_S: Final[float] = 1.0

# Module-level rate-limit tracker. Crude but sufficient for the
# single-user demo. ``time.monotonic`` is the right clock here —
# unaffected by wall-clock adjustments.
_last_request_ts: float = 0.0


@dataclass(frozen=True)
class GeocodeResult:
    """One geocoded match returned by Nominatim."""

    display_name: str
    lat:          float
    lon:          float


class GeocodingError(Exception):
    """Raised on transport errors, malformed responses, or other
    geocoder failures the UI should surface to the user."""


def geocode(query: str) -> list[GeocodeResult]:
    """Return up to ``_MAX_RESULTS`` matches for ``query``.

    Empty / whitespace-only queries return ``[]`` without an HTTP call.
    Network errors, JSON parse failures, and timeouts all raise
    ``GeocodingError`` with a message suitable for the UI to display.
    """
    query = query.strip()
    if not query:
        return []

    _respect_rate_limit()

    try:
        response = requests.get(
            _NOMINATIM_URL,
            params={
                "q":      query,
                "format": "json",
                "limit":  _MAX_RESULTS,
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT_S,
        )
        response.raise_for_status()
        raw = response.json()
    except requests.RequestException as exc:
        raise GeocodingError(f"Network error: {exc}") from exc
    except ValueError as exc:  # JSON decode error.
        raise GeocodingError(
            f"Could not parse geocoder response: {exc}"
        ) from exc

    parsed = [_parse_result(item) for item in raw if _is_valid(item)]
    # Defensive — Nominatim usually honours ``limit`` but a future API
    # change shouldn't bleed extra rows through to the UI.
    return parsed[:_MAX_RESULTS]


def _respect_rate_limit() -> None:
    """Sleep if needed so consecutive calls stay ≥1 sec apart."""
    global _last_request_ts
    now = time.monotonic()
    elapsed = now - _last_request_ts
    if elapsed < _MIN_REQUEST_INTERVAL_S:
        time.sleep(_MIN_REQUEST_INTERVAL_S - elapsed)
    _last_request_ts = time.monotonic()


def _is_valid(raw: dict) -> bool:
    """Defensive shape check — Nominatim sometimes returns entries
    with missing or non-numeric coordinates."""
    try:
        float(raw["lat"])
        float(raw["lon"])
        return bool(raw.get("display_name"))
    except (KeyError, TypeError, ValueError):
        return False


def _parse_result(raw: dict) -> GeocodeResult:
    """Convert one raw Nominatim entry to a typed ``GeocodeResult``."""
    return GeocodeResult(
        display_name=raw["display_name"],
        lat=float(raw["lat"]),
        lon=float(raw["lon"]),
    )
