"""End-to-end flow via the Yosys-only `sat` backend. This runs whenever *any*
Yosys is available — including the pip-installed `yowasp-yosys` — so it executes on
Windows with no OSS CAD Suite. Opt-in: `pytest -m integration`.

Note: yowasp-yosys runs Yosys as WASM sandboxed to the CWD, so the working dir and
sources must live under the current directory (run pytest from the repo root).
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


def _discharge_sat(props_name: str) -> dict[str, PropertyResult]:
    from inductor.adapters.yosys import YosysCli
    from inductor.adapters.yosys_sat import YosysSatCli
    from inductor.loaders import load_property_set
    from inductor.pipeline.discharge import discharge

    exe = find_yosys()
    assert exe is not None
    dut = REPO / "designs" / "counter.v"
    workdir = REPO / "designs" / "_build" / f"_it_{props_name.replace('.', '_')}"
    shutil.rmtree(workdir, ignore_errors=True)

    yosys = YosysCli(executable=exe)
    iface = yosys.extract_interface([dut], "counter")
    pset = load_property_set(REPO / "designs" / props_name)
    results = discharge(
        iface, pset, duts=[dut], yosys=yosys, runner=YosysSatCli(executable=exe),
        workdir=workdir, depth=20, run_pdr=False,
    )
    return {r.pid: r for r in results}


def test_clean_counter_invariants_pass() -> None:
    by = _discharge_sat("counter.props.json")
    assert by["P1"].verdict in (Verdict.PROVEN, Verdict.BOUNDED_PASS)
    assert by["P2"].verdict in (Verdict.PROVEN, Verdict.BOUNDED_PASS)


def test_overstrong_property_falsified_with_waveform() -> None:
    by = _discharge_sat("counter_bad.props.json")
    assert by["PB"].verdict is Verdict.FALSIFIED
    assert by["PB"].trace_vcd is not None
    assert by["PB"].trace_vcd.exists()
