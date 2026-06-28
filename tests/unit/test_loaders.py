"""Loading hand-written property files (the --no-llm path)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inductor.domain.properties import PropertyKind
from inductor.loaders import load_property_set

REPO = Path(__file__).resolve().parents[2]


def test_loads_the_checked_in_counter_props() -> None:
    pset = load_property_set(REPO / "designs" / "counter.props.json")
    pids = [p.pid for p in pset.properties]
    assert pids == ["P1", "P2", "P3"]
    assert pset.asserts()[0].kind is PropertyKind.ASSERT
    assert pset.covers()[0].pid == "P3"
    assert pset.has_reachability_witness()


def test_unknown_kind_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"properties": [{"pid": "X", "kind": "wish", "expr": "1"}]}))
    with pytest.raises(ValueError, match="unknown kind"):
        load_property_set(bad)


def test_asserts_without_a_cover_violate_anti_vacuity(tmp_path: Path) -> None:
    bad = tmp_path / "novac.json"
    bad.write_text(json.dumps({"properties": [{"pid": "A", "kind": "assert", "expr": "x"}]}))
    with pytest.raises(ValueError, match="anti-vacuity"):
        load_property_set(bad)


def test_comment_only_or_cover_only_sets_are_fine(tmp_path: Path) -> None:
    f = tmp_path / "cov.json"
    f.write_text(json.dumps({"_comment": "ok", "properties": [{"pid": "C", "kind": "cover", "expr": "y"}]}))  # noqa: E501
    pset = load_property_set(f)
    assert pset.covers()[0].pid == "C"
