"""Witness parsing for the SymbiYosys backend (`.yw` / VCD → `Trace`). See
DESIGN.md §6.4.

The structured `Trace` type lives in `domain/trace.py`. The **yosys-sat** backend
parses Yosys's `sat` model table directly (`adapters/yosys_sat.parse_sat_model`,
the path verified live). This module is the home for the SymbiYosys witness
formats; a full `.yw` (Yosys `ywio`) parser lands with the live sby backend.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from toroid.domain.trace import Trace

__all__ = ["Trace", "WitnessParser", "parse_vcd"]


class WitnessParser(Protocol):
    def parse(self, path: Path, signal_names: Sequence[str]) -> Trace: ...


def parse_vcd(path: Path, signal_names: Sequence[str]) -> Trace:
    """Parse a VCD counterexample (vcdvcd) into a Trace. Implemented with the live
    sby backend; the yosys-sat backend uses the model-table parser instead."""
    raise NotImplementedError(
        "VCD/.yw witness parsing lands with the SymbiYosys backend; the yosys-sat "
        "backend parses the sat model table (yosys_sat.parse_sat_model)."
    )
