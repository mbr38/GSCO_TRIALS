"""Regenerate demo/saved_analyses fixtures for M-WIND-A1 v2.0.

M-WIND-A1 v2.0 adds seven additive fields inside ``provenance.extra`` for
each of the five in-scope Air indicators (NO₂, SO₂, HCHO, AAI, AOD):

    wind_attributability_state    "high" / "moderate" / "low" / "sparse"
    wind_mean_speed_ms            float | None
    wind_mean_asymmetry_ratio     float | None
    wind_mean_direction_deg       float | None
    wind_n_anomaly_days           int
    wind_n_calm_days              int
    wind_data_window              ISO date-range string | None

The two demo seeds (Sapezal 5 km, Distrito Federal 43.1 km) were committed
before the milestone shipped, so their provenance.extra blocks do NOT carry
these fields. Until the seeds are refreshed, the wind arrow overlay and the
C5 / PDF Low disclaimer surfaces will appear only for fresh screenings, never
for the pre-seeded analyses a demo viewer opens from P-10.

Pattern carried from ``tools/regen_saved_analyses_m_tier_a3.py``: preserve
the top-level ``id`` and ``name`` so any P-10 view-state bookmarks survive
the regen; only ``date_saved`` + ``payload`` are refreshed.

Run via:

    EE_PROJECT_ID=supply-chain-observatory .venv/bin/python \\
        tools/regen_saved_analyses_m_wind_a1.py

Wall time: ~10-15 min total (mostly the 43.1 km Distrito Federal run; AOD
chunking dominates). The script logs the wind state and underlying numbers
for each in-scope indicator per fixture so the operator can spot-check that
the regen surfaces at least one Low or Moderate state worth demoing — if
both fixtures land in High across all five indicators, the visual surfaces
will be invisible and the demo wouldn't actually exercise the new feature.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from the repo root via `python tools/...`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ee  # type: ignore[import]

from engine.constants import WIND_ATTRIBUTABILITY_INDICATORS
from engine.orchestrator import ScreeningRun


_SEED_DIR = Path(__file__).resolve().parent.parent / "demo" / "saved_analyses"

# Sort key so the report is deterministic. WIND_ATTRIBUTABILITY_INDICATORS
# is a frozenset; sorting gives the consistent NO₂ → SO₂ → HCHO → AAI → AOD
# audit order analysts expect.
_WIND_IDS_SORTED: tuple[str, ...] = tuple(sorted(WIND_ATTRIBUTABILITY_INDICATORS))


def _init_ee() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        sys.exit(
            "EE_PROJECT_ID not set; export it (e.g. supply-chain-observatory) "
            "and rerun."
        )
    ee.Initialize(project=project)


def _format_wind_row(payload: dict, indicator_id: str) -> str:
    """One-line summary of one indicator's wind block, for the console report."""
    prov = payload.get(f"_provenance.{indicator_id}") or {}
    extra = prov.get("extra") or {}
    if "wind_attributability_state" not in extra:
        return f"    {indicator_id:10s}  (no wind block — indicator may be skipped or absent)"
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


def _regen_one(path: Path) -> dict:
    """Regenerate the fixture at `path` and return a one-line summary."""
    print(f"\n=== {path.name} ===", flush=True)
    fixture = json.loads(path.read_text(encoding="utf-8"))
    payload_before = fixture["payload"]
    meta_before = payload_before["_meta"]

    aoi                 = meta_before["aoi"]
    time_range          = tuple(meta_before["time_range"])
    selected_indicators = set(meta_before["selected_indicators"])
    centre_metadata     = meta_before["centre_metadata"]

    print(f"  AOI:            {aoi}")
    print(f"  time_range:     {time_range}")
    print(f"  indicators:     {len(selected_indicators)}")
    print(f"  running screening (this takes a few minutes)...", flush=True)

    run = ScreeningRun(
        aoi=aoi,
        selected_indicators=selected_indicators,
        time_range=time_range,
        ee_client=None,
        centre_metadata=centre_metadata,
    )
    payload_after = run.run()

    # Surface the per-indicator wind state so the operator can sanity-check
    # whether the demo will actually visualise the arrow / fire the disclaimer.
    print("  wind attribution per in-scope indicator:")
    states_seen: list[str] = []
    for ind_id in _WIND_IDS_SORTED:
        print(_format_wind_row(payload_after, ind_id))
        prov = payload_after.get(f"_provenance.{ind_id}") or {}
        extra = prov.get("extra") or {}
        s = extra.get("wind_attributability_state")
        if s:
            states_seen.append(s)

    fixture_after = {
        "id":              fixture["id"],   # preserve UUID
        "name":            fixture["name"], # preserve display name
        "type":            fixture.get("type", "screening"),
        "date_saved":      datetime.now(timezone.utc).isoformat(),
        "screening_setup": fixture.get("screening_setup", {}),
        "payload":         payload_after,
    }

    path.write_text(
        json.dumps(fixture_after, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    print(f"  wrote: {path}", flush=True)
    return {
        "name":   path.name,
        "states": states_seen,
    }


def main() -> None:
    _init_ee()
    fixtures = sorted(_SEED_DIR.glob("*.json"))
    if not fixtures:
        sys.exit(f"no fixtures found in {_SEED_DIR}")
    results = [_regen_one(p) for p in fixtures]
    print("\n=== summary ===")
    for r in results:
        states = ", ".join(r["states"]) or "(no wind states seen)"
        print(f"  {r['name']:40s} states: {states}")
    # Demo-quality check: at least one Low or Moderate across both fixtures
    # makes the demo actually exercise the wind arrow / disclaimer paths.
    all_states = [s for r in results for s in r["states"]]
    if any(s in ("low", "moderate") for s in all_states):
        print("\n  ✓ at least one Low/Moderate state present — visual surfaces will fire.")
    else:
        print(
            "\n  ⚠ no Low/Moderate states across either fixture — wind arrow will be"
            " green-only in the demo. Consider running a deliberately wind-affected"
            " location through the picker to bake a Low/Moderate demo seed."
        )


if __name__ == "__main__":
    main()
