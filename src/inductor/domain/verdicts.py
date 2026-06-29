"""The verdict taxonomy — the honesty layer.

See DESIGN.md §4.4. Every reported result is one of these, tied to a real solver
run. The critical distinctions: PROVEN (an unbounded engine closed it) vs
BOUNDED_PASS (no counterexample within depth k — *not* unbounded), and VACUOUS (a
pass whose reachability witness is unreachable — a false "proof").
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from inductor.domain.trace import Trace


class Verdict(StrEnum):
    PROVEN = "proven"  # unbounded: k-induction or pdr passed, no CEX
    BOUNDED_PASS = "bounded_pass"  # BMC to depth k, no CEX within k (NOT unbounded)
    FALSIFIED = "falsified"  # CEX found — trace attached
    VACUOUS = "vacuous"  # assert passed but its cover is UNREACHABLE
    INCONCLUSIVE = "inconclusive"  # timeout / resource limit / solver gave up
    ERROR = "error"  # compile/elaboration failure — never reached a solver

    @property
    def is_trustworthy_pass(self) -> bool:
        """True only for results a senior engineer would sign off on as a pass."""
        return self in (Verdict.PROVEN, Verdict.BOUNDED_PASS)


@dataclass(frozen=True, slots=True)
class RawOutcome:
    """The per-property raw results gathered from SymbiYosys task runs, before the
    policy layer maps them to a single `Verdict`. `None` means "task not run"."""

    bmc_pass: bool | None = None  # bounded model checking, no CEX within depth
    prove_pass: bool | None = None  # k-induction proof
    pdr_pass: bool | None = None  # IC3/PDR proof
    cover_reachable: bool | None = None  # antecedent / reachability witness
    depth: int = 0
    falsified: bool = False
    error: bool = False
    inconclusive: bool = False


@dataclass(frozen=True, slots=True)
class PropertyResult:
    """The final, reportable result for one property."""

    pid: str
    verdict: Verdict
    summary: str = ""
    engine: str | None = None  # "smtbmc/bitwuzla", "abc/pdr", ...
    depth: int | None = None
    trace_yw: Path | None = None  # structured witness (falsified)
    trace_vcd: Path | None = None  # human waveform (falsified)
    trace: Trace | None = None  # parsed per-step counterexample (falsified)
    wall_seconds: float = 0.0
    detail: str = ""
