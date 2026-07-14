"""Replay the RECORDED Claude synthesis through the real pipeline — this exercises
the LLM path end-to-end with **no API key** (gated only on a Yosys), so CI covers
the M2 flow offline. The fixture in tests/fixtures/counter.synth.json was captured
live via scripts/capture_fixtures.py.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from inductor.adapters.yosys import find_yosys
from inductor.domain.verdicts import Verdict

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(find_yosys() is None, reason="needs a Yosys (pip install yowasp-yosys)"),
]

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "tests" / "fixtures"


def test_recorded_synthesis_compiles_and_proves() -> None:
    from inductor.adapters.recorded import RecordedLLM
    from inductor.adapters.yosys import YosysCli
    from inductor.adapters.yosys_sat import YosysSatCli
    from inductor.pipeline.discharge import discharge
    from inductor.pipeline.synth import synthesize_properties

    exe = find_yosys()
    assert exe is not None
    dut = REPO / "designs" / "counter.v"
    workdir = REPO / "designs" / "_build" / "_it_replay"
    shutil.rmtree(workdir, ignore_errors=True)

    yosys = YosysCli(executable=exe)
    iface = yosys.extract_interface([dut], "counter")
    llm = RecordedLLM.from_files(FIX / "counter.synth.json")

    # The recorded set passes the (real) compile gate...
    synth = synthesize_properties(
        iface, (REPO / "designs" / "counter.md").read_text(encoding="utf-8"),
        llm=llm, yosys=yosys, duts=[dut], workdir=workdir,
    )
    assert synth.compiled, synth.errors
    assert len(synth.pset.asserts()) >= 3  # Claude proposed a real, non-trivial set

    # ...and every synthesized assertion holds on the (correct) counter.
    results = discharge(
        iface, synth.pset, duts=[dut], yosys=yosys, runner=YosysSatCli(executable=exe),
        workdir=workdir, depth=20, run_pdr=False,
    )
    assert results, "no asserts discharged"
    assert all(r.verdict in (Verdict.PROVEN, Verdict.BOUNDED_PASS) for r in results), {
        r.pid: r.verdict.value for r in results
    }
