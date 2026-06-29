"""The M4 headline demo, live via yosys-sat: the clean FIFO proves the flag/occupancy
invariants; the buggy FIFO (off-by-one `full`) falsifies F1 with a counterexample
while F2 still holds. Runs wherever a Yosys is available. Opt-in: `pytest -m integration`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from inductor.adapters.yosys import find_yosys
from inductor.domain.verdicts import PropertyResult, Verdict

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(find_yosys() is None, reason="needs a Yosys (pip install yowasp-yosys)"),
]

REPO = Path(__file__).resolve().parents[2]


def _verify(rtl: str) -> dict[str, PropertyResult]:
    from inductor.adapters.yosys import YosysCli
    from inductor.adapters.yosys_sat import YosysSatCli
    from inductor.loaders import load_property_set
    from inductor.pipeline.discharge import discharge

    exe = find_yosys()
    assert exe is not None
    dut = REPO / "designs" / rtl
    workdir = REPO / "designs" / "_build" / f"_it_{rtl.replace('.', '_')}"
    shutil.rmtree(workdir, ignore_errors=True)

    yosys = YosysCli(executable=exe)
    iface = yosys.extract_interface([dut], "fifo")
    pset = load_property_set(REPO / "designs" / "fifo.props.json")
    results = discharge(
        iface, pset, duts=[dut], yosys=yosys, runner=YosysSatCli(executable=exe),
        workdir=workdir, depth=20, run_pdr=False,
    )
    return {r.pid: r for r in results}


def test_clean_fifo_proves_the_invariants() -> None:
    by = _verify("fifo.v")
    assert by["F1"].verdict is Verdict.PROVEN
    assert by["F2"].verdict is Verdict.PROVEN


def test_buggy_fifo_falsifies_the_full_flag_invariant() -> None:
    by = _verify("fifo_buggy.v")
    assert by["F1"].verdict is Verdict.FALSIFIED  # the off-by-one is caught
    assert by["F1"].trace is not None  # with a counterexample trace
    assert by["F2"].verdict is Verdict.PROVEN  # the unaffected invariant still holds
