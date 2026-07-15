"""The wrapper renderer must emit valid open-Yosys-subset SystemVerilog: symbolic
stimulus for driven inputs, a by-name DUT instantiation, a reset assumption, and
immediate assert/cover statements in one clocked block (DESIGN.md §4.1).
"""

from __future__ import annotations

from toroid.domain.interface import ModuleInterface, Port
from toroid.domain.properties import Property, PropertyKind, PropertySet
from toroid.render.checker import render_wrapper


def _counter_iface() -> ModuleInterface:
    return ModuleInterface(
        top="counter",
        ports=(
            Port("clk", "input", 1, is_clock=True),
            Port("rst", "input", 1, is_reset=True),
            Port("en", "input", 1),
            Port("count", "output", 4),
        ),
        clock="clk",
        reset="rst",
    )


def _pset() -> PropertySet:
    return PropertySet(
        properties=(
            Property("P1", PropertyKind.ASSERT, "no overflow", "count <= 4'd15"),
            Property("P3", PropertyKind.COVER, "can reach max", "count == 4'd15"),
        )
    )


def test_wrapper_module_header_and_clock() -> None:
    sv = render_wrapper(_counter_iface(), _pset())
    assert "module counter_fv (input clk);" in sv
    assert sv.rstrip().endswith("endmodule")


def test_driven_inputs_get_anyseq_but_clock_does_not() -> None:
    sv = render_wrapper(_counter_iface(), _pset())
    assert "wire rst = $anyseq;" in sv
    assert "wire en = $anyseq;" in sv
    # The clock is a wrapper port, never an $anyseq wire.
    assert "wire clk = $anyseq;" not in sv


def test_vector_output_declared_with_width() -> None:
    sv = render_wrapper(_counter_iface(), _pset())
    assert "wire [3:0] count;" in sv


def test_dut_instantiated_by_name() -> None:
    sv = render_wrapper(_counter_iface(), _pset())
    assert "counter dut (.clk(clk), .rst(rst), .en(en), .count(count));" in sv


def test_reset_assumption_emitted() -> None:
    sv = render_wrapper(_counter_iface(), _pset())
    assert "if ($initstate) assume (rst);" in sv


def test_assert_and_cover_in_clocked_block() -> None:
    sv = render_wrapper(_counter_iface(), _pset())
    assert "always @(posedge clk) begin" in sv
    assert "assert (count <= 4'd15);" in sv
    assert "cover (count == 4'd15);" in sv


def test_active_low_reset_is_negated() -> None:
    iface = ModuleInterface(
        top="m",
        ports=(Port("clk", "input", 1, is_clock=True), Port("rstn", "input", 1, is_reset=True)),
        clock="clk",
        reset="rstn",
        reset_active_high=False,
    )
    sv = render_wrapper(iface, PropertySet())
    assert "assume (!rstn);" in sv
