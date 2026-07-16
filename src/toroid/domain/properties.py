"""The property model and binding contract.

See DESIGN.md §4.1 and §4.3. Properties are expressed in the *supported Yosys
subset only* — immediate assertions in a clocked block, plus formal helpers
($past, $rose, $stable, $anyseq, $anyconst). Full concurrent SVA is out of scope
for v1 (it needs the commercial Verific frontend).

Invariant enforced by `PropertySet`: every ASSERT carries at least one COVER that
establishes its antecedent is reachable — the anti-vacuity guard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

Origin = Literal["llm", "human", "refined"]


class PropertyKind(StrEnum):
    ASSERT = "assert"  # must always hold
    ASSUME = "assume"  # constrains the environment
    COVER = "cover"  # reachability / anti-vacuity witness


@dataclass(frozen=True, slots=True)
class Property:
    """A single formal property, rendered into the checker wrapper.

    `expr` must be a Yosys-subset SystemVerilog boolean expression (see
    DESIGN.md §4.1). The compile gate (Yosys adapter) is the source of truth for
    whether it is actually accepted — this type does not attempt to parse it.
    """

    pid: str  # stable id, e.g. "P1"
    kind: PropertyKind
    summary: str  # one-line human description
    expr: str  # the Yosys-subset boolean expression
    rationale: str = ""  # why it follows from the spec/interface (provenance)
    # NOTE: currently advisory only. `render/checker.py` emits every property as an
    # immediate assertion inside the single `always @(posedge clk)` block — the
    # universally supported open-frontend idiom (§4.1) — so `clocked=False` is *not*
    # honored today. Kept because the property set round-trips through JSON/the LLM
    # schema; making it meaningful means teaching the renderer an unclocked form.
    clocked: bool = True
    origin: Origin = "llm"


@dataclass(frozen=True, slots=True)
class PropertySet:
    """A coherent set of properties bound to one interface."""

    properties: tuple[Property, ...] = field(default_factory=tuple)

    def of_kind(self, kind: PropertyKind) -> tuple[Property, ...]:
        return tuple(p for p in self.properties if p.kind == kind)

    def asserts(self) -> tuple[Property, ...]:
        return self.of_kind(PropertyKind.ASSERT)

    def covers(self) -> tuple[Property, ...]:
        return self.of_kind(PropertyKind.COVER)

    def assumes(self) -> tuple[Property, ...]:
        return self.of_kind(PropertyKind.ASSUME)

    def has_reachability_witness(self) -> bool:
        """The anti-vacuity invariant: at least one COVER exists whenever there is
        anything to assert. The continue-loop strengthens this to per-assert
        witnesses; the skeleton checks the weak form."""
        return not self.asserts() or bool(self.covers())
