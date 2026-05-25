# GSCO Tool — Style Guide

> Visual source of truth: **https://app.cambridge-gsco.co.uk**.
> This document captures the tokens, conventions, and re-verification
> prompts used to keep the Streamlit tool visually aligned with the
> parent platform.

## 1. Reference site

The Streamlit tool is a sub-module of the Cambridge Global Supply Chain
Observatory. Its visual layer (palette, type, card chrome, persistent
nav) must read as a clear sibling of the public platform at
`app.cambridge-gsco.co.uk`.

When in doubt, the live site wins — the tokens in
[`ui/theme/tokens.py`](ui/theme/tokens.py) are direct measurements, not
designer-chosen values.

## 2. Locked tokens (measured 2026-05-25)

All values pulled from `app.cambridge-gsco.co.uk` via Chrome DevTools
MCP. Update only after re-measuring (see §4).

### Colors

| Token | Value | Notes |
|---|---|---|
| `body_bg` | `#060a12` | near-black, applied to `<body>` |
| `card_bg` | `rgba(255, 255, 255, 0.016)` | barely-elevated wash |
| `text_primary` | `#ffffff` | white, applied on inner wrapper |
| `text_secondary` | `rgba(255, 255, 255, 0.55)` | subhead paragraphs |
| `text_muted` | `rgba(255, 255, 255, 0.35)` | stat labels |
| `accent_green` | `#7bc342` | primary brand |
| `accent_cyan` | `#0bbab0` | secondary brand |
| `card_border` | `rgba(123, 195, 66, 0.12)` | green-tinted on ALL cards |
| `button_secondary_border` | `rgba(123, 195, 66, 0.35)` | outlined buttons |

### Fonts

Both loaded from Google Fonts via `@import` in
[`ui/theme/theme.py`](ui/theme/theme.py).

- **Display serif** — `Instrument Serif`, weight 400 only (designed to
  read heavy at regular).
- **Body sans** — `DM Sans`, weights 400 / 500 / 600 / 700.

### Type scale (measured)

| Use | Size | Weight | Family |
|---|---|---|---|
| Hero heading | 66px | 400 | Instrument Serif |
| Body / subheading | 17.28px (1.08rem) | 400 | DM Sans |
| Button label | 14.4px (0.9rem) | 600 | DM Sans |
| Caption / stat label | 10.72px (0.67rem) | 400 | DM Sans |
| Card icon glyph | 24px (1.5rem) | regular | DM Sans |

### Card chrome (identical across all reference cards)

- Background: `rgba(255, 255, 255, 0.016)`
- Border: `1px solid rgba(123, 195, 66, 0.12)`
- Border-radius: 6px
- Padding: 32px (2rem)
- **No box-shadow, no filter, no glow** — confirmed via MCP.
- Icons are Unicode glyphs (`◉` green ring, `◎` cyan ring, `◈` cyan
  diamond), styled only by `color` and `font-size`.

### Primary button (gradient)

- Background: `linear-gradient(135deg, #7bc342, #0bbab0)`
- Box-shadow: `0 4px 24px rgba(123, 195, 66, 0.25)`
- Color: `#ffffff`
- Border-radius: 4px
- Padding: 14.4px 32px
- Font: DM Sans 14.4px / weight 600

### Secondary button (outlined)

- Background: transparent
- Color: `#7bc342`
- Border: `1px solid rgba(123, 195, 66, 0.35)`
- Same radius / padding / font as primary.

## 3. Module layout

**Running the app.** Use `streamlit run gsco_app.py` for the full app —
it's the navigation orchestrator that wires up all pages via `st.Page`
/ `st.navigation`. `streamlit run app.py` runs only the landing page
(P-01); useful for landing-specific work but bypasses the sidebar and
the rest of the pages.

The theme scaffolding lives under `ui/theme/`:

```
ui/theme/
├── __init__.py
├── tokens.py    # single source of truth — all values measured
├── theme.py     # apply_gsco_theme() — global CSS injector
├── card.py      # render_card / render_workflow_card
└── nav.py       # render_top_nav (uses streamlit-option-menu)
```

Pages reach the theme via:

```python
from ui.theme.theme import apply_gsco_theme
from ui.theme.card import render_card, render_workflow_card
from ui.theme.nav import render_top_nav
```

`apply_gsco_theme()` is injected once at the top of
[`gsco_app.py`](gsco_app.py) (the canonical `streamlit run` entry) and
once in [`app.py`](app.py) right after `st.set_page_config()` so the
landing page is themed when invoked directly. It is idempotent —
calling twice in the same rerun is harmless.

Streamlit's standard rerun model re-executes the entry-point script
`gsco_app.py` top-to-bottom on every user interaction (`st.navigation`
is a router, not an alternative execution model), so the top-level
`apply_gsco_theme()` call themes every page render automatically. New
page modules do not need to import or call `apply_gsco_theme()` —
adding them to the `st.Page(...)` list in `gsco_app.py` is sufficient.

## 4. How to re-measure (MCP re-verification prompts)

Use these verbatim against a running Chrome DevTools MCP session:

> **Prompt 1 — base tokens.** "Open `https://app.cambridge-gsco.co.uk`
> in Chrome. For body, the 'made visible' heading, the subheading
> paragraph, the 'Explore the Observatory' button, the 'View Research
> Domains' button, the persistent header bar, and the bottom-row stat
> labels, return `background-color`, `color`, `font-family`,
> `font-size`, `font-weight`, `border`, `border-radius`, `padding`.
> Output as JSON."

> **Prompt 2 — gradients and cards.** "On the Explore the Observatory
> button, return `background-image`. On any feature card (Visibility /
> Traceability / Transparency), return `background-color`, `border`,
> `border-radius`, `padding`. On the green ring icon and cyan ring
> icon, return `color`, `filter`, `box-shadow`, `text-shadow`."

> **Prompt 3 — drift check (run periodically).** "Compare current
> tokens in `ui/theme/tokens.py` against live values from
> app.cambridge-gsco.co.uk. List any drift."

The site's hero auto-rotates between headlines — if the 'made visible'
heading isn't on screen when Prompt 1 fires, reload the page and run
immediately.

## 5. Deliberately NOT replicated

The following are scope-out for the Streamlit tool. Don't reintroduce
without an explicit design ask.

- **The 3D rotating globe** in the public hero.
- **The auto-rotating headline carousel.**
- **The marketing footer** with stakeholder logos.
- **Public-site stats counters** with their animated count-up.

## 6. Adding a new page

Add an `st.Page(...)` entry to `gsco_app.py`'s navigation list. The
theme is applied automatically — the page module itself does not need
to import or call `apply_gsco_theme()`, because `gsco_app.py` reruns
top-to-bottom on every interaction and re-injects the theme before the
selected page runs.

A typical themed page module looks like this — note the absence of any
theme import:

```python
import streamlit as st

# Streamlit's hard rule — page_config must be the first st.* call.
st.set_page_config(
    page_title="…",
    page_icon="…",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# (Optional) persistent top nav — for P-02..P-11 only. Not on P-01.
from ui.theme.nav import render_top_nav
new_page = render_top_nav(
    active_page="P-09",          # one of P-09, P-10, P-11
    scope_name=st.session_state.get("scope_name"),
    user_type=st.session_state.get("user_type_label"),
)
if new_page == "P-09":
    st.switch_page("pages/09_Indicator_Library.py")
# … etc.

# Render cards via the helpers:
from ui.theme.card import render_card
render_card(
    title="Visibility",
    body="Map complex multi-tier supplier networks automatically.",
    icon="◉",
    accent="green",
)
```

Wiring `render_top_nav` into actual page files is a follow-up to the
current pass — the function is importable and tested in isolation, but
no production page has adopted it yet.
