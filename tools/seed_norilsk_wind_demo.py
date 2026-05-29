"""Generate the Norilsk wind-demo seed (M-WIND-A1 v2.0).

The fourth wind demo (Comodoro Rivadavia) returned sparse across all five
in-scope Air indicators because Patagonian air is genuinely clean and the
small-buffer-vs-large-ring HF detector never crosses z >= 2.0. To exercise
the **Low** surfaces (C5 expander "Wind attribution context" sub-section
and PDF audit-appendix Low block) we need a location where real industrial
emissions create dramatic site-vs-ring contrast — enough to produce
anomaly days regardless of bg_std behaviour.

Why Norilsk (lat 69.35, lon 88.19):

- **World's largest single-source SO₂ emitter.** The Nornickel polar
  smelter complex emits ~2 million tonnes of SO₂ per year — visible from
  space as a persistent plume on every S5P SO₂ daily image. Site-vs-ring
  contrast is extreme: the smelter sits in roughly 200 km of empty
  Siberian taiga in every direction.
- **Real anomaly days at z >= 2.0.** Unlike Sapezal / Brasilia / Suape
  where AAI's near-zero bg_std artefactually inflates hf, Norilsk's SO₂
  spike days are honest 2σ events against a clean tundra background. The
  wind module gets real anomaly dates to sample ERA5 on.
- **Wind asymmetry potential.** With a single-point emitter and a roughly
  homogeneous background, the upwind vs downwind half-ring contrast on
  anomaly days should be strong — the asymmetry ratio has a clear path
  to crossing the 2.5 Low gate even without high mean wind speed.

Risks (logged for the operator):

- Snow / ice cover dominates Norilsk Feb-May. MAIAC AOD has known issues
  over bright snow surfaces (likely sparse). S5P NO₂ / SO₂ / HCHO are
  largely unaffected.
- AAI over the Arctic may behave atypically — the bg_std behaviour that
  drove 89 anomaly days at the tropical seeds is unlikely to repeat here.
- Coverage is good for S5P (TROPOMI is polar-orbiting); MODIS MAIAC may
  thin out at very high solar zenith angles.

If this seed also lands all-sparse, the fallback is to drop the centre
south by ~5° (e.g. Nizhnevartovsk Siberian oilfield, ~60°N) or tune
WIND_SPEED_LOW_MIN_MS via the v1.x Q-WA-1 calibration.

Run via:

    EE_PROJECT_ID=supply-chain-observatory .venv/bin/python \\
        tools/seed_norilsk_wind_demo.py
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
    / "demo" / "saved_analyses" / "wind_low_attribution_norilsk.json"
)
_WIND_IDS_SORTED: tuple[str, ...] = tuple(sorted(WIND_ATTRIBUTABILITY_INDICATORS))


_FIXTURE: dict = {
    "name": "Norilsk — Nornickel Polar Smelter Complex, Russia",
    "centre": {"lat": 69.3536, "lon": 88.1864},
    "radius_km": 10,
    "centre_metadata": {
        "node_id":   "smelter_norilsk",
        "node_name": "Nornickel polar smelter (demo)",
        "source":    (
            "P-04 supply-chain scope · Nickel & copper smelting "
            "— Norilsk-Taimyr, Russian Arctic"
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


def _format_indicator_diag(payload: dict, indicator_id: str) -> str:
    """Surface site/bg/hf/z so 'all sparse' results are diagnosable."""
    prov = payload.get(f"_provenance.{indicator_id}") or {}
    extra = prov.get("extra") or {}
    site = payload.get(f"{indicator_id}.site")
    bg   = payload.get(f"{indicator_id}.background")
    hf   = payload.get(f"{indicator_id}.hf")
    z    = payload.get(f"{indicator_id}.z")
    n    = extra.get("n_valid_dates")
    skip = prov.get("skipped_reason")
    site_s = f"{site:.3g}" if isinstance(site, (int, float)) else str(site)
    bg_s   = f"{bg:.3g}"   if isinstance(bg,   (int, float)) else str(bg)
    z_s    = f"{z:.2f}"    if isinstance(z,    (int, float)) else str(z)
    return (
        f"    {indicator_id:10s}  site={site_s:>10s}  bg={bg_s:>10s}  "
        f"hf={hf}  z={z_s}  n_valid={n}  skip={skip}"
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

    print("  indicator diagnostic (site / bg / hf / z / n_valid / skip):")
    for ind_id in _WIND_IDS_SORTED:
        print(_format_indicator_diag(payload, ind_id))

    print("\n  wind attribution per in-scope indicator:")
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
        print("  ◐ Moderate states only — wind arrow fires amber, no Low text.")
    else:
        print(
            "  ⚠ no Moderate/Low states — likely the small-buffer-vs-ring "
            "z >= 2 detector still didn't trip even at Nornickel. Consider "
            "shifting south or tuning thresholds."
        )


if __name__ == "__main__":
    main()
