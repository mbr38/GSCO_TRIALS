"""Parameter transparency registry (M-UX-A1 item 2.8).

Single source of truth for the user-facing-threshold constants surfaced on
the P-09 Indicator Library. Each in-scope constant carries a structured
``# @parameter`` annotation block immediately above its definition (format
§4.3 of the M-UX-A1 spec); this module parses those blocks at import time
and exposes them to the P-09 renderer.

Design (locked decisions, M-UX-A1):
  * UX9 — rationale lives in the code, next to the value. There is no
    separate registry data file; the annotation *is* the source of truth.
  * UX8 — only user-facing thresholds are in scope. The canonical inventory
    is the ``_INVENTORY`` list below. Adding a constant here without
    annotating it is what the UX12 lint test catches.
  * UX11 — three calibration tiers: ``first-pass`` / ``calibrated`` /
    ``spec-mandated``.
  * UX14 — the code-path pointer is ``<module/path.py>::<CONSTANT_NAME>``.
  * UX19 — a constant consumed by multiple indicators renders under each,
    with a "(shared)" note derived from ``applies_to``.

Annotation format (§4.3), e.g.::

    # @parameter
    # tier: first-pass
    # rationale: First-pass intuition that a per-day z-score of 2.0 is the
    #     right gate for "anomalous day". Continuation lines are indented.
    # source: spec/Indicators_Computation_v4.md §0.4; calibration pending
    # last_reviewed: 2026-05-28
    # applies_to: [air.no2, air.so2, ghg.ch4]
    ANOMALY_Z_THRESHOLD: float = 2.0

Required fields: ``tier``, ``rationale``, ``source``. Optional: ``last_reviewed``,
``applies_to``. A constant in ``_INVENTORY`` whose block is missing or lacks a
required field is reported via :func:`lint_inventory` (and, per UX-Q2, surfaced
as a warning rather than a hard failure).
"""

# M-UX-A1
from __future__ import annotations

import importlib
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any


# Three-tier calibration vocabulary (UX11). ``spec-mandated`` is not "better"
# than ``calibrated`` — it is a different *kind* of grounding (prescribed by a
# methodology doc), which is why UX13 colours it blue, distinct from the
# severity/attributability green-amber-red.
VALID_TIERS: frozenset[str] = frozenset(
    {"first-pass", "calibrated", "spec-mandated"}
)

_REQUIRED_FIELDS: tuple[str, ...] = ("tier", "rationale", "source")
_KNOWN_FIELDS: frozenset[str] = frozenset(
    {"tier", "rationale", "source", "last_reviewed", "applies_to"}
)

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Canonical inventory (UX8) — the definitive list of user-facing thresholds.
# Each entry: (constant_name, dotted_module). Adding a constant here without
# the ``# @parameter`` annotation trips the UX12 lint (see lint_inventory).
#
# Scope locked at M-UX-A1 Step B: the 15 UX8-named thresholds plus the two
# spec-mandated headline constants (TRAFFIC_LIGHT_THRESHOLDS, NORMALISATION_K).
# Internal / decision-influencing constants (weight dicts, QA tables, fallback
# multipliers, etc.) are deliberately out of scope.
# ---------------------------------------------------------------------------
_INVENTORY: tuple[tuple[str, str], ...] = (
    # Severity bands (M-UI-A4) — lives in the UI layer, not engine.constants.
    ("SEVERITY_BANDS", "ui.components.severity"),
    # Repeatable-core / headline thresholds.
    ("ANOMALY_Z_THRESHOLD", "engine.constants"),
    ("NORMALISATION_K", "engine.constants"),
    ("TRAFFIC_LIGHT_THRESHOLDS", "engine.constants"),
    # Wind attributability buckets (M-WIND-A1 v2.0).
    ("WIND_SPEED_HIGH_MAX_MS", "engine.constants"),
    ("WIND_SPEED_LOW_MIN_MS", "engine.constants"),
    ("WIND_ASYMMETRY_HIGH_MAX", "engine.constants"),
    ("WIND_ASYMMETRY_LOW_MIN", "engine.constants"),
    ("WIND_CALM_THRESHOLD_MS", "engine.constants"),
    ("WIND_N_MIN_ANOMALY_DAYS", "engine.constants"),
    # Habitat attributability buckets (M-ATTRIB-A1).
    ("HABITAT_SPATIAL_LINK_HIGH_KM", "engine.constants"),
    ("HABITAT_SPATIAL_LINK_MOD_KM", "engine.constants"),
    ("N_MIN_PIXELS_FOR_CENTROID", "engine.constants"),
    # Nature reference / saturation thresholds.
    ("HANSEN_LOSS_RATIO_THRESHOLD", "engine.constants"),
    ("KBA_DISTANCE_DECAY_KM", "engine.constants"),
    ("CONVERSION_SATURATION_PCT", "engine.constants"),
    ("WATER_FLOODED_VEG_SATURATION_PCT", "engine.constants"),
)


@dataclass(frozen=True)
class ParameterRecord:
    """One annotated user-facing threshold, ready for P-09 rendering."""

    name: str
    module: str                     # dotted import path
    value: Any                      # the live runtime value (single source)
    tier: str
    rationale: str
    source: str
    last_reviewed: str | None = None
    applies_to: tuple[str, ...] = ()
    # Lint bookkeeping — populated even for malformed blocks.
    missing_fields: tuple[str, ...] = ()
    annotated: bool = True

    @property
    def code_path(self) -> str:
        """UX14 — ``<module/path.py>::<CONSTANT_NAME>`` pointer."""
        rel = _module_relpath(self.module)
        return f"{rel}::{self.name}"

    @property
    def is_valid(self) -> bool:
        return self.annotated and not self.missing_fields and self.tier in VALID_TIERS

    @property
    def shared_count(self) -> int:
        """Number of *other* indicators this constant applies to (UX19)."""
        return max(0, len(self.applies_to) - 1)


# ---------------------------------------------------------------------------
# Source-file helpers
# ---------------------------------------------------------------------------

def _module_relpath(module: str) -> str:
    """Repo-relative file path for a dotted module (for the code-path pointer)."""
    mod = importlib.import_module(module)
    path = Path(mod.__file__).resolve()
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


@lru_cache(maxsize=None)
def _source_lines(module: str) -> tuple[str, ...]:
    mod = importlib.import_module(module)
    return tuple(Path(mod.__file__).read_text(encoding="utf-8").splitlines())


# A constant definition line: ``NAME: type = ...`` or ``NAME = ...`` at column 0.
def _definition_line_index(lines: tuple[str, ...], name: str) -> int | None:
    pattern = re.compile(rf"^{re.escape(name)}\s*(:[^=]+)?=")
    for i, line in enumerate(lines):
        if pattern.match(line):
            return i
    return None


_FIELD_RE = re.compile(
    r"^(tier|rationale|source|last_reviewed|applies_to):\s?(.*)$"
)


def _parse_annotation_block(lines: tuple[str, ...], def_idx: int) -> dict | None:
    """Extract the ``# @parameter`` field dict for the constant at ``def_idx``.

    Walks backward over the contiguous comment lines directly above the
    definition. Returns ``None`` when no ``# @parameter`` marker is present
    (the constant is unannotated). Field values support indented
    continuation lines (joined with a single space).
    """
    # Gather contiguous comment lines immediately above the definition.
    block: list[str] = []
    i = def_idx - 1
    while i >= 0:
        stripped = lines[i].strip()
        if stripped.startswith("#"):
            block.append(stripped)
            i -= 1
            continue
        break
    block.reverse()  # restore top-to-bottom order

    # Strip the leading "#" (and one optional space) from each comment line.
    comment_text = [re.sub(r"^#\s?", "", ln) for ln in block]

    # Find the @parameter marker; everything after it is the field block.
    marker_idx = None
    for idx, text in enumerate(comment_text):
        if text.strip() == "@parameter":
            marker_idx = idx
            break
    if marker_idx is None:
        return None

    fields: dict[str, str] = {}
    current_key: str | None = None
    for text in comment_text[marker_idx + 1:]:
        m = _FIELD_RE.match(text)
        if m:
            current_key = m.group(1)
            fields[current_key] = m.group(2).strip()
        elif current_key is not None:
            # Continuation line for the current field.
            fields[current_key] = (fields[current_key] + " " + text.strip()).strip()
        # Lines before any recognised key (shouldn't happen) are ignored.
    return fields


def _parse_applies_to(raw: str | None) -> tuple[str, ...]:
    """Parse ``[air.no2, air.so2]`` → ("air.no2", "air.so2")."""
    if not raw:
        return ()
    raw = raw.strip().strip("[]")
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_registry() -> tuple[ParameterRecord, ...]:
    """Parse every inventory constant into a ParameterRecord.

    Unannotated constants and those missing required fields still produce a
    record (with ``annotated=False`` / ``missing_fields`` populated) so the
    lint can report them; valid records carry the parsed metadata and the
    live value.
    """
    records: list[ParameterRecord] = []
    for name, module in _INVENTORY:
        mod = importlib.import_module(module)
        value = getattr(mod, name, None)
        lines = _source_lines(module)
        def_idx = _definition_line_index(lines, name)

        if def_idx is None:
            records.append(ParameterRecord(
                name=name, module=module, value=value,
                tier="", rationale="", source="",
                missing_fields=("definition-not-found",), annotated=False,
            ))
            continue

        block = _parse_annotation_block(lines, def_idx)
        if block is None:
            records.append(ParameterRecord(
                name=name, module=module, value=value,
                tier="", rationale="", source="",
                missing_fields=_REQUIRED_FIELDS, annotated=False,
            ))
            continue

        missing = tuple(f for f in _REQUIRED_FIELDS if not block.get(f))
        records.append(ParameterRecord(
            name=name,
            module=module,
            value=value,
            tier=block.get("tier", ""),
            rationale=block.get("rationale", ""),
            source=block.get("source", ""),
            last_reviewed=block.get("last_reviewed") or None,
            applies_to=_parse_applies_to(block.get("applies_to")),
            missing_fields=missing,
            annotated=True,
        ))
    return tuple(records)


def _id_matches(applies_to_entry: str, indicator_id: str) -> bool:
    """Whether an ``applies_to`` entry matches a library card's indicator_id.

    Library cards use full IDs (``air.no2.score``); annotations use base IDs
    (``air.no2``). Matches on exact equality, dotted-prefix, or two-segment
    base equality (same two-tier trick as p09_library._confidence_explanation_for).
    """
    if indicator_id == applies_to_entry:
        return True
    if indicator_id.startswith(applies_to_entry + "."):
        return True
    base = ".".join(indicator_id.split(".")[:2])
    return base == applies_to_entry


def get_parameters_for_indicator(indicator_id: str) -> list[ParameterRecord]:
    """Return all valid annotated constants that apply to ``indicator_id``.

    Used by the P-09 renderer. Only well-formed records are returned (a
    malformed one is a lint concern, not something to surface to users).
    Ordering follows the inventory order for stable rendering.
    """
    out: list[ParameterRecord] = []
    for rec in load_registry():
        if not rec.is_valid:
            continue
        if any(_id_matches(a, indicator_id) for a in rec.applies_to):
            out.append(rec)
    return out


def lint_inventory() -> list[str]:
    """Return human-readable problems with the inventory annotations (UX12).

    Per UX-Q2 (locked: warning, not hard gate) the test that consumes this
    emits a warning rather than failing CI. An empty list means every
    inventory constant carries a well-formed annotation.
    """
    problems: list[str] = []
    for rec in load_registry():
        if not rec.annotated:
            problems.append(
                f"{rec.code_path}: missing the `# @parameter` annotation block"
            )
            continue
        if rec.missing_fields:
            problems.append(
                f"{rec.code_path}: missing required field(s): "
                f"{', '.join(rec.missing_fields)}"
            )
        if rec.tier and rec.tier not in VALID_TIERS:
            problems.append(
                f"{rec.code_path}: unknown tier {rec.tier!r} "
                f"(expected one of {sorted(VALID_TIERS)})"
            )
    return problems


def inventory_names() -> tuple[str, ...]:
    """The canonical inventory constant names (for tests / introspection)."""
    return tuple(name for name, _ in _INVENTORY)
