"""The equivalence miter renderer and the port-compatibility check. Pure."""

from __future__ import annotations

from inductor.domain.interface import ModuleInterface, Port
from inductor.pipeline.equiv import _port_mismatch
from inductor.render.equiv import render_equiv_wrapper


def _iface(top: str = "max2") -> ModuleInterface:
    return ModuleInterface(
        top=top,
        ports=(
            Port("a", "input", 4),
            Port("b", "input", 4),
            Port("y", "output", 4),
        ),
    )


def test_miter_shares_inputs_and_asserts_output_equality() -> None:
    sv = render_equiv_wrapper(_iface(), "max2", "max2_alt")
    assert "module equiv_fv (input clk);" in sv
    assert "wire [3:0] a = $anyseq;" in sv  # shared input
    assert "wire [3:0] b = $anyseq;" in sv
    assert "wire [3:0] a_y;" in sv and "wire [3:0] b_y;" in sv  # per-side outputs
    assert "max2 dut_a (.a(a), .b(b), .y(a_y));" in sv  # spec, outputs -> a_*
    assert "max2_alt dut_b (.a(a), .b(b), .y(b_y));" in sv  # impl, outputs -> b_*
    assert "assert ((a_y == b_y));" in sv


def test_port_mismatch_detects_incompatible_interfaces() -> None:
    a = _iface("m1")
    b = ModuleInterface(
        top="m2",
        ports=(Port("a", "input", 4), Port("b", "input", 8), Port("y", "output", 4)),  # b wider
    )
    assert _port_mismatch(a, a) == ""  # identical -> compatible
    msg = _port_mismatch(a, b)
    assert "differ" in msg and "b" in msg
