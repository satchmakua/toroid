"""Inductor command-line interface.

    inductor verify <rtl...> --spec <md> --top <name> [--depth 20] [--max-refine 5]
    inductor extract <rtl...> --top <name>     # interface model only (debug)
    inductor demo                              # offline showcase: render + report
    inductor version

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

from inductor import __version__
from inductor.domain.interface import ModuleInterface, Port
from inductor.domain.policy import DEFAULT_BMC_DEPTH, DEFAULT_MAX_REFINE, decide_verdict
from inductor.domain.properties import Property, PropertyKind, PropertySet
from inductor.domain.verdicts import PropertyResult, RawOutcome, Verdict
from inductor.pipeline.report import render_report
from inductor.render.checker import render_wrapper

_NO_YOSYS_HELP = (
    "No Yosys found. Either:\n"
    "  • `pip install yowasp-yosys`  (lightweight, runs the built-in `sat` backend; "
    "works on Windows), or\n"
    "  • install the full OSS CAD Suite for the SymbiYosys + Bitwuzla backend "
    "(https://github.com/YosysHQ/oss-cad-suite-build; WSL2 on Windows).\n"
    "Meanwhile, `inductor demo` runs fully offline."
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
        internal_signals=(),
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


def _cmd_demo(_: argparse.Namespace) -> int:
    iface = _demo_interface()
    pset = _demo_property_set()
    print("# Rendered formal wrapper (designs/_build/counter_fv.sv)\n")
    print(render_wrapper(iface, pset))
    print(render_report(iface, _demo_results()))
    print("(demo: no solver was run — verdicts above illustrate the policy layer.)")
    return 0


def _cmd_version(_: argparse.Namespace) -> int:
    print(f"inductor {__version__}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    from inductor.adapters import toolchain_status
    from inductor.adapters.sby import SbyCli, SbyJobRunner
    from inductor.adapters.yosys import YosysCli, find_yosys
    from inductor.adapters.yosys_sat import YosysSatCli
    from inductor.pipeline.discharge import discharge

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
    if args.no_llm:
        from inductor.loaders import load_property_set

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
        from inductor.adapters.llm import ClaudeAdapter
        from inductor.pipeline.synth import synthesize_properties

        spec = Path(args.spec).read_text(encoding="utf-8") if args.spec else ""
        synth = synthesize_properties(
            interface, spec, llm=ClaudeAdapter(), yosys=yosys, duts=rtl,
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
    from inductor.adapters.yosys import YosysCli, find_yosys

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
    parser = argparse.ArgumentParser(prog="inductor", description=__doc__)
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
    p_verify.add_argument("--engine", default="bitwuzla", help="solver engine (sby backend)")
    p_verify.add_argument(
        "--backend", choices=("auto", "sby", "yosys-sat"), default="auto",
        help="discharge backend: 'sby' (SymbiYosys+Bitwuzla, needs OSS CAD Suite) or "
        "'yosys-sat' (built-in minisat, Yosys-only). auto picks sby if available.",
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
