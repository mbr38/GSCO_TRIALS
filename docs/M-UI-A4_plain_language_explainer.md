# M-UI-A4 — What changed on the Screening Results page (plain-language)

**Date.** 27 May 2026. **Audience.** Stakeholders / supervisors / demo viewers.

## The one-line version

The Screening Results page (P-05) now opens with an **Indicator snapshot**
that answers "what's actually concerning about this supplier?" at a glance —
each indicator shows *how unusual* it is and a colour-coded severity word,
and only the concerning ones show by default.

## What it looked like before

A flat 12-tile grid of air and GHG indicators. Each tile showed the raw site
value (e.g. "NO₂ — 215 µmol m⁻²") with a small up/down arrow. To judge whether
a number was *bad*, you had to already know what "normal" looks like for that
pollutant. The Nature pillar (biodiversity, forest loss, land cover,
vegetation) had no tiles at all — it was buried in a drill-down.

## What it looks like now

**1. The headline is the anomaly, not the raw number.** Each atmospheric tile
leads with a big z-score — e.g. "**+2.3σ**, above regional baseline" — which
says how far the site sits from its surroundings. The raw value is still
there, demoted to a secondary line. Nature tiles lead with their natural
metric: kilometres to the nearest Key Biodiversity Area, dominant land-cover
class, vegetation deviation.

**2. A severity word + coloured dot on every tile.** "High" (red), "Concern"
(amber), "Normal" (green outline), or "Sparse data" (grey, when there isn't
enough good data to judge). The severity is computed in the app from the data
already on screen — there's no hidden engine score deciding it.

**3. The Nature pillar is now in the headline.** Biodiversity proximity (KBA),
Dynamic World land cover, and NDVI vegetation deviation all get tiles, so all
three pillars get equal billing. The old Nature drill-down became a "Nature
details" deep-dive for the supporting numbers. (Hansen forest loss and ODIAC
CO₂ stay in that deep-dive as *reference datasets* — they describe long-run
context rather than a live screening signal, so they're shown but not scored
as severity tiles.)

**4. Only the concerning tiles show by default.** The snapshot shows the
critical indicators (High / Concern); a "Show all indicators" expander reveals
everything else. A header makes the filtering honest: *"Indicator snapshot —
2 critical of 14 screened."* If nothing is critical, the snapshot still shows
the three most-notable indicators so the section is never empty.

**5. A "View on map →" link on every tile.** For now it points at a
placeholder ("Multi-indicator map view — landing in the next release"); the
real map arrives in the next milestone (2.3b).

## What did *not* change

- The confidence dots, the click-the-name-for-an-explanation popovers, the
  failed-indicator handling, and the partial-coverage banner all work exactly
  as before.
- The engine didn't change how it computes anything. The one tiny addition was
  *surfacing* a value the engine already computed for nighttime-lights (its
  anomaly z-score) so it could join the severity tiles.
- The composite score and the PDF report are unchanged — the redesign is the
  in-app P-05 view for now.

## One honest caveat

The severity thresholds (what counts as "High" vs "Concern") are sensible
first-pass defaults, not yet calibrated against external benchmarks. They're
easy to tune and a calibration pass against the demo sites is a planned
follow-up.
