"""NDVI validation — extraction harness (evidence-only, no engine changes).

Validates the Nature pillar's vegetation indicator against an INDEPENDENT
productivity reference (MOD17A2H GPP), mirroring the AOD↔PM2.5 and AAI↔FIRMS
raw-vs-anomaly checks.

For each site we extract three numbers over one fixed window / 5 km AOI:
  (a) raw NDVI            — site window-mean NDVI (engine `nature.ndvi.mean`)
  (b) engine anomaly score — `nature.ndvi.score`  = clamp((NDVI_bg − NDVI_site)/(3σ),0,1)
                             via the PRODUCTION path (engine.nature.compute_ndvi_condition).
                             Higher = worse (inverted, lower-NDVI-is-worse, IC §3.2 / §7.4).
  (c) reference GPP        — window-mean MOD17A2H Gpp over the same site buffer.

Reference independence: MOD17 GPP is produced by the BIOME-PROPERTY-LOOK-UP /
light-use-efficiency model driven by MOD15A2H FPAR/LAI and GMAO meteorology —
NOT the MOD13Q1 NDVI value the engine scores. It is the brief's preferred
"ground-truth-equivalent" productivity reference (not the weaker NDVI-derived VCI
fallback).

Run:
    EE_PROJECT_ID=supply-chain-observatory python analysis/ndvi_gpp_extract.py

Writes analysis/ndvi_gpp_validation.csv. Does not touch engine/ or constants.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("EE_PROJECT_ID", "supply-chain-observatory")

import ee  # noqa: E402
import pandas as pd  # noqa: E402

# Production engine path — same modules the live screening uses.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.nature import compute_ndvi_condition  # noqa: E402
from engine.core.fallback import FallbackContext  # noqa: E402
from engine.core.buffers import site_buffer  # noqa: E402

# --- Window / radius — consistent with the other validations -----------------
# AOD used 181 d / 5 km; AAI used 5 km. We use a 184-day NH-growing-season
# window so the temperate/boreal controls are leaf-on (equatorial controls are
# aseasonal). Seasonal phenology affects (a),(b),(c) identically per site since
# all three read the SAME window — the cross-site comparison is apples-to-apples.
WINDOW = ("2025-05-01", "2025-10-31")
RADIUS_KM = 5.0

GPP_ASSET = "MODIS/061/MOD17A2H"   # 8-day, 500 m, band 'Gpp' (kg C m⁻² 8d⁻¹, scale 1e-4)
GPP_FILL_SCALED = 3.0              # scaled fill values (>=3.276) → mask out

SITES_JSON = ROOT / "analysis" / "ndvi_gpp_sites.json"
OUT_CSV = ROOT / "analysis" / "ndvi_gpp_validation.csv"


def _init_ee() -> None:
    ee.Initialize(project=os.environ["EE_PROJECT_ID"])


def _ref_gpp(lat: float, lon: float) -> float | None:
    """Window-mean GPP over the site buffer — independent productivity reference.

    Same buffer geometry as the engine site reduction. Good-quality pixels only
    (Psn_QC MODLAND bit 0 == 0) and fill values masked.
    """
    buf = site_buffer({"lat": lat, "lon": lon}, RADIUS_KM)
    ic = ee.ImageCollection(GPP_ASSET).filterDate(*WINDOW).filterBounds(buf)

    def _clean(img):
        gpp = img.select("Gpp").multiply(0.0001).rename("Gpp")
        qc = img.select("Psn_QC")
        good = qc.bitwiseAnd(1).eq(0)            # MODLAND QC: 0 = good quality
        notfill = gpp.lt(GPP_FILL_SCALED)
        return gpp.updateMask(good).updateMask(notfill)

    mean_img = ic.map(_clean).mean()
    val = mean_img.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=buf, scale=500, maxPixels=1e9,
    ).get("Gpp")
    return val.getInfo() if val is not None else None


def main() -> None:
    _init_ee()
    sites = json.loads(SITES_JSON.read_text())["sites"]
    fb = FallbackContext()  # production defaults: not strict, SPPY temporal fallback
    rows = []
    for i, s in enumerate(sites, 1):
        aoi = {"centre": {"lat": s["lat"], "lon": s["lon"]}, "radius_km": RADIUS_KM}
        row = {
            "id": s["id"], "category": s["category"], "name": s["name"],
            "lat": s["lat"], "lon": s["lon"],
        }
        # (a)(b) production NDVI path
        try:
            snap = compute_ndvi_condition(aoi, WINDOW, "screening", ee, fallback=fb)
            row["ndvi_raw"] = snap.get("nature.ndvi.mean")
            row["ndvi_score"] = snap.get("nature.ndvi.score")  # anomaly, higher=worse
            row["ndvi_z"] = snap.get("nature.ndvi.z")
            row["ndvi_anomaly"] = snap.get("nature.ndvi.anomaly")
            row["ndvi_conf"] = snap.get("nature.ndvi.confidence")
            row["low_ndvi_pct"] = snap.get("nature.low_ndvi.pct")
            row["ndvi_err"] = None
        except Exception as e:  # IndicatorComputeError etc. — record, don't crash
            row.update(dict.fromkeys(
                ["ndvi_raw", "ndvi_score", "ndvi_z", "ndvi_anomaly",
                 "ndvi_conf", "low_ndvi_pct"], None))
            row["ndvi_err"] = f"{type(e).__name__}: {e}"
        # (c) independent reference
        try:
            row["gpp_ref"] = _ref_gpp(s["lat"], s["lon"])
            row["gpp_err"] = None
        except Exception as e:
            row["gpp_ref"] = None
            row["gpp_err"] = f"{type(e).__name__}: {e}"

        print(f"[{i:2d}/{len(sites)}] {s['id']:24s} "
              f"raw={row['ndvi_raw']!s:>8.8} score={row['ndvi_score']!s:>8.8} "
              f"gpp={row['gpp_ref']!s:>8.8} {row['ndvi_err'] or ''}")
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nwrote {OUT_CSV}  ({len(df)} rows)")


if __name__ == "__main__":
    main()
