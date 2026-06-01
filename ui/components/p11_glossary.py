"""Content-aware glossary appendix for P-11 reports (M-REPORT-A1 §6).

Every report carries a glossary appendix (RT12). It is **content-aware** (RT13):
it renders definitions only for the terms that actually appear in *this* report,
not a fixed master dump. Selection is a **static term → definition lookup** with
a post-render fragment scan (RT15 — no LLM; Step A §8.5 mechanism, chosen to suit
the flat section model). Definitions are the locked copy from spec §6.

The scan strips HTML tags from the rendered report body, then matches each term's
surface forms against the visible text with word-boundary guards (so "AOD" never
matches inside another token). Matched terms render grouped by family —
statistical · methodological · domain/dataset — in that fixed order.
"""

# M-REPORT-A1
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class _Term:
    term:       str          # display label
    definition: str          # locked plain-language copy (§6)
    family:     str          # "statistical" | "methodological" | "domain"
    aliases:    tuple[str, ...] = field(default_factory=tuple)

    def surface_forms(self) -> tuple[str, ...]:
        """All literal strings whose presence selects this term."""
        return (self.term, *self.aliases)


# Family order + display headings (rendered only when the family has matches).
_FAMILY_ORDER: tuple[tuple[str, str], ...] = (
    ("statistical",   "Statistical"),
    ("methodological", "Methodological"),
    ("domain",        "Domain / dataset"),
)

# ── Master registry (§6). Definitions are the locked copy. ─────────────────
_MASTER_TERMS: tuple[_Term, ...] = (
    # 6.1 Statistical
    _Term("z-score (σ)",
          "How far a value sits from its local average, measured in "
          "standard-deviation units.",
          "statistical", aliases=("z-score", "z score")),
    _Term("standard deviation (σ)",
          "The spread of values around the average; the unit a z-score is "
          "measured in.",
          "statistical", aliases=("standard deviation",)),
    _Term("p-value",
          "The probability a trend this strong could appear by chance; below "
          "0.05 is treated as significant.",
          "statistical", aliases=("p value",)),
    _Term("Theil-Sen slope",
          "A robust estimate of a trend's direction and rate, resistant to "
          "outliers.",
          "statistical", aliases=("Theil-Sen", "Theil–Sen")),
    _Term("Mann-Kendall test",
          "The significance test paired with Theil-Sen to decide whether a "
          "trend is real.",
          "statistical", aliases=("Mann-Kendall", "Mann–Kendall")),
    _Term("percentile",
          "Where a value falls in a ranked distribution (90th percentile = "
          "higher than 90% of the rest).",
          "statistical"),
    # 6.2 Methodological
    _Term("AOI / buffer",
          "The circular area screened around the site (centre plus radius).",
          "methodological", aliases=("AOI", "buffer")),
    _Term("background ring",
          "The annular reference zone around the AOI used as the \"normal\" "
          "baseline the site is compared against.",
          "methodological"),
    _Term("hotspot frequency",
          "The fraction of days a pixel exceeded its anomaly threshold over "
          "the screening window.",
          "methodological", aliases=("hotspot",)),
    _Term("anomaly",
          "A value departing from the local norm by more than the set "
          "threshold (2σ).",
          "methodological"),
    _Term("follow-up priority score",
          "The per-pillar severity ranking the tool produces; a measure of "
          "severity, not certainty.",
          "methodological", aliases=("follow-up priority", "followup priority",
                                     "priority score")),
    _Term("measurement quality / attribution confidence",
          "How trustworthy a measurement is, kept deliberately separate from "
          "severity (the M-ATTRIB-A1 split).",
          "methodological", aliases=("measurement quality",
                                     "attribution confidence")),
    _Term("attributability",
          "Whether an observed signal can plausibly be linked to the specific "
          "site, versus drifting in from elsewhere (wind, regional "
          "background). Context only; never enters the score.",
          "methodological", aliases=("attribution",)),
    _Term("confidence multiplier",
          "A factor that lowers reported confidence when a fallback or coarse "
          "data source was used.",
          "methodological"),
    _Term("fallback (temporal / climatology)",
          "Substitute data used when the primary source is too cloudy or "
          "sparse, at reduced confidence.",
          "methodological", aliases=("fallback", "climatology")),
    _Term("composite / overall screening score",
          "The blend of the three pillar priority scores.",
          "methodological", aliases=("composite", "overall screening")),
    # 6.3 Domain / dataset
    _Term("NDVI",
          "A vegetation-health index from satellite reflectance; higher means "
          "greener / healthier.",
          "domain"),
    _Term("AAI (Absorbing Aerosol Index)",
          "A measure of UV-absorbing aerosols such as smoke and dust.",
          "domain", aliases=("AAI", "Absorbing Aerosol Index")),
    _Term("AOD (Aerosol Optical Depth)",
          "How much aerosol blocks light through the atmospheric column.",
          "domain", aliases=("AOD", "Aerosol Optical Depth")),
    _Term("Dynamic World classes",
          "Google's nine satellite land-cover categories (Water, Trees, "
          "Crops, Built, etc.).",
          "domain", aliases=("Dynamic World",)),
    _Term("TROPOMI / Sentinel-5P",
          "The satellite instrument behind the gas measurements (NO₂, "
          "SO₂, CO, HCHO, O₃, CH₄).",
          "domain", aliases=("TROPOMI", "Sentinel-5P", "Sentinel 5P", "S5P")),
    _Term("CAMS",
          "The ~44 km global model grid behind the PM₂.₅ / "
          "PM₁₀ values.",
          "domain"),
    _Term("VIIRS nightlights",
          "Night-time light intensity, used as an industrial / urban activity "
          "proxy.",
          "domain", aliases=("VIIRS",)),
    _Term("KBA (Key Biodiversity Area)",
          "Designated biodiversity-important sites (BirdLife International).",
          "domain", aliases=("KBA", "Key Biodiversity Area")),
    _Term("Hansen / ODIAC",
          "Reference datasets (forest loss; CO₂ emissions) shown as "
          "context, not scored.",
          "domain", aliases=("Hansen", "ODIAC")),
    _Term("GWP (Global Warming Potential)",
          "The warming strength of a gas relative to CO₂.",
          "domain", aliases=("GWP", "Global Warming Potential")),
    _Term("ESRS E1 / E2 / E4",
          "The EU disclosure standards for Climate / Pollution / "
          "Biodiversity.",
          "domain", aliases=("ESRS", "ESRS E1", "ESRS E2", "ESRS E4")),
)

_TAG_RE = re.compile(r"<[^>]+>")


def _compile_surface(form: str) -> re.Pattern:
    """Boundary-guarded, case-insensitive matcher for one surface form.

    Guards on alphanumeric edges only — so internal hyphens / spaces in the
    form are honoured while partial-word hits (e.g. "AOD" inside "AODX") are
    rejected. Matching is on visible text, not HTML.
    """
    return re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(form) + r"(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


# Pre-compile (term, pattern) pairs once at import.
_TERM_MATCHERS: tuple[tuple[_Term, tuple[re.Pattern, ...]], ...] = tuple(
    (t, tuple(_compile_surface(f) for f in t.surface_forms()))
    for t in _MASTER_TERMS
)


def _visible_text(report_html: str) -> str:
    """Strip HTML tags so the scan matches reader-visible prose only."""
    return _TAG_RE.sub(" ", report_html or "")


def collect_terms(report_html: str) -> list[_Term]:
    """The master terms present in the rendered report, in registry order.

    Content-aware (RT13): a term is selected if any of its surface forms
    appears in the visible text. Deduplicated by construction (each term is
    tested once); registry order is preserved.
    """
    text = _visible_text(report_html)
    return [
        term
        for term, matchers in _TERM_MATCHERS
        if any(m.search(text) for m in matchers)
    ]


def render_glossary(report_html: str) -> str:
    """Render the content-aware glossary appendix as an HTML fragment.

    Scans ``report_html`` (the joined body of every other section) and emits
    definitions only for the terms found, grouped by family in the fixed
    statistical → methodological → domain order. The section header is always
    present (RT12); when no master term is detected it renders a short note
    rather than an empty block.
    """
    present = collect_terms(report_html)
    blocks = [
        "<section class='chapter-break glossary'>",
        "<h2>Glossary</h2>",
        "<p><em>Plain-language definitions of the terms used in this "
        "report.</em></p>",
    ]
    if not present:
        blocks.append("<p>No glossary terms were used in this report.</p>")
        blocks.append("</section>")
        return "\n".join(blocks)

    by_family: dict[str, list[_Term]] = {}
    for term in present:
        by_family.setdefault(term.family, []).append(term)

    for family_key, family_label in _FAMILY_ORDER:
        terms = by_family.get(family_key)
        if not terms:
            continue
        blocks.append(f"<h3>{html.escape(family_label)}</h3>")
        blocks.append("<dl class='glossary-list'>")
        for term in terms:
            blocks.append(
                f"<dt>{html.escape(term.term)}</dt>"
                f"<dd>{html.escape(term.definition)}</dd>"
            )
        blocks.append("</dl>")
    blocks.append("</section>")
    return "\n".join(blocks)
