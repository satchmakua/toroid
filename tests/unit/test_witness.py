"""Parsing solver counterexamples into a Trace, and the deterministic narration.
Pure — exercises the real Yosys `sat` model-table and SymbiYosys VCD formats with no
toolchain (the VCD fixture was captured from a live sby run).
"""

from __future__ import annotations

from pathlib import Path

from toroid.adapters.witness import parse_vcd, parse_vcd_text
from toroid.adapters.yosys_sat import parse_sat_model
from toroid.domain.trace import Trace, summarize_trace

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# Real `sat -show-all` row shape: "<step>  \<name>  <dec>  <hex>  <bin>".
MODEL = """\
Setting up time steps...
   0 \\rst                          0         0             0
   0 \\en                           1         1             1
   0 \\count                        6         6          0110
   0 \\dut.count                    6         6          0110
   0 $auto$async2sync.cc:1$2        1         1             1
   1 \\rst                          0         0             0
   1 \\en                           1         1             1
   1 \\count                        7         7          0111
   2 \\rst                          0         0             0
   2 \\en                           1         1             1
   2 \\count                       11         b          1011
"""


def test_parses_only_requested_signals_in_order() -> None:
    t = parse_sat_model(MODEL, ["rst", "en", "count"])
    assert t.signals == ("rst", "en", "count")  # requested order, internal cols dropped
    assert len(t.steps) == 3
    assert t.value("count", 0) == 6
    assert t.value("count", 2) == 11
    assert t.failing_step == 2  # last step of the counterexample


def test_unknown_signals_are_skipped() -> None:
    t = parse_sat_model(MODEL, ["count", "nonexistent"])
    assert t.signals == ("count",)


def test_summarize_is_a_readable_table() -> None:
    t = parse_sat_model(MODEL, ["rst", "en", "count"])
    text = summarize_trace(t)
    assert "rst" in text and "en" in text and "count" in text
    assert "counterexample ends" in text  # marks the final step
    assert "11" in text  # the violating value is visible


def test_summarize_empty_trace() -> None:
    assert summarize_trace(Trace(signals=(), steps=())) == "(no trace)"


# --- SymbiYosys VCD witness (fixture captured from a live sby run) ---------------

FIFO_PORTS = ["rst", "wr_en", "rd_en", "wdata", "rdata", "full", "empty", "count"]


def test_vcd_recovers_the_real_sby_counterexample() -> None:
    # The committed fixture is the actual VCD sby wrote for the buggy FIFO's F1
    # (`full ⟺ count==DEPTH`). The violating state is the off-by-one boundary:
    # count == 4 while full == 0.
    t = parse_vcd(FIXTURES / "fifo_f1.trace.vcd", FIFO_PORTS)
    assert t.signals == tuple(FIFO_PORTS)
    assert len(t.steps) == 3
    assert t.value("count", 0) == 4
    assert t.value("full", 0) == 0
    assert t.value("rst", 0) == 1
    assert t.failing_step == 2


def test_vcd_prefers_the_wrapper_port_over_a_same_named_dut_signal() -> None:
    # The fixture declares `count` twice: n1 in the wrapper (top scope) and n8 inside
    # `dut`. Resolving to the shallowest scope must pick the wrapper's.
    t = parse_vcd(FIXTURES / "fifo_f1.trace.vcd", ["count"])
    assert t.signals == ("count",)
    assert t.value("count", 0) == 4


def test_vcd_uses_smt_step_not_raw_timestamps() -> None:
    # smtbmc emits sub-timestamps for the clock edges (#0/#5/#10...). Steps must come
    # from `smt_step`, so 3 solver steps stay 3 — not one row per timestamp.
    text = (FIXTURES / "fifo_f1.trace.vcd").read_text(encoding="utf-8")
    assert text.count("#") >= 5  # more timestamps than steps
    assert len(parse_vcd_text(text, FIFO_PORTS).steps) == 3


def test_vcd_unknown_signals_are_skipped_and_x_is_not_reported_as_zero() -> None:
    t = parse_vcd(FIXTURES / "fifo_f1.trace.vcd", ["count", "nonexistent"])
    assert t.signals == ("count",)
    # An x/z value must not be silently reported as a concrete 0.
    vcd = (
        "$var integer 32 t smt_step $end\n"
        "$scope module m $end\n$var wire 4 n1 sig $end\n$upscope $end\n"
        "$enddefinitions $end\n"
        "#0\nb0 t\nbxxxx n1\n#5\n"
    )
    assert parse_vcd_text(vcd, ["sig"]).signals == ()


def test_vcd_with_no_body_is_an_empty_trace() -> None:
    assert parse_vcd_text("$enddefinitions $end\n", ["a"]).steps == ()
