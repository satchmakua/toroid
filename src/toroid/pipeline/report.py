"""Aggregate `PropertyResult`s into a Markdown report. Pure and testable; the
Markdown is the demo screenshot, and the same data serializes to JSON for the
benchmark scripts. See DESIGN.md §6.5.
"""

from __future__ import annotations

from collections.abc import Sequence

from toroid.domain.interface import ModuleInterface
from toroid.domain.verdicts import PropertyResult, Verdict

_BADGE = {
    Verdict.PROVEN: "✅ PROVEN",
    Verdict.BOUNDED_PASS: "🟢 BOUNDED-PASS",
    Verdict.FALSIFIED: "❌ FALSIFIED",
    Verdict.VACUOUS: "⚠️ VACUOUS",
    Verdict.INCONCLUSIVE: "⏱️ INCONCLUSIVE",
    Verdict.ERROR: "🛑 ERROR",
}


def badge(verdict: Verdict) -> str:
    return _BADGE[verdict]


def render_report(interface: ModuleInterface, results: Sequence[PropertyResult]) -> str:
    """Render a verdict table + per-property detail as Markdown."""
    lines: list[str] = []
    lines.append(f"# Toroid report — `{interface.top}`")
    lines.append("")
    lines.append("| Property | Verdict | Engine | Depth | Time (s) |")
    lines.append("|---|---|---|---|---|")
    for r in results:
        depth = "—" if r.depth is None else str(r.depth)
        engine = r.engine or "—"
        lines.append(
            f"| `{r.pid}` {r.summary} | {badge(r.verdict)} | {engine} | "
            f"{depth} | {r.wall_seconds:.2f} |"
        )

    falsified = [r for r in results if r.verdict == Verdict.FALSIFIED]
    if falsified:
        lines.append("")
        lines.append("## Counterexamples")
        for r in falsified:
            lines.append("")
            lines.append(f"### `{r.pid}` — {r.summary}")
            if r.trace_vcd:
                lines.append(f"- waveform: `{r.trace_vcd.as_posix()}`")
            if r.detail:
                lines.append("")
                lines.append("```")
                lines.append(r.detail)
                lines.append("```")

    # A compile-gate failure carries its diagnostics in `detail`; surface them, or the
    # user gets a bare ERROR row with no way to see what went wrong.
    errored = [r for r in results if r.verdict is Verdict.ERROR and r.detail]
    if errored:
        lines.append("")
        lines.append("## Errors")
        for r in errored:
            lines.append("")
            lines.append(f"### `{r.pid}` — {r.summary}")
            lines.append("")
            lines.append("```")
            lines.append(r.detail)
            lines.append("```")

    lines.append("")
    lines.append(
        "_Every PROVEN / BOUNDED-PASS / FALSIFIED / VACUOUS verdict above is tied to a "
        "real solver run — never to a model's say-so. BOUNDED-PASS means no "
        "counterexample within the depth bound, not an unbounded proof._"
    )
    # Don't let the line above overclaim: these two verdicts never came from a solver.
    if any(r.verdict in (Verdict.ERROR, Verdict.INCONCLUSIVE) for r in results):
        lines.append("")
        lines.append(
            "_ERROR and INCONCLUSIVE are **not** solver verdicts: ERROR means the "
            "property never reached a solver (it failed the compile gate), and "
            "INCONCLUSIVE means the solver was cut off (timeout / resource limit) "
            "without deciding._"
        )
    return "\n".join(lines) + "\n"
