"""Demo seeded saved analyses (M-P10).

At app startup, ``seed_saved_analyses(session_state)`` is called once
per session. If the saved_analyses list is empty (cold start),
seeds it with the two demo JSON files committed alongside this module.
If the list already has entries (user added saves in this session),
it's a no-op — we don't overwrite user data.

The JSON files are real engine results captured once, then committed.
Generation is a manual demo-prep step (Phase 2 of M-P10):

  1. Boot the app and run a screening that produces the desired signal.
  2. P-05 → click "Save as report".
  3. Navigate to P-10, click "Export JSON" on the new entry.
  4. Replace the matching seed file in this directory with the export.

Until Phase 2 lands, the seed files are minimal stubs — P-10 will render
them as broken entries with helpful messaging on Open.
"""

# M-P10
from __future__ import annotations

import json
from pathlib import Path


_SEED_DIR = Path(__file__).parent

# M-P10-POLISH — flag tracking whether this session has already been
# seeded. Survives intermediate mutations of ``saved_analyses`` (saves
# added, entries deleted), so a stray re-render of app.py can't clobber
# user data the way a "list-emptiness" guard could.
_SEED_FLAG_KEY = "saved_analyses_seeded"


def seed_saved_analyses(session_state) -> None:
    """Load the demo seed files into ``session_state.saved_analyses``.

    Idempotent — uses a flag in session_state to track whether this
    session has been seeded already, regardless of the current contents
    of ``saved_analyses``. Safe to call on every page render; fires only
    on cold session entry.

    M-P10-POLISH: switched from list-emptiness guard to flag-based.
    The list-emptiness check broke once the user could delete entries:
    deleting all stubs reset the guard, so the next app.py re-render
    would silently re-add them. The flag survives mutations and only
    resets when the whole session_state clears (sign-out / new tab).
    """
    if session_state.get(_SEED_FLAG_KEY):
        return  # Already seeded this session.

    seeded: list[dict] = []
    for seed_path in sorted(_SEED_DIR.glob("*.json")):
        with seed_path.open("r", encoding="utf-8") as f:
            seeded.append(json.load(f))

    # Defensive — if a save was somehow added before the seed fired
    # (shouldn't happen with the canonical app.py call site, but cheap
    # to handle), preserve it by appending after the seeded entries.
    existing = session_state.get("saved_analyses", []) or []
    session_state["saved_analyses"] = seeded + existing
    session_state[_SEED_FLAG_KEY] = True
