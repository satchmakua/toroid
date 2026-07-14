"""Property-based tests for the honesty core `decide_verdict` (H3). Hypothesis fuzzes
*every* combination of raw solver outcomes and checks the load-bearing invariants
hold universally — not just on the hand-picked examples in test_policy.py. If any of
these can be broken, the project's credibility claim can be broken.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from inductor.domain.policy import decide_verdict
from inductor.domain.verdicts import RawOutcome, Verdict

_tri = st.sampled_from([True, False, None])
_outcomes = st.builds(
    RawOutcome,
    bmc_pass=_tri,
    prove_pass=_tri,
    pdr_pass=_tri,
    cover_reachable=_tri,
    depth=st.integers(min_value=0, max_value=64),
    falsified=st.booleans(),
    error=st.booleans(),
    inconclusive=st.booleans(),
)


@given(_outcomes)
def test_total_and_deterministic(o: RawOutcome) -> None:
    # never raises, always returns a Verdict, and is deterministic
    assert decide_verdict(o) is decide_verdict(o)
    assert isinstance(decide_verdict(o), Verdict)


@given(_outcomes)
def test_proven_requires_an_unbounded_engine(o: RawOutcome) -> None:
    # THE headline honesty rule: PROVEN is only ever awarded when k-induction or PDR
    # actually succeeded — never from BMC alone, never on error/falsified/vacuous.
    if decide_verdict(o) is Verdict.PROVEN:
        assert bool(o.prove_pass) or bool(o.pdr_pass)
        assert not o.error and not o.falsified
        assert o.cover_reachable is not False


@given(_outcomes)
def test_bmc_only_pass_is_never_proven(o: RawOutcome) -> None:
    if o.bmc_pass and not o.prove_pass and not o.pdr_pass and not o.error and not o.falsified:
        assert decide_verdict(o) is not Verdict.PROVEN  # at best BOUNDED_PASS


@given(_outcomes)
def test_a_trustworthy_pass_is_never_invented(o: RawOutcome) -> None:
    # The forward-honesty dual of test_proven_requires_an_unbounded_engine, extended to
    # BOUNDED_PASS: ANY verdict a senior engineer would sign off on as a pass must be
    # backed by a REAL solver pass (k-induction, PDR, or BMC) — never conjured from a
    # reachable cover or any other signal. This closes the gap that would let a false
    # BOUNDED_PASS (e.g. cover_reachable=True with no bmc/prove/pdr pass) slip through.
    if decide_verdict(o).is_trustworthy_pass:
        assert bool(o.prove_pass) or bool(o.pdr_pass) or bool(o.bmc_pass)


@given(_outcomes)
def test_error_and_counterexample_take_precedence(o: RawOutcome) -> None:
    if o.error:
        assert decide_verdict(o) is Verdict.ERROR  # a compile error beats everything
    elif o.falsified:
        assert decide_verdict(o) is Verdict.FALSIFIED  # a real CEX beats any pass


@given(_outcomes)
def test_vacuous_exactly_when_a_pass_has_an_unreachable_cover(o: RawOutcome) -> None:
    v = decide_verdict(o)
    any_pass = bool(o.prove_pass) or bool(o.pdr_pass) or bool(o.bmc_pass)
    if v is Verdict.VACUOUS:
        assert o.cover_reachable is False and any_pass and not o.error and not o.falsified
    # and the converse: a genuine pass whose cover is unreachable is never a clean pass
    if any_pass and o.cover_reachable is False and not o.error and not o.falsified:
        assert v is Verdict.VACUOUS


@given(_outcomes)
def test_unchecked_cover_never_forces_vacuous(o: RawOutcome) -> None:
    # cover_reachable is None ("not checked") must not be treated as unreachable
    if o.cover_reachable is None and not o.error and not o.falsified:
        assert decide_verdict(o) is not Verdict.VACUOUS
