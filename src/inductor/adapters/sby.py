"""SymbiYosys adapter: build a single-mode `.sby` job, run it, and parse the
result. See DESIGN.md §6.3.

`build_sby_file` and `parse_sby_output` are pure and unit-tested against the real
SymbiYosys console format:

    SBY [job] DONE (PASS, rc=0)
    SBY [job] DONE (FAIL, rc=2)
    SBY [job] engine_0.basecase: ##  Assert failed in counter: <name>
    SBY [job] engine_0.basecase: ##  Writing trace to VCD file: engine_0/trace.vcd
    SBY [job] engine_0: ##  Reached cover statement at <name> in step 2.

Per-property composition (running bmc/prove/cover and mapping to a verdict) lives
in `pipeline/discharge.py`, not here — this adapter is one tool invocation.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from inductor.adapters import ToolchainError, toolchain_status
from inductor.domain.trace import Trace

SbyMode = Literal["bmc", "prove", "cover", "live"]
SbyStatus = Literal["pass", "fail", "unknown", "error", "timeout"]


@dataclass(frozen=True, slots=True)
class SbyJob:
    name: str  # job/outdir name (also the .sby basename)
    workdir: Path  # directory the .sby file and outdir live in
    script_files: tuple[str, ...]  # basenames read in the [script] section
    file_paths: tuple[Path, ...]  # source paths listed in [files]
    top: str  # the prep -top target (the formal wrapper)
    mode: SbyMode
    depth: int = 20
    engine: str = "smtbmc bitwuzla"


@dataclass(frozen=True, slots=True)
class SbyRunResult:
    status: SbyStatus
    mode: SbyMode
    engine: str
    depth: int
    basecase_failed: bool = False  # prove: a real CEX (vs an induction-only failure)
    failed_assert: str | None = None
    covers_reached: int = 0
    trace_vcd: Path | None = None
    trace_yw: Path | None = None
    raw: str = ""


class SbyJobRunner(Protocol):
    def run_job(self, job: SbyJob) -> SbyRunResult: ...

    def parse_trace(
        self, result: SbyRunResult, signal_names: Sequence[str]
    ) -> Trace | None:
        """Parse a counterexample into a structured Trace (None if unavailable)."""
        ...


# --- pure builders + parsers (unit-tested offline) -----------------------------


def build_sby_file(job: SbyJob) -> str:
    reads = "\n".join(f"read_verilog -formal {f}" for f in job.script_files)
    files = "\n".join(str(p) for p in job.file_paths)
    return (
        "[options]\n"
        f"mode {job.mode}\n"
        f"depth {job.depth}\n"
        "\n"
        "[engines]\n"
        f"{job.engine}\n"
        "\n"
        "[script]\n"
        f"{reads}\n"
        f"prep -top {job.top}\n"
        "\n"
        "[files]\n"
        f"{files}\n"
    )


_STATUS_MAP: dict[str, SbyStatus] = {
    "PASS": "pass",
    "FAIL": "fail",
    "UNKNOWN": "unknown",
    "ERROR": "error",
    "TIMEOUT": "timeout",
}

_DONE_RE = re.compile(r"DONE \((PASS|FAIL|UNKNOWN|ERROR|TIMEOUT), rc=(\d+)\)")
_ASSERT_RE = re.compile(r"Assert failed in \S+: (\S+)")
_VCD_RE = re.compile(r"Writing trace to VCD file: (\S+)")
_YW_RE = re.compile(r"Writing trace to Yosys witness file: (\S+)")
_YW_FALLBACK_RE = re.compile(r"(\S+\.yw)\b")
_COVER_RE = re.compile(r"Reached cover statement")
_BASECASE_FAIL_RE = re.compile(r"basecase:.*(Status: failed|Assert failed)")


def parse_sby_output(stdout: str, mode: SbyMode, engine: str, depth: int) -> SbyRunResult:
    """Map raw sby console output to a structured result."""
    done = _DONE_RE.search(stdout)
    status: SbyStatus = _STATUS_MAP[done.group(1)] if done else "unknown"

    assert_m = _ASSERT_RE.search(stdout)
    vcd_m = _VCD_RE.search(stdout)
    yw_m = _YW_RE.search(stdout) or _YW_FALLBACK_RE.search(stdout)

    return SbyRunResult(
        status=status,
        mode=mode,
        engine=engine,
        depth=depth,
        basecase_failed=bool(_BASECASE_FAIL_RE.search(stdout)),
        failed_assert=assert_m.group(1) if assert_m else None,
        covers_reached=len(_COVER_RE.findall(stdout)),
        trace_vcd=Path(vcd_m.group(1)) if vcd_m else None,
        trace_yw=Path(yw_m.group(1)) if yw_m else None,
        raw=stdout,
    )


# --- live adapter (needs the toolchain) ----------------------------------------


class SbyCli:
    """Real adapter that shells out to `sby`."""

    def __init__(self, executable: str = "sby", *, timeout: float = 900.0) -> None:
        self.executable = executable
        self.timeout = timeout
        if not toolchain_status().sby:
            raise ToolchainError(
                "sby (SymbiYosys) not found on PATH. Install the OSS CAD Suite "
                "(https://github.com/YosysHQ/oss-cad-suite-build). On Windows, use WSL2."
            )

    def run_job(self, job: SbyJob) -> SbyRunResult:
        job.workdir.mkdir(parents=True, exist_ok=True)
        sby_path = job.workdir / f"{job.name}.sby"
        sby_path.write_text(build_sby_file(job), encoding="utf-8")

        try:
            proc = subprocess.run(
                [self.executable, "-f", sby_path.name],
                cwd=job.workdir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            # Honest INCONCLUSIVE (discharge maps "timeout" like "unknown"), not a hang.
            return SbyRunResult(
                status="timeout", mode=job.mode, engine=job.engine, depth=job.depth
            )
        result = parse_sby_output(
            proc.stdout + proc.stderr, job.mode, job.engine, job.depth
        )

        # Resolve trace paths (sby reports them relative to the outdir).
        outdir = job.workdir / job.name
        return _resolve_traces(result, outdir)

    def parse_trace(
        self, result: SbyRunResult, signal_names: Sequence[str]
    ) -> Trace | None:
        # Structured .yw/VCD witness parsing for the sby backend lands later; the
        # report still links the on-disk trace_vcd. (yosys-sat parses its model.)
        return None


def _resolve_traces(result: SbyRunResult, outdir: Path) -> SbyRunResult:
    def _abs(rel: Path | None) -> Path | None:
        if rel is None:
            return None
        candidate = outdir / rel
        return candidate if candidate.exists() else rel

    from dataclasses import replace

    return replace(result, trace_vcd=_abs(result.trace_vcd), trace_yw=_abs(result.trace_yw))
