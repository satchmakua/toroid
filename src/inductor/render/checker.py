"""Render a `PropertySet` into a Yosys-checkable formal wrapper module.

See DESIGN.md §4.1. The wrapper (`<top>_fv`) instantiates the DUT, drives every
input except the clock with `$anyseq` symbolic stimulus, optionally holds reset for
the first cycle, and emits the assert/assume/cover statements as *immediate*
assertions inside a single `always @(posedge clk)` block — the universally
supported open-frontend idiom. No SystemVerilog `bind`, no concurrent SVA.

This module is pure: `PropertySet` + `ModuleInterface` -> `str`. It does not run
Yosys; the Yosys adapter's compile gate decides whether the output elaborates.
"""

from __future__ import annotations

from inductor.domain.interface import ModuleInterface, Port
from inductor.domain.properties import PropertySet

_INDENT = "    "


def _decl(port: Port, *, driven: bool) -> str:
    """A wire declaration for the wrapper. Driven inputs get `= $anyseq`.

    `(* keep *)` stops the optimizer from dissolving the signal so it survives into
    the counterexample trace (VCD/.yw) under its real name — essential for readable
    cycle-by-cycle narration (M3)."""
    span = f"[{port.width - 1}:0] " if port.is_vector else ""
    suffix = " = $anyseq" if driven else ""
    return f"{_INDENT}(* keep *) wire {span}{port.name}{suffix};"


def render_wrapper(interface: ModuleInterface, pset: PropertySet) -> str:
    """Produce the `<top>_fv` formal wrapper as SystemVerilog source."""
    top = interface.top
    clk = interface.clock or "clk"

    lines: list[str] = []
    lines.append(f"// Auto-generated formal wrapper for `{top}` — Inductor.")
    lines.append("// Supported open-Yosys subset only (immediate assertions).")
    lines.append(f"module {top}_fv (input {clk});")

    # Symbolic stimulus for every driven input; free wires for outputs.
    for p in interface.driven_inputs():
        if p.name == clk:
            continue
        lines.append(_decl(p, driven=True))
    for p in interface.outputs():
        lines.append(_decl(p, driven=False))

    # DUT instantiation, connected by name.
    conns = ", ".join(f".{p.name}({p.name})" for p in interface.ports)
    lines.append("")
    lines.append(f"{_INDENT}{top} dut ({conns});")

    # Optional: hold reset asserted on the first cycle so properties start from a
    # known state.
    if interface.reset:
        level = interface.reset if interface.reset_active_high else f"!{interface.reset}"
        lines.append("")
        lines.append(f"{_INDENT}always @(posedge {clk})")
        lines.append(f"{_INDENT}{_INDENT}if ($initstate) assume ({level});")

    # Assumptions, asserts, and covers in one clocked block.
    body: list[str] = []
    for prop in pset.assumes():
        body.append(f"{_INDENT}{_INDENT}assume ({prop.expr});  // {prop.pid}: {prop.summary}")
    for prop in pset.asserts():
        body.append(f"{_INDENT}{_INDENT}assert ({prop.expr});  // {prop.pid}: {prop.summary}")
    for prop in pset.covers():
        body.append(f"{_INDENT}{_INDENT}cover ({prop.expr});  // {prop.pid}: {prop.summary}")

    if body:
        lines.append("")
        lines.append(f"{_INDENT}always @(posedge {clk}) begin")
        lines.extend(body)
        lines.append(f"{_INDENT}end")

    lines.append("endmodule")
    return "\n".join(lines) + "\n"
