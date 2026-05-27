# M-UI-A5 — Plain-language explainer

**What shipped.** The screening results page (P-05) now has an interactive
**map** that shows where each environmental signal sits on the ground.

## The one-sentence version

> Click any indicator's **"View on map →"** link, and the page scrolls to a
> satellite map showing that indicator's spatial pattern across your site.

## What you see

When a screening finishes, the results page shows a row of indicator tiles
(NO₂, methane, vegetation, biodiversity areas, and so on). Below those tiles
there is now a map.

- **At first, the map is empty** — it shows the satellite view of your area
  with a red ring marking the buffer you screened and a marker at the centre.
  A small prompt tells you to click an indicator to see its data.
- **Click "View on map →"** on any tile, and that indicator's data paints onto
  the map: a heat-map of air pollution, methane, or night-time activity; the
  vegetation field; or the boundaries of nearby protected biodiversity areas.
- **Click a different tile's link**, and the map switches to that indicator.
- **Click "✕ Close map"** (top-right) to go back to the empty satellite view.

Each map comes with a short plain-English caption explaining what the colours
mean — for example, warm colours mark pixels with above-typical pollution for
your area, and the scale is the same across indicators so they're comparable.

## Which indicators have maps

All **14 scored indicators**: the nine air pollutants (NO₂, SO₂, CO, HCHO,
O₃, AAI, PM₂.₅, PM₁₀, aerosol optical depth), methane and night-time lights,
nearby Key Biodiversity Areas, land cover, and vegetation (NDVI).

Two **reference datasets** — Hansen forest loss and ODIAC CO₂ — are
intentionally left off the map for now. They're context layers rather than
scored signals; giving them their own map treatment is planned for a later
update.

## A couple of honest caveats

- **PM₂.₅ / PM₁₀** come from a global ~44 km weather-model grid, not a
  fine-grained satellite. At normal site sizes their map shows the regional
  haze field rather than street-level detail; the caption says so.
- **Vegetation (NDVI)** shows the raw greenness field. The tile next to it
  scores how *unusual* the greenness is versus the regional norm — the two are
  complementary: the tile says "vegetation is unusually low here", the map
  shows "here's how vegetation is distributed".

## Why it feels fast

The first time you open an indicator's map, the tool fetches the imagery from
Earth Engine. If you click back to the same indicator later in the session,
it reuses what it already fetched — no waiting. Running a brand-new screening
clears that memory so you never see stale imagery on fresh data.

## What this is *not* (yet)

- No time slider — each map is a single snapshot averaged over the screening
  window. Watching change over time is the Trend page's job.
- No hover-to-read-the-exact-value, no downloading the map as a file, no
  comparing two suppliers side by side. Those are deliberate later items.
