"""M-DIAG-A1 — re-run the 5 existing seeds with bg_std instrumentation active.

Writes diagnostic-augmented payloads to ``demo/saved_analyses/diagnostic/``
WITHOUT touching the production seeds at ``demo/saved_analyses/``. Per the
M-DIAG-A1 spec §7 Step B / DG7 / R5: production seeds stay intact for the
duration of the milestone; the diagnostic JSONs are the audit trail the
report cites.

The five seeds (locked by DG3 — no new locations in this milestone):

  - Sapezal (Pará / Mato Grosso) — clean tropical, 5 km buffer
  - Brasilia (Distrito Federal) — regional 43.1 km
  - Suape (Pernambuco) — coastal industrial, 10 km
  - Comodoro Rivadavia (Patagonia) — clean Patagonian, 10 km
  - Norilsk (Nornickel polar smelter) — extreme single-point source, 10 km

Each fixture is the byte-for-byte centre/radius/time_range/centre_metadata
of the production seed; only the OUTPUT path differs. So a seed re-run with
instrumentation present will produce a JSON with all the original fields
PLUS the new ``provenance.extra._diag_bg_std`` block per indicator.

Run from the repo root::

    EE_PROJECT_ID=supply-chain-observatory .venv/bin/python \\
        tools/m_diag_a1_rerun_seeds.py

Takes ~30-45 minutes total (5 × 6-9 minutes per fixture).

REVERTED AT STEP F of the milestone: this tool stays in tree as an audit
artefact (Q-DG-1 = commit), but it becomes inert once the instrumentation
is removed — the ``_diag_bg_std`` block simply won't be populated and the
re-run output collapses to the production shape.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ee  # noqa: E402

from engine.orchestrator import ScreeningRun  # noqa: E402
from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS  # noqa: E402


_TIME_RANGE: tuple[str, str] = ("2026-02-22", "2026-05-23")
_OUTPUT_DIR: Path = (
    Path(__file__).resolve().parents[1] / "demo" / "saved_analyses" / "diagnostic"
)


_FIXTURES: list[dict] = [
    {
        "output_basename": "sapezal.json",
        "name":            "Sapezal Plantation (demo) — Soy & Cattle — Pará / Mato Grosso",
        "centre":          {"lat": -13.5417, "lon": -58.7642},
        "radius_km":       5,
        "centre_metadata": {
            "node_id":   "soy_04",
            "node_name": "Sapezal Plantation (demo)",
            "source":    "P-04 supply-chain scope · Soy & Cattle — Pará / Mato Grosso",
        },
    },
    {
        "output_basename": "brasilia.json",
        "name":            "Distrito Federal, Brazil — Region screening",
        "centre":          {"lat": -15.7808, "lon": -47.7968},
        "radius_km":       43.1,
        "centre_metadata": {
            "country":     "Brazil",
            "region_name": "Distrito Federal",
            "source":      "P-04 region scope · Distrito Federal, Brazil",
        },
    },
    {
        "output_basename": "suape.json",
        "name":            "Suape Port Industrial Complex — Pernambuco, Brazil",
        "centre":          {"lat": -8.4023, "lon": -34.9614},
        "radius_km":       10,
        "centre_metadata": {
            "node_id":   "suape_port",
            "node_name": "Suape port industrial complex (demo)",
            "source":    "P-04 supply-chain scope · Coastal industrial — Pernambuco",
        },
    },
    {
        "output_basename": "comodoro.json",
        "name":            "Comodoro Rivadavia — San Jorge Oil & Gas Basin, Argentina",
        "centre":          {"lat": -45.8645, "lon": -67.4969},
        "radius_km":       10,
        "centre_metadata": {
            "node_id":   "comodoro_oilgas",
            "node_name": "Comodoro Rivadavia oil & gas basin (demo)",
            "source":    "P-04 supply-chain scope · Oil & gas — Patagonia",
        },
    },
    {
        "output_basename": "norilsk.json",
        "name":            "Norilsk — Nornickel Polar Smelter Complex, Russia",
        "centre":          {"lat": 69.3536, "lon": 88.1864},
        "radius_km":       10,
        "centre_metadata": {
            "node_id":   "smelter_norilsk",
            "node_name": "Nornickel polar smelter (demo)",
            "source":    (
                "P-04 supply-chain scope · Nickel & copper smelting "
                "— Norilsk-Taimyr, Russian Arctic"
            ),
        },
    },
]


def _init_ee() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        sys.exit(
            "EE_PROJECT_ID not set; export it (e.g. supply-chain-observatory) "
            "and rerun."
        )
    ee.Initialize(project=project)


def _run_one(fixture: dict) -> dict:
    aoi = {"centre": fixture["centre"], "radius_km": fixture["radius_km"]}
    indicators = set(ALL_INDICATOR_IDS)
    print(
        f"[m-diag-a1] {fixture['name']} — running ScreeningRun "
        f"(radius_km={fixture['radius_km']})…",
        flush=True,
    )
    payload = ScreeningRun(
        aoi=aoi,
        selected_indicators=indicators,
        time_range=_TIME_RANGE,
        ee_client=None,
        centre_metadata=fixture["centre_metadata"],
    ).run()

    # Sanity: confirm that at least one indicator carried the diag bundle.
    seen_diag = sum(
        1 for k, v in payload.items()
        if k.startswith("_provenance.")
        and isinstance(v, dict)
        and (v.get("extra") or {}).get("_diag_bg_std") is not None
    )
    print(
        f"[m-diag-a1]   indicators carrying _diag_bg_std: {seen_diag}",
        flush=True,
    )

    return {
        "id":              str(uuid.uuid4()),
        "name":            fixture["name"],
        "type":            "screening",
        "screening_setup": {
            "centre":          fixture["centre"],
            "centre_metadata": fixture["centre_metadata"],
            "indicators":      sorted(indicators),
            "mode":            "screening",
            "radius_km":       fixture["radius_km"],
            "time_range":      list(_TIME_RANGE),
        },
        "date_saved":      datetime.now(timezone.utc).isoformat(),
        "payload":         payload,
    }


def main() -> None:
    # Optional CLI args: names (without ".json") of fixtures to include.
    # Example: `python m_diag_a1_rerun_seeds.py sapezal norilsk` runs just
    # those two. No args = all 5. Lets a subset-first re-run land cheaply.
    requested = {a.strip().removesuffix(".json") for a in sys.argv[1:] if a.strip()}
    if requested:
        fixtures = [
            f for f in _FIXTURES
            if f["output_basename"].removesuffix(".json") in requested
        ]
        missing = requested - {
            f["output_basename"].removesuffix(".json") for f in fixtures
        }
        if missing:
            sys.exit(
                f"unknown fixture name(s): {sorted(missing)}; "
                f"valid: {sorted(f['output_basename'].removesuffix('.json') for f in _FIXTURES)}"
            )
    else:
        fixtures = _FIXTURES

    _init_ee()
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(
        f"[m-diag-a1] running {len(fixtures)} fixture(s): "
        f"{[f['output_basename'].removesuffix('.json') for f in fixtures]}",
        flush=True,
    )
    for fixture in fixtures:
        envelope = _run_one(fixture)
        out_path = _OUTPUT_DIR / fixture["output_basename"]
        out_path.write_text(
            json.dumps(envelope, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"[m-diag-a1]   wrote {out_path}", flush=True)

    print("[m-diag-a1] done.")


if __name__ == "__main__":
    main()
