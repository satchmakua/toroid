"""The discharge composition — the M1 orchestration — tested fully offline by
injecting fake Yosys/sby adapters that return realistic results. This verifies the
mapping from per-mode sby outcomes to the verdict taxonomy without any toolchain.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from inductor.adapters.sby import SbyJob, SbyRunResult
from inductor.adapters.yosys import CompileResult
from inductor.domain.interface import ModuleInterface, Port
from inductor.domain.properties import Property, PropertyKind, PropertySet
from inductor.domain.verdicts import PropertyResult, Verdict
from inductor.pipeline.discharge import discharge


def _iface() -> ModuleInterface:
    return ModuleInterface(
        top="counter",
        ports=(
            Port("clk", "input", 1, is_clock=True),
            Port("rst", "input", 1, is_reset=True),
            Port("en", "input", 1),
            Port("count", "output", 4),
        ),
        clock="clk",
        reset="rst",
    )


def _pset() -> PropertySet:
    return PropertySet(
        properties=(
            Property("P1", PropertyKind.ASSERT, "no overflow", "count <= 4'd15"),
            Property("P2", PropertyKind.ASSERT, "holds when disabled", "count == $past(count)"),
            Property("P3", PropertyKind.COVER, "reaches max", "count == 4'd15"),
        )
    )


class FakeYosys:
    def __init__(self, ok: bool = True, errors: str = "") -> None:
        self._result = CompileResult(ok=ok, errors=errors)

    def extract_interface(self, sources: list[Path], top: str) -> ModuleInterface:
        raise NotImplementedError

    def compile_check(self, sources: list[Path], wrapper: Path, top: str) -> CompileResult:
        return self._result


class FakeSby:
    """Routes each job to a canned result via a (pid_or_'cover', mode_name) key."""

    def __init__(self, fn: Callable[[str, str], SbyRunResult]) -> None:
        self.fn = fn
        self.jobs: list[SbyJob] = []

    def run_job(self, job: SbyJob) -> SbyRunResult:
        self.jobs.append(job)
        key = "cover" if job.name == "cover" else job.workdir.parent.name
        # Real adapters set the result's engine from the job; mirror that so the
        # report's engine attribution can be asserted.
        return replace(self.fn(key, job.name), engine=job.engine)


def _r(status: str, **kw: object) -> SbyRunResult:
    return SbyRunResult(status=status, mode="bmc", engine="smtbmc bitwuzla", depth=20, **kw)  # type: ignore[arg-type]


def _run(
    fn: Callable[[str, str], SbyRunResult], tmp_path: Path, *, ok: bool = True
) -> dict[str, PropertyResult]:
    results = discharge(
        _iface(), _pset(),
        duts=[Path("counter.v")],
        yosys=FakeYosys(ok=ok),
        runner=FakeSby(fn),
        workdir=tmp_path,
    )
    return {r.pid: r for r in results}


def test_proven_via_kinduction_and_bounded_via_bmc(tmp_path: Path) -> None:
    def fn(key: str, mode: str) -> SbyRunResult:
        if key == "cover":
            return _r("pass")
        if key == "P1":  # both bmc and k-induction pass -> PROVEN
            return _r("pass")
        if key == "P2":  # bmc passes, induction fails, pdr fails -> BOUNDED_PASS
            if mode == "bmc":
                return _r("pass")
            return _r("fail")  # prove + pdr both fail (induction-only, not basecase)
        return _r("unknown")

    out = _run(fn, tmp_path)
    assert out["P1"].verdict is Verdict.PROVEN
    assert out["P1"].engine == "smtbmc bitwuzla"  # the k-induction run's engine
    assert out["P2"].verdict is Verdict.BOUNDED_PASS
    assert out["P2"].depth == 20


def test_proven_via_pdr_when_kinduction_fails(tmp_path: Path) -> None:
    def fn(key: str, mode: str) -> SbyRunResult:
        if key == "cover":
            return _r("pass")
        if mode == "bmc":
            return _r("pass")
        if mode == "prove":
            return _r("fail")  # k-induction can't close it
        return _r("pass")  # but PDR proves it

    out = _run(fn, tmp_path)
    assert out["P1"].verdict is Verdict.PROVEN
    assert out["P1"].engine == "abc pdr"  # the PDR run's engine


def test_falsified_collects_trace(tmp_path: Path) -> None:
    def fn(key: str, mode: str) -> SbyRunResult:
        if key == "cover":
            return _r("pass")
        if key == "P1" and mode == "bmc":
            return _r("fail", failed_assert="assert_0", trace_vcd=Path("engine_0/trace.vcd"))
        return _r("pass")

    out = _run(fn, tmp_path)
    assert out["P1"].verdict is Verdict.FALSIFIED
    assert out["P1"].trace_vcd == Path("engine_0/trace.vcd")
    assert "bmc" in (out["P1"].engine or "")


def test_vacuous_when_cover_unreachable(tmp_path: Path) -> None:
    def fn(key: str, mode: str) -> SbyRunResult:
        if key == "cover":
            return _r("fail")  # the reachability witness is unreachable
        return _r("pass")  # everything "passes" — but that's vacuous

    out = _run(fn, tmp_path)
    assert out["P1"].verdict is Verdict.VACUOUS
    assert out["P2"].verdict is Verdict.VACUOUS


def test_compile_error_short_circuits_without_running_sby(tmp_path: Path) -> None:
    def fn(key: str, mode: str) -> SbyRunResult:
        raise AssertionError("sby must not run when the compile gate fails")

    sby = FakeSby(fn)
    results = discharge(
        _iface(), _pset(),
        duts=[Path("counter.v")],
        yosys=FakeYosys(ok=False, errors="syntax error near 'assrt'"),
        runner=sby,
        workdir=tmp_path,
    )
    by_pid = {r.pid: r for r in results}
    assert by_pid["P1"].verdict is Verdict.ERROR
    assert "syntax error" in by_pid["P1"].detail
    assert sby.jobs == []  # the gate ran before any solver
