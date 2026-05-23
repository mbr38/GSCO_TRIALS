# How the Tool Learned to Say "I'm Not Sure"

*A plain-language story of the M-TIER-A1 milestone*

---

## The big picture

Imagine you have a friend who looks at the world from outer space and tells you about places on Earth. Your friend uses cameras on satellites — like Google Earth, but smarter. They can tell you things like:

- "There's a lot of pollution near this factory in Brazil."
- "The forest near this farm has been getting smaller."
- "The air over this region has more methane than usual."

Now imagine you're a company that buys soy from that Brazilian farm. You want to know: *can I trust what my satellite-friend is telling me?* Because if they're wrong, you might make a bad decision — like accusing a good farm of being polluting, or trusting a bad farm that secretly is.

So you ask your friend: "How sure are you?"

This is the story of how we taught our tool to honestly answer that question.

---

## Where we started: the tool that always said "I'm very sure"

When the tool was first built, every time it told you something, it would say "I'm 80% sure" or "I'm 100% sure" — but those numbers were **made up**. They were placeholders. The tool wasn't actually checking anything; it was just printing a polite-sounding number.

It's like asking a child "did you brush your teeth?" and they always say "yes" — even on days they didn't. The answer means nothing.

This was OK while we were building the rest of the tool, but eventually we had to make those numbers **real**. That's what M-TIER-A1 was about.

---

## What "being sure" actually means

When your satellite-friend looks at a place, four things can make them more or less sure of what they see:

### 1. Quality (QA)
*How good was the camera that day?*

Satellites have built-in quality checks. Some pictures are crisp; some are blurry or have weird sensor errors. We give each picture a score from 0 (terrible) to 1 (perfect).

**Like:** taking 10 photos with your phone. If 8 came out crisp and 2 came out blurry, your "quality score" is 0.8.

### 2. How many times we looked (N_valid)
*Did we see the place on lots of days, or just once?*

Looking at a place once is like glimpsing it. Looking at it 30 times over 3 months is like really getting to know it.

**Like:** if you want to know what your friend is like, talking to them for 30 days tells you more than meeting them once. If we expected 30 visits but only got 5 — score = 5/30 ≈ 0.17. If we got all 30 — score = 1.0.

### 3. How strong the signal was (anomaly_strength)
*When we did see something, was it a clear "uh oh!" or was it borderline?*

If on most of the days we looked, the place looked notably different from its surroundings — that's a strong signal. If only a few days were borderline — that's weak.

**Like:** if you suspect your neighbour is having a loud party, hearing music on 7 out of 10 nights is a strong signal. Hearing music on 1 out of 10 nights is a weak signal — could be your imagination.

### 4. How well the picture fits the place (spatial_context)
*Was the camera zoomed in close enough to actually see the place?*

Satellites have "pixels" — like the tiny dots that make up a phone screen. Some satellites have small pixels (zoomed in, can see a single building); some have huge pixels (each dot is 7 kilometres wide, can only see a whole town).

If you're trying to look at a single farm but each pixel covers an area bigger than the farm itself, your "view" isn't really of the farm — it's of the farm plus a lot of other stuff.

**Like:** if you want to know what's on your friend's plate at dinner but you can only see their whole house from the window, your view is fuzzy. If you're sitting at the table next to them, your view is sharp.

---

## The recipe

We mix these four ingredients together to get one "confidence" number, like this:

```
Confidence = (0.30 × Quality)
           + (0.30 × Times-we-looked)
           + (0.25 × Signal-strength)
           + (0.15 × Picture-fit)
```

The numbers in front (0.30, 0.30, 0.25, 0.15) say how important each ingredient is. They add up to 1.0, so the final answer is always between 0 (no confidence at all) and 1 (totally confident).

**Why those numbers?** We thought "quality" and "how many times we looked" matter most, so they each get 30%. The strength of the signal matters too but a little less — 25%. The pixel-size thing matters but is the least important — 15%.

We can change these numbers later if it turns out one ingredient matters more than we thought.

---

## A special honesty rule for certain gases

Here's an interesting wrinkle. Satellites measure pollution by looking at the **whole column of air** between the ground and space — not just the air down where people breathe. This works great for some gases and poorly for others.

| Gas | How well the column tells us about ground-level air | Honesty multiplier |
|---|---|---|
| NO₂ (car exhaust, factories) | Pretty good | × 0.95 |
| SO₂ (heavy industry, coal) | Slightly less good | × 0.88 |
| CO (combustion, fires) | Not great — CO drifts around for months | × 0.80 |
| CH₄ (methane, livestock, landfills) | Not great — methane lives for years | × 0.80 |
| HCHO (chemical activity) | Pretty good | × 0.95 |

So even on a perfect day with perfect data, **CO confidence can never go above 0.80**, because the very nature of the measurement is uncertain. NO₂ can go up to 0.95.

**Like:** even if you take a great photo with your phone (quality = 1.0) of a person standing 500 metres away, you can't see their face clearly — the situation has a limit. Some satellite measurements are like that.

This is the **honesty multiplier**. It gets applied to the final confidence as a discount.

---

## The first big surprise: a hidden bug

When we ran the new formula at our two demo locations — Sapezal Plantation (a soy farm in the Brazilian Amazon) and Distrito Federal (Brazil's capital region) — something looked weird.

Two specific measurements kept coming back as **"zero observations"** — meaning the tool was saying "I never saw this place at all." This was for:

- **AOD** (a measurement of dust and smoke in the atmosphere)
- **CH₄** (methane)

That made no sense. The satellites pass over Brazil every day. How could we have zero observations in 90 days?

### Investigation 1: Maybe the data is just bad?

We ran a test at a control site (Rotterdam, Netherlands — clearer skies, fewer clouds) to see if it was just a Brazilian-weather problem. The result was strange: **Rotterdam also showed almost zero observations.** That ruled out "wet-season Brazilian clouds" as the main cause.

### Investigation 2: Looking deeper

We dug into the code and found something embarrassing: the tool had a rule that said *"only look at the first 100 satellite images."* This was a safety limit to prevent the computer from getting overwhelmed.

For most measurements (like NO₂), this is fine — Brazil gets about 1 satellite image per day, so 100 images covers ~100 days. But some satellites work differently:

- **AOD (MAIAC)**: Brazil gets **~58 swath images per day**. So "first 100 images" covers... **1.7 days** of the 90-day window. The tool was checking less than 2 days of the 90-day window we'd asked for.
- **CH₄**: Brazil gets ~14 images per day. So "first 100" covers ~7 days.

**Like:** imagine you want to know the weather over a whole summer, but you only check the weather on the first two days of June. Of course you'd miss most of summer's weather. The tool was effectively doing this.

We fixed this by removing the limit and processing all images.

---

## The second surprise: counting the wrong thing

After removing the limit, AOD at Brasilia jumped from "zero observations" to **107 observations**. Hooray! Except... we then realised we were counting the wrong unit.

Remember, AOD gets 58 swath images per day. So "107 observations" really meant "107 swath segments, spread across about 2 days." We were counting **camera clicks**, not **distinct days when we saw the place**.

This matters because:

- The formula asks "how many times did we see the place?" — and that should mean "how many days," not "how many camera clicks."
- 107 camera clicks across 2 days is much less information than 60 camera clicks across 60 days. The 60-day version covers the whole season; the 2-day version misses the rest.

**Like:** taking 100 photos of your friend on their birthday tells you what they wore that day. Taking 30 photos of them across 30 different days tells you much more about how they live.

So we fixed the tool to **count distinct days**, not images.

---

## The third surprise: the computer ran out of memory and time

When we removed the 100-image limit, the tool tried to process **all 5,218 AOD images** for a single screening. This took so long that Google's computer (where the calculations happen) gave up after 5 minutes and showed an error.

We fixed this by:

1. **Combining all images from the same day** into one "average image" first. So 58 images from one day become 1 daily image. This cuts the workload from 5,218 images down to ~90 daily images — a 58× reduction.
2. **Splitting the 90-day window into 9 chunks of 10 days each**, doing each chunk separately, then combining the answers in Python. This keeps each individual calculation small enough that Google's computer doesn't time out.

After these fixes, the same screening that used to take 5+ minutes (and fail) now takes about 10 seconds.

---

## The results we ended up with

After all the fixes, here's what the tool now actually reports for our two demo locations:

### Brasilia (Brazil's capital region — control "low-pollution" demo)

| Measurement | Days we saw it | Confidence |
|---|---|---|
| AOD | 64 out of ~90 | **0.72** (good) |
| CH₄ | 4 out of ~90 | **0.36** (low — methane retrieval is hard in cloudy weather) |

### Rotterdam (clearer skies, control site)

| Measurement | Days we saw it | Confidence |
|---|---|---|
| AOD | 70 out of ~90 | **0.72** (good) |
| CH₄ | 27 out of ~90 | **0.56** (better than Brasilia, as expected) |

The pattern makes sense:
- **AOD confidence is similar at both sites** (0.72) because the formula saturates — once you have enough days, more days doesn't help.
- **CH₄ confidence is much higher at Rotterdam** (0.56 vs 0.36) because Rotterdam had many more clear-sky CH₄ retrievals.
- **CH₄ is lower than AOD at both sites** because of the honesty multiplier (× 0.80) — methane column measurements are intrinsically less reliable.

This is the tool finally being honest in a useful way. It's not just saying "I'm 80% sure" anymore — it's saying:

> *"I saw AOD on 64 days, which is solid coverage, so my AOD confidence is good. I only saw CH₄ on 4 days because of cloud cover, and methane is hard to measure from a column anyway, so my CH₄ confidence is fairly low. Combine these honestly."*

---

## Why this whole story mattered

Before this milestone, if you'd asked the tool "how confident are you about pollution levels at this Brazilian farm?", it would have said **"80%"** for every farm, every time, every measurement. Always the same answer. The number was decorative.

After this milestone:

- Confidence varies meaningfully between places (Rotterdam vs Brasilia)
- Confidence varies meaningfully between measurements (AOD vs CH₄)
- Confidence reflects **actual** data quality, not a made-up placeholder
- Some indicators honestly admit "I have no data here" instead of pretending
- When data really is missing, the tool says so instead of hiding it
- The methodology is **defensible** — we can show an auditor exactly how each confidence number was calculated

This is what makes the tool trustworthy. It's no longer a tool that always says "yes" to "did you brush your teeth?" — it's a tool that says "yes, fully" or "yes, but only on the front teeth" or "no, I didn't have time today," depending on the truth.

---

## What's still left

This story isn't quite finished. The next step is to **re-run the tool for our two demo sites** (Sapezal Plantation and Distrito Federal), look at the full confidence numbers for every measurement, and check that:

- High-pollution sites get appropriately high "concern" scores
- Low-pollution sites get appropriately low "concern" scores
- Confidence values are sensibly distributed (not all 0.95, not all 0.3)
- The verbal summary tool produces sensible English text about each site

If all of this looks right, the milestone is officially closed and we move on to the next thing (the **trend engine** — teaching the tool to spot whether things are getting better or worse over time).

---

## Glossary

- **AOD** — Aerosol Optical Depth. How much dust, smoke and haze is in the air.
- **CH₄** — Methane. A greenhouse gas mostly from livestock, landfills, gas leaks.
- **Column measurement** — Looking at the whole air between the ground and space, not just ground-level. Some gases are easier to interpret this way than others.
- **Confidence** — A number between 0 and 1 saying how much we trust a measurement. Higher = more trustworthy.
- **HF (Hotspot Frequency)** — Fraction of days when the place looked notably different from its surroundings.
- **MAIAC** — A specific way of processing satellite images to get AOD. The one we use.
- **N_valid** — How many days we actually got usable data for, divided by how many we expected.
- **QA (Quality)** — The satellite's own check on whether the data is clean.
- **Sentinel-5P (S5P)** — A European satellite that measures atmospheric gases (NO₂, SO₂, CO, CH₄, etc.).
- **TROPOMI** — The instrument on Sentinel-5P that does the measuring.
- **Z-score** — How many "standard deviations" away from normal a measurement is. A high Z means very unusual.

---

*Written in plain language to accompany the M-TIER-A1 technical documentation. For the technical details, see `docs/M-TIER-A1_spec.md` and `engine/core/confidence.py`.*

*Updated 23 May 2026, after Step 8 recalibration and the daily-mosaic / chunked-compute fix.*
