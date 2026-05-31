"""Canary tests — engine constants ↔ docs/Indicators_Computation_v4.md lockstep.

Catches drift between engine weight dicts and the IC_v4 doc that documents
them. Both are sources of truth: engine constants drive runtime behaviour,
IC_v4 drives auditor / reviewer understanding. When they disagree, follow
the M-V1x-RECONCILE verification protocol — if the engine is right, update
the doc; if the doc is right, file a milestone for the engine change.

Approach: tests parse the IC_v4 markdown by regex-extracting the numeric
weights from the documented formulas, then compare against the engine
constants. The expected formulas are pinned by line content so any future
edit to the doc that drops a term, changes a weight, or renames a sub-score
trips the test loudly.

Added by M-V1x-RECONCILE per the spec's §5 step 13.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from engine.constants import (
    CORE_GHG_AUDIT_SUPPORT_WEIGHTS,
    GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS,
    HABITAT_CONVERSION_WEIGHTS,
)


_IC_PATH = (
    Path(__file__).resolve().parent.parent
    / "docs" / "Indicators_Computation_v4.md"
)


def _ic_text() -> str:
    return _IC_PATH.read_text(encoding="utf-8")


def _approx_set(values: list[float]) -> list[float]:
    """Return a sorted list of values rounded to 2 dp for set-equality compare."""
    return sorted(round(v, 2) for v in values)


class TestDocConstantsSync:
    def test_ic_v4_habitat_conversion_weights_match_engine_constants(self) -> None:
        # Audit §9.3 v1.4: Hansen demoted, four DW-based terms summing to 1.00.
        text = _ic_text()
        # Find the Habitat_Conversion formula block.
        m = re.search(
            r"Habitat_Conversion =.*?\(sums to 1\.00\)",
            text, flags=re.DOTALL,
        )
        assert m is not None, "Could not find Habitat_Conversion formula block in IC_v4"
        block = m.group(0)
        # Pull every "0.NN·" coefficient out of the block.
        doc_weights = [float(x) for x in re.findall(r"(\d\.\d{2})·", block)]
        assert _approx_set(doc_weights) == _approx_set(
            list(HABITAT_CONVERSION_WEIGHTS.values())
        ), (
            f"Habitat_Conversion weights in IC_v4 §3.2 ({doc_weights}) drifted "
            f"from engine HABITAT_CONVERSION_WEIGHTS "
            f"({list(HABITAT_CONVERSION_WEIGHTS.values())})"
        )
        # And four terms after the Hansen demotion.
        assert len(doc_weights) == 4

    def test_ic_v4_ghg_dqa_weights_match_engine_constants(self) -> None:
        # IC §2.3: Sector_Match scrapped; Wind_Consistency deferred; four
        # remaining weights = 0.33 / 0.27 / 0.27 / 0.13.
        text = _ic_text()
        m = re.search(
            r"GHG_Data_Quality_Attribution_v1 =.*?\(sums to 1\.00\)",
            text, flags=re.DOTALL,
        )
        assert m is not None, "Could not find GHG_Data_Quality_Attribution_v1 block"
        block = m.group(0)
        doc_weights = [float(x) for x in re.findall(r"(\d\.\d{2})·", block)]
        assert _approx_set(doc_weights) == _approx_set(
            list(GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS.values())
        ), (
            f"GHG DQA weights in IC_v4 §2.3 ({doc_weights}) drifted from "
            f"engine GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS "
            f"({list(GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS.values())})"
        )

    def test_ic_v4_core_ghg_audit_support_weights_match_engine_constants(self) -> None:
        # M-GHG-REDESIGN-A1 (GATE B): 2-key dict, 0.60 / 0.40 (VIIRS-led).
        # Weights may be 2–3 dp, so the coefficient regex allows 2–3 dp.
        text = _ic_text()
        m = re.search(
            r"Core_GHG_Audit_Support_v1 =.*?\(sums to 1\.00\)",
            text, flags=re.DOTALL,
        )
        assert m is not None, "Could not find Core_GHG_Audit_Support_v1 block"
        block = m.group(0)
        doc_weights = [float(x) for x in re.findall(r"(\d\.\d{2,3})·", block)]
        assert _approx_set(doc_weights) == _approx_set(
            list(CORE_GHG_AUDIT_SUPPORT_WEIGHTS.values())
        ), (
            f"Core_GHG_Audit_Support weights in IC_v4 §2.3 ({doc_weights}) "
            f"drifted from engine CORE_GHG_AUDIT_SUPPORT_WEIGHTS "
            f"({list(CORE_GHG_AUDIT_SUPPORT_WEIGHTS.values())})"
        )
        # M-CH4-A1: two keys after ODIAC demotion + CH₄ reclassification.
        assert len(doc_weights) == 2
