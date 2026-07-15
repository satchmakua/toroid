"""End-to-end M2 pipeline with a FAKE LLM but REAL Yosys: synthesize → compile-gate
→ discharge via yosys-sat. This verifies everything in the LLM path except the model
call itself (which needs ANTHROPIC_API_KEY — see test_synth_live below). Runs
wherever a Yosys is available. Opt-in: `pytest -m integration`.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from toroid.adapters.yosys import find_yosys
from toroid.domain.interface import ModuleInterface
from toroid.domain.properties import Property, PropertyKind, PropertySet
from toroid.domain.verdicts import Verdict

REPO = Path(__file__).resolve().parents[2]


class _FixedLLM:
    """Stands in for Claude: returns the counter's invariants (what a good model
    would propose), so the rest of the M2 pipeline can be exercised for real."""

    def synthesize(
        self, interface: ModuleInterface, spec: str, *, feedback: str | None = None
    ) -> PropertySet:
        return PropertySet(
            properties=(
                Property("P1", PropertyKind.ASSERT, "no overflow", "count <= 4'd15", origin="llm"),
                Property(
                    "P2", PropertyKind.ASSERT, "holds when disabled",
                    "$initstate || $past(rst) || $past(en) || count == $past(count)",
                    origin="llm",
                ),
                Property("P3", PropertyKind.COVER, "reaches max", "count == 4'd15", origin="llm"),
            )
        )


@pytest.mark.integration
@pytest.mark.skipif(find_yosys() is None, reason="needs a Yosys (pip install yowasp-yosys)")
def test_synth_then_discharge_with_fake_llm() -> None:
    from toroid.adapters.yosys import YosysCli
    from toroid.adapters.yosys_sat import YosysSatCli
    from toroid.pipeline.discharge import discharge
    from toroid.pipeline.synth import synthesize_properties

    exe = find_yosys()
    assert exe is not None
    dut = REPO / "designs" / "counter.v"
    workdir = REPO / "designs" / "_build" / "_it_synth"
    shutil.rmtree(workdir, ignore_errors=True)

    yosys = YosysCli(executable=exe)
    iface = yosys.extract_interface([dut], "counter")
    synth = synthesize_properties(
        iface, (REPO / "designs" / "counter.md").read_text(encoding="utf-8"),
        llm=_FixedLLM(), yosys=yosys, duts=[dut], workdir=workdir,
    )
    assert synth.compiled, synth.errors  # the compile gate accepted the synthesized set

    results = discharge(
        iface, synth.pset, duts=[dut], yosys=yosys, runner=YosysSatCli(executable=exe),
        workdir=workdir, depth=20, run_pdr=False,
    )
    by = {r.pid: r for r in results}
    assert by["P1"].verdict in (Verdict.PROVEN, Verdict.BOUNDED_PASS)
    assert by["P2"].verdict in (Verdict.PROVEN, Verdict.BOUNDED_PASS)


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY for a live model call"
)
@pytest.mark.skipif(find_yosys() is None, reason="needs a Yosys")
def test_synth_live_with_claude() -> None:
    """Real Claude synthesis on the counter → must compile and prove at least one
    property. Runs only when an API key is present."""
    from toroid.adapters.llm import ClaudeAdapter
    from toroid.adapters.yosys import YosysCli
    from toroid.adapters.yosys_sat import YosysSatCli
    from toroid.pipeline.discharge import discharge
    from toroid.pipeline.synth import synthesize_properties

    exe = find_yosys()
    assert exe is not None
    dut = REPO / "designs" / "counter.v"
    workdir = REPO / "designs" / "_build" / "_it_live"
    shutil.rmtree(workdir, ignore_errors=True)

    yosys = YosysCli(executable=exe)
    iface = yosys.extract_interface([dut], "counter")
    synth = synthesize_properties(
        iface, (REPO / "designs" / "counter.md").read_text(encoding="utf-8"),
        llm=ClaudeAdapter(), yosys=yosys, duts=[dut], workdir=workdir,
    )
    assert synth.compiled, synth.errors
    assert synth.pset.asserts(), "model proposed no assertions"

    results = discharge(
        iface, synth.pset, duts=[dut], yosys=yosys, runner=YosysSatCli(executable=exe),
        workdir=workdir, depth=20, run_pdr=False,
    )
    assert any(r.verdict in (Verdict.PROVEN, Verdict.BOUNDED_PASS) for r in results)
