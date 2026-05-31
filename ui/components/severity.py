"""Per-grammar severity classification for the C4b indicator snapshot (M-UI-A4).

Pure-Python, no Streamlit. Three severity *grammars* (spec v1.1), each a
function mapping an indicator's payload values to one of four severity states:

    "High"   — strong, decision-relevant signal
    "Concern"— worth surfacing
    "Normal" — within the expected band
    "Sparse" — too little / too poor data to classify (distinct from Normal)

The three grammars are **z-score** (Air + GHG CH₄/VIIRS + NDVI), **DW
categorical** (Dynamic World dominant class), and **distance/overlap** (KBA).
Hansen forest loss and ODIAC CO₂ were removed from the headline grid in spec
v1.1 as reference datasets (they live in C5 per M-UI-A6) — the loss-fraction
grammar and the ODIAC percentile scheme are no longer implemented here.

The UI owns severity (SR3): no engine flag drives these buckets. Every value
read here is an *existing* payload field — z-scores, distances, overlap
percentages, dominant-class slugs, and the per-indicator confidence float.
No new engine output is required (M-UI-A4 §2.2).

Thresholds are the v1.0 defaults from the M-UI-A4 spec §4, shipped as the
canonical ``SEVERITY_BANDS`` table below and flagged tunable. A calibration
sweep against the demo AOIs is a deferred follow-up (spec §4.6 / R1).

Authority: docs/M-UI-A4_spec §4; docs/M-UI-A4_severity_thresholds.md;
docs/Indicators_Computation_v4.md for indicator semantics.

Sign convention (resolved during recon, see §4.1):
    Severity is driven by the *magnitude* ``|z|`` — direction (above/below
    the regional baseline) drives the tile's direction icon, NOT the
    severity word (SR1: "Direction … drives the icon … without changing
    severity"). ``zscore_direction`` exposes the sign for the renderer.
"""

# M-UI-A4
from __future__ import annotations

from typing import Literal


Severity = Literal["High", "Concern", "Normal", "Sparse"]


# ---------------------------------------------------------------------------
# Canonical threshold table (spec §4.5) — the single source of truth for the
# severity bands, shared by the grammar functions, the tests, and the docs.
# ---------------------------------------------------------------------------
# @parameter
# tier: first-pass
# rationale: The v1.0 default bands that map each headline tile to High /
#     Concern / Normal / Sparse. Z-score grammar: |z| >= 2.0 High, >= 1.0
#     Concern. KBA distance grammar: < 1 km (or any overlap) High, < 10 km
#     Concern. Sparse override: confidence < 0.40 or valid-pixel fraction
#     < 0.30. These are spec defaults chosen by judgment; a calibration sweep
#     against the demo AOIs is a deferred follow-up (M-UI-A4 spec §4.6 / R1).
# source: docs/M-UI-A4_severity_thresholds.md; M-UI-A4 spec §4.5; calibration pending
# last_reviewed: 2026-05-29
# applies_to: [air.no2, air.so2, air.co, air.hcho, air.o3, air.aai, air.aod, air.pm25, air.pm10, ghg.viirs, nature.ndvi, nature.dw, nature.kba]
SEVERITY_BANDS: dict[str, dict] = {
    "zscore": {"High": 2.0, "Concern": 1.0},
    # M-GHG-REDESIGN-A1 — score-band grammar for the re-grammared VIIRS term
    # (and any future [0,1]-component-score indicator that isn't a z-score).
    # VIIRS no longer carries a z; its severity bands the persistence-weighted
    # ring-relative sustained-contrast score directly. Thresholds at thirds of
    # the [0,1] range: High >= 0.66, Concern >= 0.33. These also line up with
    # the z-score bands under the §0.4 mapping score ≈ z/k (k=3): z=1 → 0.33,
    # z=2 → 0.66, so VIIRS "Concern/High" keeps the same felt meaning as the
    # other tiles. First-pass; the obvious calibration target.
    "score": {"High": 0.66, "Concern": 0.33},
    "distance": {"High_km": 1.0, "Concern_km": 10.0, "High_overlap_pct": 0.0},
    "sparse_confidence": 0.40,
    "sparse_valid_pixel": 0.30,
}

# DW dominant-class slugs (engine.nature.DW_INDEX_TO_LABEL) that signal
# disturbance in a Nature-screening context. Built/Bare → Concern (§4.2);
# everything else (including Crops) → Normal.
_DW_CONCERN_CLASSES: frozenset[str] = frozenset({"built", "bare"})

# Near-zero magnitude below which a z reads as "no meaningful direction"
# (matches c4b_kpi_grid._FLAT_ANOMALY_EPS intent, but on the z scale).
_FLAT_Z_EPS: float = 0.1


# ---------------------------------------------------------------------------
# Sparse override (spec §4.1 SR8)
# ---------------------------------------------------------------------------

def _is_sparse(confidence: float | None, provenance: dict | None) -> bool:
    """Return True when the indicator should read as "Sparse data".

    Fires the Sparse state — distinct from Normal (SR8) — when the data is
    too thin or too poor to trust the severity classification, regardless of
    what the grammar band would otherwise say.

    Triggers, in priority order:
      1. A ``skipped_reason`` in provenance (the indicator was skipped —
         coverage gap, no usable pixels, KBA/Hansen no-coverage, etc.).
      2. An explicit ``extra.fallback_used`` flag (best-effort; not all
         indicators emit one — see recon A.2).
      3. A valid-pixel fraction below ``sparse_valid_pixel`` (0.30). Prefers
         an explicit ``extra.valid_pixel_pct``; falls back to the confidence
         formula's ``n_valid`` coverage term when present.
      4. Confidence is None or below ``sparse_confidence`` (0.40). This is
         the primary driver and mirrors the reference dot logic in
         ``traffic_light.confidence_glyph`` (recon A.4).

    The valid_pixel/fallback keys (1.x) don't yet exist on every indicator
    (recon A.2); the checks are defensive so they activate automatically if
    the engine adds them, but confidence is the dependable signal today.
    """
    prov = provenance or {}
    if prov.get("skipped_reason"):
        return True

    extra = prov.get("extra") or {}
    if extra.get("fallback_used"):
        return True

    valid_pixel_pct = extra.get("valid_pixel_pct")
    if valid_pixel_pct is None:
        terms = extra.get("confidence_terms") or {}
        valid_pixel_pct = terms.get("valid_pixel_pct")  # explicit if present
    if valid_pixel_pct is not None and valid_pixel_pct < SEVERITY_BANDS["sparse_valid_pixel"]:
        return True

    if confidence is None:
        return True
    if confidence < SEVERITY_BANDS["sparse_confidence"]:
        return True
    return False


# ---------------------------------------------------------------------------
# §4.1 — Z-score grammar (Air + GHG CH₄/VIIRS + NDVI deviation)
# ---------------------------------------------------------------------------

def severity_zscore(
    z: float | None,
    confidence: float | None,
    provenance: dict | None,
) -> Severity:
    """Severity from a spatiotemporal-anomaly z-score (spec §4.1).

    Bands on ``|z|``: ``|z| ≥ 2.0`` High, ``1.0 ≤ |z| < 2.0`` Concern,
    ``|z| < 1.0`` Normal. The Sparse override (``_is_sparse``) wins over any
    band. A missing z (``None``) reads as Sparse, not a crash (§7.1).

    Direction (positive vs negative z) does NOT change severity — it drives
    the tile's direction icon via ``zscore_direction``.
    """
    if _is_sparse(confidence, provenance):
        return "Sparse"
    if z is None:
        return "Sparse"
    az = abs(z)
    if az >= SEVERITY_BANDS["zscore"]["High"]:
        return "High"
    if az >= SEVERITY_BANDS["zscore"]["Concern"]:
        return "Concern"
    return "Normal"


def zscore_direction(z: float | None) -> Literal["above", "below", "near"]:
    """Sign of the z → which side of the regional baseline the site sits on.

    ``above`` for positive z, ``below`` for negative z, ``near`` for
    ``|z| < _FLAT_Z_EPS`` or a missing z. Presentation-only: drives the
    ▲/▼/● icon and the plain-language framing line; never the severity word.
    """
    if z is None or abs(z) < _FLAT_Z_EPS:
        return "near"
    return "above" if z > 0 else "below"


# ---------------------------------------------------------------------------
# §4.1b — Score-band grammar (M-GHG-REDESIGN-A1; VIIRS sustained contrast)
# ---------------------------------------------------------------------------

def severity_score_band(
    score: float | None,
    confidence: float | None,
    provenance: dict | None,
) -> Severity:
    """Severity from a [0,1] component score (M-GHG-REDESIGN-A1).

    Bands on the raw score: ``score >= 0.66`` High, ``0.33 <= score < 0.66``
    Concern, ``score < 0.33`` Normal. Used by the VIIRS tile, whose score is
    the persistence-weighted ring-relative sustained contrast (no z-score).
    The Sparse override (``_is_sparse``) wins over any band; a missing score
    reads as Sparse (the engine routes genuine no-data to a skip, so a None
    here means "computed-but-absent", which is correctly Sparse).

    Like the z-score grammar this is a magnitude — there is no direction
    concept for a sustained-contrast score (it is unsigned: site brighter
    than its ring or not), so there is no score-band equivalent of
    ``zscore_direction``.
    """
    if _is_sparse(confidence, provenance):
        return "Sparse"
    if score is None:
        return "Sparse"
    if score >= SEVERITY_BANDS["score"]["High"]:
        return "High"
    if score >= SEVERITY_BANDS["score"]["Concern"]:
        return "Concern"
    return "Normal"


# ---------------------------------------------------------------------------
# §4.2 — DW-categorical grammar (Dynamic World dominant class)
# ---------------------------------------------------------------------------

def severity_categorical(
    value: str | None,
    confidence: float | None,
    provenance: dict | None,
    *,
    scheme: Literal["dw"] = "dw",
) -> Severity:
    """Severity for the DW dominant-class categorical grammar (spec §4.2 v1.1).

    ``value`` is the Dynamic-World dominant-class slug (e.g. ``"built"``,
    ``"crops"``). Built/Bare → Concern; everything else (including Crops) →
    Normal. DW alone never fires High — the categorical signal needs
    corroborating context (Hansen loss, NDVI trend), so this is deliberately
    conservative.

    Sparse override + None handling as in ``severity_zscore``.

    The ``scheme`` parameter is retained (DW-only) for call-site symmetry; the
    former ``scheme="odiac"`` branch was removed in spec v1.1 when ODIAC left
    the headline grid as a reference dataset.
    """
    if scheme != "dw":
        raise ValueError(f"unknown categorical scheme: {scheme!r}")
    if _is_sparse(confidence, provenance):
        return "Sparse"
    if value is None:
        return "Sparse"
    return "Concern" if str(value) in _DW_CONCERN_CLASSES else "Normal"


# ---------------------------------------------------------------------------
# §4.3 — Distance/overlap grammar (KBA proximity)
# ---------------------------------------------------------------------------

def severity_distance(
    dist_km: float | None,
    overlap_pct: float | None,
    confidence: float | None,
    provenance: dict | None,
) -> Severity:
    """Severity from KBA proximity — distance OR overlap, whichever fires
    more severely (spec §4.3).

    ``buffer_overlap_pct > 0`` OR ``dist_km < 1.0`` → High (the footprint
    touches, or is sub-kilometre from, a designated biodiversity area).
    ``1.0 ≤ dist_km < 10.0`` → Concern. ``dist_km ≥ 10.0`` → Normal.

    Both inputs missing → Sparse (the KBA query failed or the AOI has no KBA
    coverage data — also caught by ``_is_sparse`` via ``skipped_reason``).
    """
    if _is_sparse(confidence, provenance):
        return "Sparse"
    if dist_km is None and overlap_pct is None:
        return "Sparse"

    overlap = overlap_pct or 0.0
    bands = SEVERITY_BANDS["distance"]
    if overlap > bands["High_overlap_pct"] or (dist_km is not None and dist_km < bands["High_km"]):
        return "High"
    if dist_km is not None and bands["High_km"] <= dist_km < bands["Concern_km"]:
        return "Concern"
    if dist_km is not None and dist_km >= bands["Concern_km"]:
        return "Normal"
    # dist_km unknown and no overlap → can't classify confidently.
    return "Sparse"


# Note (spec v1.1): the loss-fraction grammar (Hansen forest loss) was removed
# — Hansen is a reference dataset, not a scored headline tile, and lives in C5
# per M-UI-A6. No ``severity_loss_fraction`` is implemented.


# ---------------------------------------------------------------------------
# Shared helpers for the renderer
# ---------------------------------------------------------------------------

# Ordering used for the SR9 "top up to 3" rule and any severity sort.
# Higher index = more severe. Sparse sorts below Normal (non-critical, but
# above nothing) so the top-up prefers a real Normal reading over Sparse.
_SEVERITY_RANK: dict[str, int] = {
    "Sparse": 0,
    "Normal": 1,
    "Concern": 2,
    "High": 3,
}


def severity_rank(severity: Severity) -> int:
    """Numeric rank for sorting tiles by severity (High highest)."""
    return _SEVERITY_RANK[severity]


def is_critical(severity: Severity) -> bool:
    """Critical = severity ∉ {Normal, Sparse} (SR2). Failure tiles count as
    Sparse for this purpose (SR12) and are therefore non-critical."""
    return severity in ("High", "Concern")
