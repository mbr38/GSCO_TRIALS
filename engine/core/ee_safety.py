"""Server-side guards against the empty-collection band-less-image crash.

The failure mode this module defends against
--------------------------------------------
An ``ee.ImageCollection`` is filtered (``.filterDate(...).filterBounds(...)``)
and then reduced to a single image with an aggregation (``.mean()``,
``.mode()``, ``.median()``, ``.min()``, ``.max()``, ``.sum()``, ...). When the
filtered collection is **empty**, that aggregation returns a **band-less image
(0 bands)**. A subsequent **per-pixel band-wise operation** —
``.lt() / .gt() / .lte() / .gte() / .eq() / .neq() / .remap() / .And() /
.Or() / .where() / .expression()`` etc. — then throws a raw ``ee.EEException``
at ``.getInfo()`` time::

    Image.lt: If one image has no bands, the other must also have no bands.
    Got 0 and 1.

That exception is NOT an ``IndicatorComputeError``, so the pillar dispatchers
do not catch it gracefully — it fails the whole indicator (or the whole
screening). It bit ``engine.nature._ndvi_low_area_pct`` when six_step's SPPY
fallback recovered an NDVI site over an earlier window but the secondary
low-area reduction re-filtered the *original* (empty) window.

``reduceRegion`` itself is safe on a band-less image (it returns ``{}``); only
*per-pixel* band ops throw. So the risk surface is exactly:
``<filtered collection>.<aggregate>()`` → ``<per-pixel band op>``.

Why a server-side guard (not ``.size().getInfo()``)
---------------------------------------------------
The obvious guard — ``if ic.size().getInfo() == 0: ...`` — costs an extra
``getInfo`` round-trip on the screening hot path. ``with_guaranteed_band``
performs the check **inside the existing computation graph** via
``ee.Algorithms.If(image.bandNames().size().gt(0), ...)``, so it adds **zero**
round-trips: the band-count test is evaluated as part of whatever
``getInfo`` the caller already issues.

Use this at every site that does ``collection.<aggregate>() → band op``.
"""

from __future__ import annotations

import ee


def with_guaranteed_band(image: ee.Image, band: str) -> ee.Image:
    """Return ``image`` guaranteed to carry at least one band named ``band``.

    Use this to wrap the output of an aggregation over a collection that may
    be empty, immediately before any per-pixel band-wise op (``.lt``, ``.gt``,
    ``.remap``, ``.eq``, ...). It prevents the ``"Image.xx: ... Got 0 and 1"``
    crash that a band-less aggregation triggers.

    Semantics:

    - **Non-empty source** (``image`` already has ≥ 1 band): returned
      unchanged — no reprojection, no value change. The wrap is a no-op on the
      data path; downstream band ops and ``reduceRegion`` behave identically.
    - **Empty source** (band-less ``image``): a single **fully-masked**
      constant band named ``band`` is substituted. It is well-typed (band
      count 1) so per-pixel ops no longer throw, but it carries **no data** —
      a downstream ``reduceRegion`` returns no value for ``band`` (→ ``None``).
      That is the honest no-data outcome; callers map it to their existing
      missing-value handling rather than crashing or fabricating a default.

    Server-side only — **zero** ``getInfo`` round-trips. The band-count test
    runs inside the caller's existing computation graph.

    Args:
        image: an ``ee.Image`` that may be band-less (e.g. ``ic.mean()`` over a
            possibly-empty filtered collection).
        band: the band name to guarantee. For a no-data substitution it names
            the masked constant; pass the same band the downstream reduction /
            ``.get(...)`` expects so its key is present (and ``None``) on empty.

    Returns:
        An ``ee.Image`` that always has ≥ 1 band — the original when non-empty,
        a fully-masked single-band constant when empty.
    """
    masked = ee.Image.constant(0).rename(band).updateMask(ee.Image.constant(0))
    return ee.Image(
        ee.Algorithms.If(image.bandNames().size().gt(0), image, masked)
    )
