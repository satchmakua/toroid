"""The `.sby` builder and the sby-output parser, tested against the real
SymbiYosys console format. Pure — no toolchain needed.
"""

from __future__ import annotations

from pathlib import Path

from toroid.adapters.sby import SbyJob, build_sby_file, parse_sby_output

# --- builder -------------------------------------------------------------------


def _job(mode: str, engine: str = "smtbmc bitwuzla") -> SbyJob:
    return SbyJob(
        name=f"counter_{mode}",
        workdir=Path("work"),
        script_files=("counter.v", "counter_fv.sv"),
        file_paths=(Path("designs/counter.v"), Path("work/counter_fv.sv")),
        top="counter_fv",
        mode=mode,  # type: ignore[arg-type]
        depth=20,
        engine=engine,
    )


def test_build_sby_has_all_sections() -> None:
    text = build_sby_file(_job("bmc"))
    assert "[options]\nmode bmc\ndepth 20" in text
    assert "[engines]\nsmtbmc bitwuzla" in text
    assert "read_verilog -formal counter.v" in text
    assert "read_verilog -formal counter_fv.sv" in text
    assert "prep -top counter_fv" in text
    assert "[files]" in text
    assert "designs/counter.v" in text.replace("\\", "/")


def test_build_sby_prove_with_pdr_engine() -> None:
    text = build_sby_file(_job("prove", engine="abc pdr"))
    assert "mode prove" in text
    assert "[engines]\nabc pdr" in text


# --- parser (real output fixtures) ---------------------------------------------

PASS_OUT = """\
SBY 12:00:01 [counter_bmc] engine_0: smtbmc bitwuzla
SBY 12:00:02 [counter_bmc] engine_0: ##   0:00:01  Checking assertions in step 0..
SBY 12:00:03 [counter_bmc] engine_0: ##   0:00:02  Status: passed
SBY 12:00:03 [counter_bmc] engine_0: Status returned by engine: PASS
SBY 12:00:03 [counter_bmc] summary: engine_0 (smtbmc bitwuzla) returned PASS
SBY 12:00:03 [counter_bmc] DONE (PASS, rc=0)
"""

FAIL_OUT = """\
SBY [counter_bmc] engine_0: ##  Assert failed in counter_fv: assert_0
SBY [counter_bmc] engine_0: ##  Writing trace to VCD file: engine_0/trace.vcd
SBY [counter_bmc] engine_0: ##  Status: failed
SBY [counter_bmc] summary: engine_0 (smtbmc bitwuzla) returned FAIL
SBY [counter_bmc] DONE (FAIL, rc=2)
"""

PROVE_BASECASE_FAIL = """\
SBY [counter_prove] engine_0.basecase: ##  Assert failed in counter_fv: assert_0
SBY [counter_prove] engine_0.basecase: ##  Writing trace to VCD file: engine_0/trace.vcd
SBY [counter_prove] engine_0.basecase: ##  Status: failed
SBY [counter_prove] DONE (FAIL, rc=2)
"""

PROVE_INDUCTION_FAIL = """\
SBY [counter_prove] engine_0.basecase: ##  Status: passed
SBY [counter_prove] engine_0.induction: ##  Status: failed
SBY [counter_prove] DONE (FAIL, rc=2)
"""

COVER_REACHED = """\
SBY [counter_cover] engine_0: ##  Reached cover statement at cover_0 in step 7.
SBY [counter_cover] engine_0: ##  Writing trace to VCD file: engine_0/trace0.vcd
SBY [counter_cover] DONE (PASS, rc=0)
"""

COVER_UNREACHED = """\
SBY [counter_cover] engine_0: ##  Unreached cover statement at cover_0.
SBY [counter_cover] DONE (FAIL, rc=2)
"""

UNKNOWN_OUT = "SBY [x] DONE (UNKNOWN, rc=4)\n"


def test_parse_pass() -> None:
    r = parse_sby_output(PASS_OUT, "bmc", "smtbmc bitwuzla", 20)
    assert r.status == "pass"
    assert r.failed_assert is None
    assert r.trace_vcd is None


def test_parse_bmc_fail_with_assert_and_trace() -> None:
    r = parse_sby_output(FAIL_OUT, "bmc", "smtbmc bitwuzla", 20)
    assert r.status == "fail"
    assert r.failed_assert == "assert_0"
    assert r.trace_vcd == Path("engine_0/trace.vcd")


def test_prove_basecase_failure_is_a_real_cex() -> None:
    r = parse_sby_output(PROVE_BASECASE_FAIL, "prove", "smtbmc bitwuzla", 20)
    assert r.status == "fail"
    assert r.basecase_failed is True


def test_prove_induction_only_failure_is_not_a_cex() -> None:
    r = parse_sby_output(PROVE_INDUCTION_FAIL, "prove", "smtbmc bitwuzla", 20)
    assert r.status == "fail"
    assert r.basecase_failed is False  # holds to depth, just not proven by induction


def test_cover_reached_and_unreached() -> None:
    assert parse_sby_output(COVER_REACHED, "cover", "smtbmc bitwuzla", 20).status == "pass"
    assert parse_sby_output(COVER_REACHED, "cover", "smtbmc bitwuzla", 20).covers_reached == 1
    assert parse_sby_output(COVER_UNREACHED, "cover", "smtbmc bitwuzla", 20).status == "fail"


def test_unknown_status() -> None:
    assert parse_sby_output(UNKNOWN_OUT, "bmc", "smtbmc bitwuzla", 20).status == "unknown"
