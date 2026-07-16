"""The module interface model — extracted from Yosys, never guessed by the LLM.

See DESIGN.md §4.2. The interface is produced by the Yosys adapter via `write_json`
and is the grounding the LLM receives for property synthesis: real port names, real
directions, real widths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Direction = Literal["input", "output", "inout"]


@dataclass(frozen=True, slots=True)
class Port:
    """A single module port with its true width and direction."""

    name: str
    direction: Direction
    width: int  # bit-width, derived from the JSON "bits" array
    is_clock: bool = False
    is_reset: bool = False

    def __post_init__(self) -> None:
        if self.width < 1:
            raise ValueError(f"port {self.name!r} has non-positive width {self.width}")

    @property
    def is_vector(self) -> bool:
        return self.width > 1


@dataclass(frozen=True, slots=True)
class ModuleInterface:
    """The full interface of the design-under-test (DUT)."""

    top: str
    ports: tuple[Port, ...]
    clock: str | None = None
    reset: str | None = None
    reset_active_high: bool = True

    def inputs(self) -> tuple[Port, ...]:
        return tuple(p for p in self.ports if p.direction == "input")

    def outputs(self) -> tuple[Port, ...]:
        return tuple(p for p in self.ports if p.direction == "output")

    def port(self, name: str) -> Port:
        for p in self.ports:
            if p.name == name:
                return p
        raise KeyError(f"no port named {name!r} on module {self.top!r}")

    def driven_inputs(self) -> tuple[Port, ...]:
        """Inputs the formal wrapper must drive with symbolic stimulus
        (every input except the clock, which the harness toggles)."""
        return tuple(p for p in self.inputs() if not p.is_clock)
