"""Loader for the analysis-window-picker profile fixture (M-UI-A3).

The fixture (``demo/window_picker_profiles.json``) is the single source
of truth for picker behaviour: preset chips, min/max bounds, validation
copy, and compute-estimate coefficients. The picker component reads
profiles from here so item 1.4's trend-window addition is a pure
fixture change (add a ``trend`` block) with no code edits.
"""

# M-UI-A3
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path


_PROFILES_JSON = Path(__file__).parent / "window_picker_profiles.json"


@dataclass(frozen=True)
class Preset:
    """One preset chip in the picker (e.g. ``30 d``, ``90 d``)."""
    key:   str
    label: str
    days:  int


@dataclass(frozen=True)
class ComputeEstimateCoefficients:
    """Tunable coefficients for the WP10 compute-estimate formula.

    Calibrated against the rule-of-thumb timing comments in the codebase,
    not against real benchmark data — see the fixture's
    ``coefficient_calibration_note`` for the source.
    """
    base_overhead_s:              float
    per_day_coef_s:               float
    complexity_small_max_km:      float
    complexity_medium_max_km:     float
    complexity_factor_small:      float
    complexity_factor_medium:     float
    complexity_factor_large:      float
    long_window_threshold_days:   int
    long_window_penalty_s:        float
    soft_warning_threshold_s:     float
    long_window_warning:          str


@dataclass(frozen=True)
class WindowProfile:
    """A single window-picker profile (e.g. ``screening``).

    Profiles parameterise the picker so the same component renders the
    screening-window UI on P-04 / P-07 today, and (in future item 1.4)
    the trend-window UI on P-06 by switching profile name.
    """
    name:                str
    label:               str
    default_preset:      str
    presets:             tuple[Preset, ...]
    min_days:            int
    max_days:            int
    validation_messages: dict[str, str]
    coefficients:        ComputeEstimateCoefficients

    def default_days(self) -> int:
        """Number of days for the profile's default preset."""
        for p in self.presets:
            if p.key == self.default_preset:
                return p.days
        # Defensive — fixture should always carry a matching preset.
        raise KeyError(
            f"Profile {self.name!r} default_preset={self.default_preset!r} "
            f"does not match any preset key."
        )


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------

@cache
def load_profile(name: str) -> WindowProfile:
    """Load a named profile from the JSON fixture.

    Raises ``KeyError`` if the profile doesn't exist — callers should
    only pass known profile names (``"screening"`` today, ``"trend"`` once
    item 1.4 lands).
    """
    raw = _load_raw()
    block = raw.get(name)
    if block is None:
        raise KeyError(
            f"Unknown window-picker profile {name!r}. "
            f"Defined profiles: {sorted(k for k in raw if not k.startswith('_'))}"
        )
    presets = tuple(
        Preset(key=p["key"], label=p["label"], days=int(p["days"]))
        for p in block["presets"]
    )
    coefs_raw = block["compute_estimate_coefficients"]
    coefs = ComputeEstimateCoefficients(
        base_overhead_s=float(coefs_raw["base_overhead_s"]),
        per_day_coef_s=float(coefs_raw["per_day_coef_s"]),
        complexity_small_max_km=float(coefs_raw["complexity_small_max_km"]),
        complexity_medium_max_km=float(coefs_raw["complexity_medium_max_km"]),
        complexity_factor_small=float(coefs_raw["complexity_factor_small"]),
        complexity_factor_medium=float(coefs_raw["complexity_factor_medium"]),
        complexity_factor_large=float(coefs_raw["complexity_factor_large"]),
        long_window_threshold_days=int(coefs_raw["long_window_threshold_days"]),
        long_window_penalty_s=float(coefs_raw["long_window_penalty_s"]),
        soft_warning_threshold_s=float(coefs_raw["soft_warning_threshold_s"]),
        long_window_warning=str(coefs_raw["long_window_warning"]),
    )
    return WindowProfile(
        name=name,
        label=block["label"],
        default_preset=block["default_preset"],
        presets=presets,
        min_days=int(block["min_days"]),
        max_days=int(block["max_days"]),
        validation_messages=dict(block["validation_messages"]),
        coefficients=coefs,
    )


def _load_raw() -> dict:
    return json.loads(_PROFILES_JSON.read_text())
