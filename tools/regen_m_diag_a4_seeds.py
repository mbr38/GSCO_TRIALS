"""M-DIAG-A4 Phase 3 (E1/E2) — regenerate ALL 5 production seeds post-fix.

Generic over the 5 seeds in ``demo/saved_analyses/*.json``: reads each seed's
own ``screening_setup`` (centre / radius / metadata / time_range / id / name)
so every seed regenerates against its original AOI + window — and therefore the
correct trailing climatology baseline — then re-runs ``ScreeningRun`` against the
post-M-DIAG-A4 engine and writes the seed back in place.

Captures a per-seed composite-stability record (DGC7: "accept defensible
movement") to ``analysis/m_diag_a4_seed_stability.json`` — before/after
``composite.overall_screening`` + ``composite.confidence`` and the per-air-
indicator z/score deltas the temporal denominator drives.

Run from repo root:
    EE_PROJECT_ID=supply-chain-observatory python tools/regen_m_diag_a4_seeds.py

Long run (full screening incl. Nature per seed; the 43.1 km Distrito Federal
seed dominates). EE must be authenticated; reads EE_PROJECT_ID from env.
"""

from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ee

from engine.orchestrator import ScreeningRun
from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS

_REPO = Path(__file__).resolve().parents[1]
_SEED_GLOB = str(_REPO / "demo" / "saved_analyses" / "*.json")
_AIR_GHG = (
    "air.aai", "air.aod", "air.co", "air.hcho", "air.no2",
    "air.o3", "air.so2", "ghg.ch4", "ghg.viirs",
)


def _init_ee() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        sys.exit("EE_PROJECT_ID is not set; aborting.")
    ee.Initialize(project=project)


def _snapshot_metrics(payload: dict) -> dict:
    """The composite + per-air metrics we track for the stability record."""
    out = {
        "composite.overall_screening": payload.get("composite.overall_screening"),
        "composite.confidence": payload.get("composite.confidence"),
    }
    for ind in _AIR_GHG:
        out[f"{ind}.z"] = payload.get(f"{ind}.z")
        out[f"{ind}.score"] = payload.get(f"{ind}.score")
        out[f"{ind}.hf"] = payload.get(f"{ind}.hf")
    return out


def main() -> None:
    _init_ee()
    now = datetime.now(timezone.utc)
    stability = []

    for path in sorted(glob.glob(_SEED_GLOB)):
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        setup = record["screening_setup"]
        aoi = {"centre": setup["centre"], "radius_km": setup["radius_km"]}
        time_range = tuple(setup["time_range"])
        before = _snapshot_metrics(record.get("payload", {}))

        print(f"[regen] {Path(path).name} — {setup['radius_km']} km "
              f"{time_range} …", flush=True)
        payload = ScreeningRun(
            aoi=aoi,
            selected_indicators=set(ALL_INDICATOR_IDS),
            time_range=time_range,
            ee_client=None,
            centre_metadata=setup.get("centre_metadata"),
        ).run()
        after = _snapshot_metrics(payload)

        record["payload"] = payload
        record["date_saved"] = now.isoformat()
        Path(path).write_text(
            json.dumps(record, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        b = before["composite.overall_screening"]
        a = after["composite.overall_screening"]
        delta = (a - b) if (isinstance(a, (int, float)) and isinstance(b, (int, float))) else None
        print(f"[regen]   composite {b} -> {a}  (Δ={delta})", flush=True)
        stability.append({
            "seed": Path(path).name,
            "name": record.get("name"),
            "radius_km": setup["radius_km"],
            "time_range": list(time_range),
            "before": before,
            "after": after,
            "composite_delta": delta,
        })

    out = _REPO / "analysis" / "m_diag_a4_seed_stability.json"
    out.write_text(json.dumps({"_meta": {"milestone": "M-DIAG-A4", "phase": 3,
                   "regenerated": now.isoformat()}, "seeds": stability},
                   indent=2, default=str), encoding="utf-8")
    print(f"[regen] wrote {out}")


if __name__ == "__main__":
    main()
