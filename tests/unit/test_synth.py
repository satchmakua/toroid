"""The synthesis compile-gate + anti-vacuity repair loop, tested offline with a fake
LLM and a fake Yosys. No model or toolchain.
"""

from __future__ import annotations

from pathlib import Path

from inductor.adapters.yosys import CompileResult
from inductor.domain.interface import ModuleInterface, Port
from inductor.domain.properties import Property, PropertyKind, PropertySet
from inductor.pipeline.synth import synthesize_properties


def _iface() -> ModuleInterface:
    return ModuleInterface(
        top="counter",
        ports=(Port("clk", "input", 1, is_clock=True), Port("count", "output", 4)),
        clock="clk",
    )


def _good() -> PropertySet:
    return PropertySet(
        properties=(
            Property("P1", PropertyKind.ASSERT, "no overflow", "count <= 4'd15"),
            Property("P3", PropertyKind.COVER, "reaches max", "count == 4'd15"),
        )
    )


def _no_cover() -> PropertySet:
    return PropertySet(properties=(Property("P1", PropertyKind.ASSERT, "x", "count <= 4'd15"),))


class FakeLLM:
    """Returns a queued PropertySet per call; records the feedback it received."""

    def __init__(self, queue: list[PropertySet]) -> None:
        self.queue = queue
        self.feedbacks: list[str | None] = []

    def synthesize(
        self, interface: ModuleInterface, spec: str, *, feedback: str | None = None
    ) -> PropertySet:
        self.feedbacks.append(feedback)
        return self.queue.pop(0)


class FakeYosys:
    """compile_check returns the queued ok/err results in order."""

    def __init__(self, results: list[CompileResult]) -> None:
        self.results = results

    def extract_interface(self, sources: list[Path], top: str) -> ModuleInterface:
        raise NotImplementedError

    def compile_check(self, sources: list[Path], wrapper: Path, top: str) -> CompileResult:
        return self.results.pop(0)


def test_first_attempt_compiles(tmp_path: Path) -> None:
    llm = FakeLLM([_good()])
    res = synthesize_properties(
        _iface(), "spec", llm=llm, yosys=FakeYosys([CompileResult(ok=True)]),
        duts=[Path("counter.v")], workdir=tmp_path,
    )
    assert res.compiled and res.attempts == 1
    assert llm.feedbacks == [None]  # no repair needed


def test_repairs_a_compile_error_then_succeeds(tmp_path: Path) -> None:
    llm = FakeLLM([_good(), _good()])
    yosys = FakeYosys(
        [CompileResult(ok=False, errors="syntax error near foo"), CompileResult(ok=True)]
    )
    res = synthesize_properties(
        _iface(), "spec", llm=llm, yosys=yosys, duts=[Path("counter.v")], workdir=tmp_path,
    )
    assert res.compiled and res.attempts == 2
    # the second call received the compiler error as feedback
    assert llm.feedbacks[0] is None
    assert "syntax error near foo" in (llm.feedbacks[1] or "")


def test_anti_vacuity_repair_does_not_call_the_compiler(tmp_path: Path) -> None:
    llm = FakeLLM([_no_cover(), _good()])
    yosys = FakeYosys([CompileResult(ok=True)])  # only the 2nd (valid) set is compiled
    res = synthesize_properties(
        _iface(), "spec", llm=llm, yosys=yosys, duts=[Path("counter.v")], workdir=tmp_path,
    )
    assert res.compiled and res.attempts == 2
    assert "cover" in (llm.feedbacks[1] or "")


def test_gives_up_after_max_repairs(tmp_path: Path) -> None:
    llm = FakeLLM([_good()] * 5)
    yosys = FakeYosys([CompileResult(ok=False, errors="nope")] * 5)
    res = synthesize_properties(
        _iface(), "spec", llm=llm, yosys=yosys, duts=[Path("counter.v")],
        workdir=tmp_path, max_repairs=2,
    )
    assert not res.compiled
    assert res.attempts == 3  # initial + 2 repairs
    assert "nope" in res.errors
