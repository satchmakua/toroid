"""Capture live Claude outputs as replayable fixtures (the standing pattern: run
once with a key, commit the result, replay in CI with no key).

    ANTHROPIC_API_KEY=... python scripts/capture_fixtures.py

Writes tests/fixtures/{counter.synth.json, fifo_full.classify.json}. Re-run to
refresh after a prompt/schema change.
"""

from __future__ import annotations

import json
from pathlib import Path

from inductor.adapters.llm import ClaudeAdapter
from inductor.adapters.recorded import write_classify_fixture
from inductor.adapters.yosys import YosysCli, find_yosys
from inductor.adapters.yosys_sat import YosysSatCli
from inductor.domain.properties import Property, PropertyKind
from inductor.loaders import load_property_set, property_set_to_dict
from inductor.pipeline.discharge import discharge_assert
from inductor.pipeline.synth import synthesize_properties

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures"


def main() -> None:
    exe = find_yosys()
    if exe is None:
        raise SystemExit("No Yosys found (pip install yowasp-yosys).")
    claude = ClaudeAdapter()
    yosys = YosysCli(executable=exe)
    runner = YosysSatCli(executable=exe)
    FIX.mkdir(parents=True, exist_ok=True)

    # 1) Real synthesis on the counter — captured through the SAME pipeline `verify`
    #    uses, so the fixture is the repaired, compile-gated, anti-vacuity-checked set
    #    the live flow would actually discharge (not a raw first attempt that might not
    #    replay). Then round-trip through the replay loader so we never commit a fixture
    #    that RecordedLLM.from_files would reject.
    counter = REPO / "designs" / "counter.v"
    iface = yosys.extract_interface([counter], "counter")
    spec = (REPO / "designs" / "counter.md").read_text(encoding="utf-8")
    synth = synthesize_properties(
        iface, spec, llm=claude, yosys=yosys, duts=[counter],
        workdir=REPO / "designs" / "_build" / "_capture_synth",
    )
    if not synth.compiled:
        raise SystemExit(f"synthesis did not compile after repairs:\n{synth.errors}")
    synth_path = FIX / "counter.synth.json"
    synth_path.write_text(
        json.dumps(property_set_to_dict(synth.pset), indent=2), encoding="utf-8"
    )
    load_property_set(synth_path)  # replay-loader gate: raises if the fixture is invalid
    n_assert = len(synth.pset.asserts())
    print(
        f"counter.synth.json: {len(synth.pset.properties)} properties "
        f"({n_assert} asserts + {len(synth.pset.properties) - n_assert} covers), "
        f"compiled in {synth.attempts} attempt(s)"
    )

    # 2) Real classification of a falsified buggy-FIFO invariant.
    fifo = REPO / "designs" / "fifo_buggy.v"
    fiface = yosys.extract_interface([fifo], "fifo")
    prop = Property(
        "F1", PropertyKind.ASSERT, "full matches count==DEPTH", "full == (count == 3'd4)"
    )
    res = discharge_assert(
        fiface, prop, (), duts=[fifo], runner=runner,
        workdir=REPO / "designs" / "_build" / "_capture", top="fifo_fv",
        depth=20, cover_reachable=None, run_pdr=False,
    )
    assert res.verdict.value == "falsified" and res.trace is not None, res.verdict
    diag = claude.classify_cex(prop, res.trace, fiface)
    write_classify_fixture(FIX / "fifo_full.classify.json", [diag])
    print(f"fifo_full.classify.json: cause={diag.cause.value}")


if __name__ == "__main__":
    main()
