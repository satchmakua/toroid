"""Counterexample trace — a pure, per-step view of signal values used for
narration and classification (DESIGN.md §6.4). Adapters parse the solver's output
(Yosys `sat` model table, or a `.yw`/VCD witness) into this shape; the domain and
the LLM reason over it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Trace:
    signals: tuple[str, ...]
    steps: tuple[dict[str, int], ...]  # step -> {signal: value}
    failing_step: int = -1

    def value(self, signal: str, step: int) -> int | None:
        if 0 <= step < len(self.steps):
            return self.steps[step].get(signal)
        return None


def summarize_trace(trace: Trace, *, max_steps: int = 24) -> str:
    """Deterministic, no-LLM rendering of a trace as a compact step table — the
    honest baseline narration that appears in the report even without the model."""
    if not trace.steps:
        return "(no trace)"
    sigs = trace.signals
    header = "step | " + " ".join(f"{s:>6}" for s in sigs)
    lines = [header, "-" * len(header)]
    shown = list(enumerate(trace.steps))[:max_steps]
    for i, row in shown:
        mark = "  <- counterexample ends" if i == trace.failing_step else ""
        cells = " ".join(f"{row.get(s, '?'):>6}" for s in sigs)
        lines.append(f"{i:>4} | {cells}{mark}")
    if len(trace.steps) > max_steps:
        lines.append(f"... ({len(trace.steps) - max_steps} more steps)")
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class _Builder:
    """Internal helper for adapters assembling steps incrementally."""

    by_step: dict[int, dict[str, int]] = field(default_factory=dict)

    def set(self, step: int, signal: str, value: int) -> None:
        self.by_step.setdefault(step, {})[signal] = value

    def build(self, signals: tuple[str, ...]) -> Trace:
        ordered = sorted(self.by_step)
        steps = tuple(self.by_step[s] for s in ordered)
        return Trace(signals=signals, steps=steps, failing_step=len(steps) - 1)
