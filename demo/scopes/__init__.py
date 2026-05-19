"""Demo supply chains for MNC user-type screening (M-DEMO-DATA).

Loads the three hand-curated JSON files in this directory and exposes
them as typed dataclasses. Consumers:
- P-02 (scope setup) — pick which supply chain to load into session.
- P-04 (inspect setup) — Supplier tab pulls nodes from the loaded scope.
- P-07 (prioritisation setup) — batch screening over a scope's nodes.

JSON files are read once at module import and cached in memory. Bad
JSON fails loudly at app startup, not silently at first use.
"""

# M-DEMO-DATA
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final


@dataclass(frozen=True)
class SupplyChainNode:
    """One node in a supply chain."""

    id:    str
    name:  str
    tier:  str
    lat:   float
    lon:   float
    notes: str | None = None


@dataclass(frozen=True)
class SupplyChain:
    """A demo supply chain — name, industry, list of nodes."""

    id:       str
    name:     str
    industry: str
    country:  str
    nodes:    tuple[SupplyChainNode, ...]

    @classmethod
    def from_dict(cls, raw: dict) -> "SupplyChain":
        return cls(
            id=raw["id"],
            name=raw["name"],
            industry=raw["industry"],
            country=raw["country"],
            nodes=tuple(
                SupplyChainNode(
                    id=n["id"],
                    name=n["name"],
                    tier=n.get("tier", "—"),
                    lat=float(n["lat"]),
                    lon=float(n["lon"]),
                    notes=n.get("notes"),
                )
                for n in raw["nodes"]
            ),
        )


_SCOPES_DIR: Final[Path] = Path(__file__).parent


def _load_all() -> dict[str, SupplyChain]:
    """Read every ``*.json`` in this directory and parse to SupplyChain.

    Errors surface immediately — bad JSON should fail loudly at app
    startup rather than at first use deep inside the UI.
    """
    scopes: dict[str, SupplyChain] = {}
    for path in sorted(_SCOPES_DIR.glob("*.json")):
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        scope = SupplyChain.from_dict(raw)
        scopes[scope.id] = scope
    return scopes


# Module-level cache; populated on first import.
_SCOPES: dict[str, SupplyChain] = _load_all()


def all_scopes() -> tuple[SupplyChain, ...]:
    """Return every demo scope, sorted alphabetically by name."""
    return tuple(sorted(_SCOPES.values(), key=lambda s: s.name))


def get_scope(scope_id: str) -> SupplyChain | None:
    """Look up one scope by its canonical ID. ``None`` if not found."""
    return _SCOPES.get(scope_id)
