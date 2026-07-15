"""Adapters: the impure boundary to external systems (Yosys, SymbiYosys, the LLM,
the filesystem). Each is defined as a `Protocol` so the pipeline can be tested with
all of them mocked. See DESIGN.md §5.

The walking skeleton ships the Protocols and toolchain detection; concrete
implementations land in M1+ (see ROADMAP.md).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass


class ToolchainError(RuntimeError):
    """Raised when a required external tool is missing or misbehaves."""


@dataclass(frozen=True, slots=True)
class ToolchainStatus:
    yosys: bool
    sby: bool

    @property
    def ready(self) -> bool:
        return self.yosys and self.sby

    def missing(self) -> tuple[str, ...]:
        out: list[str] = []
        if not self.yosys:
            out.append("yosys")
        if not self.sby:
            out.append("sby")
        return tuple(out)


def toolchain_status() -> ToolchainStatus:
    """Detect the open formal toolchain on PATH (the OSS CAD Suite ships both)."""
    return ToolchainStatus(
        yosys=shutil.which("yosys") is not None,
        sby=shutil.which("sby") is not None,
    )
