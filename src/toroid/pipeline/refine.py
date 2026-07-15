"""The counterexample refinement loop. See DESIGN.md §6.4.

For a FALSIFIED assert: parse the trace (done in discharge), ask the LLM to classify
the cause, and — guarded by the policy — patch and re-discharge until the property
resolves or a bound is hit. The guarantees that make this safe:

* **Terminates** — at most `max_rounds`, and each round must change the property set
  (a no-op / invalid patch stops the loop).
* **RTL-bug is terminal** — Toroid never edits the design; an `rtl_bug` verdict
  ends the loop with the counterexample reported.
* **Never cheats** — a `missing_assumption` patch is rejected if it makes the
  reachability cover unreachable (the anti-vacuity guard); the property keeps its
  prior (honest) state.

The LLM classifier, Yosys, and the runner are injected, so the loop is unit-tested
offline with fakes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from toroid.adapters.llm import CexCause, CexDiagnosis
from toroid.adapters.sby import SbyJobRunner
from toroid.adapters.yosys import YosysAdapter
from toroid.domain.interface import ModuleInterface
from toroid.domain.properties import Property, PropertyKind
from toroid.domain.trace import Trace
from toroid.domain.verdicts import PropertyResult, Verdict
from toroid.pipeline.discharge import check_cover_reachable, discharge_assert


class CexClassifier(Protocol):
    def classify_cex(
        self, prop: Property, trace: Trace, interface: ModuleInterface
    ) -> CexDiagnosis: ...


@dataclass(frozen=True, slots=True)
class RefineStep:
    round: int
    verdict: Verdict
    diagnosis: CexDiagnosis | None
    note: str


@dataclass(frozen=True, slots=True)
class RefineOutcome:
    result: PropertyResult  # final verdict for the (possibly refined) property
    prop: Property  # final property (refined if over_strong)
    assumes: tuple[Property, ...]  # final assumptions (augmented if missing_assumption)
    steps: tuple[RefineStep, ...]
    stop_reason: str

    @property
    def rounds(self) -> int:
        return len(self.steps)


def refine_property(
    interface: ModuleInterface,
    prop: Property,
    assumes: Sequence[Property],
    covers: Sequence[Property],
    *,
    duts: Sequence[Path],
    yosys: YosysAdapter,
    runner: SbyJobRunner,
    classifier: CexClassifier,
    workdir: Path,
    depth: int = 20,
    max_rounds: int = 5,
    run_pdr: bool = False,
) -> RefineOutcome:
    top = f"{interface.top}_fv"
    cur_prop = prop
    cur_assumes: tuple[Property, ...] = tuple(assumes)
    covers_t: tuple[Property, ...] = tuple(covers)
    steps: list[RefineStep] = []
    last: PropertyResult | None = None

    for rnd in range(max_rounds + 1):
        rdir = workdir / f"r{rnd}"
        cover_reachable = check_cover_reachable(
            interface, cur_assumes, covers_t, duts=duts, runner=runner,
            workdir=rdir / "cover", top=top, depth=depth,
        )
        res = discharge_assert(
            interface, cur_prop, cur_assumes, duts=duts, runner=runner,
            workdir=rdir, top=top, depth=depth, cover_reachable=cover_reachable, run_pdr=run_pdr,
        )
        last = res

        if res.verdict is not Verdict.FALSIFIED:
            steps.append(RefineStep(rnd, res.verdict, None, "resolved"))
            return RefineOutcome(res, cur_prop, cur_assumes, tuple(steps), res.verdict.value)

        if res.trace is None:
            steps.append(RefineStep(rnd, res.verdict, None, "no trace to classify"))
            return RefineOutcome(res, cur_prop, cur_assumes, tuple(steps), "no_trace")

        diag = classifier.classify_cex(cur_prop, res.trace, interface)

        if diag.cause is CexCause.RTL_BUG:
            steps.append(RefineStep(rnd, res.verdict, diag, "RTL bug — terminal"))
            return RefineOutcome(res, cur_prop, cur_assumes, tuple(steps), "rtl_bug")

        patch = diag.proposed_patch
        if patch is None:
            steps.append(RefineStep(rnd, res.verdict, diag, "no patch proposed"))
            return RefineOutcome(res, cur_prop, cur_assumes, tuple(steps), "no_patch")

        if diag.cause is CexCause.OVER_STRONG:
            if patch.kind is not PropertyKind.ASSERT or patch.expr == cur_prop.expr:
                steps.append(RefineStep(rnd, res.verdict, diag, "invalid/no-op refinement"))
                return RefineOutcome(res, cur_prop, cur_assumes, tuple(steps), "stuck")
            steps.append(RefineStep(rnd, res.verdict, diag, f"refined assert: {patch.expr}"))
            cur_prop = patch
        else:  # MISSING_ASSUMPTION
            if patch.kind is not PropertyKind.ASSUME:
                steps.append(RefineStep(rnd, res.verdict, diag, "invalid assumption patch"))
                return RefineOutcome(res, cur_prop, cur_assumes, tuple(steps), "stuck")
            candidate = (*cur_assumes, patch)
            # anti-vacuity guard: the assumption must not kill the cover's reachability.
            if covers_t:
                reach = check_cover_reachable(
                    interface, candidate, covers_t, duts=duts, runner=runner,
                    workdir=rdir / "vacuity", top=top, depth=depth,
                )
                if reach is False:
                    note = "rejected: assumption makes the cover unreachable"
                    steps.append(RefineStep(rnd, res.verdict, diag, note))
                    return RefineOutcome(
                        res, cur_prop, cur_assumes, tuple(steps), "vacuity_guard"
                    )
            steps.append(RefineStep(rnd, res.verdict, diag, f"added assume: {patch.expr}"))
            cur_assumes = candidate

    assert last is not None
    return RefineOutcome(last, cur_prop, cur_assumes, tuple(steps), "max_rounds")
