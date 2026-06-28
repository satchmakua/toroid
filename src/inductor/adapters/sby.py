"""SymbiYosys adapter: build a `.sby` job, run it, parse PASS/FAIL/UNKNOWN and the
depth reached, collect `.yw` / `.vcd` traces on failure. See DESIGN.md §6.3.

The Protocol is stable; `SbyCli` (the real runner) lands in M1.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from inductor.adapters import ToolchainError, toolchain_status
from inductor.domain.verdicts import PropertyResult

SbyMode = Literal["bmc", "prove", "cover", "live"]


@dataclass(frozen=True, slots=True)
class SbyJob:
    workdir: Path
    sources: tuple[Path, ...]
    top: str  # the formal wrapper top, e.g. "counter_fv"
    modes: tuple[SbyMode, ...] = ("bmc", "prove", "cover")
    depth: int = 20
    engine: str = "smtbmc bitwuzla"


class SbyAdapter(Protocol):
    def run(self, job: SbyJob) -> list[PropertyResult]: ...


class SbyCli:
    """Real adapter that shells out to `sby`. Implemented in M1."""

    def __init__(self) -> None:
        if not toolchain_status().sby:
            raise ToolchainError(
                "sby (SymbiYosys) not found on PATH. Install the OSS CAD Suite "
                "(https://github.com/YosysHQ/oss-cad-suite-build). On Windows, use WSL2."
            )

    def run(self, job: SbyJob) -> list[PropertyResult]:
        raise NotImplementedError("SymbiYosys runner lands in M1 (see ROADMAP.md).")
