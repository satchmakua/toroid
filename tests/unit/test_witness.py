"""Parsing Yosys `sat` model tables into a Trace, and the deterministic narration.
Pure — exercises the real model-table format with no toolchain.
"""

from __future__ import annotations

from inductor.adapters.yosys_sat import parse_sat_model
from inductor.domain.trace import Trace, summarize_trace

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
