"""P-11 CSV export (M-P11.4).

Flat per-indicator table. One row per (source, pillar, indicator)
tuple. Multiple sources expand the row count; columns stay stable.
Prioritisation sources expand to per-supplier rows so each supplier's
indicator-level data is visible in the flat table.

Designed for analysis-ready import into pandas / Excel — column order
is locked, score values are numeric strings (no thousands separator),
empty cells are empty strings (not the literal "None").
"""

# M-P11.4
from __future__ import annotations

import csv
from io import StringIO

from ui.components.p04_indicator_registry import INDICATORS_BY_PILLAR


# M-P11.4-FIX: prefix the CSV with a UTF-8 BOM so Excel on macOS /
# Windows reads the file as UTF-8 (preserving em-dashes, accents)
# instead of falling back to the local 8-bit encoding.
_UTF8_BOM = "﻿"


_COLUMNS = (
    "source_name",
    "source_type",
    "pillar",
    "indicator_id",
    "score",
    "confidence",
    "asset_id",
    "native_scale_m",
    "time_range_start",
    "time_range_end",
    "skipped_reason",
)


def render_csv(state, sources: list[dict]) -> str:
    """Build a CSV string from the report's sources.

    The ``state`` argument is accepted for parity with ``render_pdf``
    and ``render_json`` — the CSV body is fully derived from the
    source list, but keeping the signature uniform makes the three
    export wrappers in ``p11_renderer.py`` trivial.

    M-P11.4-FIX:
      - ``QUOTE_ALL`` so every field is wrapped in quotes — commas
        in source names or asset IDs no longer break the column
        layout when opened in Excel.
      - Leading UTF-8 BOM (``\\ufeff``) so Excel on macOS / Windows
        reads the file as UTF-8 (preserving em-dashes / accents)
        instead of falling back to the system's local encoding.
    """
    del state  # not used; see docstring.
    buffer = StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=_COLUMNS,
        quoting=csv.QUOTE_ALL,    # M-P11.4-FIX
    )
    writer.writeheader()

    for src in sources:
        if src.get("type") == "screening":
            _write_screening_rows(writer, src)
        elif src.get("type") == "prioritisation":
            _write_prioritisation_rows(writer, src)

    return _UTF8_BOM + buffer.getvalue()  # M-P11.4-FIX


def _write_screening_rows(writer: csv.DictWriter, src: dict) -> None:
    """One row per indicator for a screening source."""
    source_name = src.get("name", "Untitled")
    payload = src.get("payload") or {}
    for pillar, indicator_ids in INDICATORS_BY_PILLAR.items():
        for indicator_id in indicator_ids:
            writer.writerow(_build_row(
                source_name=source_name,
                source_type="screening",
                pillar=pillar,
                indicator_id=indicator_id,
                payload=payload,
            ))


def _write_prioritisation_rows(writer: csv.DictWriter, src: dict) -> None:
    """One row per (supplier, pillar, indicator) for a prioritisation source.

    Suppliers without a usable result (``status in {"failed",
    "cancelled"}`` or empty ``result``) are skipped so the CSV stays
    populated with cells consumers can plot.
    """
    base_name = src.get("name", "Untitled")
    for supplier in src.get("supplier_results", []):
        result = supplier.get("result") or {}
        if not result:
            continue
        supplier_name = f"{base_name} / {supplier.get('name', 'Unknown')}"
        for pillar, indicator_ids in INDICATORS_BY_PILLAR.items():
            for indicator_id in indicator_ids:
                writer.writerow(_build_row(
                    source_name=supplier_name,
                    source_type="prioritisation",
                    pillar=pillar,
                    indicator_id=indicator_id,
                    payload=result,
                ))


def _build_row(
    *,
    source_name: str,
    source_type: str,
    pillar: str,
    indicator_id: str,
    payload: dict,
) -> dict[str, str]:
    """Construct one CSV row from the payload.

    Looks up the provenance block at ``_provenance.<pillar>.<base>``
    where ``<base>`` is the first two dot-segments of the indicator
    ID (e.g. ``air.no2.score`` → ``_provenance.air.no2``); that's the
    pattern the pillar modules emit per ``docs/provenance_schema.md``.
    Confidence is the sibling payload key ``<base>.confidence``.
    """
    base = _indicator_base(indicator_id)
    provenance = payload.get(f"_provenance.{base}")
    if not isinstance(provenance, dict):
        provenance = {}

    score = payload.get(indicator_id)
    confidence = payload.get(f"{base}.confidence")
    time_range = provenance.get("time_range") or (None, None)
    return {
        "source_name":      source_name,
        "source_type":      source_type,
        "pillar":           pillar,
        "indicator_id":     indicator_id,
        "score":            _fmt_value(score),
        "confidence":       _fmt_value(confidence),
        "asset_id":         provenance.get("asset_id") or "",
        "native_scale_m":   _fmt_scale(provenance.get("native_scale_m")),
        "time_range_start": (time_range[0] or "") if time_range else "",
        "time_range_end":   (time_range[1] or "") if time_range else "",
        "skipped_reason":   provenance.get("skipped_reason") or "",
    }


def _indicator_base(indicator_id: str) -> str:
    """Return ``<pillar>.<short>`` — the first two dot-segments.

    Examples: ``air.no2.score`` → ``air.no2``;
    ``nature.kba.proximity_score`` → ``nature.kba``;
    ``nature.habitat.natural_loss_ha`` → ``nature.habitat``.
    """
    parts = indicator_id.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else indicator_id


def _fmt_value(value) -> str:
    """Format numeric scores / confidences as 4-decimal strings; None
    and non-numeric values become empty strings so the CSV cells
    are blank rather than the literal "None"."""
    if value is None:
        return ""
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return ""


def _fmt_scale(value) -> str:
    """Format a native scale value as plain meters (no decimals)."""
    if value is None:
        return ""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return ""
