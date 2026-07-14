"""RecordedLLM replay + diagnosis serialization roundtrip. Pure — no toolchain, no
key. (The recorded fixtures themselves are exercised live in the integration suite.)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inductor.adapters.llm import CexCause, CexDiagnosis
from inductor.adapters.recorded import RecordedLLM, diagnosis_from_dict, diagnosis_to_dict
from inductor.domain.interface import ModuleInterface, Port
from inductor.domain.properties import Property, PropertyKind, PropertySet
from inductor.domain.trace import Trace
from inductor.loaders import property_set_to_dict


def _iface() -> ModuleInterface:
    return ModuleInterface(top="m", ports=(Port("clk", "input", 1, is_clock=True),))


def test_diagnosis_roundtrips_through_json() -> None:
    patch = Property(
        "F1", PropertyKind.ASSERT, "gated", "rst || (full == (count == 4))", origin="refined"
    )
    d = CexDiagnosis(CexCause.OVER_STRONG, "count=4 during reset", patch)
    back = diagnosis_from_dict(diagnosis_to_dict(d))
    assert back.cause is CexCause.OVER_STRONG
    assert back.narration == d.narration
    assert back.proposed_patch is not None
    assert back.proposed_patch.expr == patch.expr
    assert back.proposed_patch.origin == "refined"  # round-trips as recorded


def test_rtl_bug_diagnosis_has_no_patch() -> None:
    d = CexDiagnosis(CexCause.RTL_BUG, "genuine fault", None)
    assert diagnosis_from_dict(diagnosis_to_dict(d)).proposed_patch is None


def test_recorded_llm_replays_synth_then_diagnoses_in_order() -> None:
    pset = PropertySet(
        properties=(
            Property("P1", PropertyKind.ASSERT, "a", "x", origin="llm"),
            Property("C1", PropertyKind.COVER, "c", "y", origin="llm"),
        )
    )
    d1 = CexDiagnosis(CexCause.OVER_STRONG, "n1", None)
    d2 = CexDiagnosis(CexCause.RTL_BUG, "n2", None)
    llm = RecordedLLM(synth=pset, diagnoses=[d1, d2])

    assert llm.synthesize(_iface(), "spec").properties[0].pid == "P1"
    trace = Trace(signals=(), steps=())
    prop = pset.asserts()[0]
    assert llm.classify_cex(prop, trace, _iface()).cause is CexCause.OVER_STRONG
    assert llm.classify_cex(prop, trace, _iface()).cause is CexCause.RTL_BUG
    # exhausted -> repeats the last (bounded, deterministic replay)
    assert llm.classify_cex(prop, trace, _iface()).cause is CexCause.RTL_BUG


def test_from_files_fails_loud_on_missing_classify_fixture(tmp_path: Path) -> None:
    # A valid synth fixture (assert + cover so the anti-vacuity loader accepts it).
    pset = PropertySet(
        properties=(
            Property("P1", PropertyKind.ASSERT, "a", "x", origin="llm"),
            Property("C1", PropertyKind.COVER, "c", "y", origin="llm"),
        )
    )
    synth_path = tmp_path / "synth.json"
    synth_path.write_text(json.dumps(property_set_to_dict(pset)), encoding="utf-8")

    # No classify path -> legitimate synth-only replay with empty diagnoses.
    assert RecordedLLM.from_files(synth_path).diagnoses == []

    # A provided-but-missing classify path must fail loud (a typo shouldn't silently
    # degrade to a no-op replay that exercises no recorded diagnosis).
    with pytest.raises(FileNotFoundError):
        RecordedLLM.from_files(synth_path, tmp_path / "does_not_exist.json")
