"""Discharge a `PropertySet` against a DUT and produce per-property verdicts.

See DESIGN.md §6.3. Strategy for M1: **one assert per sby run** so verdict
attribution is trivial and robust (the task-level PASS/FAIL *is* that property's
result). For each assert we run BMC and k-induction (smtbmc/bitwuzla) plus PDR
(abc/pdr); reachability is one `cover` run over the set's covers. Outcomes are
mapped to verdicts by the pure `decide_verdict` policy.

The adapters are injected (`YosysAdapter`, `SbyJobRunner`), so this whole
composition is unit-tested offline with fakes — only the adapters touch the
toolchain.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path

from toroid.adapters.sby import SbyJob, SbyJobRunner, SbyMode, SbyRunResult
from toroid.adapters.yosys import YosysAdapter
from toroid.domain.interface import ModuleInterface
from toroid.domain.policy import decide_verdict
from toroid.domain.properties import Property, PropertySet
from toroid.domain.trace import summarize_trace
from toroid.domain.verdicts import PropertyResult, RawOutcome, Verdict
from toroid.render.checker import render_wrapper

SMT = "smtbmc bitwuzla"
PDR = "abc pdr"


def _write_wrapper(interface: ModuleInterface, pset: PropertySet, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_wrapper(interface, pset), encoding="utf-8")
    return dest


def _sources_for(
    duts: Sequence[Path], wrapper: Path
) -> tuple[tuple[str, ...], tuple[Path, ...]]:
    """(script basenames, [files] paths). sby copies file_paths into its src/, and
    the script reads them by basename."""
    paths = (*duts, wrapper)
    return tuple(p.name for p in paths), paths


def discharge(
    interface: ModuleInterface,
    pset: PropertySet,
    *,
    duts: Sequence[Path],
    yosys: YosysAdapter,
    runner: SbyJobRunner,
    workdir: Path,
    depth: int = 20,
    run_pdr: bool = True,
) -> list[PropertyResult]:
    top = f"{interface.top}_fv"
    assumes = pset.assumes()

    # 1) Compile gate on the full wrapper — a malformed property never reaches a solver.
    full = _write_wrapper(interface, pset, workdir / f"{top}.sv")
    gate = yosys.compile_check(list(duts), full, top)
    if not gate.ok:
        return [
            PropertyResult(p.pid, Verdict.ERROR, p.summary, detail=gate.errors)
            for p in pset.asserts()
        ]

    # 2) Reachability: one cover run over the set's covers (anti-vacuity witness).
    cover_reachable = check_cover_reachable(
        interface, assumes, pset.covers(), duts=duts, runner=runner,
        workdir=workdir / "cover", top=top, depth=depth,
    )

    # 3) One run-group per assert.
    results: list[PropertyResult] = []
    for prop in pset.asserts():
        results.append(
            discharge_assert(
                interface, prop, assumes, duts=duts, runner=runner,
                workdir=workdir / prop.pid, top=top, depth=depth,
                cover_reachable=cover_reachable, run_pdr=run_pdr,
            )
        )
    return results


def check_cover_reachable(
    interface: ModuleInterface,
    assumes: tuple[Property, ...],
    covers: tuple[Property, ...],
    *,
    duts: Sequence[Path],
    runner: SbyJobRunner,
    workdir: Path,
    top: str,
    depth: int,
) -> bool | None:
    """Run `cover` over the covers under the given assumptions. Tri-state: pass ->
    reachable, fail -> unreachable, anything else -> unchecked (None, so it never
    falsely trips the vacuity guard). This is the anti-vacuity witness."""
    if not covers:
        return None
    wrap = _write_wrapper(interface, PropertySet((*assumes, *covers)), workdir / f"{top}.sv")
    names, paths = _sources_for(duts, wrap)
    cov = runner.run_job(SbyJob("cover", workdir, names, paths, top, "cover", depth, SMT))
    return {"pass": True, "fail": False}.get(cov.status)


def discharge_assert(
    interface: ModuleInterface,
    prop: Property,
    assumes: tuple[Property, ...],
    *,
    duts: Sequence[Path],
    runner: SbyJobRunner,
    workdir: Path,
    top: str,
    depth: int,
    cover_reachable: bool | None,
    run_pdr: bool,
) -> PropertyResult:
    pset = PropertySet(properties=(*assumes, prop))
    wrapper = _write_wrapper(interface, pset, workdir / f"{top}.sv")
    names, paths = _sources_for(duts, wrapper)

    def job(name: str, mode: SbyMode, engine: str) -> SbyRunResult:
        return runner.run_job(
            SbyJob(name, workdir / name, names, paths, top, mode, depth, engine)
        )

    t0 = time.monotonic()
    bmc = job("bmc", "bmc", SMT)
    prove = job("prove", "prove", SMT)
    pdr = job("pdr", "prove", PDR) if run_pdr else None
    elapsed = time.monotonic() - t0

    falsified = bmc.status == "fail" or (prove.status == "fail" and prove.basecase_failed)
    errored = bmc.status == "error" or prove.status == "error"
    inconclusive = bmc.status in ("unknown", "timeout") and prove.status != "pass"

    outcome = RawOutcome(
        bmc_pass=bmc.status == "pass",
        prove_pass=prove.status == "pass",
        pdr_pass=(pdr.status == "pass") if pdr else None,
        cover_reachable=cover_reachable,
        depth=depth,
        falsified=falsified,
        error=errored,
        inconclusive=inconclusive,
    )
    verdict = decide_verdict(outcome)

    engine, used_depth, vcd, yw, detail = _attribute(verdict, bmc, prove, pdr)

    # On a counterexample, parse the trace and attach a deterministic narration.
    trace = None
    if verdict is Verdict.FALSIFIED:
        src = bmc if bmc.status == "fail" else prove
        signal_names = [p.name for p in interface.ports if not p.is_clock]
        trace = runner.parse_trace(src, signal_names)
        if trace is not None:
            detail = summarize_trace(trace)

    return PropertyResult(
        pid=prop.pid,
        verdict=verdict,
        summary=prop.summary,
        engine=engine,
        depth=used_depth,
        trace_vcd=vcd,
        trace_yw=yw,
        trace=trace,
        wall_seconds=elapsed,
        detail=detail,
    )


def _attribute(
    verdict: Verdict,
    bmc: SbyRunResult,
    prove: SbyRunResult,
    pdr: SbyRunResult | None,
) -> tuple[str | None, int | None, Path | None, Path | None, str]:
    """Pick the engine/depth/trace that produced the verdict (engine label comes
    from the run that actually decided it, so it's accurate per backend)."""
    if verdict is Verdict.FALSIFIED:
        src = bmc if bmc.status == "fail" else prove
        return src.engine, src.depth, src.trace_vcd, src.trace_yw, ""
    if verdict is Verdict.PROVEN:
        if prove.status == "pass":
            return prove.engine, None, None, None, ""
        if pdr is not None and pdr.status == "pass":
            return pdr.engine, None, None, None, ""
    if verdict is Verdict.BOUNDED_PASS:
        return bmc.engine, bmc.depth, None, None, ""
    return None, bmc.depth, None, None, ""
