"""RTL-to-RTL equivalence, live via yosys-sat: two equivalent max2 implementations
prove equivalent; the min-returning impostor is falsified with a distinguishing
input. Combinational, so assumption-free. Opt-in: `pytest -m integration`.
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


def _equiv(file_b: str, top_b: str) -> PropertyResult:
    from inductor.adapters.yosys import YosysCli
    from inductor.adapters.yosys_sat import YosysSatCli
    from inductor.pipeline.equiv import check_equivalence

    exe = find_yosys()
    assert exe is not None
    workdir = REPO / "designs" / "_build" / f"_it_equiv_{top_b}"
    shutil.rmtree(workdir, ignore_errors=True)
    return check_equivalence(
        REPO / "designs" / "max2.v", "max2",
        REPO / "designs" / file_b, top_b,
        yosys=YosysCli(executable=exe), runner=YosysSatCli(executable=exe),
        workdir=workdir, depth=8,
    )


def test_equivalent_implementations_prove() -> None:
    assert _equiv("max2_alt.v", "max2_alt").verdict is Verdict.PROVEN


def test_impostor_is_falsified_with_a_distinguishing_input() -> None:
    res = _equiv("max2_min_bug.v", "max2_min_bug")
    assert res.verdict is Verdict.FALSIFIED
    assert res.trace is not None  # the distinguishing input is captured
