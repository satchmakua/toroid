"""Property synthesis with a compile-gate + anti-vacuity repair loop. See
DESIGN.md §6.2.

The LLM proposes a `PropertySet`; before anything reaches a solver we (1) enforce
the anti-vacuity invariant (every assert needs a cover) and (2) run the Yosys
compile gate on the rendered wrapper. Either failure is fed back to the LLM as
repair feedback, up to `max_repairs` times. Only a property set that elaborates is
returned for discharge — a malformed or vacuous set never reaches the model checker.

The LLM and Yosys are injected, so this whole loop is unit-tested offline with
fakes; only the adapters touch the model/toolchain.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from toroid.adapters.yosys import YosysAdapter
from toroid.domain.interface import ModuleInterface
from toroid.domain.properties import PropertySet
from toroid.render.checker import render_wrapper


class Synthesizer(Protocol):
    def synthesize(
        self, interface: ModuleInterface, spec: str, *, feedback: str | None = None
    ) -> PropertySet: ...


@dataclass(frozen=True, slots=True)
class SynthResult:
    pset: PropertySet
    compiled: bool
    attempts: int
    errors: str = ""


def synthesize_properties(
    interface: ModuleInterface,
    spec: str,
    *,
    llm: Synthesizer,
    yosys: YosysAdapter,
    duts: Sequence[Path],
    workdir: Path,
    max_repairs: int = 3,
) -> SynthResult:
    top = f"{interface.top}_fv"
    feedback: str | None = None
    pset = PropertySet()
    errors = ""

    for attempt in range(1, max_repairs + 2):  # one initial attempt + repairs
        pset = llm.synthesize(interface, spec, feedback=feedback)

        # (1) anti-vacuity: every assert needs a reachability cover.
        if not pset.has_reachability_witness():
            errors = "Every assert needs at least one cover making its antecedent reachable."
            feedback = errors
            continue

        # (2) compile gate: the rendered wrapper must elaborate under Yosys.
        wrapper = workdir / f"{top}.sv"
        wrapper.parent.mkdir(parents=True, exist_ok=True)
        wrapper.write_text(render_wrapper(interface, pset), encoding="utf-8")
        gate = yosys.compile_check(list(duts), wrapper, top)
        if gate.ok:
            return SynthResult(pset, compiled=True, attempts=attempt)

        errors = gate.errors
        feedback = (
            "The properties did not elaborate under Yosys (read_verilog -formal). "
            "Fix exactly these errors and re-emit the full set:\n" + gate.errors
        )

    return SynthResult(pset, compiled=False, attempts=max_repairs + 1, errors=errors)
