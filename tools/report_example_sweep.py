"""Report Section 7 worked-example sweep (read-only).

Runs a STANDARD single-supplier screening for each candidate supplier
facility, exactly as the app does (same ScreeningRun entry point, same
19-indicator P-04 "all indicators" set, same 5 km site buffer + engine-default
5x-capped background ring, same default 90-day latest-valid window anchored to
today with the engine's SPPY temporal fallback ON), then captures a comparison
table to surface which sites best illustrate the engine's scoring mechanisms.

This script does NOT modify engine code, constants, or docs. It only calls the
public ScreeningRun API and reads its result payload — the same payload the
P-05 result page renders.

Run from repo root:

    EE_PROJECT_ID=supply-chain-observatory python tools/report_example_sweep.py

Writes tools/report_example_sweep.csv and prints a markdown table sorted so the
most mechanism-rich sites surface first.

Invocation pattern mirrors tools/regen_demo_saved_analyses.py:
  - aoi = {"centre": {"lat", "lon"}, "radius_km": 5}
  - selected_indicators = set(ALL_INDICATOR_IDS)  (19 user-facing IDs)
  - ScreeningRun(...).run()
The 5 km site buffer and the 5x-capped background ring are the engine defaults
(engine/core/buffers.py: BACKGROUND_RING_RADIUS_MULTIPLE=5, MAX_KM cap); they
are not passed explicitly because the pillars derive the ring from radius_km.
"""

from __future__ import annotations

import csv
import os
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

# Repo root on sys.path so `engine` + `ui` import when running directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ee

from engine.orchestrator import ScreeningRun
from ui.components.p04_indicator_registry import (
    ALL_INDICATOR_IDS,
    INDICATORS_BY_PILLAR,
)
from ui.components.traffic_light import band_for_score, band_label


# ---------------------------------------------------------------------------
# Standard single-supplier defaults (match the app)
# ---------------------------------------------------------------------------

SITE_RADIUS_KM: float = 5.0          # P-04 default single-supplier buffer
SCREENING_WINDOW_DAYS: int = 90      # SCREENING_WINDOW_DAYS_DEFAULT
_END = date.today()                  # default end anchor = "today" (picker)
_START = _END - timedelta(days=SCREENING_WINDOW_DAYS)
TIME_RANGE: tuple[str, str] = (_START.isoformat(), _END.isoformat())

# Pedagogy-flag thresholds (local to this report tool — NOT engine constants).
HIGH_SIGNAL_COMPOSITE = 0.50
GHG_DIVERGENCE_DELTA = 0.30          # |combustion - viirs| considered "large"
NATURE_ACTIVE_FOLLOWUP = 0.40
LOW_CONFIDENCE_COMPOSITE = 0.40


# ---------------------------------------------------------------------------
# Candidate supplier facilities (coords per the report brief; these target
# GSCO's critical industries). Coordinates are the brief's approximations —
# good enough for mechanism illustration; small offsets don't change which
# engine grammars a site exercises.
# ---------------------------------------------------------------------------

CANDIDATES: list[dict] = [
    {"name": "Norilsk Nickel — Nadezhda smelter", "country": "Russia",
     "industry": "Ni/Cu/Pd smelting (heavy SO₂)", "lat": 69.33, "lon": 88.16},
    {"name": "Escondida copper mine", "country": "Chile",
     "industry": "Copper mining (arid)", "lat": -24.27, "lon": -69.07},
    {"name": "Grasberg mine", "country": "Indonesia (Papua)",
     "industry": "Cu/Au mining in rainforest", "lat": -4.06, "lon": 137.11},
    {"name": "Comodoro Rivadavia oil & gas", "country": "Argentina",
     "industry": "Oil & gas / flaring", "lat": -45.86, "lon": -67.50},
    {"name": "Jamnagar refinery", "country": "India (Gujarat)",
     "industry": "Refining (combustion + flaring)", "lat": 22.35, "lon": 69.85},
    {"name": "Ganzhou rare-earth processing", "country": "China (Jiangxi)",
     "industry": "Critical minerals (REE)", "lat": 25.85, "lon": 114.93},
    {"name": "CATL battery plant, Ningde", "country": "China (Fujian)",
     "industry": "EV batteries", "lat": 26.66, "lon": 119.55},
    {"name": "Tongwei/LONGi polysilicon, Leshan", "country": "China (Sichuan)",
     "industry": "Solar PV polysilicon", "lat": 29.55, "lon": 103.77},
    {"name": "TSMC Fab 18, Tainan", "country": "Taiwan",
     "industry": "Semiconductors", "lat": 22.97, "lon": 120.27},
    {"name": "Morowali Industrial Park (IMIP)", "country": "Indonesia (Sulawesi)",
     "industry": "Nickel/EV (deforestation frontier)", "lat": -2.82, "lon": 122.15},
    {"name": "Carajás iron ore mine", "country": "Brazil (Pará)",
     "industry": "Iron ore mining in Amazon", "lat": -6.06, "lon": -50.16},
    {"name": "Bayan Obo rare-earth mine", "country": "China (Inner Mongolia)",
     "industry": "Critical minerals (REE, arid)", "lat": 41.77, "lon": 109.97},
]


# ---------------------------------------------------------------------------
# Payload extraction helpers
# ---------------------------------------------------------------------------

def _f(x):
    """Round a float for display, pass through None."""
    return None if x is None else round(float(x), 3)


def _detect_fallback(payload: dict) -> list[str]:
    """Return the indicator-provenance blocks where a temporal/climatology
    fallback fired (robust scan: any provenance value whose nested dict has a
    truthy key containing 'fallback' and 'used'/'applied')."""
    fired: list[str] = []
    for key, block in payload.items():
        if not key.startswith("_provenance.") or not isinstance(block, dict):
            continue
        if _block_has_fallback(block):
            fired.append(key.replace("_provenance.", ""))
    return fired


def _block_has_fallback(obj) -> bool:
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if "fallback" in kl and ("used" in kl or "applied" in kl) and bool(v):
                return True
            if _block_has_fallback(v):
                return True
    return False


def _dropped_indicators(payload: dict) -> list[str]:
    """Of the 19 user-selectable indicators, which returned None (degradation)."""
    return [iid for iid in ALL_INDICATOR_IDS if payload.get(iid) is None]


def _failure_summary(payload: dict) -> list[str]:
    """Flatten payload['_failures'] into 'pillar:reason(detail)' strings."""
    out: list[str] = []
    failures = payload.get("_failures") or {}
    for pillar, items in failures.items():
        for f in items:
            ids = ",".join(f.get("indicator_ids", [])) or f.get("type", "?")
            reason = f.get("reason", "?")
            detail = f.get("reason_detail")
            out.append(f"{pillar}:{ids}={reason}" + (f"({detail})" if detail else ""))
    return out


def _wind_states(payload: dict) -> dict[str, str]:
    """Collect per-pollutant wind attributability states from air provenance."""
    states: dict[str, str] = {}
    for key, block in payload.items():
        if not key.startswith("_provenance.air.") or not isinstance(block, dict):
            continue
        extra = block.get("extra") or {}
        st = extra.get("wind_attributability_state")
        if st is not None:
            states[key.replace("_provenance.air.", "")] = st
    return states


def _extract(site: dict, payload: dict) -> dict:
    """Pull every reported field out of a successful screening payload."""
    composite = payload.get("composite.overall_screening")
    conf = payload.get("composite.confidence")

    air_fu = payload.get("air.audit_followup_priority")
    ghg_fu = payload.get("ghg.audit_followup_priority")
    nat_fu = payload.get("nature.followup_priority")

    ghg_comb = payload.get("ghg.combustion_proxy")
    ghg_viirs = payload.get("ghg.viirs.score")
    ghg_activity = payload.get("ghg.activity_score")

    kba_overlap = payload.get("nature.kba.overlap_ha")
    nat_loss = payload.get("nature.habitat.natural_loss_ha")

    dropped = _dropped_indicators(payload)
    fallbacks = _detect_fallback(payload)
    failures = _failure_summary(payload)
    wind = _wind_states(payload)

    # --- pedagogy flags (computed automatically) ---
    flags: list[str] = []
    if composite is not None and composite > HIGH_SIGNAL_COMPOSITE:
        flags.append("HIGH_SIGNAL")
    if ghg_comb is not None and ghg_viirs is not None and \
            abs(ghg_comb - ghg_viirs) >= GHG_DIVERGENCE_DELTA:
        flags.append("GHG_GRAMMAR_DIVERGENCE")
    if (nat_fu is not None and nat_fu > NATURE_ACTIVE_FOLLOWUP) or \
            (kba_overlap is not None and kba_overlap > 0):
        flags.append("NATURE_ACTIVE")
    if dropped or fallbacks or failures:
        flags.append("DEGRADATION")
    if conf is not None and conf < LOW_CONFIDENCE_COMPOSITE:
        flags.append("LOW_CONFIDENCE")

    return {
        "site": site["name"],
        "country": site["country"],
        "industry": site["industry"],
        "lat": site["lat"],
        "lon": site["lon"],
        "status": "ok",
        "error": "",
        "composite_overall": _f(composite),
        "composite_band": band_label(band_for_score(composite)),
        "composite_confidence": _f(conf),
        "air_followup": _f(air_fu),
        "ghg_followup": _f(ghg_fu),
        "nature_followup": _f(nat_fu),
        "air_confidence": _f(payload.get("air.measurement_quality_score")),
        "ghg_confidence": _f(payload.get("ghg.measurement_quality")),
        "nature_confidence": _f(payload.get("nature.measurement_quality")),
        # GHG grammar split
        "ghg_combustion_proxy": _f(ghg_comb),
        "ghg_viirs_flaring_score": _f(ghg_viirs),
        "ghg_activity_score": _f(ghg_activity),
        "ghg_combustion_minus_viirs": (
            None if ghg_comb is None or ghg_viirs is None
            else round(ghg_comb - ghg_viirs, 3)
        ),
        # Nature specifics
        "nature_kba_proximity": _f(payload.get("nature.kba.proximity_score")),
        "nature_kba_dist_km": _f(payload.get("nature.kba.dist_km")),
        "nature_kba_overlap_ha": _f(kba_overlap),
        "nature_kba_overlap_pct": _f(payload.get("nature.kba.overlap_pct")),
        "nature_habitat_conversion": _f(payload.get("nature.habitat.conversion_score")),
        "nature_habitat_loss_ha": _f(nat_loss),
        # Attributability labels
        "nature_habitat_attrib_state": payload.get("nature.habitat.attributability_state"),
        "nature_spatial_offset_km": _f(
            payload.get("nature.supplier_spatial_link.centroid_offset_km")),
        "ghg_viirs_attrib_state": payload.get("ghg.viirs.attributability_state"),
        "ghg_viirs_lit_contrast_pct": _f(payload.get("ghg.viirs.lit_contrast_percentile")),
        "wind_attrib_states": ";".join(f"{k}={v}" for k, v in wind.items()),
        # Degradation detail
        "dropped_indicators": ";".join(dropped),
        "fallbacks_fired": ";".join(fallbacks),
        "failures": " | ".join(failures),
        "pedagogy_flags": ";".join(flags),
        "_flag_count": len(flags),
    }


def _prov_extra(payload: dict, indicator_base: str) -> dict:
    """Return the `extra` dict of an indicator's provenance block ({} if absent)."""
    prov = payload.get(f"_provenance.{indicator_base}")
    if not isinstance(prov, dict):
        return {}
    ex = prov.get("extra")
    return ex if isinstance(ex, dict) else {}


def _perindicator_rows(site: dict, payload: dict) -> list[dict]:
    """Long-format per-(site, indicator) detail for the report's deeper tables.

    Captures, per indicator: raw value, bg_median, bg_std (the standardising σ
    that reconciles z, plus the spatial/temporal components), z, score,
    confidence, and the four confidence sub-terms (QA / N_valid /
    anomaly_strength / spatial_context) read from
    `_provenance.<id>.extra.confidence_terms`. GHG CO₂ (ODIAC) and VIIRS use
    their own key sets and have no z/bg — those cells stay None and the
    GHG-specific extras land in `extra_note`.
    """
    rows: list[dict] = []

    def _bg_std_used(anomaly, z):
        if anomaly is None or z in (None, 0):
            return None
        return abs(anomaly / z)

    # --- Air pollutants (full repeatable-core trace) ---
    for p in ("no2", "so2", "co", "hcho", "pm25", "pm10", "o3", "aai", "aod"):
        base = f"air.{p}"
        ex = _prov_extra(payload, base)
        ct = ex.get("confidence_terms") or {}
        anomaly = payload.get(f"{base}.anomaly")
        z = payload.get(f"{base}.z")
        rows.append({
            "site": site["name"], "pillar": "air", "indicator": base,
            "raw_value": payload.get(f"{base}.site"),
            "bg_median": payload.get(f"{base}.background"),
            "anomaly": anomaly,
            "bg_std": _bg_std_used(anomaly, z),
            "bg_std_spatial": ex.get("bg_std_spatial"),
            "bg_std_temporal": ex.get("bg_std_temporal"),
            "z": z,
            "score": payload.get(f"{base}.score"),
            "confidence": payload.get(f"{base}.confidence"),
            "qa": ct.get("qa"),
            "n_valid": ct.get("n_valid"),
            "anomaly_strength": ct.get("anomaly_strength"),
            "spatial_context": ct.get("spatial_context"),
            "extra_note": "",
        })

    # --- GHG CH₄ (full trace, same grammar as Air) ---
    ex = _prov_extra(payload, "ghg.ch4")
    ct = ex.get("confidence_terms") or {}
    anomaly = payload.get("ghg.ch4.anomaly")
    z = payload.get("ghg.ch4.z")
    rows.append({
        "site": site["name"], "pillar": "ghg", "indicator": "ghg.ch4",
        "raw_value": payload.get("ghg.ch4.site"),
        "bg_median": payload.get("ghg.ch4.background"),
        "anomaly": anomaly, "bg_std": _bg_std_used(anomaly, z),
        "bg_std_spatial": ex.get("bg_std_spatial"),
        "bg_std_temporal": ex.get("bg_std_temporal"),
        "z": z, "score": payload.get("ghg.ch4.score"),
        "confidence": payload.get("ghg.ch4.confidence"),
        "qa": ct.get("qa"), "n_valid": ct.get("n_valid"),
        "anomaly_strength": ct.get("anomaly_strength"),
        "spatial_context": ct.get("spatial_context"),
        "extra_note": "context — not scored (M-CH4-A1 reference)",
    })

    # --- GHG CO₂ (ODIAC inventory: mean / relative_intensity / total) ---
    ex = _prov_extra(payload, "ghg.co2")
    ct = ex.get("confidence_terms") or {}
    ri = payload.get("ghg.co2.relative_intensity")
    tot = payload.get("ghg.co2.total")
    rows.append({
        "site": site["name"], "pillar": "ghg", "indicator": "ghg.co2",
        "raw_value": payload.get("ghg.co2.mean"),
        "bg_median": None, "anomaly": None, "bg_std": None,
        "bg_std_spatial": None, "bg_std_temporal": None, "z": None,
        "score": payload.get("ghg.co2.score"),
        "confidence": payload.get("ghg.co2.confidence"),
        "qa": ct.get("qa"), "n_valid": ct.get("n_valid"),
        "anomaly_strength": ct.get("anomaly_strength"),
        "spatial_context": ct.get("spatial_context"),
        "extra_note": (
            f"context — not scored; rel_intensity={ri} (cap 10), "
            f"total_tCO2yr={tot}"
        ),
    })

    # --- GHG VIIRS (brightness severity + attributability) ---
    ex = _prov_extra(payload, "ghg.viirs")
    ct = ex.get("confidence_terms") or {}
    rows.append({
        "site": site["name"], "pillar": "ghg", "indicator": "ghg.viirs",
        "raw_value": payload.get("ghg.viirs.site"),
        "bg_median": None, "anomaly": None, "bg_std": None,
        "bg_std_spatial": None, "bg_std_temporal": None, "z": None,
        "score": payload.get("ghg.viirs.score"),
        "confidence": payload.get("ghg.viirs.confidence"),
        "qa": ct.get("qa"), "n_valid": ct.get("n_valid"),
        "anomaly_strength": ct.get("anomaly_strength"),
        "spatial_context": ct.get("spatial_context"),
        "extra_note": (
            f"flaring_frac={payload.get('ghg.viirs.flaring_frac')}, "
            f"lit_contrast_pct={payload.get('ghg.viirs.lit_contrast_percentile')}, "
            f"state={payload.get('ghg.viirs.attributability_state')}"
        ),
    })

    return rows


_PERINDICATOR_COLUMNS = [
    "site", "pillar", "indicator", "raw_value", "bg_median", "anomaly",
    "bg_std", "bg_std_spatial", "bg_std_temporal", "z", "score", "confidence",
    "qa", "n_valid", "anomaly_strength", "spatial_context", "extra_note",
]


def _failed_row(site: dict, err: str) -> dict:
    return {
        "site": site["name"], "country": site["country"],
        "industry": site["industry"], "lat": site["lat"], "lon": site["lon"],
        "status": "FAILED", "error": err,
        "composite_overall": None, "composite_band": "—",
        "composite_confidence": None,
        "air_followup": None, "ghg_followup": None, "nature_followup": None,
        "air_confidence": None, "ghg_confidence": None, "nature_confidence": None,
        "ghg_combustion_proxy": None, "ghg_viirs_flaring_score": None,
        "ghg_activity_score": None, "ghg_combustion_minus_viirs": None,
        "nature_kba_proximity": None, "nature_kba_dist_km": None,
        "nature_kba_overlap_ha": None, "nature_kba_overlap_pct": None,
        "nature_habitat_conversion": None, "nature_habitat_loss_ha": None,
        "nature_habitat_attrib_state": None, "nature_spatial_offset_km": None,
        "ghg_viirs_attrib_state": None, "ghg_viirs_lit_contrast_pct": None,
        "wind_attrib_states": "", "dropped_indicators": "",
        "fallbacks_fired": "", "failures": err,
        "pedagogy_flags": "SITE_FAILED", "_flag_count": -1,
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

_CSV_COLUMNS = [
    "rank", "site", "country", "industry", "lat", "lon", "status",
    "composite_overall", "composite_band", "composite_confidence",
    "air_followup", "ghg_followup", "nature_followup",
    "air_confidence", "ghg_confidence", "nature_confidence",
    "ghg_combustion_proxy", "ghg_viirs_flaring_score", "ghg_activity_score",
    "ghg_combustion_minus_viirs",
    "nature_kba_proximity", "nature_kba_dist_km", "nature_kba_overlap_ha",
    "nature_kba_overlap_pct", "nature_habitat_conversion", "nature_habitat_loss_ha",
    "nature_habitat_attrib_state", "nature_spatial_offset_km",
    "ghg_viirs_attrib_state", "ghg_viirs_lit_contrast_pct", "wind_attrib_states",
    "dropped_indicators", "fallbacks_fired", "failures",
    "pedagogy_flags", "error",
]


def _richness_key(row: dict):
    """Sort key: most mechanism-rich first.

    Primary = number of pedagogy flags (multi-mechanism sites surface first);
    secondary = composite score (so a high-signal site outranks a quiet one at
    the same flag count). Failed sites sink to the bottom (_flag_count = -1).
    """
    comp = row.get("composite_overall")
    return (row["_flag_count"], comp if comp is not None else -1.0)


def _print_markdown(rows: list[dict]) -> None:
    cols = [
        ("site", "Site"), ("composite_overall", "Comp"), ("composite_band", "Band"),
        ("composite_confidence", "Conf"),
        ("air_followup", "Air"), ("ghg_followup", "GHG"), ("nature_followup", "Nat"),
        ("ghg_combustion_proxy", "Comb"), ("ghg_viirs_flaring_score", "VIIRS"),
        ("nature_kba_overlap_ha", "KBA_ov"), ("nature_habitat_conversion", "HabConv"),
        ("pedagogy_flags", "Pedagogy flags"),
    ]
    header = "| # | " + " | ".join(h for _, h in cols) + " |"
    sep = "|---|" + "|".join("---" for _ in cols) + "|"
    print(header)
    print(sep)
    for i, r in enumerate(rows, 1):
        cells = []
        for key, _ in cols:
            v = r.get(key)
            cells.append("" if v is None else str(v))
        print(f"| {i} | " + " | ".join(cells) + " |")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _init_ee() -> None:
    project = os.environ.get("EE_PROJECT_ID") or "supply-chain-observatory"
    ee.Initialize(project=project)
    print(f"[sweep] Earth Engine initialised (project={project})")


def main() -> None:
    _init_ee()
    indicators = set(ALL_INDICATOR_IDS)
    print(f"[sweep] window={TIME_RANGE}  radius={SITE_RADIUS_KM} km  "
          f"indicators={len(indicators)} (all 3 pillars)")
    print(f"[sweep] pillars selected: "
          + ", ".join(f"{p}={len(v)}" for p, v in INDICATORS_BY_PILLAR.items()))

    rows: list[dict] = []
    perindicator: list[dict] = []
    for i, site in enumerate(CANDIDATES, 1):
        print(f"\n[sweep] ({i}/{len(CANDIDATES)}) {site['name']} "
              f"({site['lat']}, {site['lon']})…")
        aoi = {"centre": {"lat": site["lat"], "lon": site["lon"]},
               "radius_km": SITE_RADIUS_KM}
        try:
            payload = ScreeningRun(
                aoi=aoi,
                selected_indicators=indicators,
                time_range=TIME_RANGE,
                ee_client=None,
                centre_metadata={
                    "node_name": site["name"],
                    "country": site["country"],
                    "source": "report Section 7 example sweep",
                },
            ).run()
            row = _extract(site, payload)
            perindicator.extend(_perindicator_rows(site, payload))
            print(f"[sweep]   composite={row['composite_overall']} "
                  f"({row['composite_band']})  conf={row['composite_confidence']}  "
                  f"flags={row['pedagogy_flags']}")
        except Exception as exc:  # record, never drop silently
            err = f"{type(exc).__name__}: {exc}"
            print(f"[sweep]   FAILED — {err}")
            traceback.print_exc()
            row = _failed_row(site, err)
        rows.append(row)

    # Per-indicator long-format CSV (deeper dump for report tables 7.1/7.3/7.5).
    out_long = Path(__file__).resolve().parent / "report_example_perindicator.csv"
    with out_long.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_PERINDICATOR_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(perindicator)
    print(f"\n[sweep] wrote {out_long} ({len(perindicator)} rows)")

    # Sort most mechanism-rich first.
    rows.sort(key=_richness_key, reverse=True)

    # Write CSV.
    out_csv = Path(__file__).resolve().parent / "report_example_sweep.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows, 1):
            w.writerow({"rank": i, **r})
    print(f"\n[sweep] wrote {out_csv}")

    print("\n=== COMPARISON TABLE (most mechanism-rich first) ===\n")
    _print_markdown(rows)

    print(f"\n[sweep] window used: {TIME_RANGE[0]} → {TIME_RANGE[1]} "
          f"(standard latest-valid 90-day, end anchored to today)")


if __name__ == "__main__":
    main()
