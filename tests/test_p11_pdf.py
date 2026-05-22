"""Tests for the M-P11.3 PDF export pipeline.

Two layers:

1. **Pure-Python helpers** — ``_pdf_cache_key`` and ``_build_filename``
   in ``ui/components/p11_renderer.py``. No Streamlit / weasyprint
   needed; these pin the cache-invalidation contract and the
   filename-safety rules used by ``st.download_button``.
2. **End-to-end smoke test** — actually invokes ``render_pdf`` from
   ``ui/components/p11_pdf.py``. Skipped when weasyprint can't load
   its native libraries (Pango/Cairo), so CI runs without the system
   deps still pass.
"""

# M-P11.3
from __future__ import annotations

import builtins
import sys
import types

import pytest

from ui.components.p11_pdf      import PdfDependencyError, render_pdf
from ui.components.p11_renderer import _build_filename, _pdf_cache_key
from ui.p11_state import ReportState


def _make_state(
    *,
    template_id="policy_audit",
    source_ids=None,
    title="Q2 demo report",
    notes="",
) -> ReportState:
    return ReportState(
        template_id=template_id,
        source_ids=list(source_ids) if source_ids else ["a", "b"],
        title=title,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 5a / 5b / 5c — _pdf_cache_key invalidation contract
# ---------------------------------------------------------------------------

def test_pdf_cache_key_same_state_returns_same_key():
    a = _pdf_cache_key(_make_state())
    b = _pdf_cache_key(_make_state())
    assert a == b


def test_pdf_cache_key_different_title_invalidates():
    a = _pdf_cache_key(_make_state(title="Q2 report"))
    b = _pdf_cache_key(_make_state(title="Q3 report"))
    assert a != b


def test_pdf_cache_key_different_sources_invalidates():
    a = _pdf_cache_key(_make_state(source_ids=["src-1"]))
    b = _pdf_cache_key(_make_state(source_ids=["src-2"]))
    assert a != b


def test_pdf_cache_key_source_order_does_not_invalidate():
    # Sorted internally — ['a', 'b'] and ['b', 'a'] are the same report.
    a = _pdf_cache_key(_make_state(source_ids=["a", "b"]))
    b = _pdf_cache_key(_make_state(source_ids=["b", "a"]))
    assert a == b


def test_pdf_cache_key_different_notes_invalidates():
    a = _pdf_cache_key(_make_state(notes="initial"))
    b = _pdf_cache_key(_make_state(notes="revised"))
    assert a != b


# ---------------------------------------------------------------------------
# 5d / 5e / 5f / 5g / 5h — _build_filename safety contract
# ---------------------------------------------------------------------------

def test_build_filename_happy_path():
    name = _build_filename(_make_state(title="Q2 2026 demo"), "pdf")
    assert name.endswith(".pdf")
    assert name.startswith("Q2_2026_demo_")


def test_build_filename_strips_path_unsafe_characters():
    name = _build_filename(
        _make_state(title="Report: Brazil / Soy & Cattle (v2)"),
        "pdf",
    )
    # No slashes, no colons, no parentheses — all stripped by the
    # safe-character regex.
    for forbidden in ("/", ":", "(", ")"):
        assert forbidden not in name
    assert name.endswith(".pdf")


def test_build_filename_spaces_become_underscores():
    name = _build_filename(_make_state(title="Q2 demo report"), "pdf")
    assert "Q2_demo_report" in name
    assert " " not in name


def test_build_filename_empty_title_falls_back_to_report():
    name = _build_filename(_make_state(title=""), "pdf")
    assert name.startswith("report_")
    assert name.endswith(".pdf")


def test_build_filename_whitespace_only_title_falls_back_to_report():
    name = _build_filename(_make_state(title="   "), "pdf")
    assert name.startswith("report_")


def test_build_filename_very_long_title_truncated_to_60_chars():
    long_title = "A" * 200
    name = _build_filename(_make_state(title=long_title), "pdf")
    # Stem before the date is at most 60 chars of A's.
    stem = name.split("_")[0]
    assert len(stem) == 60
    assert set(stem) == {"A"}


# M-P11.4: ext argument lets CSV / JSON exports share the same builder.
def test_build_filename_csv_extension():
    name = _build_filename(_make_state(title="Q2 demo"), "csv")
    assert name.endswith(".csv")


def test_build_filename_json_extension():
    name = _build_filename(_make_state(title="Q2 demo"), "json")
    assert name.endswith(".json")


# ---------------------------------------------------------------------------
# 5i — render_pdf end-to-end smoke
# ---------------------------------------------------------------------------

@pytest.fixture
def _weasyprint_or_skip():
    """Skip if weasyprint or its native deps (Pango/Cairo) aren't available.

    The Python package may install on systems missing the C libraries;
    weasyprint loads its native libs at *import* time and raises
    ``OSError`` if they're missing, so the same try/except has to
    cover both ImportError and OSError. CI without the system deps
    still passes the rest of the suite.
    """
    try:
        from weasyprint import HTML  # noqa: F401
    except (ImportError, OSError) as exc:
        pytest.skip(f"weasyprint unavailable: {exc}")


def test_render_pdf_produces_pdf_bytes(_weasyprint_or_skip):
    html = (
        "<!DOCTYPE html><html><head><title>Test</title></head>"
        "<body><h1>Test report</h1>"
        "<p>Lorem ipsum dolor sit amet.</p></body></html>"
    )
    out = render_pdf(html)

    assert isinstance(out, (bytes, bytearray))
    # PDFs carry the %PDF- magic at byte 0.
    assert bytes(out[:4]) == b"%PDF"
    # Even a trivial PDF is >1 KB once fonts + xref are written.
    assert len(out) > 1000


# ---------------------------------------------------------------------------
# M-P11-FIX — PdfDependencyError wraps the underlying load failures
# ---------------------------------------------------------------------------

def test_render_pdf_wraps_import_failure_in_pdf_dependency_error(monkeypatch):
    """When ``from weasyprint import HTML`` raises OSError (the
    real-world mode on systems missing Pango/Cairo/GLib), render_pdf
    must surface ``PdfDependencyError`` rather than the dlopen
    traceback."""
    # Force the lazy import to re-execute by dropping any cached
    # weasyprint module entry.
    monkeypatch.delitem(sys.modules, "weasyprint", raising=False)

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "weasyprint":
            raise OSError("cannot load library 'libgobject-2.0-0'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(PdfDependencyError) as exc_info:
        render_pdf("<html></html>")
    assert "libgobject" in str(exc_info.value)


def test_render_pdf_wraps_write_pdf_failure_in_pdf_dependency_error(monkeypatch):
    """When weasyprint imports cleanly but ``write_pdf`` raises OSError
    at render time (e.g. lazy-loaded glyphs / fonts can't be found),
    render_pdf must still surface ``PdfDependencyError``."""
    fake_module = types.ModuleType("weasyprint")

    class _FakeHTML:
        def __init__(self, *args, **kwargs):
            pass

        def write_pdf(self, buffer):
            raise OSError("native font library disappeared")

    fake_module.HTML = _FakeHTML
    monkeypatch.setitem(sys.modules, "weasyprint", fake_module)

    with pytest.raises(PdfDependencyError) as exc_info:
        render_pdf("<html></html>")
    assert "native font library disappeared" in str(exc_info.value)


def test_pdf_dependency_error_is_runtime_error():
    """Subclassing RuntimeError keeps the exception hierarchy honest —
    generic ``except Exception`` handlers will still catch it, but
    callers can branch on the more specific type for friendly UI."""
    assert issubclass(PdfDependencyError, RuntimeError)
