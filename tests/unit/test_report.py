"""The report renders the verdict table and is honest about bounded vs unbounded."""

from __future__ import annotations

from pathlib import Path

from toroid.domain.interface import ModuleInterface, Port
from toroid.domain.verdicts import PropertyResult, Verdict
from toroid.pipeline.report import badge, render_report


def _iface() -> ModuleInterface:
    return ModuleInterface(top="counter", ports=(Port("clk", "input", 1, is_clock=True),))


def test_table_has_a_row_per_result() -> None:
    results = [
        PropertyResult("P1", Verdict.PROVEN, "no overflow", engine="abc/pdr", depth=20),
        PropertyResult("P2", Verdict.BOUNDED_PASS, "holds", engine="smtbmc/bitwuzla", depth=20),
    ]
    md = render_report(_iface(), results)
    assert "# Toroid report — `counter`" in md
    assert "`P1`" in md and "`P2`" in md
    assert badge(Verdict.PROVEN) in md
    assert badge(Verdict.BOUNDED_PASS) in md


def test_falsified_property_gets_a_counterexample_section() -> None:
    results = [
        PropertyResult(
            "P9",
            Verdict.FALSIFIED,
            "overflow at depth 16",
            engine="smtbmc/bitwuzla",
            depth=16,
            trace_vcd=Path("work/P9.vcd"),
            detail="At cycle 16 `count` wraps 15 -> 0 while `en` is high.",
        )
    ]
    md = render_report(_iface(), results)
    assert "## Counterexamples" in md
    assert "work/P9.vcd" in md
    assert "wraps 15 -> 0" in md


def test_report_states_the_honesty_caveat() -> None:
    md = render_report(_iface(), [])
    assert "not an" in md and "unbounded proof" in md


def test_error_result_shows_its_compile_diagnostics() -> None:
    # discharge attaches the compile-gate errors to ERROR results; a bare ERROR row
    # with no explanation is useless to the user.
    results = [
        PropertyResult("PE", Verdict.ERROR, "bad property", detail="syntax error near 'foo'")
    ]
    md = render_report(_iface(), results)
    assert "## Errors" in md
    assert "syntax error near 'foo'" in md


def test_footer_does_not_claim_a_solver_run_for_error_or_inconclusive() -> None:
    # THE honesty rule, applied to the report's own prose: ERROR never reached a solver
    # and INCONCLUSIVE never decided, so the blanket "tied to a solver run" must not
    # stand unqualified when either is present.
    for verdict in (Verdict.ERROR, Verdict.INCONCLUSIVE):
        md = render_report(_iface(), [PropertyResult("PX", verdict, "x")])
        assert "not** solver verdicts" in md, verdict
    # ...and with only real solver verdicts, the caveat is not added as noise.
    clean = render_report(_iface(), [PropertyResult("P1", Verdict.PROVEN, "ok")])
    assert "not** solver verdicts" not in clean
