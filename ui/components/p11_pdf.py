"""P-11 PDF rendering (M-P11.3 / M-P11-FIX).

One pure function: ``render_pdf(html_string) -> bytes``. Uses
weasyprint to convert the assembled HTML from
``ui.components.p11_assembler.build_report_html`` to a PDF byte
stream suitable for ``st.download_button``.

The shared shell template's CSS (M-P11.2) already includes ``@page``
rules for A4, margins, and footer page numbering — weasyprint
honours these natively.

M-P11-FIX wraps the underlying ``ImportError`` / ``OSError`` that
weasyprint raises when Pango / Cairo / GLib aren't installed into a
dedicated ``PdfDependencyError``. The renderer catches it and shows
a friendly install-instruction banner instead of dumping the raw
dlopen traceback to the user.
"""

# M-P11.3
from __future__ import annotations

from io import BytesIO


# M-P11-FIX
class PdfDependencyError(RuntimeError):
    """Raised when weasyprint can't be imported or used because its
    native system dependencies (Pango / Cairo / GLib) aren't
    available on the host."""


def render_pdf(html_string: str) -> bytes:
    """Render an HTML report string to PDF bytes.

    Imports weasyprint lazily — the import triggers Pango/Cairo
    loading (~200 MB resident memory), so we defer until first call
    to keep the app's startup cost on cold load near zero.

    M-P11-FIX: missing native deps surface as ``PdfDependencyError``.
    weasyprint loads the libs at *import* time on most systems
    (raising ``OSError``), but some installations only fail when
    ``write_pdf`` is invoked — both paths are wrapped.
    """
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:
        raise PdfDependencyError(str(exc)) from exc

    buffer = BytesIO()
    try:
        HTML(string=html_string).write_pdf(buffer)
    except OSError as exc:
        raise PdfDependencyError(str(exc)) from exc
    return buffer.getvalue()
