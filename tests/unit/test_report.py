"""The report renders the verdict table and is honest about bounded vs unbounded."""

from __future__ import annotations

from pathlib import Path

from inductor.domain.interface import ModuleInterface, Port
from inductor.domain.verdicts import PropertyResult, Verdict
from inductor.pipeline.report import badge, render_report


def _iface() -> ModuleInterface:
    return ModuleInterface(top="counter", ports=(Port("clk", "input", 1, is_clock=True),))


def test_table_has_a_row_per_result() -> None:
    results = [
        PropertyResult("P1", Verdict.PROVEN, "no overflow", engine="abc/pdr", depth=20),
        PropertyResult("P2", Verdict.BOUNDED_PASS, "holds", engine="smtbmc/bitwuzla", depth=20),
    ]
    md = render_report(_iface(), results)
    assert "# Inductor report — `counter`" in md
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
