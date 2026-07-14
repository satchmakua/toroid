"""End-to-end M1 flow against the real toolchain. Skipped cleanly when yosys/sby
are absent (e.g. on Windows without WSL2), so unit CI stays green everywhere.

Run explicitly with: pytest -m integration  (needs the OSS CAD Suite on PATH).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from inductor.adapters import toolchain_status
from inductor.domain.verdicts import Verdict

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not toolchain_status().ready, reason="needs yosys + sby on PATH"),
]

REPO = Path(__file__).resolve().parents[2]


def _discharge(props_name: str, tmp_path: Path) -> dict[str, Verdict]:
    from inductor.adapters.sby import SbyCli
    from inductor.adapters.yosys import YosysCli
    from inductor.loaders import load_property_set
    from inductor.pipeline.discharge import discharge

    dut = REPO / "designs" / "counter.v"
    yosys = YosysCli()
    iface = yosys.extract_interface([dut], "counter")
    pset = load_property_set(REPO / "designs" / props_name)
    results = discharge(
        iface, pset, duts=[dut], yosys=yosys, runner=SbyCli(), workdir=tmp_path, depth=20
    )
    return {r.pid: r.verdict for r in results}


def test_clean_counter_proves_or_bounded(tmp_path: Path) -> None:
    verdicts = _discharge("counter.props.json", tmp_path)
    assert verdicts["P1"] in (Verdict.PROVEN, Verdict.BOUNDED_PASS)
    assert verdicts["P2"] in (Verdict.PROVEN, Verdict.BOUNDED_PASS)


def test_overstrong_property_is_falsified(tmp_path: Path) -> None:
    verdicts = _discharge("counter_bad.props.json", tmp_path)
    assert verdicts["PB"] is Verdict.FALSIFIED


def test_assume_is_honored_on_sby(tmp_path: Path) -> None:
    # ADR-0004 lift: PA holds ONLY because the wrapper's assume cell is honored, so it
    # PROVES on sby (the yosys-sat backend ignores assumes and reports it FALSIFIED).
    verdicts = _discharge("counter_assume.props.json", tmp_path)
    assert verdicts["PA"] is Verdict.PROVEN


def test_vacuous_pass_is_caught_on_sby(tmp_path: Path) -> None:
    # The anti-vacuity guard: PV passes only vacuously (its cover is unreachable under
    # the assumption), so it must be reported VACUOUS, never PROVEN.
    verdicts = _discharge("counter_vacuous.props.json", tmp_path)
    assert verdicts["PV"] is Verdict.VACUOUS
