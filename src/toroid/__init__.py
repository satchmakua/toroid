"""Toroid — an agent that synthesizes formal properties for RTL, runs a model
checker, and iterates on counterexamples. The LLM proposes; the solver disposes.

See DESIGN.md for the full architecture. Public surface is intentionally small;
the build loop deepens the pipeline milestone by milestone (see ROADMAP.md).
"""

from __future__ import annotations

__version__ = "0.0.1"

from toroid.domain.interface import ModuleInterface, Port
from toroid.domain.policy import decide_verdict
from toroid.domain.properties import Property, PropertyKind, PropertySet
from toroid.domain.verdicts import PropertyResult, RawOutcome, Verdict

__all__ = [
    "__version__",
    "ModuleInterface",
    "Port",
    "Property",
    "PropertyKind",
    "PropertySet",
    "PropertyResult",
    "RawOutcome",
    "Verdict",
    "decide_verdict",
]
