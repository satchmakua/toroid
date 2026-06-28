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
import sys
from collections.abc import Sequence

from inductor import __version__
from inductor.adapters import toolchain_status
from inductor.domain.interface import ModuleInterface, Port
from inductor.domain.policy import DEFAULT_BMC_DEPTH, DEFAULT_MAX_REFINE, decide_verdict
from inductor.domain.properties import Property, PropertyKind, PropertySet
from inductor.domain.verdicts import PropertyResult, RawOutcome
from inductor.pipeline.report import render_report
from inductor.render.checker import render_wrapper

_TOOLCHAIN_HELP = (
    "The open formal toolchain (yosys + sby) was not found on PATH.\n"
    "Install the OSS CAD Suite: https://github.com/YosysHQ/oss-cad-suite-build\n"
    "On Windows, run Inductor inside WSL2 (Ubuntu) with the suite on PATH.\n"
    "Meanwhile, try `inductor demo` — it runs fully offline."
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


def _require_toolchain() -> int | None:
    status = toolchain_status()
    if status.ready:
        return None
    missing = ", ".join(status.missing())
    print(f"error: missing tool(s): {missing}\n", file=sys.stderr)
    print(_TOOLCHAIN_HELP, file=sys.stderr)
    return 2


def _cmd_verify(args: argparse.Namespace) -> int:
    rc = _require_toolchain()
    if rc is not None:
        return rc
    # The real pipeline (ingest -> synth -> render -> discharge -> refine -> report)
    # is wired milestone by milestone; see ROADMAP.md (M1+).
    print(
        f"verify: toolchain present — pipeline for {args.rtl} (top={args.top}, "
        f"depth={args.depth}) lands in M1+.",
        file=sys.stderr,
    )
    raise NotImplementedError("The verification pipeline lands in M1 (see ROADMAP.md).")


def _cmd_extract(args: argparse.Namespace) -> int:
    rc = _require_toolchain()
    if rc is not None:
        return rc
    raise NotImplementedError("Interface extraction lands in M1 (see ROADMAP.md).")


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
    p_verify.add_argument("--engine", default="bitwuzla", help="solver engine")
    p_verify.add_argument("--no-llm", action="store_true", help="use a hand-written property file")
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
