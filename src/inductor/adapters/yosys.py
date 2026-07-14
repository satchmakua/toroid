"""Yosys adapter: interface extraction (`write_json`) and the compile gate
(`read_verilog -formal`). See DESIGN.md §6.1.

The parsing of `write_json` output is a pure function (`parse_write_json`) tested
offline against captured JSON; only `YosysCli` shells out to the toolchain.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from inductor.adapters import ToolchainError
from inductor.domain.interface import Direction, ModuleInterface, Port


@dataclass(frozen=True, slots=True)
class CompileResult:
    ok: bool
    errors: str = ""  # structured diagnostics fed back to the synthesis repair loop


def find_yosys() -> str | None:
    """Locate a usable Yosys: native `yosys` (OSS CAD Suite), else the pip-installed
    WebAssembly build `yowasp-yosys` — checked on PATH and next to the interpreter,
    since console scripts in a venv aren't always on PATH."""
    for name in ("yosys", "yowasp-yosys"):
        if shutil.which(name):
            return name
    scripts = Path(sys.executable).parent
    for cand in (scripts / "yowasp-yosys.exe", scripts / "yowasp-yosys"):
        if cand.is_file():
            return str(cand)
    return None


class YosysAdapter(Protocol):
    def extract_interface(self, sources: list[Path], top: str) -> ModuleInterface: ...

    def compile_check(
        self, sources: list[Path], wrapper: Path, top: str
    ) -> CompileResult: ...


# --- pure parsing + heuristics (unit-tested offline) ---------------------------

_CLOCK_HINTS = ("clk", "clock", "clkin")
_RESET_HINTS = ("rst", "reset")
_ACTIVE_LOW_HINTS = ("_n", "rstn", "resetn", "_b")


def _looks_like_clock(name: str, direction: Direction, width: int) -> bool:
    n = name.lower()
    return direction == "input" and width == 1 and any(h in n for h in _CLOCK_HINTS)


def _looks_like_reset(name: str, direction: Direction, width: int) -> bool:
    n = name.lower()
    return direction == "input" and width == 1 and any(h in n for h in _RESET_HINTS)


def _is_active_low(name: str) -> bool:
    n = name.lower()
    return n.endswith("_n") or n.endswith("n") and any(h in n for h in _RESET_HINTS)


def parse_write_json(data: dict[str, Any], top: str) -> ModuleInterface:
    """Build a `ModuleInterface` from Yosys `write_json` output.

    Port width is `len(port["bits"])`; clock/reset are detected by name heuristics.
    """
    modules = data.get("modules", {})
    if top not in modules:
        raise KeyError(f"module {top!r} not in write_json output (have: {sorted(modules)})")
    ports_json: dict[str, Any] = modules[top].get("ports", {})

    ports: list[Port] = []
    clock: str | None = None
    reset: str | None = None
    reset_active_high = True

    for name, p in ports_json.items():
        direction: Direction = p["direction"]
        width = len(p["bits"])
        is_clock = _looks_like_clock(name, direction, width)
        is_reset = _looks_like_reset(name, direction, width)
        if is_clock and clock is None:
            clock = name
        if is_reset and reset is None:
            reset = name
            reset_active_high = not _is_active_low(name)
        ports.append(Port(name, direction, width, is_clock=is_clock, is_reset=is_reset))

    return ModuleInterface(
        top=top,
        ports=tuple(ports),
        clock=clock,
        reset=reset,
        reset_active_high=reset_active_high,
    )


# --- live adapter (needs the toolchain) ----------------------------------------


class YosysCli:
    """Real adapter that shells out to `yosys`."""

    def __init__(self, executable: str = "yosys", *, timeout: float = 300.0) -> None:
        self.executable = executable
        self.timeout = timeout
        if shutil.which(executable) is None and not Path(executable).is_file():
            raise ToolchainError(
                f"{executable!r} not found. Install the OSS CAD Suite "
                "(https://github.com/YosysHQ/oss-cad-suite-build), or for Yosys-only "
                "flows on Windows: `pip install yowasp-yosys` and pass "
                "executable='yowasp-yosys'."
            )

    def _run(self, script: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.executable, "-q", "-p", script],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as e:
            # Surface a hang as a non-zero result so callers fail cleanly (an
            # elaboration/extraction that hangs would otherwise block indefinitely).
            out = e.stdout if isinstance(e.stdout, str) else ""
            err = (e.stderr if isinstance(e.stderr, str) else "") + (
                f"\nyosys timed out after {self.timeout:.0f}s"
            )
            return subprocess.CompletedProcess(e.cmd, returncode=124, stdout=out, stderr=err)

    def extract_interface(
        self, sources: list[Path], top: str, *, workdir: Path | None = None
    ) -> ModuleInterface:
        # The output (and inputs) must live under the process CWD: the yowasp-yosys
        # WASM sandbox only mounts the current directory. Use a CWD-relative temp
        # dir and relative paths — which native Yosys handles identically.
        if workdir is None:
            base = Path(tempfile.mkdtemp(prefix="_inductor_iface_", dir="."))
            made = True
        else:
            base = workdir
            made = False
        base.mkdir(parents=True, exist_ok=True)
        out = base / "iface.json"
        reads = "; ".join(f"read_verilog -formal {os.path.relpath(s)}" for s in sources)
        script = f"{reads}; hierarchy -top {top}; proc; write_json {out.as_posix()}"
        try:
            res = self._run(script)
            if res.returncode != 0 or not out.exists():
                raise ToolchainError(
                    f"yosys interface extraction failed for {top!r}:\n{res.stderr or res.stdout}"
                )
            data = json.loads(out.read_text(encoding="utf-8"))
        finally:
            if made:
                shutil.rmtree(base, ignore_errors=True)
        return parse_write_json(data, top)

    def compile_check(
        self, sources: list[Path], wrapper: Path, top: str
    ) -> CompileResult:
        reads = "; ".join(
            f"read_verilog -formal {os.path.relpath(s)}" for s in [*sources, wrapper]
        )
        script = f"{reads}; hierarchy -top {top}; proc"
        res = self._run(script)
        if res.returncode == 0:
            return CompileResult(ok=True)
        return CompileResult(ok=False, errors=(res.stderr or res.stdout).strip())
