"""LLM adapter: property synthesis and counterexample classification via Claude.

See DESIGN.md §6.2. The one stochastic component in the system, isolated behind a
Protocol so the rest of the pipeline stays deterministic and testable. Synthesis
and classification use structured outputs (Pydantic schemas) so responses are
schema-valid by construction.

Model defaults (verified against the Anthropic API docs, 2026-06-28):
  model   = "claude-opus-4-8"
  thinking= {"type": "adaptive"}        # do NOT pass budget_tokens (400 on 4.8)
  effort  = "high"                       # via output_config
  no assistant prefill (rejected on 4.8) — structure comes from the schema.

Concrete synthesis lands in M2; classification in M3. The `anthropic` import is
lazy so the pure pipeline never depends on it.
"""

from __future__ import annotations

from typing import Protocol

from inductor.domain.interface import ModuleInterface
from inductor.domain.properties import Property, PropertySet

DEFAULT_MODEL = "claude-opus-4-8"


class CexDiagnosis:  # filled out with fields in M3
    """The LLM's read of a counterexample: cause + narration + proposed patch."""


class LLMAdapter(Protocol):
    def synthesize(self, interface: ModuleInterface, spec: str) -> PropertySet: ...

    def classify_cex(
        self, prop: Property, narration_input: object, interface: ModuleInterface
    ) -> CexDiagnosis: ...


class ClaudeAdapter:
    """Real adapter backed by the Anthropic SDK. Implemented in M2/M3."""

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self._client: object | None = None  # constructed lazily in M2

    def _ensure_client(self) -> object:
        if self._client is None:
            import anthropic  # lazy: pure pipeline never imports this

            self._client = anthropic.Anthropic()
        return self._client

    def synthesize(self, interface: ModuleInterface, spec: str) -> PropertySet:
        raise NotImplementedError("Property synthesis lands in M2 (see ROADMAP.md).")

    def classify_cex(
        self, prop: Property, narration_input: object, interface: ModuleInterface
    ) -> CexDiagnosis:
        raise NotImplementedError("CEX classification lands in M3 (see ROADMAP.md).")
