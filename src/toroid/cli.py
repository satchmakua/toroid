"""Toroid command-line interface.

    toroid verify <rtl...> --spec <md> --top <name> [--depth 20] [--max-refine 5]
    toroid extract <rtl...> --top <name>     # interface model only (debug)
    toroid demo                              # offline showcase: render + report
    toroid version

`demo` runs end-to-end with no external toolchain (the walking-skeleton path).
`verify`/`extract` need the OSS CAD Suite (yosys + sby) and print setup guidance
when it is missing. See DESIGN.md §6.6 and ROADMAP.md.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from toroid import __version__
from toroid.domain.interface import ModuleInterface, Port
from toroid.domain.policy import DEFAULT_BMC_DEPTH, DEFAULT_MAX_REFINE, decide_verdict
from toroid.domain.properties import Property, PropertyKind, PropertySet
from toroid.domain.verdicts import PropertyResult, RawOutcome, Verdict
from toroid.pipeline.report import render_report
from toroid.render.checker import render_wrapper

if TYPE_CHECKING:
    from toroid.adapters.sby import SbyJobRunner
    from toroid.adapters.yosys import YosysAdapter
    from toroid.pipeline.refine import CexClassifier, RefineOutcome

_NO_YOSYS_HELP = (
    "No Yosys found. Either:\n"
    "  • `pip install yowasp-yosys`  (lightweight, runs the built-in `sat` backend; "
    "works on Windows), or\n"
    "  • install the full OSS CAD Suite for the SymbiYosys + Bitwuzla backend "
    "(https://github.com/YosysHQ/oss-cad-suite-build; WSL2 on Windows).\n"
    "Meanwhile, `toroid demo` runs fully offline."
)


def _demo_interface() -> ModuleInterface:
    """A small 4-bit saturating counter — the canonical M0/M1 sample DUT."""
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


def _demo_property_set() -> PropertySet:
    return PropertySet(
        properties=(
            Property(
                pid="P1",
                kind=PropertyKind.ASSERT,
                summary="count never exceeds its max (no overflow)",
                expr="count <= 4'd15",
                rationale="4-bit saturating counter must stay within [0, 15].",
                origin="human",
            ),
            Property(
                pid="P2",
                kind=PropertyKind.ASSERT,
                summary="when disabled and out of reset, count holds",
                expr="$initstate || $past(rst) || $past(en) || count == $past(count)",
                rationale="en low => value is retained.",
                origin="human",
            ),
            Property(
                pid="P3",
                kind=PropertyKind.COVER,
                summary="the counter can actually reach its max (anti-vacuity)",
                expr="count == 4'd15",
                rationale="If unreachable, P1 would pass vacuously.",
                origin="human",
            ),
        )
    )


def _demo_results() -> list[PropertyResult]:
    """Illustrate the honesty layer: feed raw outcomes through the real policy."""
    p1 = decide_verdict(RawOutcome(prove_pass=True, cover_reachable=True, depth=20))
    p2 = decide_verdict(RawOutcome(bmc_pass=True, prove_pass=False, cover_reachable=True, depth=20))
    return [
        PropertyResult("P1", p1, "no overflow", engine="abc/pdr", depth=20, wall_seconds=0.41),
        PropertyResult(
            "P2", p2, "holds when disabled",
            engine="smtbmc/bitwuzla", depth=20, wall_seconds=0.18,
        ),
    ]


def _cmd_equiv(args: argparse.Namespace) -> int:
    from toroid.adapters.yosys import YosysCli, find_yosys
    from toroid.adapters.yosys_sat import YosysSatCli
    from toroid.pipeline.equiv import check_equivalence

    yosys_exe = find_yosys()
    if yosys_exe is None:
        print(f"error: {_NO_YOSYS_HELP}", file=sys.stderr)
        return 2

    spec, impl = Path(args.spec), Path(args.impl)
    workdir = (
        Path(args.workdir) if args.workdir
        else spec.parent / "_build" / f"equiv_{args.top_a}_{args.top_b}"
    )
    result = check_equivalence(
        spec, args.top_a, impl, args.top_b,
        yosys=YosysCli(executable=yosys_exe), runner=YosysSatCli(executable=yosys_exe),
        workdir=workdir, depth=args.depth,
    )
    report = render_report(ModuleInterface(top=f"{args.top_a} vs {args.top_b}", ports=()), [result])
    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")
        print(f"wrote report to {args.report}")
    else:
        print(report)
    return 1 if result.verdict in (Verdict.FALSIFIED, Verdict.ERROR) else 0


def _cmd_demo(_: argparse.Namespace) -> int:
    iface = _demo_interface()
    pset = _demo_property_set()
    print("# Rendered formal wrapper (designs/_build/counter_fv.sv)\n")
    print(render_wrapper(iface, pset))
    print(render_report(iface, _demo_results()))
    print("(demo: no solver was run — verdicts above illustrate the policy layer.)")
    return 0


def _cmd_version(_: argparse.Namespace) -> int:
    print(f"toroid {__version__}")
    return 0


def _format_refinement(outcome: RefineOutcome) -> str:
    lines = [f"Refinement: {outcome.rounds} round(s) -> {outcome.stop_reason}."]
    for s in outcome.steps:
        if s.diagnosis is not None:
            lines.append(f"  round {s.round}: {s.diagnosis.cause.value} - {s.note}")
        else:
            lines.append(f"  round {s.round}: {s.verdict.value} - {s.note}")
    return "\n".join(lines)


def _refine_falsified(
    results: list[PropertyResult],
    interface: ModuleInterface,
    pset: PropertySet,
    *,
    duts: list[Path],
    yosys: YosysAdapter,
    runner: SbyJobRunner,
    classifier: CexClassifier,
    workdir: Path,
    depth: int,
    max_rounds: int,
    run_pdr: bool,
) -> list[PropertyResult]:
    from dataclasses import replace

    from toroid.pipeline.refine import refine_property

    asserts = {p.pid: p for p in pset.asserts()}
    assumes, covers = pset.assumes(), pset.covers()
    out: list[PropertyResult] = []
    for r in results:
        if r.verdict is not Verdict.FALSIFIED or r.pid not in asserts:
            out.append(r)
            continue
        outcome = refine_property(
            interface, asserts[r.pid], assumes, covers, duts=duts, yosys=yosys,
            runner=runner, classifier=classifier, workdir=workdir / "refine" / r.pid,
            depth=depth, max_rounds=max_rounds, run_pdr=run_pdr,
        )
        note = _format_refinement(outcome)
        fr = outcome.result
        detail = note + (f"\n\n{fr.detail}" if fr.detail else "")
        out.append(replace(fr, detail=detail))
    return out


def _cmd_verify(args: argparse.Namespace) -> int:
    from toroid.adapters import toolchain_status
    from toroid.adapters.sby import SbyCli
    from toroid.adapters.yosys import YosysCli, find_yosys
    from toroid.adapters.yosys_sat import YosysSatCli
    from toroid.pipeline.discharge import discharge

    yosys_exe = find_yosys()
    if yosys_exe is None:
        print(f"error: {_NO_YOSYS_HELP}", file=sys.stderr)
        return 2

    backend = args.backend
    if backend == "auto":
        backend = "sby" if toolchain_status().sby else "yosys-sat"
    if backend == "sby" and not toolchain_status().sby:
        print("error: --backend sby needs SymbiYosys (sby) on PATH.", file=sys.stderr)
        return 2

    rtl = [Path(r) for r in args.rtl]
    dut = rtl[0]
    workdir = Path(args.workdir) if args.workdir else dut.parent / "_build" / args.top
    yosys = YosysCli(executable=yosys_exe)
    interface = yosys.extract_interface(rtl, args.top)

    # Obtain the property set — hand-written (--no-llm) or LLM-synthesized.
    classifier: CexClassifier | None = None
    if args.no_llm:
        from toroid.loaders import load_property_set

        props_path = Path(args.props) if args.props else dut.with_name(f"{args.top}.props.json")
        if not props_path.exists():
            print(f"error: property file not found: {props_path}", file=sys.stderr)
            print("Pass --props, or place <top>.props.json next to the RTL.", file=sys.stderr)
            return 2
        pset = load_property_set(props_path)
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print(
                "error: LLM synthesis needs ANTHROPIC_API_KEY (or use --no-llm with a "
                "property file). Get a key at https://console.anthropic.com/.",
                file=sys.stderr,
            )
            return 2
        from toroid.adapters.llm import ClaudeAdapter
        from toroid.pipeline.synth import synthesize_properties

        claude = ClaudeAdapter()
        classifier = claude  # reused for the refinement loop below
        spec = Path(args.spec).read_text(encoding="utf-8") if args.spec else ""
        synth = synthesize_properties(
            interface, spec, llm=claude, yosys=yosys, duts=rtl,
            workdir=workdir, max_repairs=args.max_repairs,
        )
        print(
            f"# synthesized {len(synth.pset.properties)} properties "
            f"in {synth.attempts} attempt(s)",
            file=sys.stderr,
        )
        if not synth.compiled:
            print(
                f"error: could not synthesize compiling properties after "
                f"{synth.attempts} attempt(s):\n{synth.errors}",
                file=sys.stderr,
            )
            return 1
        pset = synth.pset

    runner: SbyJobRunner = SbyCli() if backend == "sby" else YosysSatCli(executable=yosys_exe)
    results = discharge(
        interface, pset, duts=rtl, yosys=yosys, runner=runner,
        workdir=workdir, depth=args.depth, run_pdr=(backend == "sby"),
    )

    # Counterexample loop: classify + refine any falsified property (LLM path).
    if classifier is not None and not args.no_refine and any(
        r.verdict is Verdict.FALSIFIED for r in results
    ):
        results = _refine_falsified(
            results, interface, pset, duts=rtl, yosys=yosys, runner=runner,
            classifier=classifier, workdir=workdir, depth=args.depth,
            max_rounds=args.max_refine, run_pdr=(backend == "sby"),
        )

    print(f"# backend: {backend}", file=sys.stderr)
    report = render_report(interface, results)
    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")
        print(f"wrote report to {args.report}")
    else:
        print(report)

    bad = any(r.verdict in (Verdict.FALSIFIED, Verdict.ERROR) for r in results)
    return 1 if bad else 0


def _cmd_extract(args: argparse.Namespace) -> int:
    from toroid.adapters.yosys import YosysCli, find_yosys

    yosys_exe = find_yosys()
    if yosys_exe is None:
        print(f"error: {_NO_YOSYS_HELP}", file=sys.stderr)
        return 2

    rtl = [Path(r) for r in args.rtl]
    interface = YosysCli(executable=yosys_exe).extract_interface(rtl, args.top)
    print(f"module {interface.top}  (clock={interface.clock}, reset={interface.reset})")
    for p in interface.ports:
        tags = "".join(t for t, on in (("clk", p.is_clock), ("rst", p.is_reset)) if on)
        width = f"[{p.width - 1}:0]" if p.is_vector else "     "
        print(f"  {p.direction:6} {width} {p.name}  {tags}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="toroid", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    p_verify = sub.add_parser("verify", help="synthesize and discharge properties for a module")
    p_verify.add_argument("rtl", nargs="+", help="RTL source file(s)")
    p_verify.add_argument("--spec", help="natural-language spec (markdown)")
    p_verify.add_argument("--top", required=True, help="top module name")
    p_verify.add_argument("--depth", type=int, default=DEFAULT_BMC_DEPTH, help="BMC depth")
    p_verify.add_argument(
        "--max-refine", type=int, default=DEFAULT_MAX_REFINE, help="CEX refinement cap"
    )
    p_verify.add_argument(
        "--max-repairs", type=int, default=3, help="LLM synthesis repair attempts"
    )
    p_verify.add_argument(
        "--no-refine", action="store_true", help="skip the LLM counterexample-refinement loop"
    )
    p_verify.add_argument(
        "--backend", choices=("auto", "sby", "yosys-sat"), default="auto",
        help="discharge backend. 'sby' (SymbiYosys+Bitwuzla, needs the OSS CAD Suite) "
        "honors assume cells and discharges covers, so it can prove assume-dependent "
        "properties and catch VACUOUS passes. 'yosys-sat' (built-in minisat, Yosys-only) "
        "needs no external solver but ignores assume cells (ADR-0004). Both narrate "
        "counterexamples cycle-by-cycle. auto picks sby when it is on PATH, else "
        "yosys-sat.",
    )
    p_verify.add_argument("--no-llm", action="store_true", help="use a hand-written property file")
    p_verify.add_argument("--props", help="property file (JSON); default: <top>.props.json")
    p_verify.add_argument("--workdir", help="working dir for sby jobs")
    p_verify.add_argument("--report", help="write the report to this path")
    p_verify.set_defaults(func=_cmd_verify)

    p_extract = sub.add_parser("extract", help="print the extracted interface model (debug)")
    p_extract.add_argument("rtl", nargs="+", help="RTL source file(s)")
    p_extract.add_argument("--top", required=True, help="top module name")
    p_extract.set_defaults(func=_cmd_extract)

    p_equiv = sub.add_parser(
        "equiv", help="prove two designs equivalent (or find a counterexample)"
    )
    p_equiv.add_argument("spec", help="first RTL file")
    p_equiv.add_argument("impl", help="second RTL file")
    p_equiv.add_argument("--top-a", required=True, help="top module in the first file")
    p_equiv.add_argument("--top-b", required=True, help="top module in the second file")
    p_equiv.add_argument("--depth", type=int, default=DEFAULT_BMC_DEPTH, help="BMC depth")
    p_equiv.add_argument("--workdir", help="working dir for sby jobs")
    p_equiv.add_argument("--report", help="write the report to this path")
    p_equiv.set_defaults(func=_cmd_equiv)

    p_demo = sub.add_parser("demo", help="offline showcase: render a wrapper + a sample report")
    p_demo.set_defaults(func=_cmd_demo)

    p_version = sub.add_parser("version", help="print the version")
    p_version.set_defaults(func=_cmd_version)

    return parser


def _force_utf8_stdout() -> None:
    """Avoid UnicodeEncodeError when printing report glyphs to a legacy
    (cp1252) Windows console. No-op where stdout can't be reconfigured."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv: Sequence[str] | None = None) -> int:
    _force_utf8_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 0
    return int(func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
