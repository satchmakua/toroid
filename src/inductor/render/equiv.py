"""Render an equivalence-checking ("miter") wrapper: instantiate two designs that
share one interface, drive their common inputs with the same symbolic stimulus, and
assert their outputs are equal every cycle. See DESIGN.md §7 (M4/equivalence).

Pure: (interface, top_a, top_b) -> SystemVerilog. A FALSIFIED result is a
distinguishing input — the hardware sibling of Congruent's software equivalence.
"""

from __future__ import annotations

from inductor.domain.interface import ModuleInterface, Port

_INDENT = "    "


def _span(p: Port) -> str:
    return f"[{p.width - 1}:0] " if p.is_vector else ""


def render_equiv_wrapper(
    interface: ModuleInterface, top_a: str, top_b: str, *, clk: str = "clk"
) -> str:
    """`interface` is the shared interface (extracted from `top_a`; `top_b` must match)."""
    inputs = [p for p in interface.inputs() if not p.is_clock]
    outputs = interface.outputs()

    lines = [
        f"// Auto-generated equivalence miter: {top_a} vs {top_b} — Inductor.",
        f"module equiv_fv (input {clk});",
    ]
    for p in inputs:
        lines.append(f"{_INDENT}(* keep *) wire {_span(p)}{p.name} = $anyseq;")
    for side in ("a", "b"):
        for p in outputs:
            lines.append(f"{_INDENT}(* keep *) wire {_span(p)}{side}_{p.name};")

    def conns(side: str) -> str:
        parts = []
        for p in interface.ports:
            if p.direction == "input":
                wire = clk if p.is_clock else p.name
            else:
                wire = f"{side}_{p.name}"
            parts.append(f".{p.name}({wire})")
        return ", ".join(parts)

    lines.append("")
    lines.append(f"{_INDENT}{top_a} dut_a ({conns('a')});")
    lines.append(f"{_INDENT}{top_b} dut_b ({conns('b')});")

    eqs = " && ".join(f"(a_{p.name} == b_{p.name})" for p in outputs) or "1'b1"
    lines.append("")
    lines.append(f"{_INDENT}always @(posedge {clk})")
    lines.append(f"{_INDENT}{_INDENT}assert ({eqs});  // outputs equivalent")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"
