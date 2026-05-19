"""Tests for ui.components.geocoder (M-P04-Geocode).

Pure-Python — no network, no Streamlit. Stubs ``requests.get`` and
``time.sleep`` / ``time.monotonic`` so the rate-limit guard's
behaviour can be asserted on without burning real seconds.
"""

# M-P04-Geocode
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
import requests

from ui.components import geocoder as gc
from ui.components.geocoder import (
    GeocodeResult,
    GeocodingError,
    _MAX_RESULTS,
    geocode,
)


# ---------------------------------------------------------------------------
# Helpers — stubbed `requests.Response`
# ---------------------------------------------------------------------------

@dataclass
class _StubResponse:
    """Minimal duck-type of ``requests.Response`` for these tests."""

    _payload:      Any
    _status_code:  int = 200
    _raise_json:   bool = False

    def raise_for_status(self) -> None:
        if self._status_code >= 400:
            raise requests.HTTPError(f"HTTP {self._status_code}")

    def json(self) -> Any:
        if self._raise_json:
            raise ValueError("not json")
        return self._payload


@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch):
    """Zero the module's rate-limit clock + no-op time.sleep so tests
    don't depend on order or pause for real seconds.
    """
    monkeypatch.setattr(gc, "_last_request_ts", 0.0)
    monkeypatch.setattr(gc.time, "sleep", lambda _s: None)
    # Provide a monotonic clock that starts fresh per test.
    fake_clock = [1_000.0]
    monkeypatch.setattr(gc.time, "monotonic", lambda: fake_clock[0])
    return fake_clock  # tests may advance it via ``fake_clock[0] += dt``.


# ---------------------------------------------------------------------------
# Empty / whitespace input
# ---------------------------------------------------------------------------

def test_empty_query_returns_empty_without_http(monkeypatch):
    called = {"n": 0}

    def _fake_get(*a, **kw):
        called["n"] += 1
        raise AssertionError("no HTTP call should be made")

    monkeypatch.setattr(gc.requests, "get", _fake_get)
    assert geocode("") == []
    assert called["n"] == 0


def test_whitespace_query_returns_empty_without_http(monkeypatch):
    monkeypatch.setattr(
        gc.requests, "get",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no HTTP")),
    )
    assert geocode("   \t  ") == []


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_two_result_response_parses_into_typed_results(monkeypatch):
    payload = [
        {"display_name": "São Paulo, Brazil",   "lat": "-23.55", "lon": "-46.63"},
        {"display_name": "São Paulo, Portugal", "lat": "40.12",  "lon": "-8.30"},
    ]
    monkeypatch.setattr(
        gc.requests, "get",
        lambda *a, **kw: _StubResponse(payload),
    )
    results = geocode("São Paulo")
    assert results == [
        GeocodeResult("São Paulo, Brazil",   -23.55, -46.63),
        GeocodeResult("São Paulo, Portugal", 40.12,  -8.30),
    ]


def test_response_truncated_to_max_results(monkeypatch):
    """Defensive: even if Nominatim returns more than asked-for, the
    wrapper caps the list at ``_MAX_RESULTS``."""
    payload = [
        {"display_name": f"Place {i}", "lat": "0.0", "lon": "0.0"}
        for i in range(10)
    ]
    monkeypatch.setattr(
        gc.requests, "get",
        lambda *a, **kw: _StubResponse(payload),
    )
    assert len(geocode("city")) == _MAX_RESULTS


def test_invalid_entries_are_skipped(monkeypatch):
    """Entries with missing lat, non-numeric lon, or empty display_name
    are silently dropped — keeps the result list usable even when the
    upstream returns junk."""
    payload = [
        {"display_name": "Good", "lat": "1.0", "lon": "2.0"},
        {"display_name": "Bad — no lat",       "lon": "3.0"},
        {"display_name": "Bad — non-numeric",  "lat": "abc", "lon": "1.0"},
        {"display_name": "",                   "lat": "1.0", "lon": "2.0"},
    ]
    monkeypatch.setattr(
        gc.requests, "get",
        lambda *a, **kw: _StubResponse(payload),
    )
    results = geocode("city")
    assert [r.display_name for r in results] == ["Good"]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_http_error_raises_geocoding_error(monkeypatch):
    monkeypatch.setattr(
        gc.requests, "get",
        lambda *a, **kw: _StubResponse([], _status_code=503),
    )
    with pytest.raises(GeocodingError, match="Network error"):
        geocode("city")


def test_json_parse_error_raises_geocoding_error(monkeypatch):
    monkeypatch.setattr(
        gc.requests, "get",
        lambda *a, **kw: _StubResponse(None, _raise_json=True),
    )
    with pytest.raises(GeocodingError, match="parse"):
        geocode("city")


def test_timeout_raises_geocoding_error(monkeypatch):
    def _raise_timeout(*a, **kw):
        raise requests.Timeout("request timed out")
    monkeypatch.setattr(gc.requests, "get", _raise_timeout)
    with pytest.raises(GeocodingError, match="Network error"):
        geocode("city")


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------

def test_rate_limit_sleeps_when_two_calls_within_one_second(monkeypatch, _reset_module_state):
    """Two back-to-back calls within < 1s → second call sleeps for the
    remaining interval (≈ 0.5s here)."""
    sleeps: list[float] = []
    monkeypatch.setattr(gc.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(
        gc.requests, "get",
        lambda *a, **kw: _StubResponse([]),
    )

    geocode("first")          # clock at 1000.0
    _reset_module_state[0] += 0.5   # advance 0.5s
    geocode("second")
    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(0.5, abs=1e-6)


def test_rate_limit_does_not_sleep_after_full_interval(monkeypatch, _reset_module_state):
    """≥1s between calls → no sleep needed."""
    sleeps: list[float] = []
    monkeypatch.setattr(gc.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(
        gc.requests, "get",
        lambda *a, **kw: _StubResponse([]),
    )

    geocode("first")
    _reset_module_state[0] += 2.0   # advance 2 seconds
    geocode("second")
    assert sleeps == []


# ---------------------------------------------------------------------------
# Request shape
# ---------------------------------------------------------------------------

def test_user_agent_header_is_set(monkeypatch):
    """Nominatim's usage policy mandates a meaningful User-Agent."""
    captured: dict = {}

    def _capturing_get(url, params=None, headers=None, timeout=None):
        captured["url"]     = url
        captured["params"]  = params
        captured["headers"] = headers
        return _StubResponse([])

    monkeypatch.setattr(gc.requests, "get", _capturing_get)
    geocode("city")
    assert captured["headers"]["User-Agent"].startswith("GSCO")
    assert captured["params"]["format"] == "json"
    assert captured["params"]["limit"]  == _MAX_RESULTS
    assert captured["params"]["q"]      == "city"
