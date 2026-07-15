"""LLM adapter: property synthesis (M2) and counterexample classification (M3) via
Claude. See DESIGN.md §6.2.

The one stochastic component in the system, isolated behind a Protocol so the rest
of the pipeline stays deterministic and testable. Synthesis uses **structured
outputs** (a Pydantic schema) so the response is schema-valid by construction; the
`anthropic` import is lazy so the pure pipeline never depends on it.

Model defaults (verified against the Anthropic API docs, 2026-06-28):
  model    = "claude-opus-4-8"   (override via TOROID_MODEL)
  thinking = {"type": "adaptive"}   # no budget_tokens (400 on 4.8)
  no assistant prefill (rejected on 4.8) — structure comes from the schema.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel

from toroid.domain.interface import ModuleInterface
from toroid.domain.properties import Property, PropertyKind, PropertySet
from toroid.domain.trace import Trace, summarize_trace

DEFAULT_MODEL = "claude-opus-4-8"

#: Authoritative synthesis system prompt. `prompts/synth.system.md` mirrors this for
#: human reference; this constant is what actually ships to the model.
SYNTH_SYSTEM = """\
You are a senior formal hardware-verification engineer. Given a module's interface
model (exact ports, directions, widths — extracted from Yosys, authoritative) and a
natural-language spec, propose safety properties to model-check.

HARD CONSTRAINTS — the open Yosys frontend accepts only this subset:
- Emit boolean expressions for `assert` / `assume` / `cover`, evaluated inside one
  clocked block. Do NOT emit concurrent SVA (`assert property`, sequences, `|->`,
  `throughout`) — the open frontend rejects it.
- For multi-cycle behavior use the formal helpers: $past(e, n), $rose, $fell,
  $stable, $changed, $initstate. Guard the reset/initial edge with $initstate and
  $past(<reset>).
- Reference only ports that exist in the interface model, at their real widths. Use
  sized literals (e.g. 4'd15).

REQUIREMENTS:
- Every `assert` MUST be paired with at least one `cover` whose expression makes the
  assert's antecedent reachable (anti-vacuity). A pass with an unreachable cover is a
  false proof.
- Classify each property as assert, assume, or cover. Give each a stable pid (P1,
  P2, ...), a one-line summary, and a rationale tying it to the spec or interface.
- Prefer a focused set of strong, true safety properties over many weak ones.

If given REPAIR FEEDBACK, the previous attempt failed to elaborate or was vacuous —
fix exactly those problems and re-emit the full corrected set."""


class CexCause(StrEnum):
    RTL_BUG = "rtl_bug"  # the design violates a correct property — terminal
    OVER_STRONG = "over_strong"  # the property is too strict — refine it
    MISSING_ASSUMPTION = "missing_assumption"  # the environment needs a constraint


@dataclass(frozen=True, slots=True)
class CexDiagnosis:
    """The LLM's read of a counterexample: cause + narration + an optional patch."""

    cause: CexCause
    narration: str
    proposed_patch: Property | None  # a refined assert, or an assume, per the cause


CLASSIFY_SYSTEM = """\
You are a formal hardware-verification engineer debugging a FAILED safety property.
You are given the property, the module interface, and a counterexample trace (per-step
signal values from the model checker). Narrate the failing behavior cycle by cycle,
then classify the root cause as exactly one of:

- rtl_bug: the design violates a property that is correct as written. TERMINAL —
  Toroid does not edit the design. No patch.
- over_strong: the property is too strict / wrong. Propose a corrected `assert`
  (kind="assert") that captures the real intent and would hold.
- missing_assumption: the property assumed an environment constraint that wasn't
  stated (e.g. an input protocol). Propose an `assume` (kind="assume").

Any proposed patch must use the supported Yosys subset (immediate expression; $past,
$rose, $stable, $initstate; real ports/widths). Do NOT weaken a property into vacuity
to make it pass — a refinement must keep the original cover reachable. Reuse the
original pid for an over_strong refinement; give an assume a fresh pid."""


class LLMAdapter(Protocol):
    def synthesize(
        self, interface: ModuleInterface, spec: str, *, feedback: str | None = None
    ) -> PropertySet: ...

    def classify_cex(
        self, prop: Property, trace: Trace, interface: ModuleInterface
    ) -> CexDiagnosis: ...


# --- structured-output schema (Pydantic) ---------------------------------------


class _PropertyOut(BaseModel):
    pid: str
    kind: Literal["assert", "assume", "cover"]
    summary: str
    expr: str
    rationale: str = ""
    clocked: bool = True


class _PropertySetOut(BaseModel):
    properties: list[_PropertyOut]


class _PatchOut(BaseModel):
    pid: str
    kind: Literal["assert", "assume"]
    summary: str
    expr: str
    rationale: str = ""


class _CexOut(BaseModel):
    cause: Literal["rtl_bug", "over_strong", "missing_assumption"]
    narration: str
    patch: _PatchOut | None = None


def _diag_to_domain(out: _CexOut) -> CexDiagnosis:
    patch = None
    if out.patch is not None:
        patch = Property(
            pid=out.patch.pid,
            kind=PropertyKind(out.patch.kind),
            summary=out.patch.summary,
            expr=out.patch.expr,
            rationale=out.patch.rationale,
            origin="refined",
        )
    return CexDiagnosis(cause=CexCause(out.cause), narration=out.narration, proposed_patch=patch)


def _to_domain(out: _PropertySetOut) -> PropertySet:
    return PropertySet(
        properties=tuple(
            Property(
                pid=p.pid,
                kind=PropertyKind(p.kind),
                summary=p.summary,
                expr=p.expr,
                rationale=p.rationale,
                clocked=p.clocked,
                origin="llm",
            )
            for p in out.properties
        )
    )


def render_interface(interface: ModuleInterface) -> str:
    """Compact, model-facing description of the interface (the grounding)."""
    reset = interface.reset
    if reset:
        reset += " (active-high)" if interface.reset_active_high else " (active-low)"
    lines = [
        f"Module: {interface.top}",
        f"  clock: {interface.clock or '(none)'}   reset: {reset or '(none)'}",
        "  ports:",
    ]
    for p in interface.ports:
        lines.append(f"    {p.direction:6} [{p.width}] {p.name}")
    return "\n".join(lines)


def _user_prompt(interface: ModuleInterface, spec: str, feedback: str | None) -> str:
    parts = [
        "INTERFACE MODEL (authoritative):",
        render_interface(interface),
        "",
        "SPEC:",
        spec.strip() or "(no natural-language spec provided; infer safety properties "
        "from the interface and the module name.)",
    ]
    if feedback:
        parts += ["", "REPAIR FEEDBACK (the previous attempt failed):", feedback.strip()]
    return "\n".join(parts)


# --- live adapter (needs ANTHROPIC_API_KEY) ------------------------------------


class ClaudeAdapter:
    """Property synthesis backed by the Anthropic SDK (structured outputs)."""

    def __init__(self, model: str | None = None, max_tokens: int = 16000) -> None:
        self.model = model or os.environ.get("TOROID_MODEL") or DEFAULT_MODEL
        self.max_tokens = max_tokens
        self._client: object | None = None

    def _ensure_client(self) -> object:
        if self._client is None:
            import anthropic  # lazy: pure pipeline never imports this

            self._client = anthropic.Anthropic()
        return self._client

    def synthesize(
        self, interface: ModuleInterface, spec: str, *, feedback: str | None = None
    ) -> PropertySet:
        client = self._ensure_client()
        response = client.messages.parse(  # type: ignore[attr-defined]
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYNTH_SYSTEM,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": _user_prompt(interface, spec, feedback)}],
            output_format=_PropertySetOut,
        )
        out = response.parsed_output
        if out is None:
            raise RuntimeError("LLM returned no parseable property set")
        return _to_domain(out)

    def classify_cex(
        self, prop: Property, trace: Trace, interface: ModuleInterface
    ) -> CexDiagnosis:
        client = self._ensure_client()
        user = "\n".join(
            [
                "INTERFACE MODEL:",
                render_interface(interface),
                "",
                f"FAILED PROPERTY {prop.pid} ({prop.summary}):",
                f"  assert ({prop.expr});",
                "",
                "COUNTEREXAMPLE TRACE:",
                summarize_trace(trace),
            ]
        )
        response = client.messages.parse(  # type: ignore[attr-defined]
            model=self.model,
            max_tokens=self.max_tokens,
            system=CLASSIFY_SYSTEM,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": user}],
            output_format=_CexOut,
        )
        out = response.parsed_output
        if out is None:
            raise RuntimeError("LLM returned no parseable diagnosis")
        return _diag_to_domain(out)
