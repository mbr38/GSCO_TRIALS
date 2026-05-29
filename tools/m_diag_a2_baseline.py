"""M-DIAG-A2 Step C.2 — baseline regen at current thresholds + C1 fix.

Runs all 5 seeds (Sapezal, Brasilia, Suape, Comodoro, Norilsk) against:
- M-DIAG-A1 fix (mean_key = f"{band}_mean") — already live
- M-DIAG-A2 C1 fix (AAI abs() asymmetry ratio) — already live
- CURRENT first-pass wind thresholds (pre-calibration)

Outputs:
- Full JSON envelopes at ``demo/saved_analyses/_baseline_m_diag_a2/`` for
  audit + later diff-vs-calibrated comparisons (NOT promoted to production)
- A tabular wind-state matrix printed to stdout: 5 wind indicators × 5 seeds.
  Used as input to the calibration sweep (C3).

Production seeds at ``demo/saved_analyses/`` are NOT touched. Run takes
~30-45 minutes total (5 × 6-9 min).
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

from engine.constants import WIND_ATTRIBUTABILITY_INDICATORS  # noqa: E402
from engine.orchestrator import ScreeningRun  # noqa: E402
from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS  # noqa: E402


_TIME_RANGE: tuple[str, str] = ("2026-02-22", "2026-05-23")
_OUTPUT_DIR: Path = (
    Path(__file__).resolve().parents[1]
    / "demo" / "saved_analyses" / "_baseline_m_diag_a2"
)
_WIND_IDS_SORTED: tuple[str, ...] = tuple(sorted(WIND_ATTRIBUTABILITY_INDICATORS))


_FIXTURES: list[dict] = [
    {
        "output_basename": "sapezal.json",
        "name":            "Sapezal Plantation (demo) — Soy & Cattle — Pará / Mato Grosso",
        "centre":          {"lat": -13.5417, "lon": -58.7642},
        "radius_km":       5,
        "expected":        "moderate",
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
        "expected":        "moderate",
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
        "expected":        "moderate-to-low",
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
        "expected":        "sparse-to-low",
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
        "expected":        "high-on-NO2/SO2",
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


def _wind_summary(payload: dict, indicator_id: str) -> dict:
    prov = payload.get(f"_provenance.{indicator_id}") or {}
    extra = prov.get("extra") or {}
    return {
        "state":   extra.get("wind_attributability_state"),
        "n_days":  extra.get("wind_n_anomaly_days"),
        "n_calm":  extra.get("wind_n_calm_days"),
        "speed":   extra.get("wind_mean_speed_ms"),
        "ratio":   extra.get("wind_mean_asymmetry_ratio"),
        "hf":      payload.get(f"{indicator_id}.hf"),
        "z":       payload.get(f"{indicator_id}.z"),
        "skip":    prov.get("skipped_reason"),
    }


def _run_one(fixture: dict) -> tuple[dict, dict]:
    aoi = {"centre": fixture["centre"], "radius_km": fixture["radius_km"]}
    indicators = set(ALL_INDICATOR_IDS)
    print(
        f"[m-diag-a2-baseline] {fixture['name']} "
        f"— running ScreeningRun (radius_km={fixture['radius_km']})…",
        flush=True,
    )
    payload = ScreeningRun(
        aoi=aoi,
        selected_indicators=indicators,
        time_range=_TIME_RANGE,
        ee_client=None,
        centre_metadata=fixture["centre_metadata"],
    ).run()

    summaries = {ind: _wind_summary(payload, ind) for ind in _WIND_IDS_SORTED}
    return payload, summaries


def _print_matrix(per_seed_summaries: dict[str, dict]) -> None:
    """Print the wind state matrix: 5 indicators × 5 seeds."""
    print()
    print("=" * 78)
    print("WIND ATTRIBUTABILITY MATRIX (current thresholds, post-C1 fix)")
    print("=" * 78)
    seed_names = list(per_seed_summaries.keys())
    print(
        f"  {'indicator':<10s}  "
        + "  ".join(f"{n:<18s}" for n in seed_names)
    )
    for ind in _WIND_IDS_SORTED:
        row_parts = []
        for seed_name in seed_names:
            s = per_seed_summaries[seed_name].get(ind) or {}
            state = s.get("state") or "—"
            n_days = s.get("n_days")
            speed = s.get("speed")
            ratio = s.get("ratio")
            cell = f"{state}/N={n_days}"
            if isinstance(speed, (int, float)) and isinstance(ratio, (int, float)):
                cell += f" s={speed:.1f} r={ratio:.2f}"
            row_parts.append(f"{cell:<18s}")
        print(f"  {ind:<10s}  " + "  ".join(row_parts))
    print()
    print("Expected by operator (per spec §4.2 / Step A recon):")
    for fixture in _FIXTURES:
        seed = fixture["output_basename"].removesuffix(".json")
        print(f"  {seed:<12s}  {fixture['expected']}")


def main() -> None:
    requested = {a.strip().removesuffix(".json") for a in sys.argv[1:] if a.strip()}
    if requested:
        fixtures = [
            f for f in _FIXTURES
            if f["output_basename"].removesuffix(".json") in requested
        ]
    else:
        fixtures = _FIXTURES

    _init_ee()
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    per_seed_summaries: dict[str, dict] = {}
    for fixture in fixtures:
        payload, summaries = _run_one(fixture)
        envelope = {
            "id":              str(uuid.uuid4()),
            "name":            fixture["name"],
            "type":            "screening",
            "screening_setup": {
                "centre":          fixture["centre"],
                "centre_metadata": fixture["centre_metadata"],
                "indicators":      sorted(set(ALL_INDICATOR_IDS)),
                "mode":            "screening",
                "radius_km":       fixture["radius_km"],
                "time_range":      list(_TIME_RANGE),
            },
            "date_saved":      datetime.now(timezone.utc).isoformat(),
            "payload":         payload,
            "expected_attributability": fixture["expected"],
        }
        out_path = _OUTPUT_DIR / fixture["output_basename"]
        out_path.write_text(
            json.dumps(envelope, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        seed_name = fixture["output_basename"].removesuffix(".json")
        per_seed_summaries[seed_name] = summaries
        print(f"[m-diag-a2-baseline]   wrote {out_path}", flush=True)

    _print_matrix(per_seed_summaries)
    print("[m-diag-a2-baseline] done.")


if __name__ == "__main__":
    main()
