"""Pure decision logic: how raw solver outcomes become a single verdict, and the
bounding policy. No I/O — this is the most safety-critical code in the project and
is exercised directly by unit tests (DESIGN.md pillar #1).
"""

from __future__ import annotations

from inductor.domain.verdicts import RawOutcome, Verdict

#: Default bounded-model-checking depth when the user does not pass --depth.
DEFAULT_BMC_DEPTH = 20

#: Default cap on counterexample-refinement rounds (DESIGN.md §6.4).
DEFAULT_MAX_REFINE = 5


def decide_verdict(o: RawOutcome) -> Verdict:
    """Map the raw per-property outcome onto the verdict taxonomy.

    Order matters and encodes the honesty rules from DESIGN.md §4.4:

    * a compile/elaboration error never reaches a solver       -> ERROR
    * a concrete counterexample always wins                    -> FALSIFIED
    * a pass whose reachability witness is unreachable is a
      false proof                                              -> VACUOUS
    * only an unbounded engine (k-induction or PDR) earns      -> PROVEN
    * BMC alone is honest but bounded                          -> BOUNDED_PASS
    * anything left over is INCONCLUSIVE
    """
    if o.error:
        return Verdict.ERROR
    if o.falsified:
        return Verdict.FALSIFIED

    passed_unbounded = bool(o.prove_pass) or bool(o.pdr_pass)
    passed_bounded = bool(o.bmc_pass)
    any_pass = passed_unbounded or passed_bounded

    # Anti-vacuity: a pass is meaningless if the antecedent can't even be reached.
    # cover_reachable is None ("not checked") does not trip this — only an explicit
    # False does.
    if any_pass and o.cover_reachable is False:
        return Verdict.VACUOUS

    if passed_unbounded:
        return Verdict.PROVEN
    if passed_bounded:
        return Verdict.BOUNDED_PASS
    return Verdict.INCONCLUSIVE
