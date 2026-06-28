"""A Yosys-only discharge backend using Yosys's built-in `sat` command (internal
minisat) — **no external SMT solver and no SymbiYosys required**. This makes the
full proof-or-counterexample flow runnable anywhere Yosys is available, including
Windows via `pip install yowasp-yosys`.

It implements the same `SbyJobRunner` contract as the SymbiYosys backend, so
`pipeline.discharge` is agnostic to which one it drives.

Verified Yosys `sat` flow + output strings (Yosys 0.66):

    prep -top <wrapper> -flatten ; async2sync ; chformal -lower ; sat ...
    holds   -> "SAT proof finished - no model found: SUCCESS!"   (bmc / induction)
    cex     -> "SAT proof finished - model found: FAIL!"         (+ -dump_vcd trace)
    induct  -> "Induction step proven: SUCCESS!"                 (-tempinduct)

Limitations vs. the SymbiYosys backend: the `cover` mode (reachability / the
anti-vacuity witness) is not implemented here, so it returns `unknown` and the
verdict is reported without the vacuity guard. Use the SymbiYosys + Bitwuzla
backend (OSS CAD Suite) for full vacuity checking.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from inductor.adapters import ToolchainError
from inductor.adapters.sby import SbyJob, SbyMode, SbyRunResult, SbyStatus
from inductor.adapters.yosys import find_yosys

ENGINE = "yosys-sat (minisat)"


def parse_sat_output(stdout: str, mode: SbyMode, depth: int, vcd: Path | None) -> SbyRunResult:
    """Map Yosys `sat` console output to a structured result."""
    status: SbyStatus
    if "model found: FAIL!" in stdout:
        status = "fail"
    elif "SUCCESS!" in stdout:
        status = "pass"
    elif "ERROR" in stdout:
        status = "error"
    else:
        status = "unknown"
    return SbyRunResult(
        status=status,
        mode=mode,
        engine=ENGINE,
        depth=depth,
        basecase_failed=status == "fail" and mode != "prove",
        trace_vcd=vcd if (status == "fail" and vcd and vcd.exists()) else None,
        raw=stdout,
    )


class YosysSatCli:
    """Discharge backend backed by `yosys -p '... sat ...'`."""

    def __init__(self, executable: str | None = None) -> None:
        exe = executable or find_yosys()
        if exe is None:
            raise ToolchainError(
                "no Yosys found. Install the OSS CAD Suite, or for this lightweight "
                "backend: `pip install yowasp-yosys`."
            )
        self.executable: str = exe

    def run_job(self, job: SbyJob) -> SbyRunResult:
        outdir = job.workdir / job.name
        outdir.mkdir(parents=True, exist_ok=True)
        vcd = outdir / "trace.vcd"

        reads = "; ".join(f"read_verilog -formal {os.path.relpath(p)}" for p in job.file_paths)
        prep = f"prep -top {job.top} -flatten; async2sync; chformal -lower"

        if job.mode == "bmc":
            sat = f"sat -seq {job.depth} -prove-asserts -dump_vcd {os.path.relpath(vcd)}"
        elif job.mode == "prove":
            sat = "sat -tempinduct -prove-asserts"
        else:  # cover / live: not supported by this backend
            return SbyRunResult(status="unknown", mode=job.mode, engine=ENGINE, depth=job.depth)

        proc = subprocess.run(
            [self.executable, "-p", f"{reads}; {prep}; {sat}"],
            capture_output=True,
            text=True,
        )
        return parse_sat_output(proc.stdout + proc.stderr, job.mode, job.depth, vcd)
