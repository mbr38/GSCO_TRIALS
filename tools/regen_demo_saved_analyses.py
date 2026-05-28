"""Regenerate the two demo saved-analysis JSONs against the live engine.

Replaces ``demo/saved_analyses/{high_priority_amazon,low_priority_brasilia}.json``
with fresh ScreeningRun output that includes the M-ATTRIB-A1 fields
(``nature.supplier_spatial_link.*``, ``nature.habitat.attributability_state``,
``nature.regional_loss_evidence.{ratio,window}``, ``nature.measurement_quality``,
``air.measurement_quality_score``).

Run from the repo root::

    EE_PROJECT_ID=supply-chain-observatory python tools/regen_demo_saved_analyses.py

Takes ~10-15 minutes total (mostly EE round-trips for the 43.1 km
Distrito Federal buffer). Earth Engine must be authenticated; reads
``EE_PROJECT_ID`` from the environment, same as the Streamlit app.

The envelope matches what ``ui.components.c8_action_bar._save_as_report``
writes on the Save-as-report button, including ``screening_setup`` and
``centre_metadata`` so the Saved Analyses list shows the original
readable names and the M-UI-A6 Hansen card surfaces work end-to-end.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Repo root on sys.path so `engine` + `ui` import when running directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ee

from engine.orchestrator import ScreeningRun
# 19-item user-selectable subset — same set the P-04 form ships with
# "all indicators" selected (NOT engine.ids.ALL_INDICATOR_IDS, which is
# the 204 canonical emitted IDs).
from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS


# ---------------------------------------------------------------------------
# Per-analysis fixtures — drop-in replacements for the existing demo seeds.
# Radii match the prior JSONs (5 km / 43.1 km); names + centre_metadata
# preserved so the Saved Analyses list reads the same.
# ---------------------------------------------------------------------------

_TIME_RANGE: tuple[str, str] = ("2026-02-22", "2026-05-23")


_FIXTURES: list[dict] = [
    {
        "output_path": "demo/saved_analyses/high_priority_amazon.json",
        "name": "Sapezal Plantation (demo) — Soy & Cattle — Pará / Mato Grosso",
        "centre": {"lat": -13.5417, "lon": -58.7642},
        "radius_km": 5,
        "centre_metadata": {
            "node_id":   "soy_04",
            "node_name": "Sapezal Plantation (demo)",
            "source":    "P-04 supply-chain scope · Soy & Cattle — Pará / Mato Grosso",
        },
    },
    {
        "output_path": "demo/saved_analyses/low_priority_brasilia.json",
        "name": "Distrito Federal, Brazil — Region screening",
        "centre": {"lat": -15.7808, "lon": -47.7968},
        "radius_km": 43.1,
        "centre_metadata": {
            "country":     "Brazil",
            "region_name": "Distrito Federal",
            "source":      "P-04 region scope · Distrito Federal, Brazil",
        },
    },
]


def _init_ee() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        sys.exit("EE_PROJECT_ID is not set; aborting.")
    ee.Initialize(project=project)


def _run_one(fixture: dict) -> dict:
    """Run ScreeningRun against ``fixture`` and return the saved-analysis envelope."""
    aoi = {"centre": fixture["centre"], "radius_km": fixture["radius_km"]}
    indicators = set(ALL_INDICATOR_IDS)
    now = datetime.now(timezone.utc)

    print(f"[regen] {fixture['name']} — running screening ({fixture['radius_km']} km)…")
    payload = ScreeningRun(
        aoi=aoi,
        selected_indicators=indicators,
        time_range=_TIME_RANGE,
        ee_client=None,
        centre_metadata=fixture["centre_metadata"],
    ).run()

    # Sanity: surface the M-ATTRIB-A1 fields we expect to land.
    attrib_state = payload.get("nature.habitat.attributability_state")
    offset_km    = payload.get("nature.supplier_spatial_link.centroid_offset_km")
    rle_ratio    = payload.get("nature.regional_loss_evidence.ratio")
    rle_window   = payload.get("nature.regional_loss_evidence.window")
    print(
        f"[regen]   attributability={attrib_state!r}  offset={offset_km}  "
        f"ratio={rle_ratio}  window={rle_window}"
    )

    return {
        "id":              str(uuid.uuid4()),
        "name":            fixture["name"],
        "type":            "screening",
        "screening_setup": {
            "centre":           fixture["centre"],
            "centre_metadata":  fixture["centre_metadata"],
            "indicators":       sorted(indicators),
            "mode":             "screening",
            "radius_km":        fixture["radius_km"],
            "time_range":       list(_TIME_RANGE),
        },
        "date_saved":      now.isoformat(),
        "payload":         payload,
    }


def main() -> None:
    _init_ee()
    repo_root = Path(__file__).resolve().parents[1]

    for fixture in _FIXTURES:
        entry = _run_one(fixture)
        out_path = repo_root / fixture["output_path"]
        out_path.write_text(
            json.dumps(entry, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"[regen]   wrote {out_path}")

    print("[regen] done.")


if __name__ == "__main__":
    main()
