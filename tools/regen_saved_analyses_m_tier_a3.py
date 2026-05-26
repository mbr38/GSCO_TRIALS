"""Regenerate demo/saved_analyses fixtures for M-TIER-A3 Step G.

LM11 of M-TIER-A3 requires all saved-analysis fixtures to be regenerated
post-milestone. Both shipped seeds (Sapezal, Brasilia) are inland — their
ring_land_fraction is ≈ 1.0, so the masked reduction is *bit-identical*
to the pre-milestone unmasked reduction for every six_step indicator
(NO₂, SO₂, CO, HCHO, AAI, O₃, AOD, CH₄, NDVI). The only legitimate diff
is the appearance of three new provenance.extra fields:

    ring_land_fraction:     ≈ 1.0 (geometric land share of the annulus)
    land_mask_applied:      True
    land_mask_asset:        "MODIS/006/MOD44W"

Run via:

    EE_PROJECT_ID=supply-chain-observatory .venv/bin/python \\
        tools/regen_saved_analyses_m_tier_a3.py

Outputs go straight to `demo/saved_analyses/*.json`, overwriting the
shipped seeds. Diff the result against git history to see what changed.

The script preserves the existing top-level `id` and `name` so P-10
view-state survives the regen; `date_saved` and `payload` are refreshed.
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

from engine.orchestrator import ScreeningRun


_SEED_DIR = Path(__file__).resolve().parent.parent / "demo" / "saved_analyses"


def _init_ee() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        sys.exit(
            "EE_PROJECT_ID not set; export it (e.g. supply-chain-observatory) "
            "and rerun."
        )
    ee.Initialize(project=project)


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

    # Surface the new MOD44W provenance fields from one indicator so the
    # console summary makes the diff visible.
    sample_extra = (
        payload_after.get("_provenance.air.no2", {}).get("extra", {})
    )
    print(
        "  new fields seen: "
        f"ring_land_fraction={sample_extra.get('ring_land_fraction')!r}, "
        f"land_mask_applied={sample_extra.get('land_mask_applied')!r}, "
        f"land_mask_asset={sample_extra.get('land_mask_asset')!r}",
    )

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
        "name": path.name,
        "ring_land_fraction": sample_extra.get("ring_land_fraction"),
    }


def main() -> None:
    _init_ee()
    fixtures = sorted(_SEED_DIR.glob("*.json"))
    if not fixtures:
        sys.exit(f"no fixtures found in {_SEED_DIR}")
    results = [_regen_one(p) for p in fixtures]
    print("\n=== summary ===")
    for r in results:
        print(f"  {r['name']:40s} land_fraction = {r['ring_land_fraction']}")


if __name__ == "__main__":
    main()
