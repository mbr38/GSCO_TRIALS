# M-TIER-A3 — Plain-Language Explainer

**For:** non-engineering stakeholders, audit reviewers, demo viewers.
**Date:** 26 May 2026.
**Companion to:** the engineering record at `M-TIER-A3_closed_entry.md`.

---

## What changed

Before this milestone, the tool's coastal-site z-scores were systematically
wrong — *too high*. After this milestone, they're defensibly calibrated.

That's the whole story. The rest of this document explains why it was
broken, what we changed to fix it, and how to read the new outputs.

---

## What was broken

The platform measures pollution at a supplier by comparing the supplier
site to the area around it. Specifically:

1. The **site buffer** is a small circle around the supplier coordinates
   (typically 5–25 km). Pollution measurements over this circle become
   the "site value."
2. The **background ring** is a larger ring around the supplier (out to
   200 km). The pollution baseline — what's normal for the surrounding
   region — comes from this ring.
3. The supplier's anomaly score is `site − background ÷ standard deviation`.
   When the supplier is well above the background, the score is high.

This works fine inland. But for a coastal supplier — say, a Mumbai port —
the background ring extends *over the Arabian Sea*. The ring's "baseline"
ends up averaging:

- Terrestrial pixels (suburbs of Mumbai, normal urban pollution)
- **Ocean pixels (essentially clean marine air, near-zero NO₂)**

The ocean pixels drag the baseline down. Now the supplier looks anomalous
not because it's actually polluting unusually heavily, but because the
ocean is making the comparison unfair. **Every coastal supplier in the
demo set — Mumbai, Rio de Janeiro, Shenzhen, Houston — looked like it
was severely polluting**, regardless of whether it actually was.

This was the most visible methodological flaw in the v1 demo. The team
captioned it in the UI ("ring partly over water") but the underlying
score was still wrong.

## What we changed

We added a **land mask** to the background ring.

The land mask is a global map at 250 m resolution that says, for every
pixel on Earth, whether it's land or water. We use **MOD44W v6**, a
NASA-curated satellite-derived water mask, accessed live from Google
Earth Engine.

Before computing the background pollution baseline, the tool now:

1. Takes the background ring (the annulus around the supplier).
2. Intersects it with the land mask, dropping every pixel that the mask
   says is water.
3. Computes the median pollution + standard deviation over only the
   *terrestrial* portion of the ring.

The supplier site buffer is **not** masked — supplier coordinates are
assumed to be on land by the upstream scope-setup logic, and coastal
facilities like port refineries intentionally measure their on-water
operations.

## How to read the new output

Three new signals are visible to readers of the output.

**1. Confidence breakdown ("What's behind this confidence?" expander).**
For coastal sites, this expander now contains a "Coastal handling"
sub-section that says, for example:

> This site is near water. The surrounding comparison area (the
> "background ring") overlaps the coastline, so **48%** of it is ocean.
> The tool excludes those ocean pixels from the comparison, leaving the
> remaining **52%** of land to serve as the baseline.

For fully inland sites (Sapezal, Brasília) the sub-section is absent —
no ocean to handle.

**2. Indicator Library cards (P-09).** Each ring-based pollutant card
(NO₂, SO₂, CO, HCHO, AAI, O₃, AOD, CH₄, CO₂) now carries a static
"Coastal sites" methodology paragraph explaining the mask. This is
educational reading material; it doesn't depend on a specific screening
run.

**3. PDF audit appendix.** Reports that include any coastal indicator
now carry a "Coastal AOI handling" appendix sub-block listing which
indicators were affected and what the land vs water split was.

**4. (Engineering) Provenance.** Every ring-based indicator's
`provenance.extra` block now carries three new fields:

- `ring_land_fraction` — the geometric land share, 0.0 to 1.0
- `land_mask_applied` — whether the mask was applied (true in v1.x)
- `land_mask_asset` — the MOD44W asset ID, for vintage tracking

## Real-world calibration

For the demo set, the land fractions are:

| Site | Land fraction |
|------|---------------|
| Sapezal (deep Amazon interior) | **0.9999** — effectively all land |
| Brasília | **0.9950** — almost all land (small reservoirs) |
| Rio de Janeiro | **0.5708** — about 57% land, 43% Atlantic |
| Mumbai port | **0.5240** — about 52% land, 48% Arabian Sea |
| Shenzhen | **0.5853** — about 59% land, 41% South China Sea |

For Sapezal and Brasília the milestone is a no-op: the mask drops only
the few water pixels that fell across small reservoirs, and the
baseline value stays bit-identical to within rounding error.

For Mumbai, Rio, and Shenzhen, the baseline is now correctly
calculated from the terrestrial portion of the ring. The Mumbai CH₄
z-score post-milestone is **0.288** (defensibly small for an urban
coastal site) — what it would have been pre-milestone is left as an
exercise for the reader, but the spec's failure mode was specifically
"pathological z-scores" at these sites.

## What this does NOT fix

**Sparse-coverage AOIs (tropical / polar).** Some inland AOIs — e.g.
deep Amazon during the monsoon — have a background ring that's mostly
cloudy or has too few satellite overpasses to compute a meaningful
baseline. For these cases, the land mask doesn't help; the ring simply
doesn't have usable data. These continue to skip through the existing
"sparse coverage" methodology message.

The future fix here is **M-CLIM-A3b**, a per-region climatology
fallback. When the ring is empty (whether because of ocean or sparse
coverage), the tool will substitute a pre-computed regional median
for the same pollutant in the same country. The provenance fields we
ship today (`land_mask_applied`, `ring_land_fraction`) are designed
so M-CLIM-A3b can read them to decide *why* a ring is empty and
choose the right fallback. M-CLIM-A3b is a v1.x-late milestone — it
needs one climatology fixture per pollutant × per country and a
vintage story for the fallback values.

**Tiny coastal facilities.** Very small AOIs (say, a 5 km buffer) on
a narrow coastal strip will still struggle: the geometric land
fraction can fall below the 5% floor that the engine uses to draw the
"ring is effectively water-only" line. Below that floor the indicator
skips through the same methodology message as before. This is rare
in the demo set but worth knowing about.

**Mask vintage.** MOD44W v6 is a static product last refreshed around
2015. Coastline drift across ten years is small compared to the 250 m
mask resolution, but reservoir-creation projects (Jakarta Bay, Dubai
artificial islands) won't be reflected. If this becomes a problem in
production deployments, swapping to a more recent mask is a one-line
change in [engine/core/buffers.py](engine/core/buffers.py).

## Quick FAQ

**Q. Did the scores for inland suppliers change?**
Within rounding error, no. The mask drops a vanishingly small fraction
of pixels (Sapezal: 0.01%, Brasília: 0.5%). The shipped saved-analysis
fixtures for inland AOIs are bit-identical in spirit; small drifts
visible in the diff are unrelated (Sentinel-5P data ingestion progress,
plus an unrelated optimization that landed between the previous fixture
and the M-TIER-A3 regen).

**Q. Why MOD44W specifically?**
It's a single global asset, cheap to query (250 m, ~500 ms per ring),
and known-stable. The next-finer option (ESA WorldCover at 10 m) would
catch narrow coastal strips that MOD44W misses, but at significant cost
per screening. We can swap to WorldCover later if narrow-coastal sites
become a real problem in production.

**Q. Does this affect the confidence formula?**
No. The land mask changes *which pixels go into the background
reduction*, not the math afterward. The four M-TIER-A1 confidence terms
(QA, observation coverage, anomaly strength, pixel/buffer match) are
unchanged. Audit reviewers comparing confidence values pre- and
post-milestone should see them stable.

**Q. Can the supplier site buffer be over water?**
Yes — it's deliberately not masked. A port refinery's site buffer
includes its dockside operations, which are partly over water by
design. Only the *background ring* (the comparison area) is masked.

**Q. What was the spec called?**
M-TIER-A3, Tier A item 3 in the Indicators Audit and v1.x Roadmap. Other
Tier A items: M-TIER-A1 (per-indicator confidence formula — shipped),
M-TIER-A2 (multi-year trend engine — pending).

## Want more detail?

- [M-TIER-A3_spec.md](../M-TIER-A3_spec.md) — the engineering spec the milestone implemented (locks LM1-LM11, test plan, execution sequence)
- [M-TIER-A3_closed_entry.md](M-TIER-A3_closed_entry.md) — the engineering record of what shipped, with file/line citations for every lock and a record of all spec/repo deviations
- [Indicators_Audit_and_v1x_Roadmap.md](Indicators_Audit_and_v1x_Roadmap.md) — the master authority document; M-TIER-A3 closes the §1.3 Option 1 item
- [Indicators_Computation_v4.md](Indicators_Computation_v4.md) §6.3 — the canonical methodology note for coastal handling, now reflecting the land mask
