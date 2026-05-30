"""M-CH4-A1 Step D — regenerate the 5 production seeds for the CH₄
reference-data reclassification.

The reclassification changes only SCORING (composite weights, removed CH₄
sub-aggregates, QA/anomaly aggregation), all of which are PURE functions of the
per-indicator values already stored in each seed's payload (CH₄ extraction is
unchanged — CH12). So this regenerates deterministically by re-running
`recompute_ghg_aggregates` + the composite on each stored payload — no Earth
Engine round-trips, and no EE-data drift contaminating the documented movement.

For each seed it:
  - pops the stale CH₄ scored sub-aggregates the new engine no longer emits
    (ghg.ch4_hotspot_signal, ghg.ch4_context_adjusted),
  - refreshes the GHG aggregates and the cross-pillar composite,
  - rewrites the JSON, and prints the before/after movement.

Run from repo root:  python tools/regen_m_ch4_a1_seeds.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import ghg
from engine.orchestrator import compute_composite_overall, compute_composite_confidence

SEED_DIR = "demo/saved_analyses"
_STALE_CH4_SUBAGGS = ("ghg.ch4_hotspot_signal", "ghg.ch4_context_adjusted")
_TRACK = (
    "ghg.core_audit_support",
    "ghg.spatiotemporal_anomaly",
    "ghg.audit_followup_priority",
    "composite.overall_screening",
    "composite.confidence",
)


def regen_one(path: str) -> dict:
    with open(path) as f:
        seed = json.load(f)
    payload = seed["payload"]
    setup = seed["screening_setup"]
    aoi = {"centre": setup["centre"], "radius_km": setup["radius_km"]}
    selected = {i for i in setup["indicators"] if i.startswith("ghg")}

    before = {k: payload.get(k) for k in _TRACK}

    # Drop the CH₄ scored sub-aggregates the new engine no longer produces.
    for k in _STALE_CH4_SUBAGGS:
        payload.pop(k, None)

    # Pure refresh of GHG aggregates, then the cross-pillar composite. Air +
    # Nature aggregates are unchanged, so their stored values stand.
    ghg.recompute_ghg_aggregates(payload, selected, setup.get("mode", "screening"), aoi)
    payload["composite.overall_screening"] = compute_composite_overall(payload)
    payload["composite.confidence"] = compute_composite_confidence(payload)

    after = {k: payload.get(k) for k in _TRACK}

    # Sanity: CH₄ extraction preserved (raw value still present); scored
    # sub-aggregates gone.
    assert payload.get("ghg.ch4.site") is not None, "CH₄ raw value lost!"
    for k in _STALE_CH4_SUBAGGS:
        assert k not in payload, f"{k} should be gone"

    with open(path, "w") as f:
        json.dump(seed, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return {"name": os.path.basename(path), "before": before, "after": after}


def _fmt(v) -> str:
    return f"{v:.4f}" if isinstance(v, (int, float)) else str(v)


def main() -> None:
    rows = [regen_one(p) for p in sorted(glob.glob(f"{SEED_DIR}/*.json"))]
    print(f"\n{'seed':38} {'metric':28} {'before':>9} {'after':>9} {'Δ':>9}")
    for r in rows:
        for k in _TRACK:
            b, a = r["before"][k], r["after"][k]
            d = (a - b) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
            print(f"{r['name']:38} {k:28} {_fmt(b):>9} {_fmt(a):>9} {_fmt(d):>9}")
        print()


if __name__ == "__main__":
    main()
