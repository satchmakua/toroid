"""Witness adapter: parse the Yosys `.yw` witness (structured JSONL) into a
per-cycle `Trace` for counterexample narration; VCD is kept only for human display.
See DESIGN.md §6.4. Real parsing lands in M3 (the counterexample loop).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Trace:
    signals: tuple[str, ...]
    cycles: tuple[dict[str, int], ...]  # cycle -> {signal: value}
    failing_cycle: int = -1
    vcd: Path | None = None  # companion human waveform


class WitnessAdapter(Protocol):
    def parse_yw(self, yw: Path) -> Trace: ...


@dataclass(frozen=True, slots=True)
class YwWitness:
    """Real `.yw` parser (uses Yosys' `ywio`). Implemented in M3."""

    def parse_yw(self, yw: Path) -> Trace:
        raise NotImplementedError(".yw witness parsing lands in M3 (see ROADMAP.md).")
