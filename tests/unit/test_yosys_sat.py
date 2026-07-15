"""The Yosys `sat` output parser, tested against the real Yosys 0.66 strings.
Pure — no toolchain needed.
"""

from __future__ import annotations

from toroid.adapters.yosys_sat import parse_sat_output

HOLDS = "...\nSAT proof finished - no model found: SUCCESS!\n"
CEX = "...\nSAT proof finished - model found: FAIL!\n## got a witness, dumping trace\n"
INDUCT = "Base case for induction length 1 proven.\nInduction step proven: SUCCESS!\n"
ERR = "ERROR: Can't open input file `nope.v'\n"


def test_holds_is_pass() -> None:
    assert parse_sat_output(HOLDS, "bmc", 20, None).status == "pass"


def test_counterexample_is_fail() -> None:
    r = parse_sat_output(CEX, "bmc", 20, None)
    assert r.status == "fail"


def test_induction_success_is_pass() -> None:
    assert parse_sat_output(INDUCT, "prove", 20, None).status == "pass"


def test_error_is_error() -> None:
    assert parse_sat_output(ERR, "bmc", 20, None).status == "error"


def test_silence_is_unknown() -> None:
    assert parse_sat_output("nothing conclusive here", "bmc", 20, None).status == "unknown"


def test_engine_label_names_yosys_sat() -> None:
    assert "yosys-sat" in parse_sat_output(HOLDS, "prove", 20, None).engine
