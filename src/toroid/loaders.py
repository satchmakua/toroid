"""Load a hand-written `PropertySet` from a JSON file (the `--no-llm` path, M1).

Thin file I/O over the pure domain model. The JSON shape mirrors `Property`:

    {"properties": [
        {"pid": "P1", "kind": "assert", "summary": "...", "expr": "...",
         "rationale": "...", "clocked": true, "origin": "human"}
    ]}

Keys beginning with "_" (e.g. "_comment") are ignored.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from toroid.domain.properties import Property, PropertyKind, PropertySet

_VALID_KINDS = {k.value for k in PropertyKind}


def property_from_dict(d: dict[str, Any]) -> Property:
    kind = str(d["kind"]).lower()
    if kind not in _VALID_KINDS:
        raise ValueError(
            f"property {d.get('pid')!r}: unknown kind {kind!r} "
            f"(expected one of {sorted(_VALID_KINDS)})"
        )
    return Property(
        pid=str(d["pid"]),
        kind=PropertyKind(kind),
        summary=str(d.get("summary", "")),
        expr=str(d["expr"]),
        rationale=str(d.get("rationale", "")),
        clocked=bool(d.get("clocked", True)),
        origin=d.get("origin", "human"),
    )


def property_to_dict(p: Property) -> dict[str, Any]:
    return {
        "pid": p.pid,
        "kind": p.kind.value,
        "summary": p.summary,
        "expr": p.expr,
        "rationale": p.rationale,
        "clocked": p.clocked,
        "origin": p.origin,
    }


def property_set_to_dict(pset: PropertySet) -> dict[str, Any]:
    """Serialize to the same JSON shape `load_property_set` reads — so a recorded
    (real) LLM synthesis becomes a replayable fixture."""
    return {"properties": [property_to_dict(p) for p in pset.properties]}


def load_property_set(path: Path) -> PropertySet:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = data.get("properties", [])
    if not isinstance(raw, list):
        raise ValueError(f"{path}: 'properties' must be a list")
    props = tuple(property_from_dict(p) for p in raw)
    pset = PropertySet(properties=props)
    if not pset.has_reachability_witness():
        raise ValueError(
            f"{path}: property set has asserts but no cover (anti-vacuity invariant; "
            "every assert needs a reachability witness — see DESIGN.md §4.4)"
        )
    return pset
