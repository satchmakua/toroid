"""The counterexample refinement loop, tested fully offline with fake adapters.
Covers the load-bearing guarantees: an over-strong property gets refined and
resolves, an RTL bug is terminal, the anti-vacuity guard rejects an over-constraining
assumption, and the loop terminates at the round cap.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from toroid.adapters.llm import CexCause, CexDiagnosis
from toroid.adapters.sby import SbyJob, SbyRunResult
from toroid.adapters.yosys import CompileResult
from toroid.domain.interface import ModuleInterface, Port
from toroid.domain.properties import Property, PropertyKind
from toroid.domain.trace import Trace
from toroid.pipeline.refine import refine_property


def _iface() -> ModuleInterface:
    return ModuleInterface(
        top="counter",
        ports=(Port("clk", "input", 1, is_clock=True), Port("count", "output", 4)),
        clock="clk",
    )


_PROP = Property("PB", PropertyKind.ASSERT, "too strict", "count <= 4'd10")
_COVER = Property("Pc", PropertyKind.COVER, "reaches max", "count == 4'd15")
_TRACE = Trace(signals=("count",), steps=({"count": 6}, {"count": 11}), failing_step=1)


class FakeYosys:
    def extract_interface(self, sources: list[Path], top: str) -> ModuleInterface:
        raise NotImplementedError

    def compile_check(self, sources: list[Path], wrapper: Path, top: str) -> CompileResult:
        return CompileResult(ok=True)


class FakeRunner:
    """bmc status per round drives FALSIFIED vs resolved; cover checks pass unless in
    a 'vacuity' workdir (so the anti-vacuity guard can be exercised)."""

    def __init__(self, bmc_by_round: list[str]) -> None:
        self.bmc_by_round = bmc_by_round

    @staticmethod
    def _round(job: SbyJob) -> int:
        for part in job.workdir.parts:
            if len(part) > 1 and part[0] == "r" and part[1:].isdigit():
                return int(part[1:])
        return 0

    def run_job(self, job: SbyJob) -> SbyRunResult:
        if job.mode == "cover":
            unreachable = "vacuity" in job.workdir.parts
            return SbyRunResult("fail" if unreachable else "pass", "cover", "fake", job.depth)
        rnd = self._round(job)
        status = self.bmc_by_round[rnd] if rnd < len(self.bmc_by_round) else "fail"
        return SbyRunResult(status, job.mode, "fake", job.depth)  # type: ignore[arg-type]

    def parse_trace(self, result: SbyRunResult, signal_names: Sequence[str]) -> Trace | None:
        return _TRACE if result.status == "fail" else None


class FakeClassifier:
    def __init__(self, diagnoses: list[CexDiagnosis]) -> None:
        self.diagnoses = diagnoses
        self.calls = 0

    def classify_cex(
        self, prop: Property, trace: Trace, interface: ModuleInterface
    ) -> CexDiagnosis:
        d = self.diagnoses[min(self.calls, len(self.diagnoses) - 1)]
        self.calls += 1
        return d


def _refine(runner: FakeRunner, classifier: FakeClassifier, tmp_path: Path, *, max_rounds: int = 5):
    return refine_property(
        _iface(), _PROP, (), (_COVER,), duts=[Path("counter.v")], yosys=FakeYosys(),
        runner=runner, classifier=classifier, workdir=tmp_path, max_rounds=max_rounds,
    )


def test_over_strong_is_refined_and_resolves(tmp_path: Path) -> None:
    fixed = Property("PB", PropertyKind.ASSERT, "fixed", "count <= 4'd15")
    out = _refine(
        FakeRunner(["fail", "pass"]),  # falsified, then holds after the patch
        FakeClassifier([CexDiagnosis(CexCause.OVER_STRONG, "too strict", fixed)]),
        tmp_path,
    )
    assert out.stop_reason == "proven"
    assert out.prop.expr == "count <= 4'd15"
    assert out.rounds == 2  # round 0 (refine) + round 1 (resolved)


def test_rtl_bug_is_terminal(tmp_path: Path) -> None:
    out = _refine(
        FakeRunner(["fail"]),
        FakeClassifier([CexDiagnosis(CexCause.RTL_BUG, "design is wrong", None)]),
        tmp_path,
    )
    assert out.stop_reason == "rtl_bug"
    assert out.result.verdict.value == "falsified"
    assert out.rounds == 1  # did not loop after diagnosing an RTL bug


def test_vacuity_guard_rejects_over_constraining_assumption(tmp_path: Path) -> None:
    bad_assume = Property("A1", PropertyKind.ASSUME, "freeze", "en == 1'b0")
    out = _refine(
        FakeRunner(["fail", "fail"]),
        FakeClassifier([CexDiagnosis(CexCause.MISSING_ASSUMPTION, "need assume", bad_assume)]),
        tmp_path,
    )
    assert out.stop_reason == "vacuity_guard"
    assert out.assumes == ()  # the cheating assumption was NOT applied


def test_loop_terminates_at_max_rounds(tmp_path: Path) -> None:
    # Always falsified; each round proposes a distinct (non-no-op) refinement.
    diags = [
        CexDiagnosis(
            CexCause.OVER_STRONG,
            "n",
            Property("PB", PropertyKind.ASSERT, "", f"count <= 4'd{n}"),
        )
        for n in (12, 13, 14, 15)
    ]
    out = _refine(FakeRunner([]), FakeClassifier(diags), tmp_path, max_rounds=2)
    assert out.stop_reason == "max_rounds"
    assert out.rounds == 3  # initial + 2 refinements, all still falsified
