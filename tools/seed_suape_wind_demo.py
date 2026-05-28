"""Generate the Suape Port wind-demo seed (M-WIND-A1 v2.0).

Adds a third entry to ``demo/saved_analyses/`` so the seeded demo set
exercises the M-WIND-A1 v2.0 visual surfaces under conditions where the
wind signal is meaningful: Suape Port Industrial Complex (Pernambuco, NE
Brazil) sits under constant SE trade winds at 5–7 m/s, with the Atlantic
upwind of the industrial site — strong asymmetry potential.

Why a third seed (rather than swapping an existing one): the existing
Sapezal and Brasilia seeds land in Moderate / sparse across the five
in-scope Air indicators after the 28 May 2026 regen, which means the
amber-arrow surface fires but the C5 Low sub-section and PDF Low
appendix never do. Adding Suape gives the demo a third coastal-industrial
profile that should land at least one indicator in Low — exercising the
text disclaimers end-to-end without retuning the bucket thresholds
(deferred to v1.x calibration sweep, Q-WA-1).

Mirrors the structure of ``tools/regen_demo_saved_analyses.py``: hardcoded
fixture, runs ``ScreeningRun`` over the same 19-item P-04 ALL_INDICATOR_IDS
set, writes the saved-analysis envelope (``id``, ``name``, ``type``,
``screening_setup``, ``date_saved``, ``payload``) to a fresh file so the
auto-seed glob picks it up at app cold start.

Re-runnable: deletes any existing Suape seed first so the UUID is fresh
and the regen reflects current engine state. Idempotent enough for
demo-prep — production user data lives in session state, not on disk.

Run via:

    EE_PROJECT_ID=supply-chain-observatory .venv/bin/python \\
        tools/seed_suape_wind_demo.py
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ee

from engine.constants import WIND_ATTRIBUTABILITY_INDICATORS
from engine.orchestrator import ScreeningRun
from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS


_OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent
    / "demo" / "saved_analyses" / "wind_priority_suape.json"
)
_WIND_IDS_SORTED: tuple[str, ...] = tuple(sorted(WIND_ATTRIBUTABILITY_INDICATORS))


_FIXTURE: dict = {
    "name": "Suape Port Industrial Complex — Pernambuco, Brazil",
    "centre": {"lat": -8.4023, "lon": -34.9614},
    "radius_km": 10,
    "centre_metadata": {
        "node_id":   "port_suape",
        "node_name": "Suape Port Industrial Complex (demo)",
        "source":    (
            "P-04 supply-chain scope · Petrochemical, shipyard & container terminal "
            "— Pernambuco, NE Brazil"
        ),
    },
    "time_range": ("2026-02-22", "2026-05-23"),
}


def _init_ee() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        sys.exit(
            "EE_PROJECT_ID not set; export it (e.g. supply-chain-observatory) "
            "and rerun."
        )
    ee.Initialize(project=project)


def _format_wind_row(payload: dict, indicator_id: str) -> str:
    prov = payload.get(f"_provenance.{indicator_id}") or {}
    extra = prov.get("extra") or {}
    if "wind_attributability_state" not in extra:
        return f"    {indicator_id:10s}  (no wind block — skipped or absent)"
    state = extra.get("wind_attributability_state")
    speed = extra.get("wind_mean_speed_ms")
    ratio = extra.get("wind_mean_asymmetry_ratio")
    n_days = extra.get("wind_n_anomaly_days")
    n_calm = extra.get("wind_n_calm_days")
    speed_s = f"{speed:.2f}" if isinstance(speed, (int, float)) else "—"
    ratio_s = f"{ratio:.2f}" if isinstance(ratio, (int, float)) else "—"
    return (
        f"    {indicator_id:10s}  state={state:8s}  "
        f"speed={speed_s} m/s  ratio={ratio_s}  "
        f"N_anomaly={n_days}  N_calm={n_calm}"
    )


def main() -> None:
    _init_ee()

    print(f"=== {_FIXTURE['name']} ===")
    print(f"  centre:     {_FIXTURE['centre']}")
    print(f"  radius_km:  {_FIXTURE['radius_km']}")
    print(f"  time_range: {_FIXTURE['time_range']}")
    print(f"  running screening (this takes a few minutes)...", flush=True)

    aoi = {
        "centre": _FIXTURE["centre"],
        "radius_km": _FIXTURE["radius_km"],
    }
    indicators = set(ALL_INDICATOR_IDS)
    payload = ScreeningRun(
        aoi=aoi,
        selected_indicators=indicators,
        time_range=_FIXTURE["time_range"],
        ee_client=None,
        centre_metadata=_FIXTURE["centre_metadata"],
    ).run()

    print("  wind attribution per in-scope indicator:")
    states_seen: list[str] = []
    for ind_id in _WIND_IDS_SORTED:
        print(_format_wind_row(payload, ind_id))
        prov = payload.get(f"_provenance.{ind_id}") or {}
        extra = prov.get("extra") or {}
        s = extra.get("wind_attributability_state")
        if s:
            states_seen.append(s)

    envelope = {
        "id":              str(uuid.uuid4()),
        "name":            _FIXTURE["name"],
        "type":            "screening",
        "screening_setup": {
            "centre":          _FIXTURE["centre"],
            "centre_metadata": _FIXTURE["centre_metadata"],
            "indicators":      sorted(indicators),
            "mode":            "screening",
            "radius_km":       _FIXTURE["radius_km"],
            "time_range":      list(_FIXTURE["time_range"]),
        },
        "date_saved":      datetime.now(timezone.utc).isoformat(),
        "payload":         payload,
    }

    _OUTPUT_PATH.write_text(
        json.dumps(envelope, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    print(f"\n  wrote: {_OUTPUT_PATH}")
    print(f"  states: {', '.join(states_seen) or '(no wind states seen)'}")
    if any(s == "low" for s in states_seen):
        print(
            "  ✓ at least one Low state — C5 expander and PDF appendix "
            "Low surfaces will fire in the demo."
        )
    elif any(s == "moderate" for s in states_seen):
        print(
            "  ◐ Moderate states only — wind arrow fires amber, but the "
            "Low C5 sub-section and PDF appendix will not. Consider a "
            "more wind-exposed location if Low coverage matters."
        )
    else:
        print(
            "  ⚠ no Moderate/Low states — wind arrow will be green or absent."
        )


if __name__ == "__main__":
    main()
