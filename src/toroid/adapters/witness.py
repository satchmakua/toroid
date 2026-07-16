"""Witness parsing for the SymbiYosys backend (`.yw` / VCD → `Trace`). See
DESIGN.md §6.4.

The structured `Trace` type lives in `domain/trace.py`. The **yosys-sat** backend
parses Yosys's `sat` model table directly (`adapters/yosys_sat.parse_sat_model`,
the path verified live), which is what produces the inline cycle-by-cycle narration
in reports.

**Honest status:** this module is still a stub. The sby backend now runs live (H2),
but `SbyCli.parse_trace` returns `None`, so a FALSIFIED verdict discharged via **sby**
reports the on-disk `trace.vcd`/`.yw` path *without* inline narration — the narrated
counterexample tables in the README come from the yosys-sat path. Implementing a real
`.yw` (Yosys `ywio`) reader here would close that gap; it is deliberately not claimed
as done anywhere.
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
    """Parse a VCD counterexample (vcdvcd) into a Trace. Not implemented — the
    yosys-sat backend uses the model-table parser instead, and the sby backend
    currently reports the trace file path without inline narration."""
    raise NotImplementedError(
        "VCD/.yw witness parsing is not implemented. The yosys-sat backend parses the "
        "sat model table (yosys_sat.parse_sat_model); the sby backend reports the "
        "on-disk trace path instead of a narrated cycle table."
    )
