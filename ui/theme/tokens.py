"""Design tokens — single source of truth for GSCO visual style.

All values measured from app.cambridge-gsco.co.uk via Chrome DevTools MCP.
Last verified: 2026-05-25. Do not edit without re-measuring; see STYLE_GUIDE.md
for the re-verification prompts.
"""

# --------------------------------------------------------------------------
# Colors — every hex / rgba string used by the theme. Keep names stable;
# downstream callers (theme.py, card.py, nav.py) read by key.
# --------------------------------------------------------------------------
COLORS = {
    # Surfaces
    "body_bg": "#060a12",                          # rgb(6, 10, 18)
    "card_bg": "rgba(255, 255, 255, 0.016)",       # barely-elevated wash
    "card_border": "rgba(123, 195, 66, 0.12)",     # green-tinted, all cards

    # Text
    "text_primary": "#ffffff",
    "text_secondary": "rgba(255, 255, 255, 0.55)",
    "text_muted": "rgba(255, 255, 255, 0.35)",

    # Brand accents
    "accent_green": "#7bc342",                     # rgb(123, 195, 66)
    "accent_cyan": "#0bbab0",                      # rgb(11, 186, 176)

    # Button chrome
    "button_secondary_border": "rgba(123, 195, 66, 0.35)",

    # Streamlit's "secondaryBackgroundColor" — used by widgets like
    # st.selectbox, expanders, etc. Picked one step above body bg so
    # those widgets read as faintly elevated against the page.
    "surface_elevated": "#0d1422",
}

# --------------------------------------------------------------------------
# Fonts — loaded from Google Fonts via @import in theme.py.
# Instrument Serif ships at weight 400 only (designed to look heavy regular).
# DM Sans is loaded at 400 / 500 / 600 / 700.
# --------------------------------------------------------------------------
FONTS = {
    "serif_display": "'Instrument Serif', serif",
    "sans_body": "'DM Sans', sans-serif",
}

# --------------------------------------------------------------------------
# Type scale — measured in px on the reference site at default zoom.
# Where the reference uses rem, the px equivalent (at 16px root) is given.
# --------------------------------------------------------------------------
TYPE_SCALE = {
    "hero":    {"size": "66px",    "weight": 400, "family": FONTS["serif_display"]},
    "body":    {"size": "1.08rem", "weight": 400, "family": FONTS["sans_body"]},      # 17.28px
    "button":  {"size": "0.9rem",  "weight": 600, "family": FONTS["sans_body"]},      # 14.4px
    "caption": {"size": "0.67rem", "weight": 400, "family": FONTS["sans_body"]},      # 10.72px
    "icon":    {"size": "1.5rem",  "weight": 400, "family": FONTS["sans_body"]},      # 24px
}

# --------------------------------------------------------------------------
# Radii (in CSS px). Buttons are slightly tighter than cards on the
# reference site (4 vs 6).
# --------------------------------------------------------------------------
RADIUS = {
    "button": 4,
    "card": 6,
}

# --------------------------------------------------------------------------
# Card chrome — identical on every feature card on the reference site
# regardless of icon color. card.py reads all four values from here.
# No box-shadow, no filter, no glow (confirmed via MCP).
# --------------------------------------------------------------------------
CARD = {
    "bg": COLORS["card_bg"],
    "border": f"1px solid {COLORS['card_border']}",
    "radius": f"{RADIUS['card']}px",
    "padding": "2rem",   # 32px @ 16px root
}

# --------------------------------------------------------------------------
# Primary gradient + drop shadow — used on the Explore-style CTA.
# --------------------------------------------------------------------------
GRADIENT_PRIMARY = f"linear-gradient(135deg, {COLORS['accent_green']}, {COLORS['accent_cyan']})"
SHADOW_BUTTON = "0 4px 24px rgba(123, 195, 66, 0.25)"
