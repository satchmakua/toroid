"""The verdict-decision logic is the most safety-critical code in the project
(DESIGN.md pillar #1): if it ever reports PROVEN when the solver said less, the
whole thesis collapses. These tests pin every branch of the taxonomy.
"""

from __future__ import annotations

from inductor.domain.policy import decide_verdict
from inductor.domain.verdicts import RawOutcome, Verdict


def test_unbounded_pass_with_reachable_cover_is_proven() -> None:
    o = RawOutcome(prove_pass=True, cover_reachable=True, depth=20)
    assert decide_verdict(o) is Verdict.PROVEN


def test_pdr_pass_also_counts_as_unbounded_proven() -> None:
    o = RawOutcome(pdr_pass=True, cover_reachable=True, depth=30)
    assert decide_verdict(o) is Verdict.PROVEN


def test_bmc_only_pass_is_bounded_not_proven() -> None:
    o = RawOutcome(bmc_pass=True, prove_pass=False, pdr_pass=False, cover_reachable=True, depth=20)
    assert decide_verdict(o) is Verdict.BOUNDED_PASS


def test_counterexample_always_wins() -> None:
    # Even if some engine "passed", a concrete CEX falsifies the property.
    o = RawOutcome(bmc_pass=True, falsified=True)
    assert decide_verdict(o) is Verdict.FALSIFIED


def test_unreachable_cover_makes_a_pass_vacuous() -> None:
    o = RawOutcome(prove_pass=True, cover_reachable=False, depth=20)
    assert decide_verdict(o) is Verdict.VACUOUS


def test_unchecked_cover_does_not_trip_vacuity() -> None:
    # cover_reachable=None means "not checked" — must NOT be treated as unreachable.
    o = RawOutcome(prove_pass=True, cover_reachable=None, depth=20)
    assert decide_verdict(o) is Verdict.PROVEN


def test_compile_error_short_circuits_to_error() -> None:
    o = RawOutcome(error=True, falsified=True, prove_pass=True)
    assert decide_verdict(o) is Verdict.ERROR


def test_nothing_resolved_is_inconclusive() -> None:
    assert decide_verdict(RawOutcome(inconclusive=True)) is Verdict.INCONCLUSIVE
    assert decide_verdict(RawOutcome()) is Verdict.INCONCLUSIVE


def test_trustworthy_pass_classification() -> None:
    assert Verdict.PROVEN.is_trustworthy_pass
    assert Verdict.BOUNDED_PASS.is_trustworthy_pass
    assert not Verdict.VACUOUS.is_trustworthy_pass
    assert not Verdict.FALSIFIED.is_trustworthy_pass
