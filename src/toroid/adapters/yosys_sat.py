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
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path

from toroid.adapters import ToolchainError
from toroid.adapters.sby import SbyJob, SbyMode, SbyRunResult, SbyStatus
from toroid.adapters.yosys import find_yosys
from toroid.domain.trace import Trace, _Builder

ENGINE = "yosys-sat (minisat)"

# A model-table row from `sat -show-all`: "<step>  \<name>  <dec>  <hex>  <bin>".
_MODEL_ROW = re.compile(r"^\s*(\d+)\s+\\([\w.]+)\s+(-?\d+)\s+[0-9a-fx?]+\s+[01xz]+\s*$")


def parse_sat_model(stdout: str, signal_names: Sequence[str]) -> Trace:
    """Parse Yosys `sat`'s model table into a Trace, keeping `signal_names` (matched
    against the `\\name` column, e.g. interface ports). Steps are renumbered 0-based
    in solver order."""
    wanted = list(dict.fromkeys(signal_names))  # preserve order, dedupe
    wanted_set = set(wanted)
    builder = _Builder()
    seen: set[str] = set()
    for line in stdout.splitlines():
        m = _MODEL_ROW.match(line)
        if not m:
            continue
        step, name, dec = int(m.group(1)), m.group(2), int(m.group(3))
        if name in wanted_set:
            builder.set(step, name, dec)
            seen.add(name)
    signals = tuple(s for s in wanted if s in seen)
    return builder.build(signals)


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

    def __init__(self, executable: str | None = None, *, timeout: float = 300.0) -> None:
        exe = executable or find_yosys()
        if exe is None:
            raise ToolchainError(
                "no Yosys found. Install the OSS CAD Suite, or for this lightweight "
                "backend: `pip install yowasp-yosys`."
            )
        self.executable: str = exe
        self.timeout = timeout

    def run_job(self, job: SbyJob) -> SbyRunResult:
        outdir = job.workdir / job.name
        outdir.mkdir(parents=True, exist_ok=True)
        vcd = outdir / "trace.vcd"

        reads = "; ".join(f"read_verilog -formal {os.path.relpath(p)}" for p in job.file_paths)
        # memory_map bit-blasts $mem cells to FF logic so `sat` can handle designs
        # with memories (e.g. FIFOs); a no-op when there are none.
        prep = f"prep -top {job.top} -flatten; memory_map; async2sync; chformal -lower"

        if job.mode == "bmc":
            # -show-all captures the full per-step model table (the reliable trace
            # source; -dump_vcd alone is unreliable for this flow).
            sat = (
                f"sat -seq {job.depth} -prove-asserts -show-all "
                f"-dump_vcd {os.path.relpath(vcd)}"
            )
        elif job.mode == "prove":
            sat = "sat -tempinduct -prove-asserts"
        else:  # cover / live: not supported by this backend
            return SbyRunResult(status="unknown", mode=job.mode, engine=ENGINE, depth=job.depth)

        try:
            proc = subprocess.run(
                [self.executable, "-p", f"{reads}; {prep}; {sat}"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            # A pathological solve maps to the honest INCONCLUSIVE path (discharge
            # treats "timeout" like "unknown"), never a false pass or a CI hang.
            return SbyRunResult(status="timeout", mode=job.mode, engine=ENGINE, depth=job.depth)
        return parse_sat_output(proc.stdout + proc.stderr, job.mode, job.depth, vcd)

    def parse_trace(
        self, result: SbyRunResult, signal_names: Sequence[str]
    ) -> Trace | None:
        if result.status != "fail":
            return None
        trace = parse_sat_model(result.raw, signal_names)
        return trace if trace.steps else None
