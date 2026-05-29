"""Generate the Comodoro Rivadavia wind-demo seed (M-WIND-A1 v2.0).

Adds a fourth entry to ``demo/saved_analyses/`` so the seeded demo set
exercises the M-WIND-A1 v2.0 **Low** surfaces — the C5 expander "Wind
attribution context" sub-section and the PDF audit appendix "Wind
attribution context" block, both of which fire only when at least one
in-scope Air indicator lands at ``wind_attributability_state == "low"``.

Why Comodoro Rivadavia (lat -45.86, lon -67.50):

- Sits inside the Patagonian "Roaring Forties" westerly belt; mean wind
  speed at 10 m is ~7-8 m/s sustained year-round, comfortably above the
  WA7 / spec §5.2 Low gate of 5.0 m/s.
- Real oil and gas hub on the Argentinian coast (San Jorge Basin), so the
  19-item indicator screening returns real signal rather than empty
  payloads — there's actual industry inside the 10 km buffer.
- The South Atlantic sits east of the city (downwind of the westerlies),
  Patagonian steppe upwind — clean upwind ring vs industrial downwind
  means the asymmetry ratio also has a chance to push toward / cross the
  2.5 Low gate, compounding the already-Low speed gate.

The existing three seeds (Sapezal, Brasilia, Suape) all land in Moderate
for AAI — the amber arrow surface fires, but the Low text surfaces stay
un-demoed. This fourth seed is the deliberate "I want to see the
disclaimer" demo path.

Mirrors ``tools/seed_suape_wind_demo.py`` exactly; only the fixture differs.

Run via:

    EE_PROJECT_ID=supply-chain-observatory .venv/bin/python \\
        tools/seed_comodoro_wind_demo.py
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
    / "demo" / "saved_analyses" / "wind_low_attribution_patagonia.json"
)
_WIND_IDS_SORTED: tuple[str, ...] = tuple(sorted(WIND_ATTRIBUTABILITY_INDICATORS))


_FIXTURE: dict = {
    "name": "Comodoro Rivadavia — San Jorge Oil & Gas Basin, Argentina",
    "centre": {"lat": -45.8645, "lon": -67.4969},
    "radius_km": 10,
    "centre_metadata": {
        "node_id":   "oilgas_comodoro",
        "node_name": "Comodoro Rivadavia oil & gas hub (demo)",
        "source":    (
            "P-04 supply-chain scope · Oil & gas extraction / refining "
            "— San Jorge Basin, Patagonian coast"
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
            "  ✓ Low state achieved — C5 expander Wind attribution context "
            "sub-section and PDF appendix Low block will both fire."
        )
    elif any(s == "moderate" for s in states_seen):
        print(
            "  ◐ Moderate states only — wind arrow fires amber. To force Low, "
            "consider a fifth seed even further into the westerly belt "
            "(e.g. Rio Gallegos, lat -51.6) or tune WIND_SPEED_LOW_MIN_MS."
        )
    else:
        print("  ⚠ no Moderate/Low states.")


if __name__ == "__main__":
    main()
