"""RTL-to-RTL equivalence checking (DESIGN.md §7, M4-stretch). Builds a miter from
two designs sharing one interface and discharges "outputs always equal". PROVEN means
equivalent; FALSIFIED yields a distinguishing input — the hardware sibling of
Congruent's software equivalence checking.

Combinational equivalence is assumption-free, so it runs on the yosys-sat backend
(no reset needed). Sequential equivalence with differing reset states needs the sby
backend (assumptions) — same backend split as the rest of the project (ADR-0004).
"""

from __future__ import annotations

from pathlib import Path

from toroid.adapters.sby import SbyJob, SbyJobRunner, SbyMode, SbyRunResult
from toroid.adapters.yosys import YosysAdapter
from toroid.domain.interface import ModuleInterface
from toroid.domain.policy import decide_verdict
from toroid.domain.trace import summarize_trace
from toroid.domain.verdicts import PropertyResult, RawOutcome, Verdict
from toroid.render.equiv import render_equiv_wrapper

ENGINE = "yosys-sat"
TOP = "equiv_fv"


def _port_mismatch(a: ModuleInterface, b: ModuleInterface) -> str:
    sig_a = {(p.name, p.direction, p.width) for p in a.ports}
    sig_b = {(p.name, p.direction, p.width) for p in b.ports}
    if sig_a == sig_b:
        return ""
    only_a = sorted(sig_a - sig_b)
    only_b = sorted(sig_b - sig_a)
    return f"interfaces differ — only in {a.top}: {only_a}; only in {b.top}: {only_b}"


def check_equivalence(
    spec: Path,
    top_a: str,
    impl: Path,
    top_b: str,
    *,
    yosys: YosysAdapter,
    runner: SbyJobRunner,
    workdir: Path,
    depth: int = 20,
) -> PropertyResult:
    summary = f"{top_a} ≡ {top_b}"
    iface_a = yosys.extract_interface([spec], top_a)
    iface_b = yosys.extract_interface([impl], top_b)

    mismatch = _port_mismatch(iface_a, iface_b)
    if mismatch:
        return PropertyResult("EQ", Verdict.ERROR, summary, detail=mismatch)

    workdir.mkdir(parents=True, exist_ok=True)
    wrapper = workdir / f"{TOP}.sv"
    wrapper.write_text(render_equiv_wrapper(iface_a, top_a, top_b), encoding="utf-8")

    gate = yosys.compile_check([spec, impl], wrapper, TOP)
    if not gate.ok:
        return PropertyResult("EQ", Verdict.ERROR, summary, detail=gate.errors)

    paths = (spec, impl, wrapper)
    names = tuple(p.name for p in paths)
    signals = (
        [p.name for p in iface_a.inputs() if not p.is_clock]
        + [f"a_{p.name}" for p in iface_a.outputs()]
        + [f"b_{p.name}" for p in iface_a.outputs()]
    )

    def job(name: str, mode: SbyMode) -> SbyRunResult:
        return runner.run_job(
            SbyJob(name, workdir / name, names, paths, TOP, mode, depth, ENGINE)
        )

    bmc = job("bmc", "bmc")
    prove = job("prove", "prove")

    outcome = RawOutcome(
        bmc_pass=bmc.status == "pass",
        prove_pass=prove.status == "pass",
        cover_reachable=None,
        depth=depth,
        falsified=bmc.status == "fail",
        error=bmc.status == "error" or prove.status == "error",
        inconclusive=bmc.status in ("unknown", "timeout") and prove.status != "pass",
    )
    verdict = decide_verdict(outcome)

    trace = None
    detail = ""
    engine = prove.engine if verdict is Verdict.PROVEN else bmc.engine
    if verdict is Verdict.FALSIFIED:
        trace = runner.parse_trace(bmc, signals)
        if trace is not None:
            detail = summarize_trace(trace)

    return PropertyResult(
        "EQ", verdict, summary, engine=engine,
        depth=None if verdict is Verdict.PROVEN else depth,
        trace=trace, detail=detail,
    )
