"""Pure domain core — no I/O, no external tools.

These types are the project's "ground truth" vocabulary: the interface model, the
property model, the verdict taxonomy, and the pure decision logic that maps solver
outcomes onto verdicts. Everything here is deterministic and unit-testable without
Yosys, SymbiYosys, or the LLM. Keep it that way: side effects live in `adapters/`.
"""
