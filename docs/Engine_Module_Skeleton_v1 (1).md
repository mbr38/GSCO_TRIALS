# GSCO Environmental Tool — Engine Module Skeleton (v1)

**Purpose.** Reference for the Python indicator-engine layout. Tells a developer where every `compute_*` function lives, what its signature is, and how the orchestrator turns a screening request into a result payload that the UI can render.

**Architecture.** Option D from the round-3 review: **stateless pillar modules + a thin orchestrator class**. The pillar modules are flat function libraries (one Python function per pillar function in `PLFS_v4.md` Appendix B); the orchestrator class handles cross-pillar concerns (composite score, partial-failure marking, provenance assembly) and is the only stateful class in the engine.

**Authority.** Function inputs / outputs use the canonical IDs from `Indicator_ID_Schema_v1.md`. Formulas and weights come from `Indicators_Computation_v3.md`. UI integration points come from `PLFS_v4.md` and `Wireframes_All_v4.md`.

**Date.** 13 May 2026.

---

## 1. Directory layout

```
gsco_tool/
├── engine/
│   ├── __init__.py
│   ├── orchestrator.py          ← ScreeningRun / TrendRun / PrioritisationBatch
│   ├── air.py                    ← Air Pollution pillar functions
│   ├── ghg.py                    ← GHG pillar functions
│   ├── nature.py                 ← Nature/Land pillar functions
│   ├── core/
│   │   ├── __init__.py
│   │   ├── repeatable_core.py    ← the six-step pollutant core method (§0.2 of IC_v3)
│   │   ├── buffers.py            ← Site_Buffer / Background_Ring construction
│   │   ├── normalisation.py      ← raw → 0-1 score (§0.4)
│   │   ├── trend.py              ← Theil-Sen + Mann-Kendall
│   │   └── seasonality.py        ← same-month baseline filter (§0.6)
│   ├── constants.py              ← all numeric defaults (ANOMALY_Z_THRESHOLD, k, etc.)
│   ├── ids.py                    ← canonical IDs from Indicator_ID_Schema_v1, as constants
│   ├── verbal_summary.py         ← deterministic prose generator (Verbal_Summary_Templates_v1)
│   └── exceptions.py             ← IndicatorComputeError and friends
├── data_sources/
│   ├── __init__.py
│   ├── ee_client.py              ← thin GEE wrapper (auth, ImageCollection access)
│   ├── odiac.py                  ← uploaded-asset reader for ODIAC
│   └── gaul.py                   ← FAO GAUL country lookup for P-04 region mode
└── tests/
    ├── test_repeatable_core.py
    ├── test_air.py
    ├── test_ghg.py
    ├── test_nature.py
    ├── test_orchestrator.py
    └── fixtures/
        └── synthetic_payloads.py ← deterministic test inputs
```

Three principles guiding the layout:

1. **Pillar files mirror `Indicators_Computation_v3.md`'s pillar sections.** A developer reading `air.py` should see Python functions in the same order as the §1 of the indicators doc.
2. **The `core/` subpackage holds anything used by 2+ pillars.** Repeatable core method, buffers, normalisation, trend, seasonality — all live there, all stateless.
3. **Constants are external, not hard-coded.** `ANOMALY_Z_THRESHOLD`, `CAMS_MIN_VALID_PCT`, `HABITAT_BASELINE_YEARS`, `DOMINANT_CONTRIBUTOR_SHARE_THRESHOLD`, etc. all sit in `engine/constants.py` so they can be tuned without touching computation logic.

---

## 2. Pillar module signatures

Each pillar module exposes one public function per indicator (single-value, sub-aggregate, or pillar aggregate). Functions return a `dict` keyed by canonical indicator IDs from `Indicator_ID_Schema_v1.md`. **No function returns a class; everything is plain `dict` / `float` for serialisability.**

### 2.1 `engine/air.py`

```python
from .core import repeatable_core, buffers, normalisation
from .constants import (
    AIR_POLLUTANT_WEIGHTS, AIR_FOLLOWUP_WEIGHTS,
    ANOMALY_Z_THRESHOLD, NORMALISATION_K,
)

# ─── Single-value indicators (§1.1 IC_v3) ─────────────────────────────────

def compute_pollutant_snapshot(
    aoi: dict,
    pollutant: str,                  # "no2" | "so2" | "co" | "hcho" | "o3" | "aai" | "ch4"
    time_range: tuple[str, str],
    mode: str,                       # "screening" | "trend"
    ee_client,
) -> dict:
    """Implements the six-step repeatable core method.

    Returns a dict keyed by canonical IDs:
        {pillar}.{pollutant}.site / .background / .anomaly / .z / .hf
        / .trend / .trend_p / .confidence / .score
    where pillar = "air" for s5p gases and CAMS, "ghg" for ch4.

    Severity semantics (M-ATTRIB-A2): the resulting `.score` is a
    site-vs-background-ring *anomaly*, so it measures supplier-attributable
    contribution against regional context, not absolute pollution. See
    Indicators_Computation_v4.md §0.7 for the user-facing framing.
    """

def compute_pm25_proxy(aoi, time_range, mode, ee_client) -> dict: ...
def compute_pm10_proxy(aoi, time_range, mode, ee_client) -> dict: ...
def compute_aod_optional(aoi, time_range, mode, ee_client) -> dict: ...

# ─── Sub-aggregates (§1.2 IC_v3) ──────────────────────────────────────────
# Only the formula-internal ones are exposed in v1.
# Heavy_Industry_Score, VOC_Photochemical, Industrial_Air_Pollution_Burden,
# Fossil_Combustion_Score and Activity_Adjusted_CO2 are deferred to v1.x.

def compute_pm_or_aerosol(payload: dict) -> dict:
    """0.60·pm25.score + 0.40·aai.score, with the CAMS fallback (E4)."""

def compute_industrial_combustion_proxy(payload: dict) -> dict:
    """0.60·no2.score + 0.40·co.score. Used by both Air and GHG pillars."""

# ─── Pillar aggregates (§1.3 IC_v3) ───────────────────────────────────────

def compute_air_pollution_proxy_score(payload: dict, selected: set[str]) -> dict:
    """Weighted sum across single-value scores; missing ones skipped and
    weights renormalised over the present terms."""

def compute_air_audit_followup_priority(
    payload: dict,
    mode: str,                       # "screening" → trend_score = 0
    selected: set[str],
) -> dict:
    """The pillar Follow-Up Priority Score (the headline number on P-05)."""

# ─── Pillar entry point — called by the orchestrator ──────────────────────

def run_pillar(
    aoi, time_range, mode, selected_indicators, ee_client,
) -> dict:
    """Compute every selected Air indicator + aggregates. Single dict return.
    The orchestrator calls this once per pillar per run."""
```

`ghg.py` and `nature.py` follow the same shape. Their `run_pillar` is the orchestrator's only entry point into each module — all other functions are reusable but optional.

### 2.2 `engine/ghg.py` — key signatures

```python
def compute_ch4_snapshot(aoi, time_range, mode, ee_client) -> dict: ...
def compute_co2_context(aoi, time_range, mode, ee_client) -> dict:
    """Reads ODIAC via data_sources.odiac. Returns ghg.co2.{mean, total,
    anomaly, trend, confidence, score}, plus a vintage-lag flag."""
def compute_activity_score(aoi, time_range, mode, ee_client) -> dict:
    """VIIRS Black Marble."""

def compute_fire_or_regional_transport_risk(payload: dict) -> dict:
    """Same value as air.smoke_dust_regional_transport (§7.3 IC_v3).
    Used internally by compute_ch4_context_adjusted."""

def compute_ch4_context_adjusted(payload: dict) -> dict:
    """ch4.score − 0.20 · fire_or_regional_transport_risk."""

def compute_combustion_proxy(payload: dict) -> dict:
    """Borrowed from air.compute_industrial_combustion_proxy. Same value,
    surfaced under the ghg.* namespace for clarity."""

def compute_core_ghg_audit_support(payload: dict) -> dict:
    """Post-M5.5b 3-key form: 0.46·ch4_adj + 0.44·combustion + 0.10·activity.

    ODIAC's CO₂_Context demoted to standing exposure (not in live composite);
    pre-M5.5b 4-key weights (0.39·co2 + 0.28·ch4_adj + 0.22·combustion +
    0.11·activity) preserved for lineage. See IC_v4 §2.3 and audit §3.4."""

def compute_ghg_data_quality_attribution(payload: dict) -> dict:
    """v1-rescaled form per §2.3 IC_v3."""

def compute_ghg_audit_followup_priority(payload, mode, selected) -> dict: ...

def run_pillar(aoi, time_range, mode, selected, ee_client) -> dict: ...
```

### 2.3 `engine/nature.py` — key signatures

```python
def compute_kba_proximity(aoi, ee_client) -> dict:
    """Returns nature.kba.{dist_km, overlap_ha, overlap_pct, proximity_score}."""

def compute_current_land_cover(aoi, time_range, ee_client) -> dict:
    """Dynamic World mode composite. Returns the nine class percentages,
    areas, dominant class, class confidence."""

def compute_habitat_conversion(
    aoi, current_date, ee_client,
    baseline_years: int = None,      # defaults to HABITAT_BASELINE_YEARS = 5
) -> dict:
    """Compares current 90-day DW composite vs baseline composite 5 years earlier.
    Returns nature.habitat.{natural_loss_ha, nat_to_built_ha, nat_to_bare_ha,
    nat_to_crop_ha, built_expansion_ha, bare_expansion_ha, annualised_rate,
    conversion_score}."""

def compute_ndvi_condition(aoi, time_range, mode, ee_client) -> dict: ...
def compute_forest_loss(aoi, baseline_year, ee_client) -> dict: ...
def compute_water_exposure(aoi, ee_client) -> dict: ...
def compute_restoration_signal(aoi, time_range, ee_client) -> dict: ...

def compute_biodiversity_exposure(payload) -> dict: ...
def compute_vegetation_condition(payload) -> dict: ...

def compute_supplier_spatial_link(aoi, change_mask, supplier_point) -> dict: ...
def compute_external_driver_screening(aoi, payload, ee_client) -> dict: ...

def compute_nature_quality_attribution(payload) -> dict: ...
def compute_nature_followup_priority(payload, selected) -> dict: ...

def run_pillar(aoi, time_range, mode, selected, ee_client) -> dict: ...
```

---

## 3. The orchestrator

`engine/orchestrator.py` defines three classes: `ScreeningRun` (P-05), `TrendRun` (P-06), `PrioritisationBatch` (P-08). The first two share most of their implementation through a common base; the third loops over the first.

### 3.1 `ScreeningRun`

```python
from . import air, ghg, nature
from .verbal_summary import generate_verbal_summary
from .exceptions import IndicatorComputeError, PillarComputeError

PILLAR_MODULES = {"air": air, "ghg": ghg, "nature": nature}

class ScreeningRun:
    """One Inspect-Screening computation for a single AOI.
    Called by P-05's compute step; also reused by P-08's batch loop."""

    def __init__(
        self,
        aoi: dict,                   # {"centre": {"lat", "lon"}, "radius_km": 5, ...}
        selected_indicators: set[str],   # canonical IDs from Indicator_ID_Schema_v1
        time_range: tuple[str, str],
        mode: str,                   # "screening" — TrendRun subclass passes "trend"
        ee_client,
        centre_metadata: dict,
    ):
        self.aoi = aoi
        self.selected = selected_indicators
        self.time_range = time_range
        self.mode = mode
        self.ee = ee_client
        self.centre_metadata = centre_metadata
        self.payload: dict = {}
        self.failures: list[dict] = []

    def run(self) -> dict:
        for pillar_name, pillar_module in PILLAR_MODULES.items():
            try:
                self.payload.update(
                    pillar_module.run_pillar(
                        self.aoi, self.time_range, self.mode,
                        self._pillar_selection(pillar_name), self.ee,
                    )
                )
            except PillarComputeError as err:
                self._mark_pillar_failure(pillar_name, err)

        self._compute_composite()
        self._compute_composite_confidence()
        self._add_provenance()
        self._add_verbal_summary()
        return self.full_result()

    # ── helpers ──────────────────────────────────────────────────────────

    def _pillar_selection(self, pillar_name: str) -> set[str]:
        """Subset of self.selected that belongs to this pillar."""
        return {i for i in self.selected if i.startswith(f"{pillar_name}.")}

    def _compute_composite(self) -> None:
        # Equal ⅓ weighting per §4 IC_v3.
        pillar_scores = []
        for p in ("air", "ghg", "nature"):
            key = f"{p}.{'audit_followup_priority' if p != 'nature' else 'followup_priority'}"
            if key in self.payload:
                pillar_scores.append(self.payload[key])
        if pillar_scores:
            self.payload["composite.overall_screening"] = sum(pillar_scores) / len(pillar_scores)

    def _compute_composite_confidence(self) -> None:
        # Minimum across the three pillar confidences (§4 IC_v3).
        confs = [
            self.payload.get("air.attribution_confidence_score"),
            self.payload.get("ghg.data_quality_attribution"),
            self.payload.get("nature.quality_attribution"),
        ]
        confs = [c for c in confs if c is not None]
        if confs:
            self.payload["composite.confidence"] = min(confs)

    def _add_provenance(self) -> None:
        # Asset IDs and the actual data dates used per indicator.
        # Pillar modules attach provenance to the payload under
        # `_provenance.<indicator_id>` keys during their compute.
        self.payload["provenance"] = self._collect_provenance()

    def _add_verbal_summary(self) -> None:
        self.payload["verbal_summary"] = generate_verbal_summary(self.payload)

    def _mark_pillar_failure(self, pillar_name: str, err: PillarComputeError) -> None:
        self.failures.append({
            "pillar": pillar_name,
            "indicator_ids_affected": err.indicator_ids,
            "reason": str(err),
        })
        # Mark every affected ID as not-computed in the payload so
        # downstream consumers (UI, reports) render placeholders.
        for ind_id in err.indicator_ids:
            self.payload[ind_id] = None

    def full_result(self) -> dict:
        return {
            **self.payload,
            "_meta": {
                "aoi": self.aoi,
                "centre_metadata": self.centre_metadata,
                "time_range": self.time_range,
                "mode": self.mode,
                "computed_at": _utc_now(),
                "failures": self.failures,
                "selected_indicators": sorted(self.selected),
            },
        }
```

### 3.2 `TrendRun`

```python
class TrendRun(ScreeningRun):
    """Same engine, with mode="trend" — activates Trend term in pillar aggregates
    and emits the per-time-bin payloads for the chart panel."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, mode="trend", **kwargs)

    def run(self) -> dict:
        result = super().run()
        result["time_bins"] = self._build_time_bins()
        return result
```

Trend mode flips the `Trend_Score` (Air) and `GHG_Trend` terms from 0 to their computed values. Nature's formula doesn't have a separate trend term (per `PLFS_v4.md` §10 — H13).

### 3.3 `PrioritisationBatch`

```python
class PrioritisationBatch:
    """P-08: run a ScreeningRun (or TrendRun) for each node in the batch.
    Hard-capped at 30 nodes for the demo per Wireframes §P-07."""

    def __init__(self, nodes, radius_km, time_range, selected, mode, ee_client):
        if len(nodes) > 30:
            raise ValueError("Demo cap: max 30 nodes per prioritisation run")
        self.nodes = nodes
        self.radius_km = radius_km
        self.time_range = time_range
        self.selected = selected
        self.mode = mode
        self.ee = ee_client

    def run(self) -> dict:
        per_node = []
        for node in self.nodes:
            aoi = _build_aoi(node, self.radius_km)
            run_cls = TrendRun if self.mode == "trend" else ScreeningRun
            try:
                result = run_cls(
                    aoi=aoi, selected_indicators=self.selected,
                    time_range=self.time_range, ee_client=self.ee,
                    centre_metadata={"node_id": node.id, "node_name": node.name},
                ).run()
                per_node.append({"node_id": node.id, "result": result, "status": "ok"})
            except Exception as err:
                per_node.append({"node_id": node.id, "status": "failed", "reason": str(err)})

        return {
            "per_node": per_node,
            "ranking": self._rank(per_node),
            "_meta": {...},
        }
```

---

## 4. The core subpackage

`engine/core/` holds the reusable building blocks. Stateless functions only.

### 4.1 `core/repeatable_core.py`

```python
def site_value(aoi, image_collection) -> float:
    """Step 1 of §0.2: mean over Site_Buffer."""

def background_value(aoi, image_collection, seasonal: bool = True) -> tuple[float, float]:
    """Step 2 of §0.2: (median, std) over Background_Ring.
    seasonal=True applies the same-month filter (§0.6)."""

def anomaly_z_hf(site, bg_median, bg_std, time_series, z_threshold) -> dict:
    """Steps 3-5: returns {anomaly, z, hf}."""

def six_step(aoi, ic_band, time_range, ee_client, ...) -> dict:
    """All six steps in one call. Returns the standard
    {site, background, anomaly, z, hf, trend, confidence, score} dict."""
```

### 4.2 `core/buffers.py`

```python
def site_buffer(centre: dict, radius_km: float, projection: str = "geodetic") -> dict:
    """Builds the inner circular geometry. geodetic per §H14."""

def background_ring(
    centre, r_site_km, r_background_km=None,
    apply_land_mask: bool = True,
) -> dict:
    """If r_background_km is None, set to min(5·r_site_km, 200) per §6.2 IC_v4.

    M-TIER-A3 — returns a dict (was: bare ee.Geometry) with five keys:
      - geometry: ee.Geometry of the annulus (unchanged from pre-milestone)
      - mask: ee.Image binary land mask (land=1) when apply_land_mask=True, else None
      - land_fraction: float in [0.0, 1.0], geometric land share of the
        annulus per MOD44W (always computed; ~500 ms getInfo per call)
      - land_mask_applied: mirrors apply_land_mask for provenance
      - land_mask_asset: MOD44W asset ID, always populated for vintage tracking

    Below `engine.constants.LAND_MASK_FRACTION_MIN_THRESHOLD` (0.05) the
    downstream reducer raises BackgroundRingNoDataError with the distinct
    reason marker `ring_empty_post_land_mask`. Spec lock LM3 makes
    apply_land_mask=True the production default.
    """

def pixel_size_warning(selected_indicators, r_site_km) -> dict | None:
    """Returns the H10 warning payload listing affected indicators,
    or None if no warning is needed."""
```

### 4.3 `core/normalisation.py`

```python
def to_score(value, bg_median, bg_std, direction="higher_is_worse",
             k: float = 3.0) -> float:
    """The §0.4 normalisation. k=3 default; tunable."""
```

### 4.4 `core/trend.py`

```python
def theil_sen_slope(time_series: list[tuple[date, float]]) -> tuple[float, float]:
    """Returns (slope, mann_kendall_p)."""
```

### 4.5 `core/seasonality.py`

```python
def same_month_filter(image_collection, target_months: list[int],
                      years: int = 3) -> "ImageCollection":
    """§0.6 same-month seasonality baseline."""
```

---

## 5. Constants

`engine/constants.py` is a single flat file. Everything tunable lives here:

```python
# Tertile thresholds (Wireframes Appendix C.1 / Verbal_Summary §1)
TRAFFIC_LIGHT_THRESHOLDS = (0.33, 0.66)

# Repeatable core method
ANOMALY_Z_THRESHOLD = 2.0                # §0.2 step 5
NORMALISATION_K = 3.0                    # §0.4

# Habitat conversion
HABITAT_BASELINE_YEARS = 5               # §3.1

# Conversion-score saturation
CONVERSION_SATURATION_PCT = 0.10         # §3.2

# Dynamic World class buckets
DW_NATURAL_CLASSES = ("trees", "grass", "shrub_and_scrub", "flooded_vegetation")
DW_NON_NATURAL_CLASSES = ("crops", "built", "bare")
DW_EXCLUDED_CLASSES = ("snow_and_ice",)
DW_WATER_CLASS = "water"

# Air sub-aggregate fallback
CAMS_MIN_VALID_PCT = 0.5                 # §1.2 E4 trigger

# Verbal summary
DOMINANT_CONTRIBUTOR_SHARE_THRESHOLD = 0.40   # §3 Verbal_Summary

# Buffer caps
BACKGROUND_RING_MAX_KM = 200             # §6.2 IC_v4

# M-TIER-A3 — land-mask floor for Background_Ring (LM7). Below 5% land
# fraction the reducer routes through BackgroundRingNoDataError with
# reason `ring_empty_post_land_mask`. Asset ID lives next to the
# constructor in engine/core/buffers.py (LAND_MASK_ASSET = "MODIS/006/MOD44W").
LAND_MASK_FRACTION_MIN_THRESHOLD = 0.05

# Pillar weights — v1 rescaled forms
AIR_POLLUTION_PROXY_WEIGHTS = {
    "air.no2.score": 0.30,
    "air.so2.score": 0.20,
    "air.co.score": 0.15,
    "air.hcho.score": 0.15,
    "air.pm_or_aerosol": 0.10,
    "air.o3.score": 0.10,
}

AIR_FOLLOWUP_WEIGHTS = {
    "proxy": 0.35,
    "anomaly": 0.30,
    "trend": 0.20,
    "confidence": 0.15,
}

# Post-M5.5b 3-key form (engine-actual). ODIAC's CO₂_Context demoted from
# the live composite per audit §3.4; remaining three signals rescaled by
# 1/0.61. See IC_v4 §2.3 for the full rationale and the pre-M5.5b 4-key
# form (0.39 / 0.28 / 0.22 / 0.11) kept for lineage only.
CORE_GHG_AUDIT_SUPPORT_WEIGHTS = {
    "ghg.ch4_context_adjusted": 0.46,
    "ghg.combustion_proxy":     0.44,
    "ghg.activity_score":       0.10,
}

# ...and so on for the remaining pillar formulas
```

---

## 6. Error handling

```python
# engine/exceptions.py
class IndicatorComputeError(Exception):
    """Raised for a single-indicator failure (e.g. no valid pixels in buffer)."""
    def __init__(self, indicator_id: str, reason: str):
        self.indicator_id = indicator_id
        self.reason = reason

class PillarComputeError(Exception):
    """Raised when a whole pillar fails (e.g. EE service unavailable for a session).
    Carries the list of indicator IDs that won't be in the payload."""
    def __init__(self, pillar: str, indicator_ids: list[str], reason: str):
        self.pillar = pillar
        self.indicator_ids = indicator_ids
        self.reason = reason
```

Pillar modules raise `IndicatorComputeError` for single-indicator problems and catch them internally where graceful degradation is possible (e.g. CAMS fallback in §1.2). They raise `PillarComputeError` only for non-recoverable pillar-wide failures. The orchestrator catches `PillarComputeError` to populate the partial-result UI on P-05's S2_Partial state.

---

## 7. Mapping to PLFS Appendix B

For traceability, every function in `PLFS_v4.md` Appendix B's "indicator engine module map" has a concrete home here:

| PLFS Appendix B function | Engine location |
|---|---|
| `compute_pollutant_snapshot` | `engine/air.py` (Sentinel-5P gases), `engine/ghg.py` (CH₄ also imports it) |
| `compute_pm25_proxy` | `engine/air.py` |
| `compute_air_pollution_proxy_score` | `engine/air.py` |
| `compute_air_audit_followup_priority` | `engine/air.py` |
| `compute_ch4_context_adjusted` | `engine/ghg.py` |
| `compute_co2_context` | `engine/ghg.py` |
| `compute_combustion_proxy` | `engine/ghg.py` (aliased from `air.py`) |
| `compute_activity_score` | `engine/ghg.py` |
| `compute_core_ghg_audit_support` | `engine/ghg.py` |
| `compute_ghg_data_quality_attribution` | `engine/ghg.py` |
| `compute_ghg_audit_followup_priority` | `engine/ghg.py` |
| `compute_current_land_cover` | `engine/nature.py` |
| `compute_biodiversity_exposure` | `engine/nature.py` |
| `compute_ndvi_condition` | `engine/nature.py` |
| `compute_habitat_conversion` | `engine/nature.py` |
| `compute_bare_ground_expansion`, `compute_built_up_expansion`, `compute_water_exposure`, `compute_restoration_signal` | `engine/nature.py` |
| `compute_supplier_spatial_link` | `engine/nature.py` |
| `compute_external_driver_screening` | `engine/nature.py` |
| `compute_nature_quality_attribution` | `engine/nature.py` |
| `compute_nature_followup_priority` | `engine/nature.py` |
| `compute_overall_screening_score` | `engine/orchestrator.py::ScreeningRun._compute_composite` |

---

## 8. Testing surface

Unit tests live under `tests/` with one file per module. Recommended test categories:

1. **Synthetic-payload tests** — build a fake `payload` dict, call a pure function (e.g. `compute_air_pollution_proxy_score`), assert exact output. No GEE required. Catches formula errors fast.
2. **Repeatable-core-method tests** — feed `six_step` a synthetic image collection with known statistics, assert the right `site`, `background`, `z`, `hf`. Catches integration errors against the GEE wrapper.
3. **Orchestrator partial-failure tests** — mock a pillar module to raise `PillarComputeError`, assert that the payload carries the right `None`-marked IDs and that the failures list is populated.
4. **End-to-end golden tests** — one or two real AOIs (a clean rural point, a known industrial point), run the full `ScreeningRun`, assert composite score in expected band. Lower frequency, slower, runs against live GEE.

Synthetic-payload tests should run on every commit; end-to-end golden tests on a nightly schedule.

---

## 9. v1.x extension hooks

Reserved namespaces in `engine/` for v1.x extensions:

- `engine/lenses/` — the interpretive sub-aggregates (`Heavy_Industry_Score`, `VOC_Photochemical`, etc.) as a separate "lens" subpackage. Adds nothing to v1; lights up once requested.
- `engine/sector.py` — sector-aware weighting (resolves `node.sector` to a weight vector for the composite).
- `engine/wind.py` — ERA5-driven `Wind_Consistency` and directional buffers.
- `engine/external_registries.py` — E-PRTR / GHGRP integration for proper `Nearby_Source_Isolation`.

These directories should *not* exist in the v1 codebase — they're listed here so v1.x extension PRs land in predictable places.

---

*Document version 1.0 — 13 May 2026. Anchored to `PLFS_v4.md`, `Indicators_Computation_v3.md`, `Indicator_ID_Schema_v1.md`, `Wireframes_All_v4.md`, `GEE_Database_List_v3.md`, `Verbal_Summary_Templates_v1.md`.*
