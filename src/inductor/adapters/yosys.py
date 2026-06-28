"""Yosys adapter: interface extraction (`write_json`) and the compile gate
(`read_verilog -formal`). See DESIGN.md §6.1.

The Protocol is the contract the pipeline depends on; `YosysCli` is the real
implementation, landed in M1 once the OSS CAD Suite toolchain is available.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from inductor.adapters import ToolchainError, toolchain_status
from inductor.domain.interface import ModuleInterface


@dataclass(frozen=True, slots=True)
class CompileResult:
    ok: bool
    errors: str = ""  # structured diagnostics fed back to the synthesis repair loop


class YosysAdapter(Protocol):
    def extract_interface(self, sources: list[Path], top: str) -> ModuleInterface: ...

    def compile_check(
        self, sources: list[Path], wrapper: Path, top: str
    ) -> CompileResult: ...


class YosysCli:
    """Real adapter that shells out to `yosys`. Implemented in M1."""

    def __init__(self) -> None:
        if not toolchain_status().yosys:
            raise ToolchainError(
                "yosys not found on PATH. Install the OSS CAD Suite "
                "(https://github.com/YosysHQ/oss-cad-suite-build) and ensure "
                "`yosys` is on PATH. On Windows, use WSL2."
            )

    def extract_interface(self, sources: list[Path], top: str) -> ModuleInterface:
        raise NotImplementedError("Yosys interface extraction lands in M1 (see ROADMAP.md).")

    def compile_check(
        self, sources: list[Path], wrapper: Path, top: str
    ) -> CompileResult:
        raise NotImplementedError("Yosys compile gate lands in M1 (see ROADMAP.md).")
